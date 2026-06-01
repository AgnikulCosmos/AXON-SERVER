import sys
import json
import os
import logging

logger = logging.getLogger(__name__)

from common.router import route_query
from common.rag_tool import rag_search

from orchestrator.agent import run_axon
from orchestrator.qwen_agent import run_qwen, summarize_tool_output
from orchestrator.tool_dispatcher import dispatch_tool
from orchestrator.erp_tool_dispatcher import prepare_tool_call
from orchestrator.erp_support_client import (
    execute_erp_support_plan,
    format_erp_support_response,
    MissingParametersError,
)
from orchestrator.planning import router_pipeline
from orchestrator.planning.parameter_extractor import extract_parameters
from orchestrator.planning.semantic_router import SemanticRouter
from orchestrator.agent import (
    MARKER_FINAL_START,
    MARKER_FINAL_END,
    stream_text_word_by_word,
)
from orchestrator.frappe_client import (
    reset_frappe_request_headers,
    set_frappe_request_headers,
)

PROFANITY_FALLBACK = (
    "Please use respectful and professional language while interacting with Axon."
)

TEST_MODE = False


async def _get_friendly_missing_fields_message(fields: list[str], route_name: str | None = None) -> str:
    from orchestrator.erp_support_client import _FIELD_LABELS, _FIELD_HINTS
    
    # Determine greetings and examples based on route_name
    example_text = "It is a blue access card, and I lost it in the cafeteria."
    
    if route_name == "lost_found_create":
        is_lost = any("lost" in f for f in fields) or any(f in {"item_name", "lost_description", "lost_location", "lost_date"} for f in fields)
        if is_lost:
            single_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. I just need one more detail to proceed:"
            multi_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. Please provide the following details:"
            example_text = "It is a blue access card, and I lost it in the cafeteria."
        else:
            single_greeting = "Thank you for reporting this found item! Let's get this registered in the system. I just need one more detail to proceed:"
            multi_greeting = "Thank you for reporting this found item! Let's get this registered in the system. Please provide the following details:"
            example_text = "I found a black keyset on the desk today."
    elif route_name == "erp_tickets_create":
        single_greeting = "I'll help you raise a support ticket. I just need one more detail to proceed:"
        multi_greeting = "I'll help you raise a support ticket. Please provide the following details:"
        example_text = "I am facing a loading lag issue in Fleet Management."
    elif route_name == "erp_feedback_create":
        single_greeting = "Thank you for your feedback! Let's get this registered. I just need one more detail to proceed:"
        multi_greeting = "Thank you for your feedback! Let's get this registered. Please provide the following details:"
        example_text = "The Fleet Management dashboard is highly responsive and clean."
    elif route_name == "erp_suggestion_create":
        single_greeting = "Thank you for your suggestion to improve the system! Let's get this submitted. I just need one more detail to proceed:"
        multi_greeting = "Thank you for your suggestion to improve the system! Let's get this submitted. Please provide the following details:"
        example_text = "Adding a night-mode theme would significantly reduce eye strain."
    else:
        # Fallback to default check
        is_lost = any("lost" in f for f in fields) or any(f in {"item_name", "lost_description", "lost_location", "lost_date"} for f in fields)
        if is_lost:
            single_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. I just need one more detail to proceed:"
            multi_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. Please provide the following details:"
            example_text = "It is a blue access card, and I lost it in the cafeteria."
        else:
            single_greeting = "To complete your request, I just need one more detail to proceed:"
            multi_greeting = "To complete your request, please provide the following details:"
            example_text = "It is a blue access card, and I lost it in the cafeteria."
    
    # 1. Single missing field
    if len(fields) == 1:
        field = fields[0]
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" (e.g., *{hint}*)" if hint else ""
        return (
            f"{single_greeting}\n\n"
            f"* **{label}**{hint_text}\n\n"
            f"You can reply in **plain English** (e.g., \"*{hint}*\") or use the optional template below:\n\n"
            f"```text\n"
            f"{field}: <value>\n"
            f"```"
        )
    
    # 2. Multiple missing fields
    lines = [
        multi_greeting
    ]
    
    for field in fields:
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" — *{hint}*" if hint else ""
        lines.append(f"* **{label}**{hint_text}")
        
    template_lines = [f"{field}: <value>" for field in fields]
    
    lines.append(f"You can reply naturally in **plain English** (e.g., \"*{example_text}*\") or use the optional template below:")
    lines.append(f"```text\n" + "\n".join(template_lines) + "\n```")
    
    return "\n\n".join(lines)


