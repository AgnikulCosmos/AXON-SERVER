from typing import Any

from orchestrator.frappe_client import set_frappe_request_headers, reset_frappe_request_headers
from orchestrator.planning import router_pipeline
from orchestrator.erp_support_client import (
    execute_erp_support_plan,
    format_erp_support_response,
    MissingParametersError,
)
from orchestrator.dispatcher import _friendly_erp_error


def process_erp_query(query: str, frappe_headers: dict | None = None, session_id: str | None = None) -> dict[str, Any]:
    """Parse an ERP user query, call the MCP API, and return a clean result.

    Returns a dict with:
      - status: 'ok' | 'error' | 'missing'
      - message: user-facing string (for ok/error)
      - missing_fields: list (when status=='missing')
    """
    token = set_frappe_request_headers(frappe_headers)
    try:
        plan = router_pipeline.process(query)
        if not plan or not plan.get("route_name", "").startswith("erp_"):
            return {"status": "error", "message": "Could not resolve an ERP Support action from your message."}

        try:
            response = execute_erp_support_plan(plan)
            message = format_erp_support_response(plan, response)
            return {"status": "ok", "message": message}
        except MissingParametersError as e:
            return {"status": "missing", "missing_fields": e.fields, "message": str(e)}
        except Exception as exc:
            return {"status": "error", "message": _friendly_erp_error(exc)}
    finally:
        reset_frappe_request_headers(token)
