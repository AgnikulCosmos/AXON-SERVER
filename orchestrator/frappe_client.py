import os
import requests

FRAPPE_URL = os.getenv("FRAPPE_URL", "http://localhost:8000")

def call_frappe(tool_call: dict):

    method = tool_call["tool"]
    arguments = tool_call.get("arguments", {})

    url = f"{FRAPPE_URL}/api/method/{method}"

    API_KEY = os.getenv("FRAPPE_API_KEY")
    API_SECRET = os.getenv("FRAPPE_API_SECRET")

    headers = {
        "Authorization": f"token {API_KEY}:{API_SECRET}"
    }

    response = requests.post(
        url,
        json=arguments,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.json()