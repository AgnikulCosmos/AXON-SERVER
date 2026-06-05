from datetime import date
from typing import Optional, Any
import re

from orchestrator.mcp_registry import (
    create_erp_feedback,
    create_erp_suggestion,
    create_erp_ticket,
    list_erp_apps,
    list_erp_feedback,
    list_erp_suggestions,
    list_erp_tickets,
    view_erp_support_details,
)

CREATE_METHOD = "erp_support.put_api.create"
VIEW_METHOD = "erp_support.get_api.view_details"

# Cache for valid app names
_VALID_APP_NAMES_CACHE: Optional[list] = None
_APP_NAME_MAPPING_CACHE: Optional[dict] = None

_FIELD_LABELS = {
    "app_name": "Application Name",
    "priority": "Priority",
    "module": "Module",
    "description": "Description",
    "feedback": "Feedback/Suggestion",
    "ratings": "Rating",
    "helps": "Helps",
    "attachments": "Attachments",
    "roles": "Roles",
    "status": "Status",
    "name": "Record Name",
    "item_name": "Item Name",
    "lost_location": "Lost Location",
    "lost_date": "Lost Date",
    "lost_description": "Lost Description",
    "found_location": "Found Location",
    "found_date": "Found Date",
    "found_description": "Found Description",
    "req_id": "Request ID",
}

_FIELD_HINTS = {
    "app_name": "e.g., Fleet Management, HR Operations",
    "priority": "Low, Medium, or High",
    "module": "e.g., Vehicle Tracking, Leave",
    "description": "A detailed description of the issue",
    "feedback": "Your suggestions or feedback",
    "ratings": "1 to 5 stars",
    "helps": "How this suggestion helps the organization",
    "name": "e.g., LF-26-0526-08242",
    "item_name": "What is the name of the lost item?",
    "lost_location": "Where did you lose the item?",
    "lost_date": "e.g., today, yesterday, or YYYY-MM-DD",
    "lost_description": "A description of the lost item",
    "found_location": "Where did you find the item?",
    "found_date": "e.g., today, yesterday, or YYYY-MM-DD",
    "found_description": "Any comments about finding it",
    "req_id": "e.g., PC-2026-0001, MM-2026-0003, or ERP_I_9876",
}


def _get_valid_app_names() -> list:
    """Fetch valid app names from Frappe with caching."""
    global _VALID_APP_NAMES_CACHE
    
    if _VALID_APP_NAMES_CACHE is not None:
        return _VALID_APP_NAMES_CACHE
        
    try:
        response = list_erp_apps(limit=200)
        data = response.get("message", response) if isinstance(response, dict) else {}
        records = _flatten_records(data.get("data"))
        _VALID_APP_NAMES_CACHE = [str(record.get("name", "")).strip() for record in records if record.get("name")]
        return _VALID_APP_NAMES_CACHE
    except Exception:
        # Fallback to default values (do not cache, so next authenticated call can retry)
        return [
            "core", "erp_support", "fleet_management", "food",
            "hr_operations", "maintenance_management", "packaging_management",
        ]


