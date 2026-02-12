from better_profanity import profanity

# Load default English profanity list
profanity.load_censor_words()

def contains_profanity(text: str) -> bool:
    """
    Returns True if the input text contains profanity.
    Deterministic, rule-based check.
    """
    return profanity.contains_profanity(text)
