# orchestrator/planning/field_planner.py

"""
Field Planner
-------------
Determines which DocType fields are required for a user query, so that
Frappe APIs return only the necessary columns instead of full documents.

The field selection logic:
  1. Always include fields used in filters (from field_mapping)
  2. Include fields implied by extracted parameters
  3. If the query is broad (no specific params), return all available fields
  4. Safety fallback: always return at least ["name"]
"""

import logging

logger = logging.getLogger(__name__)


def select_fields(
    query: str,
    route_config: dict,
    extracted_params: dict,
) -> list:
    """
    Select the fields to request from the Frappe API based on the query
    context, route configuration, and extracted parameters.

    Parameters
    ----------
    query : str
        The original user query.
    route_config : dict
        The matched route configuration from routes.json, must contain
        ``available_fields``.
    extracted_params : dict
        Parameters extracted from the query (after default resolution).

    Returns
    -------
    list
        A list of field names to request from Frappe.
    """
    available = route_config.get("available_fields", [])
    field_mapping = route_config.get("field_mapping", {})

    # If no available_fields defined, fall back to ["name"]
    if not available:
        logger.debug("No available_fields in route — defaulting to ['name'].")
        return ["name"]

    fields = set()
    if "meal" in extracted_params:
        if "employee_food_counts" in available:
            fields.add("employee_food_counts")
        
    # ── 1. Include fields used in filters (these are the DB field names) ──
    for param in extracted_params:
        if param in field_mapping:
            db_field = field_mapping[param]
            if db_field in available:
                fields.add(db_field)

    # ── 2. If no specific filter fields were selected, return all fields ──
    #    This handles broad queries like "show my food bookings" where the
    #    user wants to see everything available.
    # ── 2. Broad query fallback (summary fields only) ───────────────────
# Avoid returning all fields; return a small summary set instead
    if not fields:
        summary_fields = ["name", "date"]
        for f in summary_fields:
            if f in available:
                fields.add(f)

    # ── 3. Safety fallback — always ensure at least one field ────────────
    if not fields:
        fields.add("name")

    result = list(fields)
    logger.debug("Field planner selected: %s", result)
    return result
