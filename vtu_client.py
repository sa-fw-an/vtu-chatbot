"""VTU portal HTTP client. Handles auth, refresh, and diary CRUD."""
from __future__ import annotations

import requests
from typing import Any

BASE = "https://vtuapi.internyet.in/api/v1"
ORIGIN = "https://vtu.internyet.in"


class VTUAuthError(Exception):
    pass


class VTUClient:
    def __init__(self, access_token: str | None = None, refresh_token: str | None = None):
        self.access_token = access_token
        self.refresh_token = refresh_token

    def _headers(self) -> dict[str, str]:
        cookie_parts = []
        if self.access_token:
            cookie_parts.append(f"access_token={self.access_token}")
        if self.refresh_token:
            cookie_parts.append(f"refresh_token={self.refresh_token}")
        return {
            "Origin": ORIGIN,
            "Content-Type": "application/json",
            "Cookie": "; ".join(cookie_parts),
        }

    @staticmethod
    def _extract_cookie(response: requests.Response, name: str) -> str | None:
        token = response.cookies.get(name)
        if token:
            return token
        for header in response.raw.headers.getlist("Set-Cookie") if hasattr(response.raw.headers, "getlist") else []:
            if f"{name}=" in header:
                return header.split(f"{name}=")[1].split(";")[0]
        set_cookie = response.headers.get("Set-Cookie", "")
        if f"{name}=" in set_cookie:
            return set_cookie.split(f"{name}=")[1].split(";")[0]
        return None

    def login(self, email: str, password: str) -> tuple[bool, str]:
        try:
            r = requests.post(
                f"{BASE}/auth/login",
                json={"email": email, "password": password},
                headers={"Origin": ORIGIN, "Content-Type": "application/json"},
                timeout=15,
            )
        except requests.RequestException as e:
            return False, f"Network error: {e}"
        if r.status_code != 200:
            try:
                msg = r.json().get("message", f"HTTP {r.status_code}")
            except Exception:
                msg = f"HTTP {r.status_code}"
            return False, msg
        access = self._extract_cookie(r, "access_token")
        refresh = self._extract_cookie(r, "refresh_token")
        if not access:
            return False, "Login OK but no access_token cookie returned."
        self.access_token = access
        self.refresh_token = refresh
        return True, r.json().get("data", {}).get("name", "")

    def refresh(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            r = requests.post(f"{BASE}/auth/refresh", headers=self._headers(), timeout=15)
        except requests.RequestException:
            return False
        if r.status_code != 200:
            return False
        access = self._extract_cookie(r, "access_token")
        refresh = self._extract_cookie(r, "refresh_token")
        if access:
            self.access_token = access
        if refresh:
            self.refresh_token = refresh
        return bool(access)

    def logout(self) -> None:
        try:
            requests.post(f"{BASE}/auth/logout", headers=self._headers(), timeout=10)
        except requests.RequestException:
            pass
        self.access_token = None
        self.refresh_token = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Call API; on 401 try refresh once, then retry."""
        url = f"{BASE}{path}"
        r = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        if r.status_code == 401 and self.refresh():
            r = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        return r

    def fetch_active_internship(self) -> dict | None:
        """Find first active internship (any non-zero status). Returns {id, name, company} or None."""
        for status in (6, 5, 4, 3, 2, 1):
            r = self._request("GET", f"/student/internship-applys?page=1&status={status}")
            if r.status_code != 200:
                continue
            items = r.json().get("data", {}).get("data", [])
            if items:
                top = items[0]
                details = top.get("internship_details", {}) or {}
                return {
                    "internship_id": top.get("internship_id"),
                    "name": details.get("name", "Unknown Internship"),
                    "company": details.get("company", ""),
                    "type": details.get("internship_type", ""),
                    "status": top.get("status"),
                }
        return None

    def list_skills(self) -> list[dict]:
        r = self._request("GET", "/master/skills")
        if r.status_code != 200:
            return []
        return r.json().get("data", []) or []

    def list_diaries(self, page: int = 1) -> dict:
        r = self._request("GET", f"/student/internship-diaries?page={page}")
        if r.status_code != 200:
            raise VTUAuthError(f"HTTP {r.status_code}")
        return r.json().get("data", {})

    def list_all_diaries(self) -> list[dict]:
        page, last_page, all_entries = 1, 1, []
        while page <= last_page:
            data = self.list_diaries(page)
            all_entries.extend(data.get("data", []) or [])
            last_page = data.get("last_page", 1)
            page += 1
        return all_entries

    def get_entry(self, entry_id: int) -> dict | None:
        r = self._request("GET", f"/student/internship-diaries/show?id={entry_id}")
        if r.status_code != 200:
            return None
        return r.json().get("data")

    def store_entry(self, payload: dict) -> tuple[bool, str, dict | None]:
        r = self._request("POST", "/student/internship-diaries/store", json=payload)
        try:
            body = r.json()
        except Exception:
            body = {}
        if r.status_code in (200, 201) and body.get("success", True):
            return True, body.get("message", "OK"), body.get("data")
        return False, body.get("message", f"HTTP {r.status_code}"), body
