# orchestrator/planning/semantic_router.py

"""
Semantic Router
---------------
Embeds route descriptions + example queries and uses cosine similarity to
match user queries to the best route.

Features:
  • Combines description + examples for richer route embeddings (Task 1)
  • Auto-rebuilds embeddings when routes.json changes (Task 8)
  • Configurable similarity threshold via env var (Task 6)
"""

import os
import json
import logging
import numpy as np
from pathlib import Path
from .embedder import get_embedding

logger = logging.getLogger(__name__)


class SemanticRouter:
    def __init__(
        self,
        routes_path=None,
        embeddings_path=None,
        similarity_threshold=None,
    ):
        if routes_path is None:
            routes_path = Path(__file__).resolve().parent / "routes.json"
        if embeddings_path is None:
            embeddings_path = Path(__file__).resolve().parent / "route_embeddings.npy"

        self.routes_path = Path(routes_path)
        self.embeddings_path = Path(embeddings_path)
        self.mappings_path = self.embeddings_path.with_name("route_mappings.json")

        # ── Task 6: Configurable threshold via env var ───────────────────
        if similarity_threshold is not None:
            self.similarity_threshold = similarity_threshold
        else:
            self.similarity_threshold = float(
                os.getenv("ROUTER_THRESHOLD", "0.65")
            )

        self.routes = self._load_routes()
        self.index_to_route_name = []
        self.route_embeddings = self._load_or_build_embeddings()

    # ---------------------------
    # Load routes
    # ---------------------------
    def _load_routes(self):
        with open(self.routes_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------------------------
    # Load or build embeddings (with staleness check)
    # ---------------------------
    def _load_or_build_embeddings(self):
        # ── Task 8: Rebuild if routes.json is newer than embeddings ───────
        if self.embeddings_path.exists() and self.mappings_path.exists():
            routes_mtime = self.routes_path.stat().st_mtime
            embed_mtime = self.embeddings_path.stat().st_mtime
            mappings_mtime = self.mappings_path.stat().st_mtime

            if routes_mtime <= embed_mtime and routes_mtime <= mappings_mtime:
                logger.info("Loading cached route embeddings and mappings.")
                try:
                    with open(self.mappings_path, "r", encoding="utf-8") as f:
                        self.index_to_route_name = json.load(f)
                    return np.load(self.embeddings_path)
                except Exception as err:
                    logger.warning("Failed to load cached embeddings/mappings: %s. Rebuilding.", err)

        return self._build_embeddings()

    def _build_embeddings(self):
        """Generate and persist individual route and example embeddings."""
        logger.info("Generating individual route/example embeddings...")

        embeddings = []
        self.index_to_route_name = []

        for route in self.routes:
            route_name = route["route_name"]
            
            # 1. Embed description
            desc_text = route.get("description", "")
            if desc_text.strip():
                desc_emb = get_embedding(desc_text.lower().strip())
                embeddings.append(desc_emb)
                self.index_to_route_name.append(route_name)

            # 2. Embed each example query
            examples = route.get("examples", [])
            for ex in examples:
                if ex.strip():
                    ex_emb = get_embedding(ex.lower().strip())
                    embeddings.append(ex_emb)
                    self.index_to_route_name.append(route_name)

        if not embeddings:
            raise ValueError("No text found to embed in routes.json")

        embeddings = np.vstack(embeddings)
        np.save(self.embeddings_path, embeddings)

        with open(self.mappings_path, "w", encoding="utf-8") as f:
            json.dump(self.index_to_route_name, f, indent=2)

        logger.info("Route embeddings and mappings saved (%d total items).", len(self.index_to_route_name))

        return embeddings

    # ---------------------------
    # Cosine similarity
    # ---------------------------
    @staticmethod
    def _cosine_similarity(query_vec, matrix):
        query_norm = query_vec / np.linalg.norm(query_vec)
        matrix_norm = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
        return np.dot(matrix_norm, query_norm)

    # ---------------------------
    def match(self, query: str, exclude_routes: list = None):
        query_embedding = get_embedding(query.lower().strip())

        similarities = self._cosine_similarity(
            query_embedding,
            self.route_embeddings
        )

        if exclude_routes:
            for idx, r_name in enumerate(self.index_to_route_name):
                if r_name in exclude_routes:
                    similarities[idx] = -1.0

        best_index = np.argmax(similarities)
        best_score = similarities[best_index]
        best_route_name = self.index_to_route_name[best_index]

        logger.debug(
            "Router match — best: '%s' (score=%.4f, threshold=%.2f)",
            best_route_name,
            float(best_score),
            self.similarity_threshold,
        )

        if best_score < self.similarity_threshold:
            logger.info(
                "No route matched (best=%.4f < threshold=%.2f)",
                float(best_score),
                self.similarity_threshold,
            )
            return None

        # Find the route dict from self.routes
        matched_route = next((r for r in self.routes if r["route_name"] == best_route_name), None)
        if not matched_route:
            return None

        return {
            "route": matched_route,
            "confidence": float(best_score)
        }