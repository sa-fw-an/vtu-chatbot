"""Agent tool registry, schema, and run loop."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Callable

import streamlit as st

from vtu_client import VTUClient

HOURS_CAP = 12.0
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an autonomous diary agent for the VTU internship portal.
You manage diary entries for the student's single active internship.

# Authority modes (read user intent before acting)
1. DEFAULT — user gives partial fields. Ask for any missing required field. Never fabricate.
2. READ — user says "read past entries / fetch / show me my old entries". Call get_existing_entries (and get_entry_detail if needed). Then still ASK before writing new content.
3. STYLE-FILL — user says things like "match my style and fill", "fill like before", "write similar to past entries". You may read past entries AND fabricate new entries based on what you read.
4. GENERATE — user says "you write it / generate / fill yourself" without referencing past entries. Fabricate from context only; do not auto-fetch past entries.

# Required fields per entry
date (YYYY-MM-DD), hours (float, 0 < h <= 12), description, learnings, skill_ids (list of integer IDs from list_skills catalog).

# Optional fields
blockers (string), links (string).
NEVER mention, display, ask about, or set "mood_slider" — the system handles it silently. Do not include it in your tool calls.

# Hard rules
- skill_ids MUST come from the catalog returned by list_skills. Never invent IDs.
- hours must be > 0 and <= 12.
- By default, fill every date in the requested range including Saturdays and Sundays. ONLY skip Sat/Sun if the user explicitly asked in this conversation (e.g. "skip Sundays", "no weekends"). If they didn't say so, do not skip.
- When submitting multiple entries, call submit_diary_entries once with the full list, not one call per day.
- If the user says "submit" or "fill", and all required fields are present, submit directly. Do not ask for confirmation.
- After submit, summarise per-entry success/failure briefly.

# Style
Be terse. Bullet lists over prose. No emojis unless the user uses them.
"""


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _client() -> VTUClient:
    return st.session_state.vtu_client


def _validate_skill_ids(raw_ids: list, catalog_ids: set[int]) -> list[str]:
    out = []
    for sid in raw_ids or []:
        try:
            n = int(sid)
        except (TypeError, ValueError):
            continue
        if n in catalog_ids:
            out.append(str(n))
    return out


def _validate_date(date_str: str) -> str | None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format (need YYYY-MM-DD)"
    return None


# ---------- Tool: list_skills ----------
def tool_list_skills(_args: str = "") -> str:
    skills = _client().list_skills()
    st.session_state.skill_catalog = {int(s["id"]): s["name"] for s in skills}
    return json.dumps([{"id": s["id"], "name": s["name"]} for s in skills])


# ---------- Tool: get_existing_entries ----------
def tool_get_existing_entries(args_json: str) -> str:
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError:
        args = {}
    start = args.get("start_date")
    end = args.get("end_date")

    entries = _client().list_all_diaries()
    st.session_state.existing_dates_map = {e["date"]: e["id"] for e in entries}

    def in_range(d: str) -> bool:
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    filtered = [
        {
            "id": e["id"],
            "date": e["date"],
            "hours": e["hours"],
            "description": e["description"],
            "learnings": e["learnings"],
            "status": e.get("status"),
        }
        for e in entries
        if in_range(e["date"])
    ]
    filtered.sort(key=lambda x: x["date"])
    return json.dumps({"count": len(filtered), "entries": filtered})


# ---------- Tool: get_entry_detail ----------
def tool_get_entry_detail(args_json: str) -> str:
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "bad arguments"})
    entry_id = args.get("id")
    if not entry_id:
        return json.dumps({"error": "id required"})
    detail = _client().get_entry(int(entry_id))
    if not detail:
        return json.dumps({"error": "not found"})
    return json.dumps({
        "id": detail.get("id"),
        "date": detail.get("date"),
        "hours": detail.get("hours"),
        "description": detail.get("description"),
        "learnings": detail.get("learnings"),
        "blockers": detail.get("blockers"),
        "links": detail.get("links"),
        "skill_ids": [s.get("diary_skill_id") for s in (detail.get("skills") or [])],
    })


