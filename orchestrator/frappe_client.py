import os
from contextvars import ContextVar

import requests
from requests import HTTPError

FRAPPE_URL = os.getenv("FRAPPE_URL", "http://localhost:8000")
FRAPPE_TIMEOUT = int(os.getenv("FRAPPE_TIMEOUT", "30"))
_frappe_request_headers: ContextVar[dict | None] = ContextVar(
    "frappe_request_headers",
    default=None,
)


def set_frappe_request_headers(headers: dict | None):
    return _frappe_request_headers.set(headers or None)


def reset_frappe_request_headers(token) -> None:
    _frappe_request_headers.reset(token)

def call_frappe(tool_call: dict):

    method = tool_call["tool"]
    arguments = tool_call.get("arguments", {})
    http_method = tool_call.get("http_method", "POST").upper()

    url = f"{FRAPPE_URL}/api/method/{method}"

    API_KEY = os.getenv("FRAPPE_API_KEY")
    API_SECRET = os.getenv("FRAPPE_API_SECRET")

    headers = dict(_frappe_request_headers.get() or {})
    if not headers and API_KEY and API_SECRET:
        headers["Authorization"] = f"token {API_KEY}:{API_SECRET}"

    auth_debug = _auth_debug(headers)

    if http_method in {"POST", "PUT", "DELETE"}:
        csrf_added = _ensure_csrf_header(headers)
        auth_debug["csrf_added_by_axon"] = csrf_added
        auth_debug["has_csrf_header"] = _has_header(headers, "x-frappe-csrf-token")

    if http_method == "GET":
        response = requests.get(url, params=arguments, headers=headers, timeout=FRAPPE_TIMEOUT)
    else:
        # Suppress the automatic "Expect: 100-continue" header that requests
        # adds for POST bodies – Werkzeug (Frappe dev server) returns 417
        # Expectation Failed when it receives that header.
        post_headers = {**headers, "Expect": ""}
        response = requests.post(url, json=arguments, headers=post_headers, timeout=FRAPPE_TIMEOUT)

    try:
        response.raise_for_status()
    except HTTPError as exc:
        detail = response.text.strip()
        if len(detail) > 500:
            detail = detail[:500] + "..."
        raise HTTPError(
            f"{exc}. AXON auth debug: {auth_debug}. Frappe response: {detail}",
            response=response,
        ) from exc

    return response.json()


def _ensure_csrf_header(headers: dict) -> bool:
    if _has_header(headers, "x-frappe-csrf-token"):
        return False

    cookie = _get_header(headers, "cookie")
    if not cookie:
        return False

    response = requests.get(
        f"{FRAPPE_URL}/api/method/axon.api.get_current_user",
        headers={"cookie": cookie},
        timeout=FRAPPE_TIMEOUT,
    )
    response.raise_for_status()

    token = response.json().get("message", {}).get("csrf_token")
    if token:
        headers["X-Frappe-CSRF-Token"] = token
        return True
    return False

def _has_header(headers: dict, name: str) -> bool:
    return any(key.lower() == name.lower() for key in headers)


def _get_header(headers: dict, name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _auth_debug(headers: dict) -> dict:
    cookie = _get_header(headers, "cookie") or ""
    return {
        "has_cookie": bool(cookie),
        "has_sid_cookie": "sid=" in cookie,
        "has_authorization": _has_header(headers, "authorization"),
        "has_csrf_header": _has_header(headers, "x-frappe-csrf-token"),
    }
