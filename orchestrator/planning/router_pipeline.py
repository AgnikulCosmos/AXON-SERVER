# orchestrator/planning/router_pipeline.py

"""
Router Pipeline
---------------
Orchestrates the full semantic-routing pipeline:

    User query
      → SemanticRouter.match()
      → ParameterExtractor.extract()
      → DefaultResolver.apply_defaults()
      → FilterMapper.map()
      → FilterValidator.validate()
      → FieldPlanner.select_fields()
      → Structured execution plan
"""

import logging
from .semantic_router import SemanticRouter
from .parameter_extractor import extract_parameters
from .default_resolver import apply_defaults
from .filter_mapper import map_filters
from .filter_validator import validate_filters
from .field_planner import select_fields

logger = logging.getLogger(__name__)

# ── Singleton router instance ────────────────────────────────────────────────
_router: SemanticRouter | None = None


def _get_router() -> SemanticRouter:
    """Lazy-initialise the SemanticRouter singleton."""
    global _router
    if _router is None:
        _router = SemanticRouter()
    return _router


def process(query: str) -> dict | None:
    """
    Run the full semantic router pipeline on *query*.

    Returns
    -------
    dict
        A structured execution plan::

            {
                "route_name": "food_requests",
                "method":     "axon.api.get_food_requests",
                "doctype":    "Food_Requests",
                "filters":    { ... },
                "fields":     ["date", "employee_food_counts"],
                "confidence": 0.87
            }

    None
        If no route matched (below similarity threshold).
    """
    # ── Step 1: Semantic route matching ──────────────────────────────────
    router = _get_router()
    match_result = router.match(query)

    if match_result is None:
        logger.info("No route matched for query: %s", query)
        return None

    route_config = match_result["route"]
    confidence = match_result["confidence"]

    logger.info(
        "Route matched: %s (confidence=%.3f)",
        route_config["route_name"],
        confidence,
    )

    # ── Step 2: Parameter extraction ─────────────────────────────────────
    extracted_params = extract_parameters(query, route_config)
    logger.info("Extracted parameters: %s", extracted_params)

    # ── Step 3: Default parameter resolution ─────────────────────────────
    resolved_params = apply_defaults(extracted_params, route_config)
    if resolved_params != extracted_params:
        logger.info("After default resolver: %s", resolved_params)
    else:
        logger.debug("Default resolver: no changes applied.")

    # ── Step 4: Parameter → filter mapping ───────────────────────────────
    raw_filters = map_filters(resolved_params, route_config)
    logger.info("Mapped filters: %s", raw_filters)

    # ── Step 5: Filter validation ────────────────────────────────────────
    validated_filters = validate_filters(raw_filters, route_config)
    logger.info("Validated filters: %s", validated_filters)

    # ── Step 6: Field selection ──────────────────────────────────────────
    selected_fields = select_fields(query, route_config, resolved_params)
    logger.info("Selected fields: %s", selected_fields)

    # ── Step 7: Build structured execution plan ──────────────────────────
    plan = {
        "route_name": route_config["route_name"],
        "method": route_config["frappe_method"],
        "doctype": route_config.get("doctype", ""),
        "filters": validated_filters if validated_filters else None,
        "fields": selected_fields,
        "confidence": confidence,
    }

    logger.info("Execution plan: %s", plan)
    return plan
