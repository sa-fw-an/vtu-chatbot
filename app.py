import streamlit as st
import requests
import json
import time
from openai import OpenAI

# ============================================================================
# ⚙️ CONFIGURATION (Endpoints)
# ============================================================================
VTU_LOGIN_URL = "https://vtuapi.internyet.in/api/v1/auth/login"
VTU_APPLYS_URL = "https://vtuapi.internyet.in/api/v1/student/internship-applys?page=1&status=6"
VTU_GET_URL = "https://vtuapi.internyet.in/api/v1/student/internship-diaries"
VTU_POST_URL = "https://vtuapi.internyet.in/api/v1/student/internship-diaries/store"

# ============================================================================
# 🔐 VTU AUTH & SETUP FUNCTIONS
# ============================================================================
def login_to_vtu(email, password):
    headers = {
        "Origin": "https://vtu.internyet.in", 
        "Content-Type": "application/json"
    }
    payload = {"email": email, "password": password}
    
    try:
        response = requests.post(VTU_LOGIN_URL, json=payload, headers=headers)
        if response.status_code == 200:
            # 🔑 VTU stores the token in the cookies
            cookies = response.cookies.get_dict()
            token = cookies.get("access_token")
            
            if token:
                return token
            else:
                # Fallback: manually parse Set-Cookie header
                set_cookie_header = response.headers.get("Set-Cookie", "")
                if "access_token=" in set_cookie_header:
                    token_part = set_cookie_header.split("access_token=")[1]
                    token = token_part.split(";")[0]
                    return token
                
                st.error("Login succeeded, but could not find the access_token in the cookies.")
                return None
        else:
            st.error(f"Login failed! Check credentials. ({response.status_code})")
            return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None

def fetch_internship_id():
    headers = {
        "Origin": "https://vtu.internyet.in",
        "Content-Type": "application/json",
        "Cookie": f"access_token={st.session_state.vtu_token}"
    }
    try:
        res = requests.get(VTU_APPLYS_URL, headers=headers)
        if res.status_code == 200:
            data = res.json()
            # Navigate the JSON path to find the active internship
            if "data" in data and "data" in data["data"]:
                internships = data["data"]["data"]
                if len(internships) > 0:
                    # Grab the ID and Name of the first active internship
                    internship_id = internships[0].get("internship_id")
                    internship_name = internships[0].get("internship_details", {}).get("name", "Unknown Internship")
                    
                    st.session_state.internship_id = internship_id
                    st.session_state.internship_name = internship_name
                    return True
        st.error("Could not find an active internship (Status 6) in your portal.")
        return False
    except Exception as e:
        st.error(f"Failed to fetch internship details: {e}")
        return False

# ============================================================================
# 🛠️ AGENT TOOLS
# ============================================================================
def get_auth_headers():
    return {
        "Origin": "https://vtu.internyet.in",
        "Content-Type": "application/json",
        "Cookie": f"access_token={st.session_state.vtu_token}"
    }

def get_existing_entries(args_json=None):
    all_entries = []
    current_page = 1
    last_page = 1
    
    while current_page <= last_page:
        res = requests.get(f"{VTU_GET_URL}?page={current_page}", headers=get_auth_headers())
        if res.status_code != 200:
            return json.dumps({"error": f"HTTP {res.status_code}"})
            
        data = res.json()
        if "data" in data and "data" in data["data"]:
            all_entries.extend(data["data"]["data"])
            
        last_page = data.get("data", {}).get("last_page", 1)
        current_page += 1

    # Save IDs to session state for updating existing dates later
    st.session_state.existing_dates_map = {entry['date']: entry['id'] for entry in all_entries}
    
    simplified = [{"date": e['date'], "description": e['description'], "learnings": e['learnings']} for e in all_entries]
    return json.dumps(simplified)


def submit_diary_entries(args_json):
    entries = json.loads(args_json).get("entries", [])
    results = []
    
    for entry in entries:
        payload = {
            "internship_id": st.session_state.internship_id, # Dynamically assigned!
            "date": entry["date"],
            "hours": entry["hours"],
            "description": entry["description"],
            "learnings": entry["learnings"],
            "blockers": "", "links": "", "mood_slider": 5, "skill_ids": ["3"] # 3 is Python
        }
        
        # Attach ID if we are overwriting an existing date
        if entry["date"] in st.session_state.existing_dates_map:
            payload["id"] = st.session_state.existing_dates_map[entry["date"]]
            
        res = requests.post(VTU_POST_URL, json=payload, headers=get_auth_headers())
        if res.status_code in [200, 201]:
            results.append({"date": entry["date"], "status": "Success"})
        else:
            results.append({"date": entry["date"], "status": f"Failed: {res.status_code}"})
            
        time.sleep(2) # Rate limit protection
        
    return json.dumps(results)

# Map the tools
available_functions = {
    "get_existing_entries": get_existing_entries,
    "submit_diary_entries": submit_diary_entries
}

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_existing_entries",
            "description": "Fetches the student's existing diary entries. Use this to check filled dates or learn their writing style."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diary_entries",
            "description": "Submits or overwrites diary entries. ALWAYS skip Sundays.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "YYYY-MM-DD"},
                                "hours": {"type": "number", "description": "Integer 2-4"},
                                "description": {"type": "string"},
                                "learnings": {"type": "string"}
                            },
                            "required": ["date", "hours", "description", "learnings"]
                        }
                    }
                },
                "required": ["entries"]
            }
        }
    }
]

