_profanity = None


def _get_profanity():
    global _profanity
    if _profanity is None:
        try:
            from better_profanity import profanity
            profanity.load_censor_words()
            _profanity = profanity
        except Exception:
            _profanity = False
    return _profanity or None


def contains_profanity(text: str) -> bool:
    p = _get_profanity()
    if p is None:
        return False
    return p.contains_profanity(text)
