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
    # Ensure app_name is properly normalized before sending to Frappe
    app_name = kwargs.get("app_name")
    if app_name:
        # The app_name should already be validated by _require()
        kwargs["app_name"] = app_name
    
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


def list_erp_apps(
    start: int = 0,
    limit: int = 100,
    query: str | None = None,
) -> dict:
    args = {
        "start": start,
        "limit": limit,
        "query": query,
    }
    return _call(
        "erp_support.get_api.get_apps",
        "GET",
        {key: value for key, value in args.items() if value is not None},
    )


def create_lost_found(**kwargs: Any) -> dict:
    return _call(
        "axon.api.create_lost_found",
        "POST",
        {**kwargs},
    )


def list_lost_found(
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
    return _call(
        "core.factory.api.get_data",
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
        description="List ERP tickets visible to the logged-in user. Employees only receive tickets they raised.",
        method="erp_support.get_api.get_tickets",
        http_method="GET",
        handler=list_erp_tickets,
    ),
    "erp_apps_list": MCPTool(
        name="erp_apps_list",
        description="List ERP Support applications that can be used as app_name when creating tickets, feedback, or suggestions.",
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
        description="List ERP suggestions visible to the logged-in user. Employees only receive suggestions they raised.",
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
}

MCP_ALIASES = {
    "erp_ticket_create": "erp_tickets_create",
}


def get_mcp_tool(name: str) -> MCPTool:
    return MCP_REGISTRY[MCP_ALIASES.get(name, name)]


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
