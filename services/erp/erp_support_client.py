from datetime import date
from typing import Optional, Any
import re

from services.erp.mcp_registry import (
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
    "attachments": "Image/Screenshot",
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
    "app_name": "Fleet Management, HR Operations",
    "priority": "Low, Medium, or High",
    "module": "Vehicle Tracking, Leave",
    "description": "A detailed description of the issue",
    "feedback": "Your suggestions or feedback",
    "ratings": "1 to 5 stars",
    "helps": "How this suggestion helps the organization",
    "attachments": "Upload an image/screenshot showing the issue",
    "name": "LF-26-0526-08242",
    "item_name": "What is the name of the lost item?",
    "lost_location": "Where did you lose the item?",
    "lost_date": "today, yesterday, or YYYY-MM-DD",
    "lost_description": "A description of the lost item",
    "found_location": "Where did you find the item?",
    "found_date": "today, yesterday, or YYYY-MM-DD",
    "found_description": "Any comments about finding it",
    "req_id": "PC-2026-0001, MM-2026-0003, or ERP_I_9876",
}


_VALID_APP_NAMES_FALLBACK = [
    "core", "erp_support", "fleet_management", "food",
    "hr_operations", "maintenance_management", "packaging_management",
]


async def _get_valid_app_names() -> list:
    global _VALID_APP_NAMES_CACHE
    
    if _VALID_APP_NAMES_CACHE is not None:
        return _VALID_APP_NAMES_CACHE
        
    try:
        response = await list_erp_apps(limit=200)
        data = response.get("message", response) if isinstance(response, dict) else {}
        records = _flatten_records(data.get("data"))
        _VALID_APP_NAMES_CACHE = [str(record.get("name", "")).strip() for record in records if record.get("name")]
        return _VALID_APP_NAMES_CACHE
    except Exception:
        return _VALID_APP_NAMES_FALLBACK