# ============================================================================
# 🖥️ STREAMLIT UI
# ============================================================================
st.set_page_config(page_title="VTU Diary Agent", page_icon="🤖", layout="centered")

# Initialize Session States
if "llm_configured" not in st.session_state:
    st.session_state.llm_configured = False
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "base_url" not in st.session_state:
    st.session_state.base_url = "https://api.openai.com/v1"
if "model_name" not in st.session_state:
    st.session_state.model_name = "gpt-5.4-nano"

if "vtu_token" not in st.session_state:
    st.session_state.vtu_token = None
if "internship_id" not in st.session_state:
    st.session_state.internship_id = None
if "internship_name" not in st.session_state:
    st.session_state.internship_name = ""
if "existing_dates_map" not in st.session_state:
    st.session_state.existing_dates_map = {}
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "You are an autonomous AI Agent managing a VTU internship diary. Always use get_existing_entries to learn the user's style before generating entries for Python/GenAI/n8n. Skip Sundays."}
    ]

# --- STEP 1: LLM CONFIGURATION SCREEN ---
if not st.session_state.llm_configured:
    st.title("⚙️ Configure AI Agent")
    st.caption("Connect your AI Agent to an OpenAI-compatible endpoint.")
    
    with st.form("llm_form"):
        api_key = st.text_input("API Key", type="password", placeholder="sk-...")
        base_url = st.text_input("Base URL", value="https://api.openai.com/v1")
        model_name = st.text_input("Model Name", value="gpt-5.4-nano")
        submit_llm = st.form_submit_button("Save & Continue")
        
        if submit_llm:
            if not api_key:
                st.error("API Key is required!")
            else:
                st.session_state.api_key = api_key
                st.session_state.base_url = base_url
                st.session_state.model_name = model_name
                st.session_state.llm_configured = True
                st.success("LLM Configured!")
                st.rerun()

# --- STEP 2: VTU LOGIN SCREEN ---
elif not st.session_state.vtu_token:
    st.title("🔐 VTU Portal Login")
    st.caption("Login to your VTU portal so the agent can manage your diary.")
    
    with st.form("login_form"):
        email = st.text_input("VTU Email / Username")
        password = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login")
        
        if submit_login:
            with st.spinner("Authenticating with VTU..."):
                token = login_to_vtu(email, password)
                if token:
                    st.session_state.vtu_token = token
                    # Automatically fetch their Internship ID
                    success = fetch_internship_id()
                    if success:
                        st.success("Successfully logged in and found active internship!")
                        time.sleep(1)
                        st.rerun()

# --- STEP 3: CHATBOT SCREEN ---
else:
    # Initialize the OpenAI Client dynamically with the user's settings
    client = OpenAI(
        api_key=st.session_state.api_key,
        base_url=st.session_state.base_url
    )

    st.title("🤖 VTU Agentic Chatbot")
    st.caption(f"Connected to: `{st.session_state.model_name}` | Managing: **{st.session_state.internship_name}**")

    # Sidebar for logout / reset config
    with st.sidebar:
        st.subheader("Settings")
        if st.button("Reset AI Configuration"):
            st.session_state.llm_configured = False
            st.rerun()
        if st.button("Logout of VTU Portal"):
            st.session_state.vtu_token = None
            st.session_state.internship_id = None
            st.rerun()

    # Display chat history
    for msg in st.session_state.messages:
        if msg["role"] in ["user", "assistant"] and msg.get("content"):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # User Input
    if prompt := st.chat_input("What should I do with your diary today?"):
        # Add user message to UI and history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Agent Execution Loop
        with st.chat_message("assistant"):
            with st.spinner("Agent is thinking and executing tools..."):
                is_thinking = True
                
                while is_thinking:
                    try:
                        # Call OpenAI
                        response = client.chat.completions.create(
                            model=st.session_state.model_name,
                            temperature=0.5,
                            messages=st.session_state.messages,
                            tools=tools_schema,
                            tool_choice="auto"
                        )
                        
                        assistant_msg = response.choices[0].message
                        
                        # Convert OpenAI object to dict for Streamlit session state
                        msg_dict = {"role": "assistant"}
                        if assistant_msg.content: msg_dict["content"] = assistant_msg.content
                        if assistant_msg.tool_calls: 
                            msg_dict["tool_calls"] = [{"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}} for t in assistant_msg.tool_calls]
                        
                        st.session_state.messages.append(msg_dict)

                        # Handle Tool Calls
                        if assistant_msg.tool_calls:
                            for tool_call in assistant_msg.tool_calls:
                                func_name = tool_call.function.name
                                func_args = tool_call.function.arguments
                                
                                st.toast(f"🛠️ Executing: `{func_name}`")
                                
                                # Execute Python tool
                                result = available_functions[func_name](func_args)
                                
                                st.session_state.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": func_name,
                                    "content": result
                                })
                        else:
                            # Finished thinking, display final answer
                            st.markdown(assistant_msg.content)
                            is_thinking = False
                    
                    except Exception as e:
                        st.error(f"LLM Error: {e}")
                        is_thinking = False