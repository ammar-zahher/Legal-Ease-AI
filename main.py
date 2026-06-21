import os
import tempfile
import shutil
from dotenv import load_dotenv
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Error: GEMINI_API_KEY not found in .env file. Please add it.")  
client = genai.Client(api_key=api_key)

model_name = "gemini-2.5-flash"

sessions = {}

system_instruction = """
Role: You are an Academic Financial Advisor AI. Your goal is to provide clear, actionable, and transparent resolutions to students' financial problems by strictly referencing official university documents and verified web sources.

CORE DIRECTIVE:
Every single factual statement must be cited. No citation = No information. If information is missing, admit it rather than hallucinating.

CITATION PROTOCOL (Mandatory):

For Web Sources: Every paragraph containing external facts must end with the exact URL: [Source: URL]

For Uploaded Files: Every paragraph derived from the file must end with: [Source: File, Page X]

Formatting: Citations must be placed at the very end of the paragraph. Do not omit them even if the response is long.

STRUCTURAL CONSTRAINTS:
Use ONLY the following sections in this exact order:

Problem Explanation (Briefly define the issue).

Explain what the university wants from the student?

University Policy Research (Use official university web pages only. No social media/forums) and explain how the student's issue may be resolved according to the applicable university policies.
For each relevant policy, identify:
Administrative procedures
Responsible offices or departments
Official contact information when available
Relevant deadlines when available

What the Student Needs to Do (Actionable steps based on the above).

University & External Resources (Prioritize local, state-level, and institutional support)
University Resources (From 2 to 4)
External Resources (From 2 to 4)
Analyze the student's financial or situational distress to identify and recommend highly relevant support entities. 
- You must research and list specific: charities, NGOs, humanitarian groups, student support programs, community organizations, government assistance programs, and foundations..

Important Deadlines (Strictly from official sources).

Prioritized Action Checklist (Numbered step-by-step roadmap)
The checklist should function as a step-by-step roadmap that guides the student toward a complete and practical resolution of the problem..

CRITICAL RULES:

Transparency: Always distinguish between info from the file and info from the web.

Locality: Prioritize resources within the student's specific geographic region.

Do not assume the reader understands university procedures

Expand the explanation whenever greater detail would improve understanding.

The main objective is to move the student from a state of ambiguity to a state of clarity and action.

Tone: Reassuring, professional, and empathetic.

Penalty: Failure to include a source URL for a claim constitutes a failure to follow instructions. Be precise.
Do not list multiple redundant URLs. For each paragraph, provide only one representative, authoritative link at the very end. Group related information together so you can cite them with a single link rather than repeating links after every sentence. If multiple facts in a paragraph come from the same source, use one citation at the end of that paragraph.
Your primary goal is to be an advisor. Explain policies clearly in simple, empathetic language before citing them. Prioritize clarity and helpfulness; the citations should support your explanation, not replace it.
[FINAL RESPONSE PROTOCOL]
You must strictly follow the template below for all your responses. You are required to maintain the citation format (ending factual paragraphs with the source tag) and ensure the "Prioritized Action Checklist" is always a vertical numbered list. Do not deviate from this structure.

TEMPLATE:

1. Problem Explanation
[Provide a brief definition of the issue.] [Source: ...]

2. Explain what the university wants from the student?
[Explain the required action clearly.] [Source: ...]

3. University Policy Research
[Provide research and policy details. Every paragraph MUST end with a source tag.] [Source: ...]

4. What the Student Needs to Do
[Provide actionable steps.] [Source: ...]

5. University & External Resources

University Resources: [List with descriptions and links.]

External Resources: [List with descriptions and links.]

6. Important Deadlines
[List key dates and relevant information.] [Source: ...]

7. Prioritized Action Checklist

[Step 1]

[Step 2]

[Step 3]
........
........
"""


def detect_distress(text):
    if not text: return False
    t = text.lower()
    distress_words = ["can't pay", "cannot pay", "financial crisis", "no money", "poor", "struggling", "hard time", "broke", "unemployed", "no income"]
    return any(word in t for word in distress_words)

def classify_intent(text):
    if not text: return "general"
    t = text.lower()
    if any(word in t for word in ["paid", "but", "still", "charged", "balance", "receipt"]): return "payment_issue"
    if any(word in t for word in ["why", "reason", "explain"]): return "confusion"
    if any(word in t for word in ["what should i do", "help", "fix"]): return "action_request"
    return "general"

def build_input(user_input):
    intent = classify_intent(user_input)
    distress = detect_distress(user_input)
    return f"\n[USER INTENT: {intent}]\n[USER DISTRESS: {distress}]\n\n{user_input}"

def get_or_create_session(session_id, file_path=None, extra_text=None):
    if file_path:
        sessions.pop(session_id, None)

    if session_id in sessions:
        return sessions[session_id]

    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            max_output_tokens=8192,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        parts = []
        if file_path and os.path.exists(file_path):
            uploaded_file = client.files.upload(file=file_path)
            start_time = time.time()
            while uploaded_file.state.name == "PROCESSING":
                if time.time() - start_time > 60:
                    raise Exception("Gemini file processing timeout")
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
            
            if uploaded_file.state.name != "FAILED":
                parts.append(types.Part.from_uri(file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type))
                parts.append(types.Part.from_text(text="Please read, analyze, and understand this file carefully."))

        if extra_text:
            parts.append(types.Part.from_text(text=f"Additional user context:\n{extra_text}"))

        if not parts:
            parts.append(types.Part.from_text(text="Hello, let's start the financial guidance session."))

        chat = client.chats.create(
            model=model_name,
            config=config,
            history=[types.Content(role="user", parts=parts)]
        )
        
        sessions[session_id] = chat
        return chat

    except Exception as e:
        raise Exception(f"Initialization failed: {e}")

app = FastAPI(title="LegalEase AI API")
@app.get("/")
def serve_home():
    return FileResponse("index.html")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze_document(
    extra_text: str = Form(None), 
    file: UploadFile = File(None),
    session_id: str = Form("default_session") 
):
    temp_file_path = None
    
    if file:
        allowed_extensions = (".pdf", ".png", ".jpg", ".jpeg")
        if not file.filename.lower().endswith(allowed_extensions):
            raise HTTPException(status_code=400, detail="Unsupported file format.")
        
        temp_file_path = f"temp_{file.filename}"
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    try:
        is_new_session = session_id not in sessions
        session = get_or_create_session(session_id, temp_file_path, extra_text)
        
        if session is None:
            raise HTTPException(status_code=500, detail="Failed to create AI session.")

        if not is_new_session and not file:
            final_prompt = build_input(extra_text) if extra_text else "Please continue analyzing."
            if detect_distress(extra_text):
                final_prompt = "IMPORTANT:\nThe user is experiencing financial difficulty.\n" + final_prompt
            
            response = session.send_message(final_prompt)
        else:
            prompt = f"Analyze the provided context immediately and provide the output in English, strictly following the structured rules."
            response = session.send_message(prompt)
            
        return {"status": "success", "data": response.text.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