def _normalize_app_name(user_input: str) -> Optional[str]:
    """
    Find the closest matching valid app name for the user's input.
    Supports partial matching and aliases.
    """
    if not user_input:
        return None
    
    import re
    def clean_str(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', s.lower())

    user_input_clean = clean_str(user_input)
    user_input_lower = user_input.strip().lower()
    valid_names = _get_valid_app_names()
    
    # First, try exact match (case-insensitive, ignoring spaces/punctuation)
    for name in valid_names:
        if clean_str(name) == user_input_clean:
            return name
    
    # Second, try alias mapping from APP_NAME_MAPPING
    from orchestrator.planning.parameter_extractor import APP_NAME_MAPPING
    for canonical, aliases in APP_NAME_MAPPING.items():
        canonical_clean = clean_str(canonical)
        if user_input_clean == canonical_clean:
            for valid in valid_names:
                if clean_str(valid) == canonical_clean:
                    return valid
        for alias in aliases:
            if user_input_clean == clean_str(alias):
                for valid in valid_names:
                    if clean_str(valid) == canonical_clean:
                        return valid
    
    # Third, try partial matching (e.g., "Fleet" matches "Fleet Management")
    for name in valid_names:
        name_clean = clean_str(name)
        if user_input_clean in name_clean or name_clean in user_input_clean:
            return name
    
    return None


def _validate_and_fix_app_name(params: dict, fields: list) -> tuple[dict, list]:
    """
    Validate and fix app_name in params. Returns (fixed_params, missing_fields).
    """
    missing = []
    fixed_params = dict(params)
    
    for field in fields:
        if field == "app_name":
            raw_app_name = params.get("app_name")
            if raw_app_name in (None, ""):
                missing.append(field)
            else:
                normalized = _normalize_app_name(str(raw_app_name))
                if normalized:
                    fixed_params["app_name"] = normalized
                else:
                    # App name not found - add to missing with helpful message
                    missing.append(field)
                    fixed_params["_app_name_error"] = f"'{raw_app_name}' is not a valid application name"
        elif params.get(field) in (None, ""):
            missing.append(field)
    
    return fixed_params, missing


def _require(params: dict, fields: list[str]) -> dict:
    """Require fields, with special handling for app_name validation."""
    # First, validate and fix app_name
    fixed_params, missing = _validate_and_fix_app_name(params, fields)
    
    if missing:
        # Check if app_name error needs special handling
        app_error = fixed_params.get("_app_name_error")
        if app_error and "app_name" in missing:
            # Remove app_name from missing since we have a specific error
            missing.remove("app_name")
            if missing:
                raise MissingParametersError(missing, extra_context=app_error)
            else:
                raise MissingParametersError([], extra_context=app_error)
        
        if missing:
            raise MissingParametersError(missing)
    
    # Return only the required fields
    result = {field: fixed_params[field] for field in fields if field in fixed_params}
    return result


# Update MissingParametersError to support extra context
class MissingParametersError(ValueError):
    def __init__(self, fields: list[str], extra_context: str = None):
        self.fields = fields
        self.extra_context = extra_context
        super().__init__(_missing_fields_message(fields, extra_context))


def _missing_fields_message(fields: list[str], extra_context: str = None) -> str:
    """Generate missing fields message with optional extra context."""
    if extra_context:
        return extra_context
    
    if len(fields) == 1:
        field = fields[0]
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" ({hint})" if hint else ""
        
        # Special handling for app_name
        if field == "app_name":
            valid_names = _get_valid_app_names()
            valid_list = "\n  • " + "\n  • ".join(valid_names[:10])
            if len(valid_names) > 10:
                valid_list += f"\n  • ... and {len(valid_names) - 10} more"
            return (
                f"I need the **application name** to continue. Valid applications are:\n{valid_list}\n\n"
                f"Please reply with: `app_name: <application name>`"
            )
        
        return (
            f"I just need the **{label}** to continue. "
            f"Please reply in this format:\n\n"
            f"`{field}: <value>`{hint_text}"
        )
    
    lines = ["Please provide the following details to continue:\n"]
    for field in fields:
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f"  ← {hint}" if hint else ""
        lines.append(f"`{field}: <value>`  — {label}{hint_text}")
    lines.append("\nReply with all fields filled in, one per line.")
    return "\n".join(lines)


def _resolve_single_date(value) -> str:
    """Resolve a relative date keyword (today, yesterday, tomorrow) or pattern to ISO YYYY-MM-DD."""
    if not value:
        return ""
    val = str(value).strip().lower()
    from datetime import date, timedelta
    today = date.today()
    if val == "today":
        return today.isoformat()
    elif val == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    elif val == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    
    # Try ISO date pattern
    import re
    match = re.search(r"\d{4}-\d{2}-\d{2}", val)
    if match:
        return match.group()
        
    return val


def execute_erp_support_plan(plan: dict) -> dict:
    route_name = plan.get("route_name")
    params = dict(plan.get("parameters") or {})

    if route_name == "lost_found_create":
        from orchestrator.mcp_registry import create_lost_found
        status = params.get("status") or "Pending"
        if status == "Found" or "name" in params:
            payload = _require(params, ["name", "found_location", "found_date", "found_description"])
            payload["found_date"] = _resolve_single_date(payload["found_date"])
            payload.update({
                "status": "Found"
            })
        else:
            payload = _require(params, ["item_name", "lost_location", "lost_date", "lost_description"])
            payload["lost_date"] = _resolve_single_date(payload["lost_date"])
            payload.update({
                "status": "Pending",
                "upload_image": params.get("upload_image") or ""
            })
        return create_lost_found(**payload)

    if route_name == "lost_found_list":
        from orchestrator.mcp_registry import list_lost_found
        return list_lost_found(**_list_params(params))

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

    # Gracefully unwrap nested 'message' if it exists as a dict (common in Frappe whitelist responses)
    if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
        data = data["message"]

    if plan.get("route_name") == "erp_support_view_details":
        if isinstance(data, dict) and data.get("status") == "success":
            details = data.get("data") or {}
        else:
            details = data if isinstance(data, dict) else {}
        return _format_details(details) if details else "I could not find details for that ERP Support record."

    if plan.get("route_name") == "lost_found_list":
        return _format_lost_found_list(data)

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
    issue_dt = params.get("issue_dt")
    if issue_dt:
        issue_dt = _resolve_single_date(issue_dt)
    else:
        issue_dt = date.today().isoformat()
    payload.update({
        "status": params.get("status") or "Yet To Start",
        "issue_dt": issue_dt,
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


def get_current_user_email() -> str:
    try:
        from orchestrator.mcp_registry import _call
        user_info = _call("axon.api.get_user_info", "GET", {})
        message = user_info.get("message") or {}
        return message.get("email") or ""
    except Exception:
        return ""


def _format_lost_found_list(data) -> str:
    if not isinstance(data, dict) or data.get("status") == "error":
        return data.get("message", "I could not fetch Lost & Found records.") if isinstance(data, dict) else str(data)

    records = _flatten_records(data.get("data"))
    
    # Filter to only lost ones (status == "Pending")
    lost_records = [r for r in records if r.get("status") == "Pending"]
    
    if not lost_records:
        return "No pending lost items reported."

    current_user = get_current_user_email()
    
    lines = [f"###  Active Lost Items ({len(lost_records)})"]
    for record in lost_records[:5]:
        name = record.get("name")
        item_name = record.get("item_name")
        location = record.get("lost_location")
        date_str = record.get("lost_date")
        desc = record.get("lost_description") or "No description provided"
        owner = record.get("owner") or ""
        owner_username = owner.split('@')[0]
        
        # List of founders who are allowed to be disclosed:
        founders = {"srinath", "moin", "satyanarayanan", "janardhana", "ravichandran", "spm"}
        
        is_allowed = False
        if owner == current_user:
            is_allowed = True
        elif owner_username in founders:
            is_allowed = True
            
        if is_allowed:
            emp_name = record.get("employee_name") or owner
        else:
            emp_name = "Employee"
        
        card = [
            f"**{item_name}** ({name})",
            f"*Location:* {location} | *Date:* {date_str}",
            f"*Reported by:* {emp_name}",
            f"*Description:* {desc}"
        ]
        
        # Display the mark found button only if the record belongs to the current user
        if owner == current_user:
            card.append(f"[action:mark_found:{name}](action:mark_found:{name})")
            
        lines.append("\n".join(card))
        lines.append("---")
        
    return "\n\n".join(lines)