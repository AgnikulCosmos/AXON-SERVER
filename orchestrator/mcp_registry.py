from dataclasses import dataclass
from typing import Any, Callable

from orchestrator.frappe_client import call_frappe


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    method: str
    http_method: str
    handler: Callable[..., dict]


def _call(method: str, http_method: str, arguments: dict) -> dict:
    return call_frappe({
        "tool": method,
        "http_method": http_method,
        "arguments": arguments,
    })


def create_erp_ticket(**kwargs: Any) -> dict:
    return _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "ticket"},
    )


def create_erp_feedback(**kwargs: Any) -> dict:
    return _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "fb_sg", "name": None, "type": "Feedback"},
    )


def create_erp_suggestion(**kwargs: Any) -> dict:
    return _call(
        "erp_support.put_api.create",
        "POST",
        {**kwargs, "req_type": "fb_sg", "name": None, "type": "Suggestion"},
    )


def view_erp_support_details(docname: str) -> dict:
    _assert_record_visible(docname)
    return _call(
        "erp_support.get_api.view_details",
        "GET",
        {"docname": docname},
    )


def list_erp_tickets(
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
    return _call(
        "erp_support.get_api.get_tickets",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


def list_erp_feedback(
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
    return _call(
        "erp_support.get_api.get_fb_sg",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


def list_erp_suggestions(
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
    return _call(
        "erp_support.get_api.get_fb_sg",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


MCP_REGISTRY: dict[str, MCPTool] = {
    "erp_ticket_create": MCPTool(
        name="erp_ticket_create",
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
        description="List ERP tickets visible to the logged-in user. Employees only receive tickets they raised.",
        method="erp_support.get_api.get_tickets",
        http_method="GET",
        handler=list_erp_tickets,
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
        description="List ERP suggestions visible to the logged-in user. Employees only receive suggestions they raised.",
        method="erp_support.get_api.get_fb_sg",
        http_method="GET",
        handler=list_erp_suggestions,
    ),
}


def get_mcp_tool(name: str) -> MCPTool:
    return MCP_REGISTRY[name]


def _assert_record_visible(docname: str) -> None:
    visible_records = []
    for fetcher in (
        lambda: list_erp_tickets(limit=1000),
        lambda: list_erp_feedback(limit=1000),
        lambda: list_erp_suggestions(limit=1000),
    ):
        response = fetcher()
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
