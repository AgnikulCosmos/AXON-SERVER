# orchestrator/planning/default_resolver.py

"""
Default Parameter Resolver
--------------------------
Infers default parameter values when they are omitted from the user query
but can be reasonably assumed (e.g. "employee = current_user").

Task 5: Automatically resolve employee-related parameters when none are
explicitly provided.
"""

import logging

logger = logging.getLogger(__name__)

# Parameter names that indicate the current user should be inferred
_EMPLOYEE_FIELDS = {
    "employee_email",
    "employee_name",
    "employee_id",
    "user",
    "requestor",
    "requested_by",
    "requested_for",
}


def apply_defaults(extracted_params: dict, route_config: dict) -> dict:
    """
    Apply default parameter values to *extracted_params* based on
    *route_config*.

    Rules:
      • If the route's parameter schema contains employee-related fields
        (employee_email, employee_name, employee_id, user, requestor, etc.)
        and NONE of them were provided in extracted_params, set the first
        matching field to ``"current_user"`` as a sentinel. The downstream
        Frappe method should resolve ``"current_user"`` to the actual
        logged-in user.

    Returns a new dict (does not mutate the input).
    """
    params_schema = route_config.get("parameters", {})
    if not params_schema:
        return extracted_params

    # Check which employee-related fields exist in the schema
    schema_employee_fields = [
        f for f in params_schema if f in _EMPLOYEE_FIELDS
    ]

    if not schema_employee_fields:
        logger.debug("No employee fields in schema — skipping defaults.")
        return extracted_params

    # Check if any employee-related field was already extracted
    already_has_employee = any(
        f in extracted_params for f in schema_employee_fields
    )

    if already_has_employee:
        logger.debug(
            "Employee field already extracted — skipping default resolver."
        )
        return extracted_params

    # ── Apply default: set employee_email (preferred) or first match ─────
    result = dict(extracted_params)

    # Prefer employee_email if available in schema
    if "employee_email" in schema_employee_fields:
        result["employee_email"] = "current_user"
        logger.info("Default resolver: set employee_email = 'current_user'")
    else:
        # Fall back to the first employee-related field in schema
        field = schema_employee_fields[0]
        result[field] = "current_user"
        logger.info("Default resolver: set %s = 'current_user'", field)

    return result
