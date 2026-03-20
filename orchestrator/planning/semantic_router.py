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
        routes_path="orchestrator/planning/routes.json",
        embeddings_path="orchestrator/planning/route_embeddings.npy",
        similarity_threshold=None,
    ):
        self.routes_path = Path(routes_path)
        self.embeddings_path = Path(embeddings_path)

        # ── Task 6: Configurable threshold via env var ───────────────────
        if similarity_threshold is not None:
            self.similarity_threshold = similarity_threshold
        else:
            self.similarity_threshold = float(
                os.getenv("ROUTER_THRESHOLD", "0.65")
            )

        self.routes = self._load_routes()
        self.route_embeddings = self._load_or_build_embeddings()

    # ---------------------------
    # Load routes
    # ---------------------------
    def _load_routes(self):
        with open(self.routes_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------------------------
    # Build embedding text from route
    # ---------------------------
    @staticmethod
    def _build_route_text(route: dict) -> str:
        """
        Combine description + example queries for richer embedding.
        """
        text = route["description"]
        examples = route.get("examples", [])
        if examples:
            text += " " + " ".join(examples)
        return text

    # ---------------------------
    # Load or build embeddings (with staleness check)
    # ---------------------------
    def _load_or_build_embeddings(self):
        # ── Task 8: Rebuild if routes.json is newer than embeddings ───────
        if self.embeddings_path.exists():
            routes_mtime = self.routes_path.stat().st_mtime
            embed_mtime = self.embeddings_path.stat().st_mtime

            if routes_mtime <= embed_mtime:
                logger.info("Loading cached route embeddings.")
                return np.load(self.embeddings_path)
            else:
                logger.info(
                    "routes.json modified after embeddings — rebuilding."
                )

        return self._build_embeddings()

    def _build_embeddings(self):
        """Generate and persist route embeddings."""
        logger.info("Generating route embeddings...")

        embeddings = []
        for route in self.routes:
            text = self._build_route_text(route)
            emb = get_embedding(text)
            embeddings.append(emb)

        embeddings = np.vstack(embeddings)
        np.save(self.embeddings_path, embeddings)
        logger.info("Route embeddings saved (%d routes).", len(self.routes))

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
    # Match route
    # ---------------------------
    def match(self, query: str):
        query_embedding = get_embedding(query)

        similarities = self._cosine_similarity(
            query_embedding,
            self.route_embeddings
        )

        best_index = np.argmax(similarities)
        best_score = similarities[best_index]

        logger.debug(
            "Router match — best: '%s' (score=%.4f, threshold=%.2f)",
            self.routes[best_index]["route_name"],
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

        return {
            "route": self.routes[best_index],
            "confidence": float(best_score)
        }