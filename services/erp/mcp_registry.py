from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from services.erp.frappe_client import call_frappe


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    method: str
    http_method: str
    handler: Callable[..., Awaitable[dict]]


async def _call(method: str, http_method: str, arguments: dict) -> dict:
    return await call_frappe({
        "tool": method,
        "http_method": http_method,
        "arguments": arguments,
    })


async def create_erp_ticket(**kwargs: Any) -> dict:
    app_name = kwargs.get("app_name")
    if app_name:
        kwargs["app_name"] = app_name
    return await _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "ticket"},
    )


async def assign_ticket_developers(ticket_name: str, fe_dev: str = "", be_dev: str = "") -> dict:
    """
    Append initial Frontend/Backend developer Responses rows to a freshly created
    ERP ticket so that the developers can see it in their ERP UI.
    Uses frappe.client.get + frappe.client.save to merge without touching other fields.
    Non-critical — errors are swallowed by the caller.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not ticket_name or not (fe_dev or be_dev):
        return {}

    try:
        # Fetch the current doc (needed for frappe.client.save)
        doc_resp = await _call(
            "frappe.client.get",
            "GET",
            {"doctype": "ERP_Tickets", "name": ticket_name},
        )
        doc = doc_resp.get("message") if isinstance(doc_resp, dict) else None
        if not isinstance(doc, dict):
            logger.warning("assign_ticket_developers: could not fetch ticket %s", ticket_name)
            return {}

        # Build new Responses rows
        existing = doc.get("responses") or []
        if fe_dev:
            existing.append({
                "doctype": "Responses",
                "email": fe_dev,
                "role": "Frontend Developer",
                "action": "Pending",
                "version": "V1.00",
            })
        if be_dev:
            existing.append({
                "doctype": "Responses",
                "email": be_dev,
                "role": "Backend Developer",
                "action": "Pending",
                "version": "V1.00",
            })
        doc["responses"] = existing

        return await _call(
            "frappe.client.save",
            "POST",
            {"doc": doc},
        )
    except Exception as exc:
        logger.warning("assign_ticket_developers failed (non-critical): %s", exc)
        return {}


async def create_erp_feedback(**kwargs: Any) -> dict:
    return await _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "fb_sg", "name": None, "type": "Feedback"},
    )


async def create_erp_suggestion(**kwargs: Any) -> dict:
    return await _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "fb_sg", "name": None, "type": "Suggestion"},
    )


async def view_erp_support_details(docname: str) -> dict:
    await _assert_record_visible(docname)
    return await _call(
        "erp_support.get_api.view_details",
        "GET",
        {"docname": docname},
    )


async def view_packaging_details(docname: str) -> dict:
    return await _call(
        "packaging_management.get_api.view_details",
        "GET",
        {"docname": docname},
    )


async def view_maintenance_details(docname: str) -> dict:
    return await _call(
        "maintenance_management.get_api.view_details",
        "GET",
        {"docname": docname},
    )


async def get_food_log(
    from_date: str,
    to_date: str,
    request_type: str = "Self",
    location: str = "All",
    meal_type: str = "All",
) -> dict:
    return await _call(
        "food.api.log.food_log",
        "GET",
        {
            "from_date": from_date,
            "to_date": to_date,
            "request_type": request_type,
            "location": location,
            "meal_type": meal_type,
        },
    )


async def get_pr_leave_tracker_mcp(**kwargs: Any) -> dict:
    return await _call(
        "payroll_management.v2.leaves.get_balance",
        "POST",
        kwargs,
    )


async def list_erp_tickets(
    from_date: str | None = None,
    to_date: str | None = None,
    start: int = 0,
    limit: int = 20,
    query: str | None = None,
) -> dict:
    args = {
        "from_date": from_date,
        "to_date": to_date,
        "start": start,
        "limit": limit,
        "query": query,
    }
    return await _call(
        "erp_support.get_api.get_tickets",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


async def list_erp_apps(
    start: int = 0,
    limit: int = 100,
    query: str | None = None,
) -> dict:
    args = {
        "start": start,
        "limit": limit,
        "query": query,
    }
    return await _call(
        "erp_support.get_api.get_apps",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


async def create_lost_found(**kwargs: Any) -> dict:
    return await _call(
        "axon.api.create_lost_found",
        "POST",
        {**kwargs},
    )


async def list_lost_found(
    from_date: str | None = None,
    to_date: str | None = None,
    start: int = 0,
    limit: int = 20,
    query: str | None = None,
) -> dict:
    args = {
        "key": "lf_list",
        "from_date": from_date,
        "to_date": to_date,
        "start": start,
        "limit": limit,
        "query": query,
    }
    return await _call(
        "core.factory.api.get_data",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


async def list_erp_feedback(
    from_date: str | None = None,
    to_date: str | None = None,
    start: int = 0,
    limit: int = 20,
    query: str | None = None,
) -> dict:
    args = {
        "type": "Feedback",
        "from_date": from_date,
        "to_date": to_date,
        "start": start,
        "limit": limit,
        "query": query,
    }
    return await _call(
        "erp_support.get_api.get_fb_sg",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


async def list_erp_suggestions(
    from_date: str | None = None,
    to_date: str | None = None,
    start: int = 0,
    limit: int = 20,
    query: str | None = None,
) -> dict:
    args = {
        "type": "Suggestion",
        "from_date": from_date,
        "to_date": to_date,
        "start": start,
        "limit": limit,
        "query": query,
    }
    return await _call(
        "erp_support.get_api.get_fb_sg",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


MCP_REGISTRY: dict[str, MCPTool] = {
    "erp_tickets_create": MCPTool(
        name="erp_tickets_create",
        description="Create an ERP Support ticket for the logged-in user.",
        method="erp_support.put_api.create",
        http_method="POST",
        handler=create_erp_ticket,
    ),
    "erp_feedback_create": MCPTool(
        name="erp_feedback_create",
        description="Create ERP Support feedback/review for the logged-in user.",
        method="erp_support.put_api.create",
        http_method="POST",
        handler=create_erp_feedback,
    ),
    "erp_suggestion_create": MCPTool(
        name="erp_suggestion_create",
        description="Create an ERP Support suggestion for the logged-in user.",
        method="erp_support.put_api.create",
        http_method="POST",
        handler=create_erp_suggestion,
    ),
    "erp_support_view_details": MCPTool(
        name="erp_support_view_details",
        description="View ERP Support ticket, feedback, or suggestion details.",
        method="erp_support.get_api.view_details",
        http_method="GET",
        handler=view_erp_support_details,
    ),
    "erp_tickets_list": MCPTool(
        name="erp_tickets_list",
        description="List ERP tickets visible to the logged-in user.",
        method="erp_support.get_api.get_tickets",
        http_method="GET",
        handler=list_erp_tickets,
    ),
    "erp_apps_list": MCPTool(
        name="erp_apps_list",
        description="List ERP Support applications.",
        method="erp_support.get_api.get_apps",
        http_method="GET",
        handler=list_erp_apps,
    ),
    "erp_feedback_list": MCPTool(
        name="erp_feedback_list",
        description="List ERP feedback/reviews visible to the logged-in user.",
        method="erp_support.get_api.get_fb_sg",
        http_method="GET",
        handler=list_erp_feedback,
    ),
    "erp_suggestions_list": MCPTool(
        name="erp_suggestions_list",
        description="List ERP suggestions visible to the logged-in user.",
        method="erp_support.get_api.get_fb_sg",
        http_method="GET",
        handler=list_erp_suggestions,
    ),
    "lost_found_create": MCPTool(
        name="lost_found_create",
        description="Report a lost item or update/mark an item as found.",
        method="core.factory.api.post_data",
        http_method="POST",
        handler=create_lost_found,
    ),
    "lost_found_list": MCPTool(
        name="lost_found_list",
        description="List active lost and found records.",
        method="core.factory.api.get_data",
        http_method="GET",
        handler=list_lost_found,
    ),
    "view_packaging_details": MCPTool(
        name="view_packaging_details",
        description="View packaging request details by document name or ID.",
        method="packaging_management.get_api.view_details",
        http_method="GET",
        handler=view_packaging_details,
    ),
    "view_maintenance_details": MCPTool(
        name="view_maintenance_details",
        description="View maintenance request details by document name or ID.",
        method="maintenance_management.get_api.view_details",
        http_method="GET",
        handler=view_maintenance_details,
    ),
    "food_log_list": MCPTool(
        name="food_log_list",
        description="List or view food booking logs/history for a date range.",
        method="food.api.log.food_log",
        http_method="GET",
        handler=get_food_log,
    ),
    "pr_leave_tracker": MCPTool(
        name="pr_leave_tracker",
        description="Check leave tracker or leave balances for the logged-in user.",
        method="payroll_management.v2.leaves.get_balance",
        http_method="POST",
        handler=get_pr_leave_tracker_mcp,
    ),
}

MCP_ALIASES = {
    "erp_ticket_create": "erp_tickets_create",
}


def get_mcp_tool(name: str) -> MCPTool:
    return MCP_REGISTRY[MCP_ALIASES.get(name, name)]


async def _assert_record_visible(docname: str) -> None:
    visible_records = []
    for fetcher in (
        lambda: list_erp_tickets(limit=1000),
        lambda: list_erp_feedback(limit=1000),
        lambda: list_erp_suggestions(limit=1000),
    ):
        response = await fetcher()
        message = response.get("message", response) if isinstance(response, dict) else {}
        if isinstance(message, dict):
            visible_records.extend(_flatten_records(message.get("data")))

    if any(record.get("name") == docname for record in visible_records):
        return

    raise ValueError("I could not find that ERP Support record in the records visible to your account.")


def _flatten_records(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        records = []
        for value in data.values():
            if isinstance(value, list):
                records.extend(item for item in value if isinstance(item, dict))
        return records
    return []