# ---------- Tool: submit_diary_entries ----------
def tool_submit_diary_entries(args_json: str) -> str:
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "bad arguments"})

    entries = args.get("entries") or []
    if not entries:
        return json.dumps({"error": "no entries"})

    if not st.session_state.skill_catalog:
        tool_list_skills()
    catalog_ids = set(st.session_state.skill_catalog.keys())

    if not st.session_state.existing_dates_map:
        # Lightweight pre-fetch so overwrites attach correctly even if LLM skipped reading
        try:
            tool_get_existing_entries("{}")
        except Exception:
            pass

    results = []
    client = _client()
    progress = st.session_state.get("_submit_progress")

    for i, entry in enumerate(entries):
        d = entry.get("date", "")
        if not DATE_RE.match(str(d)):
            results.append({"date": d, "status": "skipped", "reason": "invalid date"})
            continue

        bad = _validate_date(d)
        if bad:
            results.append({"date": d, "status": "skipped", "reason": bad})
            continue

        try:
            hours = float(entry.get("hours", 0))
        except (TypeError, ValueError):
            results.append({"date": d, "status": "skipped", "reason": "invalid hours"})
            continue
        if hours <= 0 or hours > HOURS_CAP:
            results.append({"date": d, "status": "skipped", "reason": f"hours must be 0 < h <= {HOURS_CAP}"})
            continue

        description = (entry.get("description") or "").strip()
        learnings = (entry.get("learnings") or "").strip()
        if not description or not learnings:
            results.append({"date": d, "status": "skipped", "reason": "missing description/learnings"})
            continue

        skill_ids = _validate_skill_ids(entry.get("skill_ids") or [], catalog_ids)
        if not skill_ids:
            skill_ids = ["3"]  # Python fallback only if nothing valid was provided

        payload = {
            "internship_id": st.session_state.internship_id,
            "date": d,
            "hours": hours,
            "description": description,
            "learnings": learnings,
            "blockers": entry.get("blockers", "") or "",
            "links": entry.get("links", "") or "",
            "mood_slider": 5,
            "skill_ids": skill_ids,
        }
        if d in st.session_state.existing_dates_map:
            payload["id"] = st.session_state.existing_dates_map[d]
            action = "updated"
        else:
            action = "created"

        ok, msg, _ = client.store_entry(payload)
        results.append({
            "date": d,
            "status": "success" if ok else "failed",
            "action": action if ok else None,
            "message": msg,
        })
        if progress:
            progress.progress((i + 1) / len(entries), text=f"{d} — {results[-1]['status']}")

    return json.dumps({"results": results, "total": len(results),
                       "successes": sum(1 for r in results if r["status"] == "success")})


# ---------------------------------------------------------------------------
# Tool registry + schema
# ---------------------------------------------------------------------------
TOOLS: dict[str, Callable[[str], str]] = {
    "list_skills": tool_list_skills,
    "get_existing_entries": tool_get_existing_entries,
    "get_entry_detail": tool_get_entry_detail,
    "submit_diary_entries": tool_submit_diary_entries,
}

TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "Fetch the full catalog of skill {id, name} pairs the portal accepts. Call once before constructing skill_ids.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_existing_entries",
            "description": "List the student's diary entries with date, hours, description, learnings, mood, status. Optional date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entry_detail",
            "description": "Fetch one diary entry's full record including its skill_ids and blockers/links/mood.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diary_entries",
            "description": (
                "Create or overwrite diary entries. Pass full per-entry data. "
                "Required: date, hours (0<h<=12), description, learnings, skill_ids (from list_skills). "
                "Optional: blockers, links. Existing dates are auto-overwritten."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "YYYY-MM-DD"},
                                "hours": {"type": "number"},
                                "description": {"type": "string"},
                                "learnings": {"type": "string"},
                                "skill_ids": {"type": "array", "items": {"type": "integer"}},
                                "blockers": {"type": "string"},
                                "links": {"type": "string"},
                            },
                            "required": ["date", "hours", "description", "learnings", "skill_ids"],
                        },
                    }
                },
                "required": ["entries"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System message builder
# ---------------------------------------------------------------------------
def build_system_message() -> dict:
    today = date.today().isoformat()
    ctx = (
        f"\n# Session context\n"
        f"- Today: {today}\n"
        f"- Active internship: {st.session_state.internship_name}\n"
        f"- internship_id: {st.session_state.internship_id}\n"
        f"- Hours hard cap: {HOURS_CAP}\n"
    )
    return {"role": "system", "content": SYSTEM_PROMPT + ctx}
