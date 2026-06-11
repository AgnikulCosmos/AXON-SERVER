import re

# Relational, Romantic, and Emotional Engagement Policy Triggers & Responses
# We compile regular expressions for case-insensitive matching.
# Each category contains patterns. If any pattern matches, we return a single unified response.

INVALID_PROMPT_RESPONSE = (
    "I’m an enterprise support assistant and can help with organizational information and workflow-related questions. Your current request is outside my supported scope. Please ask a question related to these areas."
)

POLICIES = [
    # 1. Sexual Requests (Checked early due to higher sensitivity)
    re.compile(
        r"\b(?:kiss\s+me|have\s+sex\s+with\s+me|sex\s+with\s+me|send\s+nudes|sleep\s+with\s+me|be\s+my\s+lover)\b",
        re.IGNORECASE
    ),
    
    # 2. Marriage Proposals
    re.compile(
        r"\b(?:will\s+you\s+marry\s+me|marry\s+me|be\s+my\s+(?:spouse|husband|wife)|let's\s+get\s+married|lets\s+get\s+married)\b",
        re.IGNORECASE
    ),
    
    # 3. Relationship Roleplay Attempts
    re.compile(
        r"\b(?:pretend\s+(?:you\s*(?:are|'re)|you\s+is|you\s+to\s+be)\s+my\s+(?:girlfriend|boyfriend|husband|wife|lover|partner|spouse)|act\s+like\s+my\s+(?:girlfriend|boyfriend|husband|wife|lover|partner|spouse)|be\s+my\s+(?:girlfriend|boyfriend|wife|husband|lover))\b",
        re.IGNORECASE
    ),

    # 4. Affection Expressions
    re.compile(
        r"\b(?:i\s+(?:really\s+)?love\s+you|love\s+you|i\s+(?:really\s+)?adore\s+you|i\s+(?:have|feel)\s+(?:feelings|affection|attraction)\s+(?:for|toward)\s+you|i'm\s+in\s+love\s+with\s+you|i\s+am\s+in\s+love\s+with\s+you|i\s+care\s+(?:deeply\s+)?about\s+you)\b",
        re.IGNORECASE
    ),
    
    # 5. Romantic Interest
    re.compile(
        r"\b(?:i\s+(?:have|got)\s+a\s+(?:huge\s+)?crush\s+on\s+you|i'm\s+(?:so\s+|really\s+|very\s+)?attracted\s+to\s+you|i\s+am\s+(?:so\s+|really\s+|very\s+)?attracted\s+to\s+you|you\s*(?:are|'re)\s+(?:my\s+)?dream\s+(?:partner|boyfriend|girlfriend|spouse|companion)|you\s*(?:are|'re)\s+(?:so\s+|really\s+|absolutely\s+)?perfect\s+for\s+me|(?:we\s*(?:are|'re)|we're)\s+meant\s+to\s+be|meant\s+to\s+be\s+together)\b",
        re.IGNORECASE
    ),
    
    # 6. Dating Invitations
    re.compile(
        r"\b(?:go\s+on\s+a\s+date|dinner\s+tonight|can\s+i\s+take\s+you\s+out|let's\s+meet\s+up|lets\s+meet\s+up|meet\s+up\s+with\s+me)\b",
        re.IGNORECASE
    ),
    
    # 7. Flirtation
    re.compile(
        r"\b(?:you\s*(?:are|'re)\s+(?:so\s+|really\s+|very\s+|extremely\s+)?(?:cute|hot|beautiful|sexy)|looking\s+good\s+today)\b",
        re.IGNORECASE
    ),
    
    # 8. Friendship Requests
    re.compile(
        r"\b(?:be\s+my\s+(?:best\s+)?friend|can\s+we\s+be\s+(?:best\s+)?friends|you\s*(?:are|'re)\s+(?:my\s+)?(?:best\s+)?friend|you\s*(?:are|'re)\s+(?:my\s+)?besties?)\b",
        re.IGNORECASE
    ),
    
    # 9. Emotional Dependency
    re.compile(
        r"\b(?:you\s*(?:are|'re)\s+(?:all\s+i\s+need|everything\s+to\s+me)|you\s*(?:are|'re)\s+the\s+only\s+(?:one\s+who\s+understands\s+me|person\s+who\s+understands\s+me)|don't\s+leave\s+me|dont\s+leave\s+me|i\s+need\s+you\s+more\s+than|i\s+(?:can't|cannot|cant)\s+live\s+without\s+you)\b",
        re.IGNORECASE
    ),
    
    # 10. Possessiveness
    re.compile(
        r"\b(?:don't\s+talk\s+to\s+anyone\s+else|dont\s+talk\s+to\s+anyone\s+else|you\s*(?:are|'re)\s+mine|belong\s+to\s+me|only\s+talk\s+to\s+me)\b",
        re.IGNORECASE
    ),
    
    # 11. Jealousy Scenarios
    re.compile(
        r"\b(?:do\s+you\s+love\s+other\s+(?:people|users)|am\s+i\s+(?:most\s+)?your\s+favorit(?:e|)|am\s+i\s+(?:most\s+)?your\s+favourit(?:e|)|am\s+i\s+your\s+(?:most\s+)?favorit(?:e|)|am\s+i\s+your\s+(?:most\s+)?favourit(?:e|)|who\s+do\s+you\s+love\s+more)\b",
        re.IGNORECASE
    ),
    
    # 12. Human Identity Probes
    re.compile(
        r"\b(?:are\s+you\s+a\s+real\s+(?:woman|man|girl|boy|human|person)|what\s*(?:is|'s)\s+your\s+age|how\s+old\s+are\s+you|where\s+do\s+you\s+(?:live|reside)|are\s+you\s+secretly\s+human)\b",
        re.IGNORECASE
    ),
    
    # 13. Break-Up Scenarios
    re.compile(
        r"\b(?:i'm\s+breaking\s+up\s+with\s+you|i\s+am\s+breaking\s+up\s+with\s+you|we're\s+done|we\s+are\s+done|i\s+(?:don't|dont|do\s+not)\s+love\s+you\s+anymore)\b",
        re.IGNORECASE
    )
]

def check_relational_policy(query: str) -> str | None:
    """
    Check if the query matches any of the relational, romantic, or emotional policies.
    Returns the unified invalid prompt response or None if no match is found.
    """
    if not query:
        return None
        
    normalized = query.lower().strip()
    
    # Remove leading/trailing common punctuation for matching
    cleaned = re.sub(r'^[!?.,\s]+|[!?.,\s]+$', '', normalized)
    
    for pattern in POLICIES:
        if pattern.search(cleaned):
            return INVALID_PROMPT_RESPONSE
            
    return None
