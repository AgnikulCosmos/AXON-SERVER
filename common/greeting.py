import random

# Common greeting patterns to detect
GREETING_PATTERNS = [
    "hi", "hello", "hey", "hola", "howdy",
    "good morning", "good afternoon", "good evening", "good night",
    "morning", "afternoon", "evening",
    "what's up", "whats up", "wassup", "sup",
    "yo", "hiya", "heya", "greetings",
    "namaste", "vanakkam"
]

# Hardcoded greeting responses (randomly selected)
GREETING_RESPONSES = [
    "Hi, I'm Axon, your internal ERP AI Assistant!",
    "Hello! I'm Axon, ready to help with your ERP queries!",
    "Hey there! I'm Axon, your friendly ERP AI Assistant!",
    "Greetings! I'm Axon, here to assist with all things ERP!",
    "Hi! Axon at your service – your internal ERP AI Assistant!"
]


def is_greeting(text: str) -> bool:
    """
    Returns True if the input text is a simple greeting.
    Deterministic, rule-based check.
    """
    normalized = text.lower().strip()
    
    # Check if the entire message is a short greeting
    for pattern in GREETING_PATTERNS:
        if normalized == pattern:
            return True
        # Also match with punctuation: "hi!" "hello?"
        if normalized.rstrip("!?.,") == pattern:
            return True
    
    return False


def get_greeting_response() -> str:
    """
    Returns a random greeting response from the hardcoded list.
    """
    return random.choice(GREETING_RESPONSES)
