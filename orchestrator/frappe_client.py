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

    if http_method == "GET":
        response = requests.get(url, params=arguments, headers=headers, timeout=FRAPPE_TIMEOUT)
    else:
        response = requests.post(url, json=arguments, headers=headers, timeout=FRAPPE_TIMEOUT)

    try:
        response.raise_for_status()
    except HTTPError as exc:
        detail = response.text.strip()
        if len(detail) > 500:
            detail = detail[:500] + "..."
        raise HTTPError(
            f"{exc}. Frappe response: {detail}",
            response=response,
        ) from exc

    return response.json()
