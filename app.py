"""VTU Diary Agent — Streamlit UI."""
from __future__ import annotations

import json

import streamlit as st
from openai import OpenAI

from agent import TOOLS, TOOLS_SCHEMA, build_system_message, start_prefetch_diaries
from config import init_session, reset_auth, reset_llm

# Initialize session before set_page_config so we can decide sidebar state per page.
init_session()
client_vtu = st.session_state.vtu_client

if not st.session_state.llm_configured:
    _page = "llm"
elif not client_vtu.access_token or not st.session_state.internship_id:
    _page = "login"
else:
    _page = "chat"

st.set_page_config(
    page_title="VTU Diary Agent",
    page_icon=":material/edit_note:",
    layout="wide",
    # Expanded only on the chat page. Streamlit auto-collapses on phones,
    # so this gives the laptop user an open sidebar after login while
    # keeping mobile clean.
    initial_sidebar_state="expanded" if _page == "chat" else "collapsed",
)

DEFAULT_MODEL = "gpt-5.4-nano"


# ---------------------------------------------------------------------------
# Dark-only theme. config.toml provides the base; this just polishes layout.
# ---------------------------------------------------------------------------
def inject_styles(hide_sidebar: bool = False) -> None:
    sidebar_css = (
        'section[data-testid="stSidebar"], button[data-testid="stSidebarCollapseButton"], '
        'button[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] '
        '{ display: none !important; }'
    ) if hide_sidebar else ""

    st.markdown(
        f"""
        <style>
          :root {{
            --vtu-bg: #0A0B0E;
            --vtu-panel: #13141A;
            --vtu-panel2: #191B22;
            --vtu-border: #272932;
            --vtu-text: #E6E7EB;
            --vtu-muted: #8A8F9B;
            --vtu-accent: #3B82F6;
          }}
          [data-testid="stHeader"] {{ background: transparent !important; border-bottom: none !important; }}
          .block-container {{ padding-top: 2rem; padding-bottom: 5.5rem; max-width: 980px; }}

          section[data-testid="stSidebar"] .stButton button {{ width: 100%; }}

          /* Header */
          .vtu-header {{
            padding: 0 0 1rem 0; margin-bottom: 1.4rem;
            border-bottom: 1px solid var(--vtu-border);
          }}
          .vtu-title {{
            font-size: 1.4rem; font-weight: 600; letter-spacing: -0.015em;
            color: var(--vtu-text); line-height: 1.2;
          }}
          .vtu-sub {{ font-size: 0.88rem; color: var(--vtu-muted); margin-top: 0.25rem; }}
          .vtu-meta {{ margin-top: 0.55rem; }}

          /* Pitch block on landing screen */
          .vtu-pitch {{
            border: 1px solid var(--vtu-border);
            background: var(--vtu-panel);
            border-radius: 14px;
            padding: 1.5rem 1.6rem;
            margin: 1.2rem 0 0 0;
          }}
          .vtu-pitch-row {{
            display: flex; gap: 0.9rem; align-items: flex-start;
            margin-bottom: 1.1rem;
          }}
          .vtu-pitch-icon {{
            flex: 0 0 auto; width: 36px; height: 36px;
            border-radius: 10px;
            background: rgba(59,130,246,0.12);
            border: 1px solid rgba(59,130,246,0.4);
            color: var(--vtu-accent); font-weight: 700;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.1rem;
          }}
          .vtu-pitch-title {{
            font-size: 1.1rem; font-weight: 600;
            color: var(--vtu-text); margin-bottom: 0.35rem;
            letter-spacing: -0.01em;
          }}
          .vtu-pitch-body {{
            font-size: 0.9rem; line-height: 1.55;
            color: var(--vtu-muted);
          }}
          .vtu-pitch-grid {{
            display: grid; grid-template-columns: repeat(2, 1fr);
            gap: 0.7rem; margin: 1rem 0 1.1rem 0;
          }}
          .vtu-pitch-card {{
            border: 1px solid var(--vtu-border);
            background: var(--vtu-panel2);
            border-radius: 10px;
            padding: 0.75rem 0.95rem;
          }}
          .vtu-pitch-card-title {{
            font-size: 0.82rem; font-weight: 600;
            color: var(--vtu-accent); margin-bottom: 0.2rem;
            letter-spacing: 0.02em; text-transform: uppercase;
          }}
          .vtu-pitch-card-body {{
            font-size: 0.84rem; color: var(--vtu-text); line-height: 1.45;
          }}
          .vtu-pitch-foot {{
            font-size: 0.78rem; color: var(--vtu-muted);
            border-top: 1px solid var(--vtu-border);
            padding-top: 0.85rem; line-height: 1.5;
          }}
          @media (max-width: 640px) {{
            .vtu-pitch-grid {{ grid-template-columns: 1fr; }}
          }}

          /* Tags */
          .tag {{
            display: inline-block; padding: 2px 9px; border-radius: 4px;
            font-size: 0.72rem; letter-spacing: 0.02em;
            border: 1px solid var(--vtu-border); background: var(--vtu-panel2);
            color: var(--vtu-muted); margin-right: 6px;
          }}
          .tag.accent {{
            color: var(--vtu-accent);
            border-color: rgba(59,130,246,0.4);
            background: rgba(59,130,246,0.12);
          }}

          /* Forms / chat */
          div[data-testid="stForm"] {{
            background: var(--vtu-panel); border: 1px solid var(--vtu-border);
            border-radius: 10px; padding: 1.1rem 1.2rem;
          }}
          [data-testid="stChatMessage"] {{
            background: var(--vtu-panel); border: 1px solid var(--vtu-border);
            border-radius: 10px; padding: 0.7rem 0.95rem;
          }}

          /* Primary button white text (icons too) */
          .stButton button[kind="primary"],
          .stFormSubmitButton button[kind="primary"] {{
            background: var(--vtu-accent) !important;
            border: 1px solid var(--vtu-accent) !important;
            color: #FFFFFF !important;
          }}
          .stButton button[kind="primary"] *,
          .stFormSubmitButton button[kind="primary"] * {{
            color: #FFFFFF !important; fill: #FFFFFF !important;
          }}
          .stButton button[kind="primary"]:hover,
          .stFormSubmitButton button[kind="primary"]:hover {{ filter: brightness(1.08); }}

          /* Footer — sits above the chat input */
          .vtu-footer {{
            position: fixed; bottom: 0; left: 0; right: 0;
            text-align: center; padding: 8px 0; font-size: 0.78rem;
            color: var(--vtu-muted); background: var(--vtu-bg);
            border-top: 1px solid var(--vtu-border); z-index: 9999;
          }}
          .vtu-footer a {{ color: var(--vtu-accent); text-decoration: none; font-weight: 500; }}
          .vtu-footer a:hover {{ text-decoration: underline; }}

          /* Lift Streamlit's bottom region (chat_input lives here) so the
             footer is fully visible underneath it. */
          [data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {{
            padding-bottom: 34px !important;
          }}

          {sidebar_css}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Reusable UI fragments
# ---------------------------------------------------------------------------
def render_footer() -> None:
    st.markdown(
        '<div class="vtu-footer">Made By '
        '<a href="https://safwansayeed.in" target="_blank" rel="noopener">Safwan Sayeed</a>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str = "", tags_html: str = "") -> None:
    meta = f'<div class="vtu-meta">{tags_html}</div>' if tags_html else ""
    st.markdown(
        f"""
        <div class="vtu-header">
          <div class="vtu-title">{title}</div>
          <div class="vtu-sub">{subtitle}</div>
          {meta}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# STEP 1 — LLM CONFIG
# ---------------------------------------------------------------------------
def _validate_llm(api_key: str, base_url: str) -> tuple[bool, list[str], str]:
    try:
        oai = OpenAI(api_key=api_key, base_url=base_url)
        page = oai.models.list()
        ids = sorted({m.id for m in page.data}) if getattr(page, "data", None) else []
        return True, ids, f"Connected. {len(ids)} models available."
    except Exception as e:
        return False, [], str(e)


def render_llm_config() -> None:
    inject_styles(hide_sidebar=True)

    render_header(
        "VTU Diary Agent",
        "Connect an OpenAI-compatible endpoint to begin.",
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        api_key = st.text_input(
            "API key", type="password", placeholder="sk-…",
            value=st.session_state.api_key, key="_cfg_api_key",
        )
    with c2:
        base_url = st.text_input(
            "Base URL", value=st.session_state.base_url, key="_cfg_base_url",
        )

    col_v, col_r = st.columns([1, 1])
    with col_v:
        if st.button(
            ":material/bolt: Validate connection",
            type="primary", use_container_width=True,
        ):
            if not api_key.strip():
                st.error("API key is required.")
            else:
                with st.status("Probing endpoint…", expanded=False) as s:
                    ok, ids, msg = _validate_llm(
                        api_key.strip(),
                        base_url.strip() or "https://api.openai.com/v1",
                    )
                    if ok:
                        st.session_state.api_key = api_key.strip()
                        st.session_state.base_url = base_url.strip() or "https://api.openai.com/v1"
                        st.session_state.available_models = ids
                        st.session_state.llm_validated = True
                        s.update(label=msg, state="complete")
                    else:
                        st.session_state.llm_validated = False
                        s.update(label=f"Validation failed — {msg}", state="error")
    with col_r:
        if st.button(":material/restart_alt: Clear", use_container_width=True,
                     disabled=not st.session_state.llm_validated):
            reset_llm()
            st.rerun()

    if not st.session_state.llm_validated:
        st.caption("Enter credentials, then validate to load the model list.")
        st.markdown(
            """
            <div class="vtu-pitch">
              <div class="vtu-pitch-row">
                <div class="vtu-pitch-icon">✦</div>
                <div>
                  <div class="vtu-pitch-title">Your internship diary, on autopilot.</div>
                  <div class="vtu-pitch-body">
                    Stop spending Sunday nights backfilling weeks of diary
                    entries. Just tell the agent what you worked on — in plain
                    English — and it writes the entry, picks the right skills,
                    and submits it to the VTU portal for you.
                  </div>
                </div>
              </div>
              <div class="vtu-pitch-grid">
                <div class="vtu-pitch-card">
                  <div class="vtu-pitch-card-title">Read</div>
                  <div class="vtu-pitch-card-body">See any range of past entries instantly.</div>
                </div>
                <div class="vtu-pitch-card">
                  <div class="vtu-pitch-card-title">Fill</div>
                  <div class="vtu-pitch-card-body">Backfill missing days from a single sentence.</div>
                </div>
                <div class="vtu-pitch-card">
                  <div class="vtu-pitch-card-title">Match style</div>
                  <div class="vtu-pitch-card-body">Generate new entries that sound like yours.</div>
                </div>
                <div class="vtu-pitch-card">
                  <div class="vtu-pitch-card-title">Rewrite</div>
                  <div class="vtu-pitch-card-body">Update any single day with one prompt.</div>
                </div>
              </div>
              <div class="vtu-pitch-foot">
                Works with any AI provider you already have an API key for —
                OpenAI, Groq, Together, OpenRouter, Ollama, and more.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="tag accent">Validated</div>'
        f'<div class="tag">{len(st.session_state.available_models)} models</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    options = list(st.session_state.available_models)
    if DEFAULT_MODEL not in options:
        options = [DEFAULT_MODEL] + options
    default_idx = options.index(DEFAULT_MODEL) if DEFAULT_MODEL in options else 0

    chosen = st.selectbox("Model", options=options, index=default_idx,
                          help=f"Default: {DEFAULT_MODEL}")

    if st.button(":material/arrow_forward: Continue",
                 type="primary", use_container_width=True):
        st.session_state.model_name = chosen or DEFAULT_MODEL
        st.session_state.llm_configured = True
        st.rerun()


# ---------------------------------------------------------------------------
# STEP 2 — LOGIN
# ---------------------------------------------------------------------------
def render_login() -> None:
    inject_styles(hide_sidebar=False)

    with st.sidebar:
        if st.button(":material/restart_alt: Reset LLM config"):
            reset_llm()
            st.rerun()

    render_header(
        "VTU Portal Login",
        "Authenticate to your student account.",
        tags_html=f'<span class="tag accent">{st.session_state.model_name}</span>',
    )

    with st.form("login_form", border=False):
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button(
            ":material/login: Login",
            type="primary", use_container_width=True,
        )
        if submit:
            with st.status("Authenticating…", expanded=False) as status:
                ok, info = client_vtu.login(email.strip(), password)
                if not ok:
                    status.update(label=f"Login failed — {info}", state="error")
                    return
                status.update(label="Authenticated. Locating active internship…")
                st.session_state.vtu_user_name = info
                internship = client_vtu.fetch_active_internship()
                if not internship:
                    status.update(label="No active internship found.", state="error")
                    return
                st.session_state.internship_id = internship["internship_id"]
                st.session_state.internship_name = internship["name"]
                st.session_state.internship_company = internship["company"]
                st.session_state.internship_type = internship["type"]
                status.update(label="Ready.", state="complete", expanded=False)
            # Warm up the diary cache in the background so the user's first
            # read query doesn't pay the full pagination cost.
            start_prefetch_diaries()
            st.rerun()


# ---------------------------------------------------------------------------
# STEP 3 — CHAT
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"##### :material/person: {st.session_state.vtu_user_name or 'Student'}"
        )
        st.caption(
            f":material/work: {st.session_state.internship_name or '—'}"
        )
        if st.session_state.internship_company:
            st.caption(
                f":material/apartment: {st.session_state.internship_company}"
            )

        st.divider()
        with st.expander(
            f":material/smart_toy: {st.session_state.model_name}",
            expanded=False,
        ):
            st.caption(st.session_state.base_url)

            new_url = st.text_input(
                "Base URL",
                value=st.session_state.base_url,
                key="_sb_base_url",
            )
            new_key = st.text_input(
                "API key",
                type="password",
                placeholder="leave blank to keep current",
                key="_sb_api_key",
            )

            if st.button(
                ":material/bolt: Re-validate",
                key="_sb_revalidate",
                use_container_width=True,
            ):
                effective_key = new_key.strip() or st.session_state.api_key
                effective_url = new_url.strip() or st.session_state.base_url
                with st.status("Probing endpoint…", expanded=False) as s:
                    ok, ids, msg = _validate_llm(effective_key, effective_url)
                    if ok:
                        st.session_state.api_key = effective_key
                        st.session_state.base_url = effective_url
                        st.session_state.available_models = ids
                        s.update(label=msg, state="complete")
                        st.rerun()
                    else:
                        s.update(label=f"Failed — {msg}", state="error")

            options = list(st.session_state.available_models) or [st.session_state.model_name]
            if DEFAULT_MODEL not in options:
                options = [DEFAULT_MODEL] + options
            try:
                idx = options.index(st.session_state.model_name)
            except ValueError:
                idx = 0
            picked = st.selectbox(
                "Model",
                options=options,
                index=idx,
                key="_sb_model",
            )
            if picked and picked != st.session_state.model_name:
                st.session_state.model_name = picked
                st.rerun()

        st.divider()
        st.markdown("##### :material/tune: Session")
        if st.button(":material/delete_sweep: Clear chat"):
            st.session_state.messages = []
            st.rerun()
        if st.button(":material/restart_alt: Reset LLM"):
            reset_llm()
            st.rerun()
        if st.button(":material/logout: Logout"):
            reset_auth()
            st.rerun()


def render_chat_history() -> None:
    for msg in st.session_state.messages:
        role = msg.get("role")
        if role in ("user", "assistant") and msg.get("content"):
            with st.chat_message(role):
                st.markdown(msg["content"])


def run_agent_turn(prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    oai = OpenAI(api_key=st.session_state.api_key, base_url=st.session_state.base_url)
    convo = [build_system_message()] + st.session_state.messages

    with st.chat_message("assistant"):
        status_box = st.status("Thinking…", expanded=False)
        is_thinking = True
        steps = 0
        max_steps = 8

        while is_thinking and steps < max_steps:
            steps += 1
            try:
                response = oai.chat.completions.create(
                    model=st.session_state.model_name,
                    temperature=0.4,
                    messages=convo,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                )
            except Exception as e:
                status_box.update(label=f"LLM error: {e}", state="error")
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"LLM error: `{e}`"}
                )
                return

            assistant_msg = response.choices[0].message
            msg_dict: dict = {"role": "assistant"}
            if assistant_msg.content:
                msg_dict["content"] = assistant_msg.content
            if assistant_msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id, "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_msg.tool_calls
                ]
            st.session_state.messages.append(msg_dict)
            convo.append(msg_dict)

            if not assistant_msg.tool_calls:
                final = assistant_msg.content or "_(no response)_"
                status_box.update(label="Done", state="complete", expanded=False)
                st.markdown(final)
                is_thinking = False
                break

            for tc in assistant_msg.tool_calls:
                fname = tc.function.name
                fargs = tc.function.arguments or "{}"
                status_box.update(label=f"Calling {fname}", state="running", expanded=True)

                if fname == "submit_diary_entries":
                    try:
                        n = len(json.loads(fargs).get("entries", []))
                    except Exception:
                        n = 0
                    if n:
                        st.session_state._submit_progress = st.progress(
                            0.0, text=f"Submitting {n} entries…")

                func = TOOLS.get(fname)
                if not func:
                    result = json.dumps({"error": f"unknown tool {fname}"})
                else:
                    try:
                        result = func(fargs)
                    except Exception as e:
                        result = json.dumps({"error": str(e)})

                if st.session_state._submit_progress is not None:
                    try:
                        st.session_state._submit_progress.empty()
                    except Exception:
                        pass
                    st.session_state._submit_progress = None

                with status_box:
                    try:
                        parsed = json.loads(result)
                        preview = parsed if isinstance(parsed, dict) else {"data": parsed}
                        st.json(preview, expanded=False)
                    except Exception:
                        st.code(result[:1500], language="json")

                tool_entry = {
                    "role": "tool", "tool_call_id": tc.id,
                    "name": fname, "content": result,
                }
                st.session_state.messages.append(tool_entry)
                convo.append(tool_entry)

        if steps >= max_steps:
            status_box.update(label="Stopped: max tool-loop depth reached.", state="error")
            st.session_state.messages.append(
                {"role": "assistant", "content": "Stopped: max tool-loop depth reached."}
            )


def render_chat() -> None:
    inject_styles(hide_sidebar=False)
    render_sidebar()

    tags = [f'<span class="tag accent">{st.session_state.model_name}</span>']
    if st.session_state.internship_type:
        tags.append(f'<span class="tag">{st.session_state.internship_type}</span>')

    render_header(
        "Diary Agent",
        st.session_state.internship_name,
        tags_html=" ".join(tags),
    )

    if not st.session_state.messages:
        with st.expander("What you can ask", icon=":material/help:", expanded=True):
            st.markdown(
                """
                - **Read** — *show me my entries between April 10 and April 20*
                - **Submit known content** — *fill April 22: 3 hours, worked on auth, learned JWT flow*
                - **Style fill** — *read my last 10 entries and fill the missing days in April matching that style*
                - **Generate fresh** — *write 3 entries for April 27–29 about prompt engineering, 3 hours each*
                - **Update** — *rewrite April 15 with: built REST endpoints, learned validation*
                - **Skip weekends** — *fill April but skip Sundays*
                """
            )

    render_chat_history()

    if prompt := st.chat_input("What should I do with your diary?"):
        run_agent_turn(prompt)
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if not st.session_state.llm_configured:
    render_llm_config()
elif not client_vtu.access_token or not st.session_state.internship_id:
    render_login()
else:
    render_chat()

render_footer()
