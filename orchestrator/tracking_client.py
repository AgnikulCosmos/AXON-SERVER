from datetime import datetime, timedelta
from typing import Any
import json
from orchestrator.mcp_registry import (
    view_erp_support_details,
    view_packaging_details,
    view_maintenance_details,
    get_food_log
)

def execute_tracking_plan(plan: dict) -> dict[str, Any]:
    route = plan.get("route_name")
    params = plan.get("parameters", {})
    
    if route == "food_log_list":
        return execute_food_log_query(params)
        
    req_id = params.get("req_id")
    if req_id:
        cleaned = req_id.strip().lower()
        if cleaned in ("track", "request", "track request", "status", "details", "check", "track_request"):
            req_id = None

    if not req_id:
        from orchestrator.erp_support_client import MissingParametersError
        raise MissingParametersError(["req_id"])
        
    req_id_upper = req_id.upper().strip()
    
    try:
        # Routing based on ID Prefix (No sequential fallback scanning)
        if req_id_upper.startswith("PC-"):
            raw_response = view_packaging_details(req_id_upper)
            return _normalize_packaging_response(raw_response)
            
        elif req_id_upper.startswith(("MM-", "MT-", "DL-", "MT_REQUESTS", "MT_ASSETS")):
            raw_response = view_maintenance_details(req_id_upper)
            return _normalize_maintenance_response(raw_response)
            
        elif req_id_upper.startswith(("ERP_I_", "ERP-SF-", "FBSG-", "SUG-", "ERP-RU-", "ERP-FAQ-", "ERP-M-")):
            raw_response = view_erp_support_details(req_id_upper)
            return _normalize_erp_support_response(raw_response)
            
        else:
            return {"status": "error", "message": f"Unsupported or unrecognized request ID format: {req_id}"}
            
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve request details for {req_id}: {str(e)}"}

