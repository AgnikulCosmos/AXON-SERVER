import json
import re
import subprocess

from qwen_convert import para_to_json
from append_dataset import append_entries
from validate_schema import validate
from incremental_vector import add_new_vectors
from qwen_convert import para_to_json, repair_json


def extract_json_array(text: str):
    """
    Extracts the first valid JSON array from model output.
    Raises a clear error if none is found.
    """
    if not text or not text.strip():
        raise ValueError("Model returned empty output")

    match = re.search(r"\[\s*{.*?}\s*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in model output")

    return json.loads(match.group(0))


def try_parse_json(raw_output: str):
    try:
        return extract_json_array(raw_output)
    except json.JSONDecodeError:
        # attempt repair once
        repaired = repair_json(raw_output)
        return extract_json_array(repaired)


def ingest(paragraph: str):
    raw_output = para_to_json(paragraph)

    # ---- DEBUG (uncomment once if needed) ----
    # print("----- RAW MODEL OUTPUT START -----")
    # print(raw_output)
    # print("----- RAW MODEL OUTPUT END -----")

    try:
        entries = try_parse_json(raw_output)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Qwen output is not valid JSON: {e}")

    validate(entries)
    append_entries(entries)
    add_new_vectors(entries)


if __name__ == "__main__":
    paragraph = input("Paste the data to be added:\n")
    ingest(paragraph)
