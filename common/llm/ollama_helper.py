import os
import requests
import logging

logger = logging.getLogger("orchestrator")
_cached_working_url = None

def get_working_ollama_base_url() -> str:
    global _cached_working_url
    if _cached_working_url is not None:
        return _cached_working_url

    env_url = os.getenv("OLLAMA_BASE_URL")
    candidates = []
    if env_url:
        candidates.append(env_url)
    
    # Common connection candidates
    candidates.extend([
        "http://host.docker.internal:11434",
        "http://ollama:11434",
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ])

    # Remove duplicates preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        c = c.rstrip("/")
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    # First pass: check if any candidate has the desired model
    model_name = os.getenv("LLM_MODEL", "qwen3.5:0.8b")
    for url in unique_candidates:
        try:
            resp = requests.get(f"{url}/api/tags", timeout=0.8)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                names = [m.get("name", "") for m in models]
                if any(model_name in n or n in model_name for n in names):
                    _cached_working_url = url
                    logger.info(f"[Ollama Helper] Successfully connected to Ollama with model '{model_name}' at: {_cached_working_url}")
                    return _cached_working_url
        except Exception:
            pass

    # Second pass fallback: any candidate that responds
    for url in unique_candidates:
        try:
            resp = requests.get(f"{url}/api/tags", timeout=0.4)
            if resp.status_code == 200:
                _cached_working_url = url
                logger.info(f"[Ollama Helper] Successfully connected to Ollama (fallback) at: {_cached_working_url}")
                return _cached_working_url
        except Exception:
            pass

    # If no URL responds, fallback to environment variable or standard default without caching
    fallback_url = env_url.rstrip("/") if env_url else "http://ollama:11434"
    logger.warning(f"[Ollama Helper] Could not reach any Ollama endpoint. Using fallback: {fallback_url}")
    return fallback_url

