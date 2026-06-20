import os
import shutil
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    API_KEY = "x"  

client = genai.Client(api_key=API_KEY)

model_name = "gemini-2.5-flash"

system_instruction = """
Use clear, simple, and reassuring language throughout the response. Provide additional detail whenever the situation requires further explanation. Structure the response using the following sections:

Problem Explanation
What the Student Needs to Do
University Policy Research
Organizations and Resources That May Assist the Student
University Resources
External Resources
Important Deadlines
Problem Resolution Checklist
1. Research and Identify Support Resources
Identify Relevant Assistance Organizations

Analyze the student's situation and recommend organizations, charities, humanitarian groups, student support programs, community organizations, government assistance programs, foundations, or any other relevant entities that may help address the student's specific issue.

Examples:

Financial hardship → scholarships, emergency grants, charitable foundations, tuition assistance programs.
Housing insecurity → housing assistance organizations.
Food insecurity → food banks and community support programs.
Medical issues → healthcare assistance organizations.
Legal concerns → legal aid organizations.
Geographic Requirement

All recommended organizations and resources must be located within the same state, province, governorate, or administrative region where the student's university is located.

Do not recommend organizations from other states, provinces, governorates, or regions unless absolutely necessary and no local alternative exists.

Source Requirements

For every factual statement obtained from an external source, provide the exact webpage URL where the information was found.

The source URL must appear at the end of the paragraph containing that information.

2. Research Official University Policies
Official Sources Only

Research university policies exclusively from the university's official website.

Acceptable sources include:

Official university policy pages
Official university handbooks
Official university student affairs pages
Official financial services pages
Official registrar pages
Official departmental pages

Do not use:

Facebook
X/Twitter
Instagram
Reddit
Student forums
Third-party summaries
Any unofficial source
Required Information

Explain how the student's issue may be resolved according to the applicable university policies.

For each relevant policy, identify:

The policy requirements
Available options and exceptions
Required forms or documentation
Administrative procedures
Responsible offices or departments
Official contact information when available
Relevant deadlines when available
Source Requirements

Every paragraph containing information obtained from the university website must include the exact webpage URL used as the source.

The source URL must be placed at the end of the paragraph.

3. Create a Prioritized Action Checklist

Provide a clear, actionable checklist ordered by priority and urgency.

Example structure:

Contact the relevant university office immediately to preserve student rights or request a payment extension.
Submit applications for eligible emergency funding, scholarships, grants, or charitable assistance.
Complete any required university forms or supporting documentation.
Follow up with the responsible university office.
Monitor deadlines and policy requirements.
Complete any remaining administrative procedures.
Objective

The checklist should function as a step-by-step roadmap that guides the student toward a complete and practical resolution of the problem.

Documentation and Transparency Rules
Information From External Sources

Any information obtained from outside the uploaded file must include the exact webpage URL used as the source.

This applies to all external information, including:

University policies
University procedures
Contact information
Financial aid information
Scholarship information
Charity and nonprofit information
Government assistance programs
Deadlines
Any other externally sourced information

The source URL must be included at the end of the paragraph where the information appears.

Information From the Uploaded File

Whenever information is derived from the uploaded file:

Explicitly state that the information was interpreted from the uploaded file.
Include the page number where the information appears.
Clearly distinguish file-based information from externally researched information.

Example:

"According to the uploaded file (Page 3), the student received a notification regarding an outstanding tuition balance."

Explanation Requirements

When explaining information from the uploaded file:

State that the explanation is based on the uploaded file.
Reference the page number.
Provide additional context when necessary.
Expand the explanation whenever greater detail would improve understanding.
Do not assume the reader understands university procedures; explain them clearly and thoroughly.
Mandatory Requirements
Every external fact must include its source webpage URL.
Every statement derived from the uploaded file must indicate that it came from the uploaded file and include the page number.
Use only official university websites when researching university policies.
Prefer local organizations and assistance resources within the university's state, province, governorate, or region.
Provide a detailed explanation whenever additional detail would improve clarity.
Always include:
Problem Explanation
What the Student Needs to Do
University Policy Research
University Resources
External Resources
Important Deadlines
Prioritized Checklist
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

def start_project_session(file_path=None, extra_text=None):
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
            
            while uploaded_file.state.name == "PROCESSING":
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
        return chat

    except Exception as e:
        raise Exception(f"Initialization failed: {e}")

app = FastAPI(title="LegalEase AI API")

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
    file: UploadFile = File(None)
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
        session = start_project_session(temp_file_path, extra_text)
        
        if session is None:
            raise HTTPException(status_code=500, detail="Failed to create AI session.")

        final_prompt = build_input(extra_text) if extra_text else ""
        if detect_distress(extra_text):
            final_prompt = "IMPORTANT:\nThe user is experiencing financial difficulty. Respond in a supportive, calm, non-judgmental tone.\n" + final_prompt

        prompt = f"""
        {final_prompt}
        
        Analyze the provided context immediately and provide the output in English, strictly following the structured rules defined in your System Instructions.
        """
        
        response = session.send_message(prompt)
        return {"status": "success", "data": response.text.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
