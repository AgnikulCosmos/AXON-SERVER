import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent.parent.parent / "dataset.json"

def append_entries(new_entries: list):
    dataset = []

    if DATASET_PATH.exists():
        dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    existing_ids = {item["id"] for item in dataset}

    for entry in new_entries:
        if entry["id"] not in existing_ids:
            dataset.append(entry)

    DATASET_PATH.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
