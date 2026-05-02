# VTU Diary Agent

An autonomous Streamlit chatbot that manages a student's internship diary on the VTU portal (`internyet.in`). Plug in any OpenAI-compatible LLM, log in with VTU credentials, and instruct the agent in natural language to read, generate, fill, or update diary entries.

Built for any student on any internship — not hardcoded to one user, one program, or one skill set.

## Features

- **Four authority modes** the agent honors strictly:
  - **Default** — agent asks for missing required fields. Never fabricates.
  - **Read** — agent fetches past entries when asked, then still asks before writing.
  - **Style fill** — agent reads past entries and fabricates new ones matching the style.
  - **Generate** — agent fabricates from context only, no auto-fetch.
- **Live skill catalog**: agent picks `skill_ids` from the portal's 120-skill master list (`/master/skills`). Invalid IDs are filtered out before submission.
- **JWT refresh loop**: every API call auto-retries once via `POST /auth/refresh` on 401, so 1-hour token expiry never breaks long sessions.
- **Background prefetch**: diary list is fetched in a daemon thread the moment login succeeds, so the user's first read query feels instant even on accounts with 20+ pages of entries.
- **Parallel pagination**: up to 16 concurrent requests for users with many pages. Cache busts automatically after a successful submit.
- **Per-session cache**: 5-minute TTL on diary reads. Multi-user safe — every cache lives in `st.session_state`, never on disk, never cross-user.
- **Hard validation**: hours capped at 12, dates validated as `YYYY-MM-DD`, skill IDs filtered against the live catalog, descriptions/learnings required.
- **Mood slider hidden**: defaults to 5 silently; the LLM never sees, asks for, or sets it.
- **Sat/Sun skip in chat only**: tell the agent "skip Sundays" mid-conversation. No global toggle — every user can decide per-session.
- **Connection validator**: the LLM config screen probes `/v1/models` against the entered endpoint, then loads the model catalog as a dropdown. `gpt-5.4-nano` is the default.
- **Editable model & endpoint** from the chat sidebar — re-validate or switch models without re-logging-in.

## Stack

- **Streamlit 1.57** — UI, session state, native chat components.
- **OpenAI Python SDK 2.x** — chat completions with tool calling. Compatible with any OpenAI-compatible endpoint.
- **Requests** — VTU HTTP client (with cookie-based JWT auth).
- **stdlib only** for the rest: `threading`, `concurrent.futures`, `dataclasses`-free.

## Layout

```
.
├── app.py             # Streamlit UI — three-screen flow (LLM config → login → chat)
├── agent.py           # Tool registry, schema, system prompt, agent loop helpers
├── vtu_client.py      # VTUClient: login, refresh, list_internships, diary CRUD
├── config.py          # Session-state init, reset helpers
├── .streamlit/
│   └── config.toml    # Dark theme + minimal toolbar
├── requirements.txt
└── README.md
```

## Setup

```bash
git clone <repo>
cd VTU-Chatbot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Usage

1. **Configure LLM** — paste an OpenAI-compatible API key + base URL, click *Validate connection*. Pick a model from the dropdown that appears.
2. **Login** — enter VTU portal email + password. The app fetches your active internship automatically.
3. **Chat** — describe what you want. Examples:
   - `show me my entries between April 10 and April 20`
   - `fill April 22: 3 hours, worked on auth, learned JWT flow`
   - `read my last 10 entries and fill the missing days in April matching that style`
   - `write 3 entries for April 27–29 about prompt engineering, 3 hours each`
   - `rewrite April 15 with: built REST endpoints, learned validation`
   - `fill April but skip Sundays`

The agent picks `skill_ids` from the live catalog based on the description content. Existing dates are auto-overwritten on submit.

## Tools the agent can call

| Tool | Purpose |
|---|---|
| `list_skills` | Fetch the 120-skill master catalog. |
| `get_existing_entries(start_date?, end_date?)` | List the student's diary entries with full body. |
| `get_entry_detail(id)` | Fetch one entry's full record including current `skill_ids`. |
| `submit_diary_entries(entries[])` | Create or overwrite entries. Auto-attaches `id` for known dates. |

## VTU API endpoints used

| Endpoint | Method |
|---|---|
| `/api/v1/auth/login` | POST |
| `/api/v1/auth/refresh` | POST |
| `/api/v1/auth/logout` | POST |
| `/api/v1/student/internship-applys?status=…` | GET |
| `/api/v1/master/skills` | GET |
| `/api/v1/student/internship-diaries?page=N` | GET |
| `/api/v1/student/internship-diaries/show?id=…` | GET |
| `/api/v1/student/internship-diaries/store` | POST |

## Security notes

- VTU access/refresh tokens live only in `st.session_state` (in-memory, per-session). Nothing is written to disk.
- Tokens are never logged or surfaced in error messages.
- `Logout` calls `POST /auth/logout` server-side and clears local session state.
- Built for multi-user deploy: every user has an isolated `VTUClient`, cache, and prefetch thread.

## Credits

Made By [Safwan Sayeed](https://safwansayeed.in)
