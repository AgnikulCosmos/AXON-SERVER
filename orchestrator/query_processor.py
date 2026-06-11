"""
Comprehensive Query Processor
==============================
Handles all user query types and returns clean, structured responses:
  • ERP Support (tickets, feedback, suggestions, list, view details)
  • Organization questions (QWEN agent)
  • Search (Wiki, DDGS, arXiv)
  • RAG knowledge base
  • Greeting & Identity

Returns a unified dict response with:
  - query_type: 'erp' | 'search' | 'organization' | 'rag' | 'identity'
  - status: 'ok' | 'error' | 'missing'
  - message: user-facing string
  - missing_fields: list (when status=='missing')
"""

import asyncio
import sys
from typing import Any

from common.router import route_query
from common.rag_tool import rag_search
from common.relational_policy import check_relational_policy

from orchestrator.planning import router_pipeline
from orchestrator.erp_support_client import (
    execute_erp_support_plan,
    format_erp_support_response,
    MissingParametersError,
)
from orchestrator.dispatcher import _friendly_erp_error
from orchestrator.frappe_client import set_frappe_request_headers, reset_frappe_request_headers
from orchestrator.qwen_agent import run_qwen, summarize_tool_output
from orchestrator.tool_dispatcher import dispatch_tool


IDENTITY_RESPONSE = "I am Axon, your friendly internal ERP AI Assistant at Agnikul Cosmos! I can help you with internal systems, HR, payroll, operations, organizational structure, and enterprise workflows."
PROFANITY_FALLBACK = "Please use respectful and professional language while interacting with Axon."


async def process_query(
    query: str,
    frappe_headers: dict | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Process any user query and return a structured response.

    Args:
        query: User input string
        frappe_headers: Optional Frappe authentication headers
        session_id: Optional session ID for tracking

    Returns:
        {
            "query_type": "erp" | "search" | "organization" | "rag" | "identity",
            "status": "ok" | "error" | "missing",
            "message": <user-facing string>,
            "missing_fields": <list, only if status=='missing'>,
        }
    """
    q = query.lower().strip("!?.,")

    # ── Relational Policy Check ──────────────────────────────────────────
    policy_response = check_relational_policy(query)
    if policy_response:
        return {"query_type": "identity", "status": "ok", "message": policy_response}

    # ── Identity & Greeting ──────────────────────────────────────────────
    if any(x in q for x in ["who are you", "what is your name", "who is axon", "what can axon help", "what can you do"]):
        return {"query_type": "identity", "status": "ok", "message": IDENTITY_RESPONSE}

    # ── Profanity Check ──────────────────────────────────────────────────
    if any(x in q for x in ["fuck", "bitch", "nigga"]):
        return {"query_type": "error", "status": "error", "message": PROFANITY_FALLBACK}

    # ── Route the query ──────────────────────────────────────────────────
    token = set_frappe_request_headers(frappe_headers)
    try:
        route = await route_query(query)

        # ── ERP Support Route ────────────────────────────────────────────
        if route.startswith("ERP_ROUTE:"):
            return _process_erp_query(query)

        # ── RAG Search Route ─────────────────────────────────────────────
        if route == "RAG":
            result = rag_search(query)
            return {"query_type": "rag", "status": "ok", "message": result}

        # ── Tools Route (Wiki, DDGS, arXiv) ──────────────────────────────
        if route == "TOOLS":
            tool_name, tool_result = await dispatch_tool(query)
            message = await summarize_tool_output(
                user_query=query,
                tool_name=tool_name,
                tool_data=tool_result,
            )
            return {"query_type": "search", "status": "ok", "message": str(message).strip()}

        # ── Organization/QWEN Route ──────────────────────────────────────
        if route == "QWEN":
            result = await run_qwen(query)
            return {"query_type": "organization", "status": "ok", "message": result}

        # ── Default: Organization Q&A ───────────────────────────────────
        result = await run_qwen(query)
        return {"query_type": "organization", "status": "ok", "message": result}

    finally:
        reset_frappe_request_headers(token)


def _process_erp_query(query: str) -> dict[str, Any]:
    """Process an ERP Support query and return structured response."""
    plan = router_pipeline.process(query)
    if not plan or not (
        plan.get("route_name", "").startswith("erp_")
        or plan.get("route_name") in ("food_log_list", "pr_leave_tracker", "lost_found_list", "lost_found_create", "track_request")
    ):
        return {
            "query_type": "erp",
            "status": "error",
            "message": "Could not resolve an ERP Support action from your message.",
        }

    try:
        response = execute_erp_support_plan(plan)
        message = format_erp_support_response(plan, response)
        return {"query_type": "erp", "status": "ok", "message": message}
    except MissingParametersError as e:
        return {
            "query_type": "erp",
            "status": "missing",
            "missing_fields": e.fields,
            "message": str(e),
        }
    except Exception as exc:
        return {
            "query_type": "erp",
            "status": "error",
            "message": _friendly_erp_error(exc),
        }


def process_query_sync(
    query: str,
    frappe_headers: dict | None = None,
) -> dict[str, Any]:
    """
    Synchronous wrapper for process_query.
    Use when async/await is not available.
    """
    # Run async function in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(process_query(query, frappe_headers))
    finally:
        loop.close()