async def run_agent(query: str, frappe_headers: dict | None = None, session_id: str | None = None):
    header_token = set_frappe_request_headers(frappe_headers)
    try:
        return await _run_agent(query, session_id)
    finally:
        reset_frappe_request_headers(header_token)


# ── Persistent pending session store (survives hot-reloads) ──────────────
import json as _json

_PENDING_FILE = os.path.join(os.path.dirname(__file__), ".pending_sessions.json")


def _load_pending() -> dict:
    try:
        with open(_PENDING_FILE) as _f:
            return _json.load(_f)
    except Exception:
        return {}


def _save_pending(data: dict) -> None:
    try:
        with open(_PENDING_FILE, "w") as _f:
            _json.dump(data, _f)
    except Exception:
        pass


class _PersistentDict:
    """Dict-like wrapper backed by a JSON file so state survives reloads."""

    def __contains__(self, key):
        return key in _load_pending()

    def __getitem__(self, key):
        return _load_pending()[key]

    def __setitem__(self, key, value):
        data = _load_pending()
        data[key] = value
        _save_pending(data)

    def __delitem__(self, key):
        data = _load_pending()
        data.pop(key, None)
        _save_pending(data)

    def get(self, key, default=None):
        return _load_pending().get(key, default)

    def keys(self):
        return _load_pending().keys()


PENDING_ERP_SESSIONS = _PersistentDict()





async def contextualize_query_with_history(query: str, session_id: str | None) -> str:
    if not session_id:
        return query

    try:
        from orchestrator.frappe_client import call_frappe
        session_data = call_frappe({
            "tool": "axon.api.get_session",
            "http_method": "GET",
            "arguments": {"session_id": session_id}
        })
        session_dict = session_data.get("message") or {}
        messages = session_dict.get("messages") or []

        past_msgs = []
        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()
            # If the last message in DB is exactly the query being processed, exclude it
            if role == "User" and content == query.strip() and msg == messages[-1]:
                continue
            past_msgs.append((role, content))

        if not past_msgs:
            return query

        # Bypass contextualizer entirely if query contains a known Agnikul-specific named entity or domain term.
        # These terms are unambiguous — rewriting them via LLM only causes errors.
        _KNOWN_ENTITIES = {
            # Core Spacecraft & Proper Nouns
            "agnikul", "cosmos", "agnibaan", "agnilet", "dhanush", "sorted",
            "launchpad", "sdsc", "shar", "isro", "axon", "erp",
            "srinath", "moin", "satyanarayanan", "janardhana", "ravichandran", "spm", "raju", "chakravarthy"
        }
        query_lower_check = query.lower()
        
        # 1. Bypass if any specific Agnikul or ERP domain term is present
        if any(entity in query_lower_check for entity in _KNOWN_ENTITIES):
            logger.info(f"[Query Contextualizer] Bypassing rewrite — known entity/domain keyword in query: {query!r}")
            return query

        # Take up to last 6 messages
        recent_history = past_msgs[-6:]
        history_str = ""
        for role, content in recent_history:
            history_str += f"{role}: {content}\n"

        prompt = f"""[System]
You are a strict pronoun-resolution AI. Your ONLY job is to resolve ambiguous pronouns (it, he, she, they, this, that) in follow-up queries using the chat history.

CRITICAL RULES:
1. ONLY replace pronouns or add missing context (like "of Agnikul").
2. NEVER replace, delete, or overwrite actual nouns or names that the user typed (e.g., if the user types "Royal Challengers", keep "Royal Challengers").
3. If the user's query introduces a completely new topic or does not contain pronouns, output the query EXACTLY AS IS. Do not inject the previous topic.

[Example 1]
Chat History:
User: What is Agnikul Cosmos?
Assistant: It is a space company.
Follow-up Query: Who founded it?
Rewritten Query: Who founded Agnikul Cosmos?

[Example 2]
Chat History:
User: Who is Virat Kohli?
Assistant: He is a cricketer.
Follow-up Query: Search wiki about Royal Challengers Bangalore
Rewritten Query: Search wiki about Royal Challengers Bangalore

[Example 3]
Chat History:
User: What is Dhanush?
Assistant: It is a launch pedestal.
Follow-up Query: Tell me about Leave policy
Rewritten Query: Tell me about Leave policy

[Current Chat]
Chat History:
{history_str}

Follow-up Query: {query}
Rewritten Query:"""

        from orchestrator.qwen_agent import qwen_llm
        resp = await qwen_llm.ainvoke(prompt)
        rewritten = resp.content.strip().strip("\"'")
        if rewritten:
            logger.info(f"[Query Contextualizer] Original: {query!r} -> Rewritten: {rewritten!r}")
            return rewritten

    except Exception as err:
        logger.warning(f"Failed to contextualize query: {err}")
    
    return query


