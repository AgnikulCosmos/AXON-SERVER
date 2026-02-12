import json
import hashlib
from pathlib import Path

# Always resolve paths from this file
BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR /"dataset.json"


def generate_stable_id(entry: dict) -> str:
    """
    Generates a stable ID based on semantic content.
    Same content => same ID.
    """
    base = (
        entry.get("source", "") +
        entry.get("title", "") +
        entry.get("content", "")
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def main():
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"{DATASET_PATH} not found")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    for entry in data:
        if "id" not in entry or not entry["id"].strip():
            entry["id"] = generate_stable_id(entry)
            updated += 1

    if updated > 0:
        with open(DATASET_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Backfill complete. IDs added to {updated} entries.")


if __name__ == "__main__":
    main()
