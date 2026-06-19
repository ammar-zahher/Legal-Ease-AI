import os
import time
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    API_KEY = "x"

client = genai.Client(api_key=API_KEY)

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

model_name = "gemini-2.5-flash"

def detect_distress(text):
    t = text.lower()
    distress_words = ["can't pay", "cannot pay", "financial crisis", "no money", "poor", "struggling", "hard time", "broke", "unemployed", "no income"]
    return any(word in t for word in distress_words)

memory_context = ""

def classify_intent(text):
    t = text.lower()
    if any(word in t for word in ["paid", "but", "still", "charged", "balance", "receipt"]): return "payment_issue"
    if any(word in t for word in ["why", "reason", "explain"]): return "confusion"
    if any(word in t for word in ["what should i do", "help", "fix"]): return "action_request"
    return "general"

def build_input(user_input):
    intent = classify_intent(user_input)
    distress = detect_distress(user_input)
    return f"\n[USER INTENT: {intent}]\n[USER DISTRESS: {distress}]\n\n{user_input}"

def ask_file_path():
    while True:
        path = input("Enter PDF or Image path (PNG, JPG, JPEG) [or press Enter to skip]: ").strip().strip('"')
        if not path: 
            return None
        
        if os.path.isfile(path):
            allowed_extensions = (".pdf", ".png", ".jpg", ".jpeg")
            if path.lower().endswith(allowed_extensions):
                return path
            else:
                print("Unsupported file format. Please provide a PDF or an Image (PNG, JPG, JPEG).")
        else:
            print("File not found. Try again or press Enter to skip.")

def ask_extra_text():
    text = input("Enter additional text (optional, press Enter to skip): ").strip()
    return text if text else None

def get_user_inputs():
    while True:
        file_path = ask_file_path()
        extra_text = ask_extra_text()
        if not file_path and not extra_text:
            print("You did not provide any input. Please try again.\n")
            continue
        return file_path, extra_text

def start_project_session(file_path, extra_text=None):
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            max_output_tokens=8192,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        parts = []
        
        if file_path and os.path.exists(file_path):
            print(f"Uploading file: {os.path.basename(file_path)} ...")
            uploaded_file = client.files.upload(file=file_path)
            
            while uploaded_file.state.name == "PROCESSING":
                print("Processing file...")
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
            
            if uploaded_file.state.name == "FAILED":
                print("File processing failed. Creating session without the file.")
            else:
                parts.append(types.Part.from_uri(file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type))
                parts.append(types.Part.from_text(text="Please read, analyze, and understand this file carefully."))
        else:
            print("No file provided or file not found. Continuing with text context only.")

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
        print(f"Initialization failed: {e}")
        return None

file_path, extra_text = get_user_inputs()
MAX_RETRIES = 3
attempt = 0
session = None

while attempt < MAX_RETRIES and session is None:
    session = start_project_session(file_path, extra_text)
    if session is None:
        attempt += 1
        print(f"Session creation failed. Retrying ({attempt}/{MAX_RETRIES})...")
        time.sleep(2)

if session is None:
    print("Failed to create session after multiple attempts. Exiting safely.")
    exit()

print("\n--- Analyzing Document / Context... ---")

first_response = session.send_message_stream(
    """
Analyze the provided context immediately and provide the output in English, strictly following the structured rules defined in your System Instructions.

Additionally, return the final answer as valid JSON only using the following schema:

{
  "document_type": "",
  "situation": {
    "summary": "",
    "severity": "",
    "source_pages": []
  },
  "problem_explanation": "",
  "student_actions": [
    {
      "priority": 1,
      "action": "",
      "reason": ""
    }
  ],
  "university_policy": [
    {
      "title": "",
      "details": "",
      "source_url": ""
    }
  ],
  "organizations": [
    {
      "name": "",
      "type": "",
      "services": "",
      "eligibility": "",
      "source_url": ""
    }
  ],
  "university_resources": [],
  "external_resources": [],
  "deadlines": [],
  "checklist": [],
  "contacts": [],
  "sources": []
}

Requirements:
- Follow ALL System Instruction rules.
- Preserve all research requirements.
- Preserve all source requirements.
- Preserve all policy research requirements.
- Return JSON only.
- Do not return Markdown.
- Do not use code fences.
- Do not add explanations outside the JSON.
"""
)
for chunk in first_response:
    print(chunk.text, end="", flush=True)
print() 

while True:
    user_input = input("\nYou: ")
    if user_input.lower() == "exit":
        break

    if user_input.startswith("/add "):
        memory_context += "\n" + user_input.replace("/add ", "").strip()
        print("Context saved.")
        continue

    final_input = build_input(user_input)

    if detect_distress(user_input):
        final_input = "IMPORTANT:\nThe user is experiencing financial difficulty. Respond in a supportive, calm, non-judgmental tone.\n" + final_input

    if memory_context:
        final_input += "\n\n[MEMORY CONTEXT]\n" + memory_context

    response = session.send_message_stream(final_input)
    for chunk in response:
        print(chunk.text, end="", flush=True)
    print()
