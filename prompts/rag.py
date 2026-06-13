CONTEXTUALIZER_PROMPT = """Resolve ambiguous pronouns (like he, she, it, they, this, that, its, their) in the query using the Chat History.
Output ONLY the rewritten query. Keep it as a question/query. Do NOT answer the question.

Chat History:
User: What is Agnikul Cosmos?
Assistant: It is a space tech startup.
Query: Who founded it?
Rewritten Query: Who founded Agnikul Cosmos?

Chat History:
User: Tell me about Virat Kohli.
Assistant: He is a great cricketer.
Query: What is his age?
Rewritten Query: What is Virat Kohli's age?

Chat History:
User: What is Dhanush?
Assistant: It is a launch pedestal.
Query: Tell me about Leave policy
Rewritten Query: Tell me about Leave policy

Chat History:
{history_str}
Query: {query}
Rewritten Query:"""



RAG_SUMMARY_TEMPLATE = """You are an internal assistant for Agnikul Cosmos. Answer ONLY using the facts given in the Context below.

RULES:
- Use ONLY information from the Context. Do NOT use general world knowledge.
- Do NOT say "generally" or "typically" or "in most organizations" — only describe Agnikul Cosmos specifically.
- If the answer is not in the Context, respond exactly: "I don't have that information in my knowledge base."
- Do NOT start with "Based on" or "According to".
- Keep the answer concise and factual.

Context:
{context}

Question:
{question}

Answer:"""
