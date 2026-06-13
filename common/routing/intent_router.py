import logging
from typing import Optional

logger = logging.getLogger(__name__)

TOP_LEVEL_CATEGORIES = {"RAG", "TOOLS", "QWEN", "IDENTITY", "HOW_TO"}

ERP_ROUTE_NAMES = {
    "food_requests", "food_menu", "food_settings", "food_log_list",
    "id_cards",
    "pr_attendance_requests", "pr_leave_requests", "pr_leave_tracker",
    "pr_permission_requests", "pr_policy", "pr_reimbursement_requests",
    "tm_projects", "tm_tasks", "tm_time_logs",
    "erp_tickets_create", "erp_tickets_list", "erp_apps_list",
    "erp_feedback_create", "erp_feedback_list",
    "erp_suggestion_create", "erp_suggestions_list",
    "erp_support_view_details",
    "lost_found_create", "lost_found_list",
    "track_request",
}

MIN_CONFIDENCE_FALLBACK = 0.45


class IntentRouter:
    def __init__(self, threshold: Optional[float] = None):
        self._semantic = None
        self._threshold = threshold
        self._last_route_config: Optional[dict] = None

    def _get_semantic(self):
        if self._semantic is not None:
            return self._semantic
        try:
            from common.routing.planning.semantic_router import SemanticRouter
            self._semantic = SemanticRouter(
                similarity_threshold=self._threshold
            )
        except Exception as e:
            logger.warning("Failed to initialise SemanticRouter: %s", e)
            self._semantic = False
        return self._semantic

    @property
    def last_route_config(self) -> Optional[dict]:
        return self._last_route_config

    def classify(self, query: str) -> Optional[str]:
        router = self._get_semantic()
        if not router:
            return None

        try:
            result = router.match(query)
        except Exception as e:
            logger.warning("SemanticRouter.match() failed: %s", e)
            return None

        if result is None:
            self._last_route_config = None
            return None

        route_name = result["route"]["route_name"]
        confidence = result["confidence"]

        if confidence < MIN_CONFIDENCE_FALLBACK:
            logger.info(
                "Low confidence (%.3f) for route %r — falling back",
                confidence, route_name,
            )
            self._last_route_config = None
            return None

        self._last_route_config = result["route"]

        if route_name in TOP_LEVEL_CATEGORIES:
            return route_name

        if route_name in ERP_ROUTE_NAMES:
            return f"ERP_ROUTE:{route_name}"

        logger.warning("Unknown route name %r — falling back", route_name)
        self._last_route_config = None
        return None

    def get_route_config(self, route_name: str) -> Optional[dict]:
        router = self._get_semantic()
        if not router:
            return None
        for route in router.routes:
            if route.get("route_name") == route_name:
                return route
        return None
