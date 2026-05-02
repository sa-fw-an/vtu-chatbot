"""Session state initialization."""
import streamlit as st

from vtu_client import VTUClient


DEFAULTS = {
    # LLM config
    "llm_configured": False,
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model_name": "gpt-5.4-nano",
    "available_models": [],
    "llm_validated": False,

    # VTU auth + internship
    "vtu_client": None,
    "vtu_user_name": "",
    "internship_id": None,
    "internship_name": "",
    "internship_company": "",
    "internship_type": "",

    # Caches the agent uses
    "skill_catalog": {},
    "existing_dates_map": {},

    # Chat
    "messages": [],
    "_submit_progress": None,
}


def init_session() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state.vtu_client is None:
        st.session_state.vtu_client = VTUClient()


def reset_auth() -> None:
    client: VTUClient = st.session_state.vtu_client
    if client:
        client.logout()
    st.session_state.vtu_client = VTUClient()
    st.session_state.vtu_user_name = ""
    st.session_state.internship_id = None
    st.session_state.internship_name = ""
    st.session_state.internship_company = ""
    st.session_state.internship_type = ""
    st.session_state.existing_dates_map = {}
    st.session_state.messages = []


def reset_llm() -> None:
    st.session_state.llm_configured = False
    st.session_state.llm_validated = False
    st.session_state.available_models = []
    st.session_state.messages = []
