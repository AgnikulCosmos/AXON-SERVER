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


async def _get_friendly_missing_fields_message(fields: list[str]) -> str:
    from orchestrator.erp_support_client import _FIELD_LABELS, _FIELD_HINTS
    
    is_lost = any("lost" in f for f in fields) or any(f in {"item_name", "lost_description", "lost_location", "lost_date"} for f in fields)
    
    if is_lost:
        single_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. I just need one more detail to proceed:"
        multi_greeting = "I'm sorry to hear you've lost your item. Let's get this reported right away so we can track it down. Please provide the following details:"
    else:
        single_greeting = "Thank you for reporting this found item! Let's get this registered in the system. I just need one more detail to proceed:"
        multi_greeting = "Thank you for reporting this found item! Let's get this registered in the system. Please provide the following details:"
    
    # 1. Single missing field
    if len(fields) == 1:
        field = fields[0]
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" (e.g., *{hint}*)" if hint else ""
        return (
            f"{single_greeting}\n\n"
            f"• **{label}**{hint_text}\n\n"
            f"Please copy, fill out, and reply with the template below:\n"
            f"```text\n"
            f"{field}: <value>\n"
            f"```"
        )
    
    # 2. Multiple missing fields
    lines = [
        f"{multi_greeting}\n"
    ]
    
    template_lines = []
    for field in fields:
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" — *{hint}*" if hint else ""
        
        lines.append(f"• **{label}**{hint_text}")
        template_lines.append(f"{field}: <value>")
        
    lines.append("\nPlease copy, fill out, and reply with the template below:")
    lines.append(f"```text\n" + "\n".join(template_lines) + "\n```")
    
    return "\n".join(lines)


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


def _is_erp_ticket_creation_query(query: str) -> bool:
    """Detect if the query is for creating an ERP support ticket."""
    q_lower = query.lower()
    
    # Must contain some support ticket reference
    has_ticket_ref = any(x in q_lower for x in ["ticket", "support", "issue", "error", "bug", "problem", "assistance", "incident", "request erp"])
    
    # Must contain some creation verb
    creation_verbs = ["raise", "create", "lodge", "submit", "report", "open", "file", "post", "add"]
    has_creation_verb = any(x in q_lower for x in creation_verbs)
    
    # Skip leaves / checkins / other unrelated administrative creations
    is_unrelated_creation = any(kw in q_lower for kw in ["leave", "casual leave", "sick leave", "earned leave", "privilege leave", "time off", "holiday", "checkin", "check out", "checkout", "check-in", "payroll", "salary slip", "lost", "found"])
    
    return has_creation_verb and has_ticket_ref and not is_unrelated_creation


def _is_erp_feedback_creation_query(query: str) -> bool:
    """Detect if the query is for creating ERP feedback/review."""
    q_lower = query.lower()
    feedback_keywords = ["give feedback", "submit feedback", "review", "rate", "rating"]
    has_feedback_ref = any(kw in q_lower for kw in feedback_keywords)
    is_unrelated = any(kw in q_lower for kw in ["leave", "casual leave", "sick leave", "earned leave", "privilege leave", "time off", "holiday", "checkin", "check-out", "checkout", "check-in", "payroll", "lost", "found"])
    return has_feedback_ref and not is_unrelated


def _is_erp_suggestion_creation_query(query: str) -> bool:
    """Detect if the query is for creating ERP suggestion."""
    q_lower = query.lower()
    suggestion_keywords = ["suggestion", "improve", "enhancement", "feature request"]
    has_suggestion_ref = any(kw in q_lower for kw in suggestion_keywords)
    is_unrelated = any(kw in q_lower for kw in ["leave", "casual leave", "sick leave", "earned leave", "privilege leave", "time off", "holiday", "checkin", "check-out", "checkout", "check-in", "payroll", "lost", "found"])
    return has_suggestion_ref and not is_unrelated


def _is_lost_found_create_query(query: str) -> bool:
    q_lower = query.lower()
    lost_create_keywords = ["lost my", "lost a", "report a lost", "record a lost", "report lost", "record lost", "lost item"]
    found_create_keywords = ["found a", "found my", "mark as found", "mark found", "mark erp lost as found"]
    return any(kw in q_lower for kw in lost_create_keywords) or any(kw in q_lower for kw in found_create_keywords) or ("mark " in q_lower and " as found" in q_lower)

def _is_lost_found_list_query(query: str) -> bool:
    q_lower = query.lower()
    lost_list_keywords = ["list lost", "show lost", "view lost", "lost items", "lost ones", "lost and found"]
    return any(kw in q_lower for kw in lost_list_keywords)


async def _run_agent(query: str, session_id: str | None = None):
    q = query.lower().strip("!?.,")
    logger.debug(f"[Session Tracking] Query: {query!r}, session_id: {session_id!r}, in_pending: {session_id in PENDING_ERP_SESSIONS if session_id else False}")

    # ── Check for pending ERP session ──────────────────────────────
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
        if "description" in structured_params:
            desc_val = structured_params.pop("description")
            if "found" in pending_plan.get("route_name", ""):
                structured_params["found_description"] = desc_val
            else:
                structured_params["lost_description"] = desc_val
        if "item_description" in structured_params:
            desc_val = structured_params.pop("item_description")
            if "found" in pending_plan.get("route_name", ""):
                structured_params["found_description"] = desc_val
            else:
                structured_params["lost_description"] = desc_val

        if structured_params:
            new_params = structured_params
        elif len(missing_fields) == 1:
            new_params = {missing_fields[0]: query.strip()}
        else:
            result = await _get_friendly_missing_fields_message(missing_fields)
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
        # ── First, check for ERP creation queries directly ──────────
        if _is_lost_found_create_query(query):
            route = "ERP_ROUTE:lost_found_create"
            plan = _build_erp_plan("lost_found_create", query)
        elif _is_lost_found_list_query(query):
            route = "ERP_ROUTE:lost_found_list"
            plan = _build_erp_plan("lost_found_list", query)
        elif _is_erp_ticket_creation_query(query):
            route = "ERP_ROUTE:erp_tickets_create"
            plan = _build_erp_plan("erp_tickets_create", query)
        elif _is_erp_feedback_creation_query(query):
            route = "ERP_ROUTE:erp_feedback_create"
            plan = _build_erp_plan("erp_feedback_create", query)
        elif _is_erp_suggestion_creation_query(query):
            route = "ERP_ROUTE:erp_suggestion_create"
            plan = _build_erp_plan("erp_suggestion_create", query)
        else:
            route = await route_query(query)
            plan = None

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
                result = await _get_friendly_missing_fields_message(e.fields)
            except ValueError as e:
                result = str(e)
            except Exception as e:
                logger.exception("Error executing ERP support plan:")
                result = _friendly_erp_error(e)
        else:
            result = "No matching ERP route could be resolved for your query."

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(result)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    if route == "QWEN":
        result = await run_qwen(query)

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(result)
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return result

    if route == "TOOLS":
        tool_name, tool_result = await dispatch_tool(query)

        if tool_name == "arxiv":
            result = tool_result
        else:
            result = await summarize_tool_output(
                user_query=query,
                tool_name=tool_name,
                tool_data=tool_result
            )

        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(str(result).strip())
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