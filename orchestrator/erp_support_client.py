from datetime import date

from orchestrator.mcp_registry import (
    create_erp_feedback,
    create_erp_suggestion,
    create_erp_ticket,
    list_erp_feedback,
    list_erp_suggestions,
    list_erp_tickets,
    view_erp_support_details,
)


CREATE_METHOD = "erp_support.put_api.create"
VIEW_METHOD = "erp_support.get_api.view_details"


def execute_erp_support_plan(plan: dict) -> dict:
    route_name = plan.get("route_name")
    params = dict(plan.get("parameters") or {})

    if route_name == "erp_support_view_details":
        return view_erp_support_details(**_require(params, ["docname"]))

    if route_name == "erp_tickets_list":
        return list_erp_tickets(**_list_params(params))

    if route_name == "erp_feedback_list":
        return list_erp_feedback(**_list_params(params))

    if route_name == "erp_suggestions_list":
        return list_erp_suggestions(**_list_params(params))

    if route_name == "erp_tickets_create":
        return create_erp_ticket(**_ticket_payload(params))
    elif route_name == "erp_feedback_create":
        return create_erp_feedback(**_feedback_payload(params))
    elif route_name == "erp_suggestion_create":
        return create_erp_suggestion(**_suggestion_payload(params))
    else:
        raise ValueError(f"Unsupported ERP Support route: {route_name}")


def format_erp_support_response(plan: dict, response: dict) -> str:
    data = response.get("message", response) if isinstance(response, dict) else response

    if plan.get("route_name") == "erp_support_view_details":
        if isinstance(data, dict) and data.get("status") == "success":
            details = data.get("data") or {}
        else:
            details = data if isinstance(data, dict) else {}
        return _format_details(details) if details else "I could not find details for that ERP Support record."

    if plan.get("route_name") in {"erp_tickets_list", "erp_feedback_list", "erp_suggestions_list"}:
        return _format_list_response(plan.get("route_name"), data)

    if isinstance(data, dict):
        status = data.get("status")
        name = data.get("name")
        message = data.get("message") or "Request processed."
        if status == "success" and name:
            return f"{message} Reference ID: {name}"
        return message

    return str(data)


def _ticket_payload(params: dict) -> dict:
    payload = _require(params, ["app_name", "priority", "module", "description"])
    payload.update({
        "status": params.get("status") or "Yet To Start",
        "issue_dt": params.get("issue_dt") or date.today().isoformat(),
    })
    _copy_optional(payload, params, ["attachments", "roles"])
    return payload


def _feedback_payload(params: dict) -> dict:
    payload = _require(params, ["app_name", "feedback", "ratings"])
    _copy_optional(payload, params, ["attachments"])
    return payload


def _suggestion_payload(params: dict) -> dict:
    payload = _require(params, ["app_name", "priority", "feedback", "helps"])
    _copy_optional(payload, params, ["attachments"])
    return payload


def _list_params(params: dict) -> dict:
    allowed = {"from_date", "to_date", "start", "limit", "query"}
    cleaned = {key: value for key, value in params.items() if key in allowed and value not in (None, "")}
    cleaned.setdefault("start", 0)
    cleaned.setdefault("limit", 20)
    return cleaned


def _require(params: dict, fields: list[str]) -> dict:
    missing = [field for field in fields if params.get(field) in (None, "")]
    if missing:
        readable = ", ".join(field.replace("_", " ") for field in missing)
        raise ValueError(f"Please provide {readable} to continue.")
    return {field: params[field] for field in fields}


def _copy_optional(payload: dict, params: dict, fields: list[str]) -> None:
    for field in fields:
        if params.get(field) not in (None, ""):
            payload[field] = params[field]


def _format_details(details: dict) -> str:
    fields = [
        ("name", "ID"),
        ("app_name", "App"),
        ("type", "Type"),
        ("priority", "Priority"),
        ("status", "Status"),
        ("module", "Module"),
        ("issue_date", "Issue date"),
        ("raised_by", "Raised by"),
        ("raised_on", "Raised on"),
        ("description", "Description"),
        ("feedback", "Feedback"),
        ("helps", "Helps"),
        ("ratings", "Ratings"),
    ]
    parts = [f"{label}: {details[key]}" for key, label in fields if details.get(key) not in (None, "")]
    return "\n".join(parts)


def _format_list_response(route_name: str, data) -> str:
    if not isinstance(data, dict) or data.get("status") == "error":
        return data.get("message", "I could not fetch ERP Support records.") if isinstance(data, dict) else str(data)

    records = _flatten_records(data.get("data"))
    total = data.get("total", len(records))

    if not records:
        label = {
            "erp_tickets_list": "tickets",
            "erp_feedback_list": "feedback",
            "erp_suggestions_list": "suggestions",
        }.get(route_name, "records")
        return f"No ERP Support {label} found for your account."

    lines = [f"Found {total} record(s). Showing {len(records)}:"]
    for record in records[:10]:
        parts = [
            record.get("name"),
            record.get("app_name"),
            record.get("priority"),
            record.get("status"),
            record.get("creation") or record.get("issue_dt"),
        ]
        summary = " | ".join(str(part) for part in parts if part not in (None, ""))
        description = record.get("description") or record.get("feedback")
        if description:
            summary = f"{summary} - {description}"
        lines.append(summary)
    return "\n".join(lines)


def _flatten_records(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        records: list[dict] = []
        for value in data.values():
            if isinstance(value, list):
                records.extend(item for item in value if isinstance(item, dict))
        return records
    return []
