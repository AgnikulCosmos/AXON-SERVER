from pathlib import Path
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent.parent

PARA_TO_JSON_PROMPT = BASE_DIR / "scripts" / "ingestion" / "prompts" / "para_to_json.txt"
NORMALIZE_PROMPT = BASE_DIR / "scripts" / "ingestion" / "prompts" / "normalize_paragraph.txt"
REPAIR_PROMPT = BASE_DIR / "scripts" / "ingestion" / "prompts" / "json_repair.txt"

import os
MODEL = os.getenv("INGESTION_MODEL", "qwen2.5:3b")


def _run_ollama(prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", MODEL, "prompt", prompt],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Ollama error: {result.stderr}")

    return result.stdout.strip()


def normalize_paragraph(paragraph: str) -> str:
    system_prompt = NORMALIZE_PROMPT.read_text(encoding="utf-8")

    full_prompt = f"""{system_prompt}

{paragraph}
"""

    output = _run_ollama(full_prompt)

    if not output:
        raise ValueError("Normalization produced empty output")

    return output


def para_to_json(paragraph: str) -> str:
    normalized = normalize_paragraph(paragraph)

    system_prompt = PARA_TO_JSON_PROMPT.read_text(encoding="utf-8")

    full_prompt = f"""{system_prompt}

PARAGRAPH:
{normalized}
"""

    return _run_ollama(full_prompt)


def repair_json(broken_json: str) -> str:
    system_prompt = REPAIR_PROMPT.read_text(encoding="utf-8")

    full_prompt = f"""{system_prompt}

{broken_json}
"""

    return _run_ollama(full_prompt)