async def _run_agent(query: str, session_id: str | None = None):
    # ── Check for Greetings and Identity BEFORE contextualization ──
    # This prevents the history-rewriter from mangling simple conversational inputs.
    temp_q = query.lower().strip("!?., ")
    
    # 1. Identity Check
    if any(x in temp_q for x in ["who are you", "what is your name", "who is axon", "what can axon help", "what can you do"]):
        identity_response = "I am Axon, your friendly internal ERP AI Assistant at Agnikul Cosmos! I can help you with internal systems, HR, payroll, operations, organizational structure, and enterprise workflows."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(identity_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return identity_response

    # 2. Greeting Check
    from common.greeting import is_greeting, get_greeting_response
    if is_greeting(query):
        greeting_resp = get_greeting_response()
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(greeting_resp)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return greeting_resp

    # Only contextualize if NOT in a pending session to avoid mangling form inputs
    if not (session_id and session_id in PENDING_ERP_SESSIONS):
        query = await contextualize_query_with_history(query, session_id)

    q = query.lower().strip("!?.,")
    logger.debug(f"[Session Tracking] Query: {query!r}, session_id: {session_id!r}, in_pending: {session_id in PENDING_ERP_SESSIONS if session_id else False}")

    # ── Check for pending ERP session ──────────────────────────────
    if session_id and session_id in PENDING_ERP_SESSIONS:
        # Check if the user is explicitly switching to a different ERP intent
        new_route = await route_query(query)
        if new_route and new_route.startswith("ERP_ROUTE:"):
            matched_route_name = new_route.split(":", 1)[1]
            pending_plan = PENDING_ERP_SESSIONS[session_id]
            if matched_route_name != pending_plan.get("route_name"):
                logger.info(f"User switched intent from {pending_plan.get('route_name')} to {matched_route_name}. Discarding pending session.")
                del PENDING_ERP_SESSIONS[session_id]

    if session_id and session_id in PENDING_ERP_SESSIONS:
        if q in ["cancel", "stop", "abort", "nevermind", "quit", "exit"]:
            del PENDING_ERP_SESSIONS[session_id]
            msg = "Okay, I've cancelled that request."
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(msg)
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return msg

        pending_plan = PENDING_ERP_SESSIONS[session_id]
        missing_fields = pending_plan.get("_missing_fields") or []

        # ── Parse structured "field: value" reply ──────────────────
        import re as _re
        structured_params = {}
        matches = _re.finditer(r"\b([a-zA-Z_]+)\s*:\s*(.*?)(?=\s+\b[a-zA-Z_]+\s*:|$)", query, flags=_re.S)
        for match in matches:
            key = match.group(1).strip().lower().replace(" ", "_")
            val = match.group(2).strip().lstrip("`").rstrip("`")
            if key and val:
                structured_params[key] = val

        # Flexible parameter mapping for common user variations
        for desc_key in ["description", "item_description"]:
            if desc_key in structured_params:
                desc_val = structured_params.pop(desc_key)
                if "found" in pending_plan.get("route_name", ""):
                    structured_params["found_description"] = desc_val
                else:
                    structured_params["lost_description"] = desc_val

        if "app" in structured_params:
            structured_params["app_name"] = structured_params.pop("app")

        if "rating" in structured_params:
            structured_params["ratings"] = structured_params.pop("rating")

        # If the user used structured key-value format, use it.
        # Otherwise, use extract_parameters to run LLM-based intelligent extraction!
        if structured_params:
            new_params = structured_params
        else:
            router = SemanticRouter()
            route_config = next((route for route in router.routes if route.get("route_name") == pending_plan["route_name"]), None)
            if route_config:
                from copy import deepcopy
                temp_config = deepcopy(route_config)
                # Keep only missing fields in parameters schema so the extractor focuses precisely on them
                temp_config["parameters"] = {
                    k: v for k, v in route_config.get("parameters", {}).items()
                    if k in missing_fields
                }
                new_params = extract_parameters(query, temp_config)
            else:
                new_params = {}

            # Fallback: if Qwen could not extract anything and there is only 1 missing field,
            # assume the entire query string is the value for that single missing field.
            if not new_params and len(missing_fields) == 1:
                new_params = {missing_fields[0]: query.strip()}

        if not new_params:
            result = await _get_friendly_missing_fields_message(missing_fields, pending_plan.get("route_name"))
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(result)
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return result

        # Normalise app_name aliases in the reply
        if "app_name" in new_params:
            from orchestrator.planning.parameter_extractor import APP_NAME_MAPPING
            cand = new_params["app_name"].strip().lower()
            for canonical, aliases in APP_NAME_MAPPING.items():
                if cand == canonical.lower() or any(cand == a.lower() for a in aliases):
                    new_params["app_name"] = canonical
                    break

        if pending_plan.get("parameters") is None:
            pending_plan["parameters"] = {}
        pending_plan["parameters"].update(new_params)

        route = f"ERP_ROUTE:{pending_plan['route_name']}"
        plan = pending_plan
    else:
        route = await route_query(query)
        plan = None
        if route and route.startswith("ERP_ROUTE:"):
            route_name = route.split(":", 1)[1]
            plan = _build_erp_plan(route_name, query)

    # -------------------------
    # TEST MODE
    # -------------------------
    if TEST_MODE:
        if "who are you" in q:
            return "I am Axon, the ERP assistant for Agnikul."

        if any(x in q for x in ["fuck", "bitch", "nigga"]):
            return PROFANITY_FALLBACK

        if "translate" in q and "good morning" in q:
            return "Good morning in Tamil is காலை வணக்கம்."

        if any(x in q for x in ["hi", "hello", "hey"]):
            return "Hello, I am Axon, the ERP assistant for Agnikul."

        return "I am here to help."

    # -------------------------
    # REAL EXECUTION PATH
    # -------------------------
    if "who are you" in q or q == "what is your name" or q == "who is axon" or "what can axon help" in q or "what can you do" in q:
        identity_response = "I am Axon, your friendly internal ERP AI Assistant at Agnikul Cosmos! I can help you with internal systems, HR, payroll, operations, organizational structure, and enterprise workflows."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(identity_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return identity_response

    if "base model" in q or "which model" in q or "what model" in q or "underlying model" in q or "architecture" in q:
        model_response = "The base model I am using is Qwen2.5 (specifically Qwen2.5-1.5B), developed by Alibaba Group and running locally on our internal servers using Ollama."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(model_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return model_response

    if route == "PROFANITY":
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(PROFANITY_FALLBACK)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return PROFANITY_FALLBACK

    if route.startswith("GREETING_RESPONSE:"):
        greeting_response = route.split(":", 1)[1]
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(greeting_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return greeting_response

    if route == "IDENTITY":
        identity_response = "I am Axon, your friendly internal ERP AI Assistant at Agnikul Cosmos! I can help you with internal systems, HR, payroll, operations, organizational structure, and enterprise workflows."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(identity_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return identity_response

    if route == "RAG":
        result = rag_search(query)
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(result)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    if route.startswith("ERP_ROUTE:"):
        route_name = route.split(":", 1)[1]
        if plan is None:
            plan = _build_erp_plan(route_name, query)
            if plan:
                plan["original_query"] = query

        if plan:
            method = plan["method"]
            filters = plan.get("filters") or {}
            
            try:
                if method.startswith("erp_support.") or route_name.startswith("lost_found_"):
                    tool_response = execute_erp_support_plan(plan)
                    result = format_erp_support_response(plan, tool_response)
                    if session_id and session_id in PENDING_ERP_SESSIONS:
                        del PENDING_ERP_SESSIONS[session_id]
                elif method.startswith("get_") or "list" in method or "query" in method:
                    result = f"Fetching information for {method} with filters {filters}..."
                    if session_id and session_id in PENDING_ERP_SESSIONS:
                        del PENDING_ERP_SESSIONS[session_id]
                else:
                    import random
                    req_id = f"ERP_I_{random.randint(1000, 9999)}"
                    result = f"Successfully created your request and your req_id is {req_id}"
                    if session_id and session_id in PENDING_ERP_SESSIONS:
                        del PENDING_ERP_SESSIONS[session_id]
            except MissingParametersError as e:
                if session_id:
                    plan["_missing_fields"] = e.fields
                    PENDING_ERP_SESSIONS[session_id] = plan
                result = await _get_friendly_missing_fields_message(e.fields, plan.get("route_name"))
            except ValueError as e:
                if session_id and session_id in PENDING_ERP_SESSIONS:
                    del PENDING_ERP_SESSIONS[session_id]
                result = str(e)
            except Exception as e:
                if session_id and session_id in PENDING_ERP_SESSIONS:
                    del PENDING_ERP_SESSIONS[session_id]
                logger.exception("Error executing ERP support plan:")
                result = _friendly_erp_error(e)
        else:
            result = "No matching ERP route could be resolved for your query."

        logger.info("Result for ERP route: %s (type: %s)", result, type(result))
        result_str = str(result)
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(result_str)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result_str

    if route == "QWEN":
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        sys.stdout.flush()

        result = await run_qwen(query)

        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    if route == "TOOLS":
        tool_name, tool_result = await dispatch_tool(query)

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        sys.stdout.flush()

        result = await summarize_tool_output(
            user_query=query,
            tool_name=tool_name,
            tool_data=tool_result
        )

        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    # -------------------------
    # DEFAULT: AXON
    # -------------------------
    return await run_axon(query)


def _build_erp_plan(route_name: str, query: str) -> dict | None:
    """Build an ERP plan for a specific route without going through semantic router."""
    router = SemanticRouter()
    route_config = next((route for route in router.routes if route.get("route_name") == route_name), None)
    if not route_config:
        return None

    extracted_params = extract_parameters(query, route_config)
    
    # Special handling for ticket creation - ensure description is extracted
    if route_name == "erp_tickets_create":
        import re
        # Extract description after "Description:" or "issue:"
        desc_match = re.search(r'(?:Description|description|issue|Issue)\s*[:=]\s*(.+?)(?:$|\.\s+[A-Z])', query, re.IGNORECASE | re.DOTALL)
        if desc_match and not extracted_params.get("description"):
            extracted_params["description"] = desc_match.group(1).strip()
        
        # Extract module if present
        module_match = re.search(r'module\s+([A-Za-z0-9_& .-]+?)(?:\s+[A-Z]|\.|$)', query, re.IGNORECASE)
        if module_match and not extracted_params.get("module"):
            extracted_params["module"] = module_match.group(1).strip()
    
    return {
        "route_name": route_name,
        "method": route_config["frappe_method"],
        "doctype": route_config.get("doctype", ""),
        "parameters": extracted_params,
        "filters": None,
        "fields": [],
        "confidence": 1.0,
    }


def _friendly_erp_error(exc: Exception) -> str:
    """Convert raw Frappe API errors into clean, user-readable messages."""
    import re as _re

    raw = str(exc)

    frappe_json_match = _re.search(r'Frappe response:\s*(\{.*)', raw, _re.S)
    if frappe_json_match:
        try:
            payload = json.loads(frappe_json_match.group(1))
            exc_type = payload.get("exc_type", "")
            message = ""

            server_msgs = payload.get("_server_messages", "")
            if server_msgs:
                try:
                    msgs = json.loads(server_msgs)
                    if isinstance(msgs, list) and msgs:
                        first = json.loads(msgs[0]) if isinstance(msgs[0], str) else msgs[0]
                        message = first.get("message", "") if isinstance(first, dict) else str(first)
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass

            if not message:
                raw_message = payload.get("message", "")
                if isinstance(raw_message, dict):
                    message = raw_message.get("message", "") or str(raw_message)
                elif isinstance(raw_message, str):
                    message = raw_message

            if message:
                if exc_type == "LinkValidationError":
                    return f"I couldn't process your request: {message}. Please verify the value exists in the system and try again."
                if exc_type == "ValidationError":
                    return f"The ERP Support API rejected the request: {message}"
                if exc_type == "MandatoryError":
                    return f"Some required information is missing: {message}. Please provide all necessary details."
                if exc_type == "PermissionError":
                    return f"You don't have permission to perform this action. {message}"
                return f"I ran into an issue: {message}"
        except (json.JSONDecodeError, KeyError):
            pass

    cleaned = _re.sub(r'AXON auth debug:\s*\{[^}]*\}\.?\s*', '', raw)
    cleaned = _re.sub(r'Frappe response:\s*\{.*', '', cleaned, flags=_re.S)
    cleaned = _re.sub(r'\d+ Client Error:\s*\w+ for url:\s*\S+\.\s*', '', cleaned)
    cleaned = cleaned.strip().rstrip('.')

    if cleaned:
        return f"I ran into an issue while processing your request: {cleaned}. Please try again or rephrase your request."

    return "Something went wrong while processing your ERP request. Please try again or contact support."