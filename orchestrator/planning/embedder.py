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
    Automatically pulls the model if it is not found.
    """
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": EMBED_MODEL,
                "prompt": text
            },
            timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # Check if it is a 404 error (typically model not found)
        if e.response is not None and e.response.status_code == 404:
            try:
                import logging
                logger = logging.getLogger("orchestrator")
                logger.info(f"Model '{EMBED_MODEL}' not found in Ollama. Attempting to pull it...")
                
                pull_response = requests.post(
                    f"{OLLAMA_URL}/api/pull",
                    json={
                        "name": EMBED_MODEL,
                        "stream": False
                    },
                    timeout=300  # Pulling might take some time
                )
                pull_response.raise_for_status()
                logger.info(f"Successfully pulled model '{EMBED_MODEL}'. Retrying embedding...")
                
                # Retry embedding after successful pull
                response = requests.post(
                    f"{OLLAMA_URL}/api/embeddings",
                    json={
                        "model": EMBED_MODEL,
                        "prompt": text
                    },
                    timeout=30
                )
                response.raise_for_status()
            except Exception as pull_err:
                raise RuntimeError(
                    f"Model '{EMBED_MODEL}' is missing in Ollama and auto-pull failed: {str(pull_err)}"
                ) from e
        else:
            raise e

    embedding = response.json().get("embedding")
    return np.array(embedding, dtype=np.float32)