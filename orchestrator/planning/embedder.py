# orchestrator/planning/embedder.py

"""
Embedder
--------
Provides embedding generation via Ollama.
Supports configurable Ollama URL via OLLAMA_BASE_URL environment variable.
"""

import os
import requests
import numpy as np

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = "mxbai-embed-large"


def get_embedding(text: str) -> np.ndarray:
    """
    Get embedding vector from Ollama.
    """
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={
            "model": EMBED_MODEL,
            "prompt": text
        },
        timeout=30
    )
    response.raise_for_status()

    embedding = response.json().get("embedding")
    return np.array(embedding, dtype=np.float32)