def execute_food_log_query(params: dict) -> dict[str, Any]:
    import calendar
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    
    def resolve_single(val: Any) -> tuple[datetime, datetime] | None:
        if not val:
            return None
        val_str = str(val).strip().lower()
        if not val_str:
            return None
        
        # 1. Day keywords
        if val_str == "today":
            return today, today
        if val_str == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        if val_str == "tomorrow":
            tomorrow = today + timedelta(days=1)
            return tomorrow, tomorrow
            
        # 2. Week keywords
        if val_str == "this week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        if val_str == "last week":
            start = today - timedelta(days=today.weekday() + 7)
            end = start + timedelta(days=6)
            return start, end
            
        # 3. Month keywords
        if val_str == "this month":
            start = today.replace(day=1)
            last_day = calendar.monthrange(today.year, today.month)[1]
            end = today.replace(day=last_day)
            return start, end
        if val_str == "last month":
            first_of_current = today.replace(day=1)
            last_month_end = first_of_current - timedelta(days=1)
            start = last_month_end.replace(day=1)
            return start, last_month_end
            
        # 4. Month Names
        months = {
            "january": 1, "jan": 1,
            "february": 2, "feb": 2,
            "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "may": 5,
            "june": 6, "jun": 6,
            "july": 7, "jul": 7,
            "august": 8, "aug": 8,
            "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "december": 12, "dec": 12
        }
        if val_str in months:
            m = months[val_str]
            start = today.replace(month=m, day=1)
            last_day = calendar.monthrange(today.year, m)[1]
            end = today.replace(month=m, day=last_day)
            return start, end
            
        # 5. Year keywords
        if val_str == "this year":
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)
            return start, end
        if val_str == "last year":
            start = today.replace(year=today.year - 1, month=1, day=1)
            end = today.replace(year=today.year - 1, month=12, day=31)
            return start, end
            
        # 6. Exact Formats
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                clean_val = val_str.split()[0] if " " in val_str else val_str
                dt = datetime.strptime(clean_val, fmt)
                return dt, dt
            except ValueError:
                continue
        return None

    from_res = resolve_single(params.get("from_date"))
    to_res = resolve_single(params.get("to_date"))
    
    if from_res and to_res:
        start_dt, end_dt = from_res[0], to_res[1]
    elif from_res:
        start_dt, end_dt = from_res[0], from_res[1]
    elif to_res:
        start_dt, end_dt = to_res[0], to_res[1]
    else:
        # Default to current week range (Monday -> Today)
        start_dt = today - timedelta(days=today.weekday())
        end_dt = today

    f_dt = start_dt.strftime("%d-%m-%Y")
    t_dt = end_dt.strftime("%d-%m-%Y")

    try:
        raw_response = get_food_log(
            from_date=f_dt,
            to_date=t_dt,
            request_type=params.get("request_type") or "Self",
            location=params.get("location") or "All",
            meal_type=params.get("meal_type") or "All"
        )
        return {
            "status": "ok",
            "type": "food_log",
            "data": raw_response.get("message", raw_response),
            "range": f"{f_dt} to {t_dt}"
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch food booking log: {str(e)}"}

def format_tracking_response(normalized: dict) -> str:
    if normalized.get("status") == "error":
        return normalized.get("message")
        
    if normalized.get("type") == "food_log":
        return _format_food_log(normalized["data"], normalized.get("range", ""))
        
    # Standard Request Details Formatting
    md = []
    md.append(f"### 🔍 Request Tracking Details: **{normalized['id']}**")
    md.append(f"- **Application:** `{normalized['app_name']}`")
    md.append(f"- **Request Type:** {normalized['type']}")
    md.append(f"- **Status:** `{normalized['status']}`")
    md.append(f"- **Raised By:** {normalized['raised_by']}")
    if normalized.get("created_at"):
        md.append(f"- **Created At:** {normalized['created_at']}")
    if normalized.get("assigned_to"):
        md.append(f"- **Assigned To:** {normalized['assigned_to']}")
    if normalized.get("priority"):
        md.append(f"- **Priority:** {normalized['priority']}")
        
    md.append(f"\n**Summary / Description:**\n> {normalized['description'] or normalized['title'] or 'No description provided.'}")
    
    customs = {k: v for k, v in normalized["custom_details"].items() if v not in (None, "")}
    if customs:
        md.append("\n**Additional Specifications:**")
        for k, v in customs.items():
            md.append(f"- **{k}:** {v}")
            
    return "\n".join(md)

def _format_food_log(data: dict, date_range: str) -> str:
    records = data.get("records", [])
    counts = data.get("counts", {})
    
    if not records or (len(records) == 1 and not records[0].get("Request Date")):
        return f"No food booking records found for the period **{date_range}**."
        
    md = []
    md.append(f"### 🍽️ Food Booking Log Summary ({date_range})")
    md.append(f"- **Total Booked:** {counts.get('Booked', 0)} | **Consumed:** {counts.get('Consumed', 0)} | **Not Consumed:** {counts.get('Not Consumed', 0)}")
    md.append("\n| Request Date | Location | Meal Type | Status |")
    md.append("| :--- | :--- | :--- | :--- |")
    for r in records:
        if r.get("Request Date"):
            md.append(f"| {r['Request Date']} | {r.get('Location', 'N/A')} | {r.get('Type')} | `{r.get('Status')}` |")
            
    return "\n".join(md)

def _normalize_packaging_response(raw_response: dict) -> dict[str, Any]:
    raw = raw_response.get("message") or raw_response
    if isinstance(raw, dict) and raw.get("status") == "error":
        return raw
    
    return {
        "status": raw.get("status") or "Open",
        "id": raw.get("name"),
        "app_name": "Packaging",
        "type": "PC Raise Request",
        "raised_by": raw.get("request_raised_by") or "N/A",
        "created_at": raw.get("requested_on"),
        "assigned_to": raw.get("assigned_to") or "Unassigned",
        "priority": "N/A",
        "description": raw.get("purpose") or raw.get("remarks") or "",
        "title": f"Packaging Request for {raw.get('requesting_for') or 'N/A'}",
        "custom_details": {
            "Component Type": raw.get("component_type"),
            "Transport Mode": raw.get("transport_mode"),
            "From Location": raw.get("transport_from"),
            "To Location": raw.get("transport_to"),
            "Packing Time": raw.get("packing_time"),
            "Remarks": raw.get("remarks")
        }
    }

def _normalize_maintenance_response(raw_response: dict) -> dict[str, Any]:
    raw = raw_response.get("message") or raw_response
    if isinstance(raw, dict) and raw.get("status") == "error":
        return raw
        
    req_type = raw.get("request_type") or "Maintenance Request"
    raised_by = raw.get("requested_by") or raw.get("requestor") or raw.get("request_raised_by") or "N/A"
    
    customs = {}
    if "asset_id" in raw:
        customs = {
            "Asset ID": raw.get("asset_id"),
            "Asset Name": raw.get("asset_name"),
            "Capacity": raw.get("capacity"),
            "Location": raw.get("location"),
            "Total Run Hours": raw.get("total_run_hours"),
            "Due Date": raw.get("due_date"),
            "Notes": raw.get("notes")
        }
    elif "access_to" in raw:
        customs = {
            "Access To": raw.get("access_to"),
            "Department": raw.get("department"),
            "From Facility": raw.get("from_facility"),
            "To Facility": raw.get("to_facility"),
            "From Date": raw.get("from_date"),
            "To Date": raw.get("to_date")
        }
    
    return {
        "status": raw.get("status") or "Open",
        "id": raw.get("name"),
        "app_name": "Maintenance",
        "type": req_type,
        "raised_by": raised_by,
        "created_at": raw.get("creation") or raw.get("assigned_on"),
        "assigned_to": raw.get("assigned_to") or "Unassigned",
        "priority": raw.get("priority") or "N/A",
        "description": raw.get("purpose") or raw.get("notes") or "",
        "title": f"Maintenance Request ({req_type})",
        "custom_details": customs
    }

def _normalize_erp_support_response(raw_response: dict) -> dict[str, Any]:
    raw = raw_response.get("message") or raw_response
    if isinstance(raw, dict) and raw.get("status") == "error":
        return raw

    # If the response wraps the actual record in a "data" key (live ERP API convention)
    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], dict):
        raw = raw["data"]

    app_name = raw.get("app_name") or "ERP Support"
    raised_by = raw.get("raised_by") or "N/A"
    created_at = raw.get("raised_on")
    status = raw.get("status") or "Open"
    description = raw.get("description") or raw.get("feedback") or ""
    
    customs = {}
    if "feedback" in raw:
        customs["Feedback / Suggestion Type"] = raw.get("type")
        if "helps" in raw:
            customs["Helps"] = raw.get("helps")
        if "ratings" in raw:
            customs["Ratings"] = raw.get("ratings")
    elif "fe_dev" in raw:
        customs["Frontend Developer"] = raw.get("fe_dev")
        customs["Backend Developer"] = raw.get("be_dev")
        customs["Module"] = raw.get("module")
        customs["Roles"] = raw.get("roles")
        
    return {
        "status": status,
        "id": raw.get("name"),
        "app_name": app_name,
        "type": raw.get("type") or "ERP Ticket",
        "raised_by": raised_by,
        "created_at": created_at,
        "assigned_to": raw.get("assigned_to") or "Unassigned",
        "priority": raw.get("priority") or "N/A",
        "description": description,
        "title": f"ERP Support: {raw.get('name')}",
        "custom_details": customs
    }
