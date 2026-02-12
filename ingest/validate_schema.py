REQUIRED_KEYS = {
    "id",
    "source",
    "title",
    "content",
    "intent_tags",
    "keywords",
    "questions"
}


def validate(entries: list):
    for i, entry in enumerate(entries):
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            raise ValueError(f"Entry {i} missing keys: {missing}")
