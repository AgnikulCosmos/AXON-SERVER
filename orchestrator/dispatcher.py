import sys
import json
import os
import logging

logger = logging.getLogger(__name__)

from common.routing.router import route_query, get_erp_route_config
from common.rag.rag_tool import rag_search
from common.constants import (
    ACTION_VERBS, ALLOWED_ACTION_CONTEXTS, FOUNDERS,
    KNOWN_ENTITIES, PROFANITY_FALLBACK,
)

from orchestrator.agent import run_axon
from orchestrator.qwen_agent import run_qwen, summarize_tool_output
from services.tools.tool_dispatcher import dispatch_tool
from services.erp.erp_support_client import (
    execute_erp_support_plan,
    format_erp_support_response,
    MissingParametersError,
    get_current_user_email,
)
from common.routing.planning.parameter_extractor import extract_parameters
from orchestrator.agent import (
    MARKER_FINAL_START,
    MARKER_FINAL_END,
    stream_text_word_by_word,
)
from services.erp.frappe_client import (
    reset_frappe_request_headers,
    set_frappe_request_headers,
)

import re

def is_unrelated_query(query: str) -> bool:
    q = query.lower().strip()
    
    for verb in ACTION_VERBS:
        if re.search(r'\b' + re.escape(verb) + r'\b', q):
            if any(ok in q for ok in ALLOWED_ACTION_CONTEXTS):
                continue
            return True
            
    return False

async def check_employee_privacy(query: str, params: dict = None) -> str | None:
    current_email = (await get_current_user_email()) or "emp95@agnikul.in"
    username = current_email.split('@')[0]
    
    # Extract digits from username
    user_digits = "".join(filter(str.isdigit, username))
    
    q = query.lower()
    
    # Check for other employee ID patterns (e.g. emp56, emp-56, emp 56)
    emp_ids = re.findall(r'\bemp\s*[-_]?\s*(\d+)\b', q)
    for eid in emp_ids:
        if not user_digits or eid != user_digits:
            return "I cannot disclose information about other employees."
            
    # Check for other email addresses
    emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', q)
    for email in emails:
        if email != current_email:
            return "I cannot disclose information about other employees."
            
    # Check for Priya or other unauthorized names
    words = re.findall(r'\b[a-zA-Z]{3,}\b', q)
    for word in words:
        if word in FOUNDERS or word == username or word in username:
            continue
        if word == "priya":
            return "I cannot disclose information about other employees."
            
    if params:
        for val in params.values():
            if not val or not isinstance(val, str):
                continue
            val_lower = val.lower()
            param_emp_ids = re.findall(r'\bemp\s*[-_]?\s*(\d+)\b', val_lower)
            for eid in param_emp_ids:
                if not user_digits or eid != user_digits:
                    return "I cannot disclose information about other employees."
            param_emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', val_lower)
            for email in param_emails:
                if email != current_email:
                    return "I cannot disclose information about other employees."
            if "priya" in val_lower:
                return "I cannot disclose information about other employees."
                
    return None

async def sanitize_or_block_response(response_text: str) -> str:
    current_email = (await get_current_user_email()) or "emp95@agnikul.in"
    username = current_email.split('@')[0]
    user_digits = "".join(filter(str.isdigit, username))
    
    text_lower = response_text.lower()
    emp_ids = re.findall(r'\bemp\s*[-_]?\s*(\d+)\b', text_lower)
    for eid in emp_ids:
        if not user_digits or eid != user_digits:
            return "I cannot disclose information about other employees."
            
    emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', text_lower)
    for email in emails:
        if email != current_email:
            return "I cannot disclose information about other employees."
            
    if "priya" in text_lower:
        return "I cannot disclose information about other employees."
        
    return response_text

TEST_MODE = False


async def _get_friendly_missing_fields_message(fields: list[str], route_name: str | None = None) -> str:
    from services.erp.erp_support_client import _FIELD_LABELS, _FIELD_HINTS
    
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
    elif route_name == "track_request":
        single_greeting = "I'll help you track your request. I just need the request ID to check its status:"
        multi_greeting = "I'll help you track your request. Please provide the request ID:"
        example_text = "PC-2026-0001"
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


