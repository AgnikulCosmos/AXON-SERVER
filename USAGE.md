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