def _normalize_app_name(user_input: str, valid_names: list) -> Optional[str]:
    if not user_input:
        return None
    
    import re
    def clean_str(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', s.lower())

    user_input_clean = clean_str(user_input)
    
    for name in valid_names:
        if clean_str(name) == user_input_clean:
            return name
    
    from common.routing.planning.parameter_extractor import APP_NAME_MAPPING
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
    
    for name in valid_names:
        name_clean = clean_str(name)
        if user_input_clean in name_clean or name_clean in user_input_clean:
            return name
    
    return None


async def _validate_and_fix_app_name(params: dict, fields: list) -> tuple[dict, list]:
    missing = []
    fixed_params = dict(params)
    valid_names = await _get_valid_app_names()
    
    for field in fields:
        if field == "app_name":
            raw_app_name = params.get("app_name")
            if raw_app_name in (None, ""):
                missing.append(field)
            else:
                normalized = _normalize_app_name(str(raw_app_name), valid_names)
                if normalized:
                    fixed_params["app_name"] = normalized
                else:
                    missing.append(field)
                    fixed_params["_app_name_error"] = f"**'{raw_app_name}'** is not a recognized ERP application. Please specify one of the valid applications (e.g., *Fleet Management*, *HR Operations*, etc.)."
        elif params.get(field) in (None, ""):
            missing.append(field)
    
    return fixed_params, missing


async def _require(params: dict, fields: list[str]) -> dict:
    fixed_params, missing = await _validate_and_fix_app_name(params, fields)
    
    if missing:
        app_error = fixed_params.get("_app_name_error")
        if app_error:
            raise MissingParametersError(missing, extra_context=app_error)
        raise MissingParametersError(missing)
    
    result = {field: fixed_params[field] for field in fields if field in fixed_params}
    return result


# Update MissingParametersError to support extra context
class MissingParametersError(ValueError):
    def __init__(self, fields: list[str], extra_context: str = None):
        self.fields = fields
        self.extra_context = extra_context
        super().__init__(_missing_fields_message(fields, extra_context))


def _missing_fields_message(fields: list[str], extra_context: str = None) -> str:
    if extra_context:
        return extra_context
    
    if len(fields) == 1:
        field = fields[0]
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        hint = _FIELD_HINTS.get(field, "")
        hint_text = f" ({hint})" if hint else ""
        
        if field == "app_name":
            valid_list = "\n  • " + "\n  • ".join(_VALID_APP_NAMES_FALLBACK)
            return (
                f"I need the **application name** to continue. Valid applications include:\n{valid_list}\n\n"
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


async def execute_erp_support_plan(plan: dict) -> dict:
    route_name = plan.get("route_name")
    params = dict(plan.get("parameters") or {})

    if route_name == "lost_found_create":
        from services.erp.mcp_registry import create_lost_found
        import datetime
        status = params.get("status") or "Pending"
        
        # If 'name' is provided in params, we are updating an existing lost item to 'Found' status.
        if params.get("name"):
            params.setdefault("found_description", "No description provided")
            payload = await _require(params, ["name", "found_location", "found_date", "found_description"])
            payload["found_date"] = _resolve_single_date(payload["found_date"])
            payload.update({"status": "Found"})
        # If 'name' is not provided but status is 'Found', it's a new found item report.
        elif status == "Found":
            params.setdefault("found_description", "No description provided")
            payload = await _require(params, ["item_name", "found_location", "found_date", "found_description"])
            payload["found_date"] = _resolve_single_date(payload["found_date"])
            payload.update({"status": "Found"})
        # Otherwise, it's a new lost item report.
        else:
            params.setdefault("lost_description", "No description provided")
            payload = await _require(params, ["item_name", "lost_location", "lost_date", "lost_description"])
            payload["lost_date"] = _resolve_single_date(payload["lost_date"])
            payload.update({
                "status": "Pending",
                "upload_image": params.get("upload_image") or ""
            })
        return await create_lost_found(**payload)

    if route_name == "lost_found_list":
        from services.erp.mcp_registry import list_lost_found
        return await list_lost_found(**_list_params(params))

    if route_name == "erp_support_view_details":
        return await view_erp_support_details(**(await _require(params, ["docname"])))

    if route_name == "erp_tickets_list":
        return await list_erp_tickets(**_list_params(params))

    if route_name == "erp_feedback_list":
        return await list_erp_feedback(**_list_params(params))

    if route_name == "erp_suggestions_list":
        return await list_erp_suggestions(**_list_params(params))

    if route_name == "erp_tickets_create":
        ticket_payload = await _ticket_payload(params)
        # Store developer info in plan for the confirmation message
        plan["_fe_dev"] = ticket_payload.pop("_fe_dev", "")
        plan["_be_dev"] = ticket_payload.pop("_be_dev", "")
        return await create_erp_ticket(**ticket_payload)
    elif route_name == "erp_feedback_create":
        return await create_erp_feedback(**(await _feedback_payload(params)))
    elif route_name == "erp_suggestion_create":
        return await create_erp_suggestion(**(await _suggestion_payload(params)))
    else:
        raise ValueError(f"Unsupported ERP Support route: {route_name}")


async def format_erp_support_response(plan: dict, response: dict) -> str:
    data = response.get("message", response) if isinstance(response, dict) else response

    if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
        data = data["message"]

    if plan.get("route_name") == "erp_support_view_details":
        if isinstance(data, dict) and data.get("status") == "success":
            details = data.get("data") or {}
        else:
            details = data if isinstance(data, dict) else {}
        return _format_details(details) if details else "I could not find details for that ERP Support record."

    if plan.get("route_name") == "lost_found_list":
        return await _format_lost_found_list(data)

    if plan.get("route_name") in {"erp_tickets_list", "erp_feedback_list", "erp_suggestions_list"}:
        return _format_list_response(plan.get("route_name"), data)

    if isinstance(data, dict):
        status = data.get("status")
        name = data.get("name")
        message = data.get("message") or "Request processed."
        if status == "success" and name:
            # For ticket creation, include assigned developer info
            if plan.get("route_name") == "erp_tickets_create":
                fe_dev = plan.get("_fe_dev", "")
                be_dev = plan.get("_be_dev", "")
                dev_line = ""
                if fe_dev or be_dev:
                    parts = []
                    if fe_dev:
                        parts.append(f"Frontend: {fe_dev}")
                    if be_dev:
                        parts.append(f"Backend: {be_dev}")
                    dev_line = f"\n👤 **Assigned to:** {', '.join(parts)}"
                return f"{message} Reference ID: **{name}**{dev_line}"
            return f"{message} Reference ID: {name}"
        return message

    return str(data)


async def _fetch_app_developers(app_name: str) -> dict:
    """Fetch FE and BE developer emails from ERP_Applications for the given app_name."""
    try:
        response = await list_erp_apps(query=app_name, limit=5)
        data = response.get("message", response) if isinstance(response, dict) else {}
        if isinstance(data, dict):
            records = data.get("data", [])
        else:
            records = []
        for record in records:
            if isinstance(record, dict):
                name_clean = str(record.get("name", "")).lower().strip()
                app_clean = app_name.lower().strip()
                if name_clean == app_clean or app_clean in name_clean or name_clean in app_clean:
                    return {
                        "fe_dev": record.get("fe_dev") or "",
                        "be_dev": record.get("be_dev") or "",
                    }
    except Exception:
        pass
    return {"fe_dev": "", "be_dev": ""}


async def _ticket_payload(params: dict) -> dict:
    payload = await _require(params, ["app_name", "priority", "module", "description", "attachments"])

    # ── Mandatory image attachment ──────────────────────────────────────────
    attachments = params.get("attachments")
    if not attachments or str(attachments).strip() in ("", "None"):
        raise MissingParametersError(
            ["attachments"],
            extra_context=(
                "📎 **An image/screenshot is required to create an ERP support ticket.**\n\n"
                "Please upload a screenshot or image showing the issue. "
                "You can attach it using the upload button, then describe your issue."
            )
        )

    # Validate image attachment file extension (images only)
    import os
    from urllib.parse import urlparse, parse_qs
    allowed_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    files_to_check = []
    
    # Try finding markdown images: ![alt](url) by parsing balanced parentheses
    attachments_str = str(attachments).strip()
    idx = 0
    while True:
        start = attachments_str.find("![", idx)
        if start == -1:
            break
        alt_close = attachments_str.find("]", start)
        if alt_close == -1:
            break
        if alt_close + 1 < len(attachments_str) and attachments_str[alt_close + 1] == "(":
            url_start = alt_close + 2
            paren_count = 1
            url_end = url_start
            while url_end < len(attachments_str) and paren_count > 0:
                if attachments_str[url_end] == "(":
                    paren_count += 1
                elif attachments_str[url_end] == ")":
                    paren_count -= 1
                url_end += 1
            if paren_count == 0:
                url = attachments_str[url_start:url_end - 1]
                files_to_check.append(url)
                idx = url_end
            else:
                idx = alt_close + 1
        else:
            idx = alt_close + 1

    if not files_to_check:
        # Try JSON parsing
        import json
        try:
            data = json.loads(attachments)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if item.get("file_name"):
                            files_to_check.append(item["file_name"])
                        elif item.get("url"):
                            files_to_check.append(item["url"])
                        elif item.get("file_id"):
                            files_to_check.append(item["file_id"])
                    elif isinstance(item, str):
                        files_to_check.append(item)
            elif isinstance(data, dict):
                if data.get("file_name"):
                    files_to_check.append(data["file_name"])
                elif data.get("url"):
                    files_to_check.append(data["url"])
                elif data.get("file_id"):
                    files_to_check.append(data["file_id"])
        except Exception:
            files_to_check.append(attachments_str)

    for f in files_to_check:
        parsed = urlparse(f)
        query_params = parse_qs(parsed.query)
        
        # Check if there's a filename or file in the query parameters
        filename_val = None
        for key in ["filename", "file", "upload", "name"]:
            if key in query_params and query_params[key]:
                filename_val = query_params[key][0]
                break
                
        if not filename_val and "upload_id" in query_params:
            upload_id = query_params["upload_id"][0]
            uploads_dir = "/app/uploads"
            if not os.path.exists(uploads_dir):
                uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
            
            session_upload_dir = os.path.join(uploads_dir, upload_id)
            if os.path.isdir(session_upload_dir):
                try:
                    files = os.listdir(session_upload_dir)
                    if files:
                        filename_val = files[0]
                except Exception:
                    pass

        check_target = filename_val if filename_val else parsed.path
        clean_target = check_target.lower().strip()
        ext = os.path.splitext(clean_target)[1]
        
        if ext not in allowed_extensions:
            # Fallback check: does the original string path contain any of the allowed extensions?
            if not any(allowed_ext in clean_target for allowed_ext in allowed_extensions):
                raise MissingParametersError(
                    ["attachments"],
                    extra_context=(
                        "**Invalid file type.** Only image attachments (PNG, JPG, JPEG, GIF, WEBP) are allowed for ERP support tickets.\n\n"
                        "Please upload a valid image/screenshot showing the issue."
                    )
                )

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

    # ── Fetch and store developer info for confirmation message ─────────────
    app_name = payload.get("app_name", "")
    if app_name:
        devs = await _fetch_app_developers(app_name)
        payload["_fe_dev"] = devs.get("fe_dev", "")
        payload["_be_dev"] = devs.get("be_dev", "")

    return payload


async def _feedback_payload(params: dict) -> dict:
    return await _require(params, ["app_name", "feedback", "ratings"])


async def _suggestion_payload(params: dict) -> dict:
    return await _require(params, ["app_name", "priority", "feedback", "helps"])


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


async def get_current_user_email() -> str:
    try:
        from services.erp.mcp_registry import _call
        user_info = await _call("axon.api.get_user_info", "GET", {})
        message = user_info.get("message") or {}
        return message.get("email") or ""
    except Exception:
        return ""


async def _format_lost_found_list(data) -> str:
    if not isinstance(data, dict) or data.get("status") == "error":
        return data.get("message", "I could not fetch Lost & Found records.") if isinstance(data, dict) else str(data)

    records = _flatten_records(data.get("data"))
    
    lost_records = [r for r in records if r.get("status") == "Pending"]
    
    if not lost_records:
        return "No pending lost items reported."

    current_user = await get_current_user_email()
    
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
