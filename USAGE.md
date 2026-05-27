# AXON Query Processor – Usage Guide

**Your internal ERP AI assistant for tickets, feedback, suggestions, organization info, and web search.**

---

## Quick Start

### 1. Import and Use

```python
from orchestrator.query_processor import process_query
import asyncio

async def main():
    response = await process_query("Your question here")
    print(response)

asyncio.run(main())
```

### 2. Response Format

```python
{
    "query_type": "erp|search|organization|rag|identity",
    "status": "ok|error|missing",
    "message": "User-friendly message",
    "missing_fields": []  # if status == "missing"
}
```

---

## Supported Query Types

### 1. ERP Support (Tickets, Feedback, Suggestions)

**Create Tickets:**
```
"Raise a P0 ERP support ticket for app <app_name> module <module>. Description: <issue>"
```

**Create Feedback:**
```
"Give feedback for app <app_name> saying <feedback> with rating <1-5>"
```

**Create Suggestions:**
```
"Suggest an improvement for app <app_name> priority <Low|Medium|High>. Feedback: <idea>. Helps: <benefit>"
```

**List Operations:**
```
"Show my ERP tickets"
"List ERP feedback"
"Show my suggestions"
"List available apps"
```

**View Details:**
```
"Show details for <record_id>"
```

---

### 2. Organization Questions

Ask about company policies, HR, holidays, etc.:
```
"What are company holidays?"
"Tell me about HR policies"
"How do I request time off?"
"What's the company mission?"
```

---

### 3. Web Search

Search Wikipedia, DuckDuckGo, arXiv:
```
"Find information about <topic> on Wikipedia"
"Search for <query> on arXiv"
"What's the latest news about <topic>?"
```

---

### 4. Identity

```
"Who are you?"
"What can you do?"
"What's your name?"
```

---

## Common Scenarios

### Scenario 1: Create a High-Priority Ticket

```python
query = "Raise a P0 ticket for app Finance module Reporting. Dashboard is down."
response = await process_query(query)

# If missing fields:
if response["status"] == "missing":
    print(f"Need: {response['missing_fields']}")
    
# If success:
if response["status"] == "ok":
    print(f"✓ {response['message']}")
```

### Scenario 2: List My Tickets

```python
response = await process_query("Show my support tickets")
print(response["message"])
```

### Scenario 3: Leave Feedback

```python
query = "Give feedback for app Inventory. Works great! Rating 5."
response = await process_query(query)
```

---

## Finding Valid App Names

**Get the list of available apps:**
```
"List available apps"
```

This will show all apps you can use for creating tickets/feedback/suggestions.

---

## 🛠️ API & Custom DocTypes Developer Guide

Axon's architecture relies on a custom Frappe application layer that persists conversation states via three custom DocTypes. Below is the developer reference for these DocTypes and their associated whitelisted API endpoints.

### 1. Custom DocType Schemas

#### 📝 `AX_Sessions`
Represents an active, titled conversation thread belonging to a specific user.
*   `user_id` (Data): Email of the owning employee.
*   `session_id` (Data - Unique): Generated UUID identifying the session.
*   `title` (Data): Conversational summary (automatically updated).
*   `status` (Select): `Active` or `Inactive`.
*   `chats` (Table): List of individual messages (linked child table of `AX_Chats`).

#### 📝 `AX_Chats` (Child Table)
Stores each message exchange (User prompt or AI assistant response) inside a session.
*   `role` (Select): `User` or `Assistant`.
*   `content` (Long Text): Message text.
*   `sequence_number` (Int): Sequential counter (1-indexed).

#### 📝 `AX_Tools`
Registers external tools/APIs dynamically at runtime.
*   `tool_name` (Data - Unique): Canonical identifier of the tool.
*   `description` (Text): Semantic description parsed by the router LLM.
*   `status` (Select): `Active` or `Inactive`.

---

### 2. Whitelisted API Endpoints (`axon.api.*`)

These endpoints are whitelisted on the Frappe frontend app proxy (`apps/axon/axon/api.py`):

| Endpoint Path | HTTP Method | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `axon.api.create_session` | POST | `title` (optional) | Creates a new `AX_Sessions` record. |
| `axon.api.get_session` | GET | `session_id` | Retrieves a session along with its chronologically ordered `AX_Chats` messages. |
| `axon.api.list_sessions` | GET | `limit`, `offset` | Lists sessions for the currently logged-in user. |
| `axon.api.add_message` | POST | `session_id`, `role`, `content` | Appends a message to `AX_Chats`. Triggers background title generation on assistant turns. |
| `axon.api.query_ai` | POST | `session_id`, `query` | Submits a query, persists both turns, and returns the JSON answer. |
| `axon.api.stream_ai` | POST | `session_id`, `query` | Streams back SSE response chunks from AXON-SERVER. |

---

### 3. Programmatic Interaction Example (Frappe Console / Scripts)

You can interact with these DocTypes and endpoints directly in python:

```python
import frappe

# 1. Programmatically initialize a session
session = frappe.get_doc({
    "doctype": "AX_Sessions",
    "user_id": "employee@agnikul.in",
    "session_id": "test-uuid-1234",
    "title": "Initial Chat Setup",
    "status": "Active"
})
session.insert(ignore_permissions=True)

# 2. Append a user message
session.append("chats", {
    "role": "User",
    "content": "Raise a ticket for Fleet Management.",
    "sequence_number": 1
})
session.save(ignore_permissions=True)
frappe.db.commit()

# 3. Fetch session with messages
doc = frappe.get_doc("AX_Sessions", session.name)
for msg in doc.chats:
    print(f"[{msg.role}] {msg.content}")
```

---

## Error Handling

### Missing Fields
```
{
    "query_type": "erp",
    "status": "missing",
    "missing_fields": ["app_name", "priority"],
    "message": "I just need: application name, priority"
}
```

### API Error
```
{
    "query_type": "erp",
    "status": "error",
    "message": "Error message from system"
}
```

---

## Configuration (Optional)

Set environment variables if needed:
```bash
export FRAPPE_URL="http://localhost:8000"
export FRAPPE_TIMEOUT="30"
export OLLAMA_BASE_URL="http://localhost:11434"
```

---

## Verification

Verify the orchestrator API is running correctly using `curl`:
```bash
curl -X POST http://localhost:8004/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Who founded Agnikul Cosmos?"}'
```

---

## Support

For issues, check:
1. Valid app name (run "List available apps")
2. Required fields for your query type
3. Frappe server is running on configured URL
4. Session credentials are valid

---

**Version:** 1.0  
**Last Updated:** 25 May 2026  
**Status:** Production Ready