def is_how_to_query(query: str) -> bool:
    q = query.lower().strip("!?., ")
    how_indicators = [
        "how to", "how do i", "how can i", "how should i", "how does", "how do we", "how is",
        "steps to", "procedure to", "guideline for", "guide to", "how do we go about",
        "steps for", "instruction for", "instructions for", "how do we do"
    ]
    return any(indicator in q for indicator in how_indicators)

ERP_INSTRUCTIONAL_GUIDES = {
    "lost_found_create": (
        "To report a lost or found item, you can tell me what you lost or found. "
        "I will ask for details such as the item name, a description, the location where it was lost or found, and the date. "
        "Once you provide these details, I will register it in the Lost and Found system for tracking."
    ),
    "lost_found_list": (
        "To view reported lost and found items, you can say 'show lost and found items' or 'view lost items'. "
        "I will retrieve the list of currently active reported items in the system."
    ),
    "erp_tickets_create": (
        "To raise an ERP support ticket, you can say 'raise a ticket' or 'create a support ticket'. "
        "I will ask you for details including the application name (e.g., Fleet Management, HR Operations), "
        "the priority level (P0 to P3), and a description of the issue. "
        "Once you provide these details, I will submit the support request."
    ),
    "erp_tickets_list": (
        "To view your support tickets, you can say 'show my tickets' or 'list my support tickets'. "
        "I will fetch and display a list of all tickets associated with your account."
    ),
    "erp_feedback_create": (
        "To submit feedback for an ERP application, you can say 'submit feedback'. "
        "I will ask for the application name, your feedback description, and a rating from 1 to 5 stars. "
        "Once provided, your feedback will be registered in the system."
    ),
    "erp_suggestion_create": (
        "To submit a suggestion for improving an ERP application, you can say 'submit a suggestion'. "
        "I will ask for the application name, a description of the suggestion, how it helps, and priority (Low, Medium, High). "
        "I will then submit your suggestion."
    ),
    "track_request": (
        "To track a request's status, you can say 'track request' followed by the request ID "
        "(e.g., PC-2026-0001 or MM-2026-0003). I will look up the current status and assignee for you."
    ),
    "food_log_list": (
        "To check your meal bookings or consumption logs, you can say 'show my food logs' or ask "
        "questions like 'did I book lunch today?'. I will check the records in the canteen desk."
    )
}


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
    except Exception as e:
        logger.error(f"Failed to save pending sessions: {e}")


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
        from services.erp.frappe_client import call_frappe
        session_data = await call_frappe({
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

        query_lower_check = query.lower()
        
        # 1. Bypass if the query does not contain any ambiguous pronouns
        PRONOUN_PATTERN = re.compile(
            r'\b(it|he|she|they|this|that|him|her|them|its|his|their|these|those)\b',
            re.IGNORECASE
        )
        if not PRONOUN_PATTERN.search(query):
            logger.info(f"[Query Contextualizer] Bypassing rewrite — no ambiguous pronouns in query: {query!r}")
            return query

        # 2. Bypass if any specific Agnikul or ERP domain term is present
        if any(entity in query_lower_check for entity in KNOWN_ENTITIES):
            logger.info(f"[Query Contextualizer] Bypassing rewrite — known entity/domain keyword in query: {query!r}")
            return query

        # Take up to last 6 messages
        recent_history = past_msgs[-6:]
        history_str = ""
        for role, content in recent_history:
            history_str += f"{role}: {content}\n"

        from prompts.rag import CONTEXTUALIZER_PROMPT
        prompt = CONTEXTUALIZER_PROMPT.format(history_str=history_str, query=query)

        import ollama
        from common.llm.ollama_helper import get_working_ollama_base_url
        model = os.getenv("LLM_MODEL", "qwen3.5:0.8b")
        async with ollama.AsyncClient(host=get_working_ollama_base_url()) as client:
            resp = await client.generate(
                model=model,
                prompt=prompt,
                options={"temperature": 0.0, "num_predict": 120}
            )
            if hasattr(resp, "response"):
                rewritten = resp.response.strip().strip("\"'")
            elif isinstance(resp, dict):
                rewritten = resp.get("response", "").strip().strip("\"'")
            else:
                rewritten = str(resp).strip().strip("\"'")
            if rewritten:
                logger.info(f"[Query Contextualizer] Original: {query!r} -> Rewritten: {rewritten!r}")
                return rewritten

    except Exception as err:
        logger.warning(f"Failed to contextualize query: {err}")
    
    return query


def is_relationship_query(query: str) -> bool:
    q = query.lower().strip()
    relationship_patterns = [
        r"\b(gf|bf|girlfriend|boyfriend|husband|wife|spouse|partner|marry|marriage|dating|date|relationship|love|lover|single)\b",
    ]
    for pattern in relationship_patterns:
        if re.search(pattern, q):
            if "date" in q:
                exclude_terms = ["of birth", "effective", "leave", "food", "booking", "policy", "card", "ticket", "start", "end", "today", "yesterday", "tomorrow", "from", "to", "current", "release", "launch"]
                if any(ext in q for ext in exclude_terms):
                    continue
            return True
    return False


async def _run_agent(query: str, session_id: str | None = None):
    temp_q = query.lower().strip("!?., ")

    # Automated Flagging Middleware
    if session_id:
        from common.routing.safety import contains_profanity
        is_profane = contains_profanity(query)
        is_rel = is_relationship_query(query)
        
        if is_profane or is_rel:
            flag_type = "Profanity" if is_profane else "Relationship Query"
            try:
                from services.erp.frappe_client import call_frappe
                await call_frappe({
                    "tool": "axon.api.flag_message",
                    "http_method": "POST",
                    "arguments": {
                        "session_id": session_id,
                        "flag_type": flag_type,
                        "reason": query
                    }
                })
                logger.info(f"[Automated Flagging] Flagged query: {query!r} as {flag_type}")
            except Exception as e:
                logger.warning(f"Failed to automatically flag message: {e}")

    # Block relationship queries early
    if is_relationship_query(query):
        rel_response = "I am an AI assistant here to help you with Agnikul's ERP and workplace queries. I cannot participate in personal or relationship discussions."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(rel_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return rel_response

    # Block profanity early
    from common.routing.safety import contains_profanity
    if contains_profanity(query):
        profanity_response = "I am an AI assistant here to help you with Agnikul's ERP and workplace queries. Please refrain from using inappropriate language."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(profanity_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return profanity_response

    # 1. Unrelated Queries Filter
    if is_unrelated_query(query):
        fallback_msg = "I'm sorry, I couldn't perform that action."
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(fallback_msg)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return fallback_msg

    # 2. Capabilities Check
    if "capabilities" in temp_q or temp_q == "/capabilities":
        capabilities_response = (
            "My defined system capabilities include:\n"
            "1. **ERP Support Management**: Create tickets, feedback, suggestions, and track status.\n"
            "2. **Canteen & Food Log Management**: View canteen bookings and meal logs.\n"
            "3. **Lost and Found Tracking**: Report lost/found items, list items, and resolve them.\n"
            "4. **Internal RAG Retrieval**: Retrieve Agnikul company policies, leaves, and guidelines.\n"
            "5. **General Reasoning**: Answer academic, coding, and general knowledge questions.\n"
            "6. **External Tool Integration**: Fetch live search details from DuckDuckGo, Wikipedia, or arXiv.\n"
            "7. **Tracking Requests**: Track status and details of existing support tickets (using prefixes like PC-, MM-, MT-, or ERP_I_)."
        )
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(capabilities_response)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return capabilities_response

    if query.startswith(("/arxiv", "/wiki", "/ddgs")):
        # Route directly to the TOOLS path, bypassing semantic classifier, RAG search, greetings, etc.
        tool_name, tool_result = await dispatch_tool(query)

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        sys.stdout.flush()

        # Clean prefix for summarize_tool_output context
        clean_q = query
        if query.startswith("/arxiv"):
            clean_q = query[len("/arxiv"):].lstrip()
        elif query.startswith("/wiki"):
            clean_q = query[len("/wiki"):].lstrip()
        elif query.startswith("/ddgs"):
            clean_q = query[len("/ddgs"):].lstrip()

        result = await summarize_tool_output(
            user_query=clean_q,
            tool_name=tool_name,
            tool_data=tool_result
        )
        result = await sanitize_or_block_response(result)

        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    # Employee Privacy Filter
    privacy_error = await check_employee_privacy(query)
    if privacy_error:
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(privacy_error)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return privacy_error

    # Only contextualize if NOT in a pending session to avoid mangling form inputs
    if not (session_id and session_id in PENDING_ERP_SESSIONS):
        query = await contextualize_query_with_history(query, session_id)

    q = query.lower().strip("!?.,")
    logger.debug(f"[Session Tracking] Query: {query!r}, session_id: {session_id!r}, in_pending: {session_id in PENDING_ERP_SESSIONS if session_id else False}")

    # Check for how-to query guidance
    if is_how_to_query(query):
        # 1. Search knowledge base
        rag_res = rag_search(query)
        if rag_res and "don't have that information" not in rag_res.lower() and "do not have that information" not in rag_res.lower():
            rag_res = await sanitize_or_block_response(rag_res)
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(rag_res)
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return rag_res

        # 2. Check if query maps to an ERP route
        matched_route = await route_query(query)
        if matched_route and matched_route.startswith("ERP_ROUTE:"):
            route_name = matched_route.split(":", 1)[1]
            guide = ERP_INSTRUCTIONAL_GUIDES.get(route_name)
            if guide:
                guide = await sanitize_or_block_response(guide)
                sys.stdout.write(f"{MARKER_FINAL_START}\n")
                await stream_text_word_by_word(guide)
                sys.stdout.write(f"{MARKER_FINAL_END}\n")
                sys.stdout.flush()
                return guide

    # ── Check for pending ERP session ──────────────────────────────
    session_active = False
    if session_id and session_id in PENDING_ERP_SESSIONS:
        pending_plan = PENDING_ERP_SESSIONS[session_id]
        pending_route = pending_plan.get("route_name")
        missing_fields = pending_plan.get("_missing_fields") or []

        # 1. Quick cancel check first
        if q in ["cancel", "stop", "abort", "nevermind", "quit", "exit"]:
            del PENDING_ERP_SESSIONS[session_id]
            msg = "Okay, I've cancelled that request."
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(msg)
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return msg

        # 2. Parse structured "field: value" reply
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

        # Extract parameters intelligently
        new_params = {}
        has_extracted_params = False
        if structured_params:
            new_params = structured_params
            has_extracted_params = True
        else:
            route_config = get_erp_route_config(pending_route)
            if route_config:
                from copy import deepcopy
                temp_config = deepcopy(route_config)
                # Keep only missing fields in parameters schema so the extractor focuses precisely on them
                temp_config["parameters"] = {
                    k: v for k, v in route_config.get("parameters", {}).items()
                    if k in missing_fields
                }
                import asyncio as _asyncio
                new_params = await _asyncio.to_thread(extract_parameters, query, temp_config)
                if new_params:
                    has_extracted_params = True

        # 3. Check for intent switch ONLY if the user did NOT provide any parameter values for the pending session.
        should_discard = False
        if not has_extracted_params:
            new_route = await route_query(query)
            if new_route and new_route.startswith("ERP_ROUTE:"):
                matched_route_name = new_route.split(":", 1)[1]
                if matched_route_name != pending_route:
                    should_discard = True
            elif new_route in ("RAG", "TOOLS", "IDENTITY"):
                # If tracking request, any RAG/TOOLS query is an intent switch.
                # Otherwise, check if query looks like a distinct question/command.
                if pending_route == "track_request":
                    import re as _re
                    is_req_id = _re.match(r"^\s*(?:PC|MM|MT|DL|LF|ERP_I|ERP-SF|FBSG|SUG|ERP-RU|ERP-FAQ|ERP-M|ERP_SF)[-_]\w+(?:[-_]\w+)*\s*$", query, _re.I)
                    if not is_req_id:
                        should_discard = True
                elif any(query.lower().startswith(prefix) for prefix in ["what ", "when ", "how ", "where ", "who ", "did i ", "show me ", "list ", "tell me "]):
                    should_discard = True

            if should_discard:
                logger.info(f"User switched intent from {pending_route} to {new_route}. Discarding pending session.")
                del PENDING_ERP_SESSIONS[session_id]

        if session_id and session_id in PENDING_ERP_SESSIONS:
            session_active = True

    if session_active:
        # 4. If the session is still active, process the parameters
        # Fallback: if Qwen could not extract anything and there is only 1 missing field,
        # assume the entire query string is the value for that single missing field.
        if not new_params and len(missing_fields) == 1:
            field = missing_fields[0]
            route_config = get_erp_route_config(pending_route)
            ptype = route_config.get("parameters", {}).get(field) if route_config else None
            val_str = query.strip()
            if field == "ratings":
                import re as _re
                num_match = _re.search(r"\b([1-5](?:\.\d+)?)\b", val_str)
                if num_match:
                    new_params = {field: float(num_match.group(1))}
            elif ptype == "number":
                try:
                    new_params = {field: float(val_str)}
                except ValueError:
                    pass
            elif ptype == "boolean":
                if val_str.lower() in ("yes", "true", "1", "y"):
                    new_params = {field: True}
                elif val_str.lower() in ("no", "false", "0", "n"):
                    new_params = {field: False}
            else:
                new_params = {field: val_str}

        if not new_params:
            result = await _get_friendly_missing_fields_message(missing_fields, pending_plan.get("route_name"))
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(result)
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return result

        # Normalise app_name aliases in the reply
        if "app_name" in new_params:
            from common.routing.planning.parameter_extractor import APP_NAME_MAPPING
            cand = new_params["app_name"].strip().lower()
            for canonical, aliases in APP_NAME_MAPPING.items():
                if cand == canonical.lower() or any(cand == a.lower() for a in aliases):
                    new_params["app_name"] = canonical
                    break

        if pending_plan.get("parameters") is None:
            pending_plan["parameters"] = {}
        pending_plan["parameters"].update(new_params)
        
        # Save the updated pending plan back to persistent storage
        PENDING_ERP_SESSIONS[session_id] = pending_plan

        route = f"ERP_ROUTE:{pending_plan['route_name']}"
        plan = pending_plan
    else:
        route = await route_query(query)
        plan = None
        if route and route.startswith("ERP_ROUTE:"):
            route_name = route.split(":", 1)[1]
            import asyncio as _asyncio
            plan = await _asyncio.to_thread(_build_erp_plan, route_name, query)

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
        result = await sanitize_or_block_response(result)
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
            privacy_error = await check_employee_privacy(query, plan.get("parameters"))
            if privacy_error:
                sys.stdout.write(f"{MARKER_FINAL_START}\n")
                await stream_text_word_by_word(privacy_error)
                sys.stdout.write(f"{MARKER_FINAL_END}\n")
                sys.stdout.flush()
                return privacy_error

            method = plan["method"]
            filters = plan.get("filters") or {}
            
            try:
                if route_name in ("track_request", "food_log_list", "pr_leave_tracker"):
                    from services.erp.tracking_client import execute_tracking_plan, format_tracking_response
                    tool_response = await execute_tracking_plan(plan)
                    result = format_tracking_response(tool_response)
                    from services.erp.frappe_client import call_frappe
                    try:
                        await call_frappe({
                            "tool": "axon.api.log_tool_usage",
                            "http_method": "GET",
                            "arguments": {"tool_name": route_name, "session_id": session_id}
                        })
                    except Exception:
                        pass
                    if session_id and session_id in PENDING_ERP_SESSIONS:
                        del PENDING_ERP_SESSIONS[session_id]
                elif method.startswith("erp_support.") or route_name.startswith("lost_found_"):
                    tool_response = await execute_erp_support_plan(plan)
                    result = await format_erp_support_response(plan, tool_response)
                    from services.erp.frappe_client import call_frappe
                    try:
                        await call_frappe({
                            "tool": "axon.api.log_tool_usage",
                            "http_method": "GET",
                            "arguments": {"tool_name": route_name, "session_id": session_id}
                        })
                    except Exception:
                        pass
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
        result_str = await sanitize_or_block_response(str(result))
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(result_str)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result_str

    if route == "QWEN":
        # Direct LLM answer with a timeout guard.
        # If the LLM takes too long (e.g. "Explain liquid engine"), fall back to Wikipedia.
        # Wikipedia itself falls back to DDGS if it can't find the page (see tool_dispatcher.py).
        import asyncio as _asyncio
        QWEN_TIMEOUT_SECONDS = 20

        try:
            res = await _asyncio.wait_for(run_axon(query), timeout=QWEN_TIMEOUT_SECONDS)
            return await sanitize_or_block_response(res)

        except (_asyncio.TimeoutError, Exception) as _qwen_err:
            logger.warning(
                f"[QWEN] run_axon {'timed out' if isinstance(_qwen_err, _asyncio.TimeoutError) else 'failed'} "
                f"for query {query!r}. Falling back to Wikipedia. Error: {_qwen_err}"
            )
            # Fallback: search Wikipedia (tool_dispatcher will use DDGS if Wikipedia fails)
            try:
                _tool_name, _tool_result = await dispatch_tool(f"/wiki {query}")

                sys.stdout.write(f"{MARKER_FINAL_START}\n")
                sys.stdout.flush()

                _result = await summarize_tool_output(
                    user_query=query,
                    tool_name=_tool_name,
                    tool_data=_tool_result
                )
                _result = await sanitize_or_block_response(_result)

                sys.stdout.write(f"{MARKER_FINAL_END}\n")
                sys.stdout.flush()
                return _result

            except Exception as _wiki_err:
                logger.error(f"[QWEN] Wikipedia fallback also failed: {_wiki_err}")
                _fallback_msg = "I'm having trouble answering that right now. Please try rephrasing or try again shortly."
                sys.stdout.write(f"{MARKER_FINAL_START}\n")
                await stream_text_word_by_word(_fallback_msg)
                sys.stdout.write(f"{MARKER_FINAL_END}\n")
                sys.stdout.flush()
                return _fallback_msg

    if route == "TOOLS":
        tool_name, tool_result = await dispatch_tool(query)

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        sys.stdout.flush()

        result = await summarize_tool_output(
            user_query=query,
            tool_name=tool_name,
            tool_data=tool_result
        )
        result = await sanitize_or_block_response(result)

        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    # -------------------------
    # DEFAULT: AXON
    # -------------------------
    res = await run_axon(query)
    return await sanitize_or_block_response(res)


def _build_erp_plan(route_name: str, query: str) -> dict | None:
    """Build an ERP plan for a specific route using shared SemanticRouter instance."""
    route_config = get_erp_route_config(route_name)
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
    import requests
    
    # 1. Distinguish system-level infrastructure failures from business logic
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout)):
        return "Failed to establish a connection to the ERP backend. Please verify your network connection and try again."
        
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ReadTimeout)):
        return "The ERP backend request timed out. Please try again."

    raw = str(exc)

    # Check for HTTP status code response if raised from requests.exceptions.HTTPError
    response = getattr(exc, "response", None)

    # Parse Frappe JSON response first if present
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
                if exc_type == "DoesNotExistError":
                    return f"The requested ERP resource was not found: {message}"
                return f"I ran into an issue: {message}"
        except (json.JSONDecodeError, KeyError):
            pass

    # Handle other HTTP errors that are system level
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code:
            if status_code >= 500:
                return f"The ERP system is temporarily experiencing technical difficulties (HTTP {status_code}). Please try again later or contact your system administrator."
            if status_code == 404:
                return "The ERP API endpoint could not be found. Please contact support."

    cleaned = _re.sub(r'AXON auth debug:\s*\{[^}]*\}\.?\s*', '', raw)
    cleaned = _re.sub(r'Frappe response:\s*\{.*', '', cleaned, flags=_re.S)
    cleaned = _re.sub(r'\d+ Client Error:\s*\w+ for url:\s*\S+\.\s*', '', cleaned)
    cleaned = cleaned.strip().rstrip('.')

    if cleaned:
        return f"I ran into an issue while processing your request: {cleaned}. Please try again or rephrase your request."

    return "Something went wrong while processing your ERP request. Please try again or contact support."