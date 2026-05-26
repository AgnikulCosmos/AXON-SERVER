# Organization Q&A & Web Search

**Answers about company policies, HR info, and web search capabilities.**

---

## 🏢 Organization Questions

Ask about company information, HR policies, and internal procedures.

### Common Questions

**Company Info:**
```
"What is the company mission?"
"Tell me about Agnikul Cosmos."
"What does the company do?"
```

**HR & Policies:**
```
"What are the company holidays this year?"
"Tell me about HR policies."
"What is the time off policy?"
"How do I request time off?"
```

**Procedures:**
```
"What's the process for promotion?"
"How do I access the company intranet?"
"How do I expense my business travel?"
"What are the office timings?"
```

**Benefits & Access:**
```
"How do I get IT access?"
"What security requirements apply?"
"Tell me about leave policies."
```

### Response

```json
{
    "query_type": "organization",
    "status": "ok",
    "message": "Based on company policies...\n\n- Holiday 1\n- Holiday 2\n..."
}
```

---

## 🔍 Web Search

Search the internet using multiple sources.

### Wikipedia Search
```
"Find information about Agnikul on Wikipedia"
"Look up information about SpaceX"
"Tell me about rocket propulsion"
```

**Example Response:**
```
{
    "query_type": "search",
    "status": "ok",
    "message": "Found results:\n1. Agnikul Cosmos - Founded in 2017...\n2. Overview of the company...\n..."
}
```

---

### arXiv Search (Academic Papers)
```
"Search for machine learning papers on arXiv"
"Find research about AI safety"
"Search for rocket engine design papers"
```

**Example Response:**
```
{
    "query_type": "search",
    "status": "ok",
    "message": "Found 10 papers:\n1. Machine Learning: A Probabilistic Perspective - Murphy et al.\n2. Deep Learning - Goodfellow et al.\n..."
}
```

---

### DuckDuckGo Search (General Web)
```
"What's the latest news about space tech?"
"Search for latest aerospace innovations"
"Find recent articles about AI"
```

**Example Response:**
```
{
    "query_type": "search",
    "status": "ok",
    "message": "Found 10 results:\n1. Latest Space News - Date\n2. Aerospace Innovation Report - Date\n..."
}
```

---

## 🎯 Query Patterns

### Organization Questions
✅ Works best with:
- Direct questions about company
- HR and policy-related questions  
- Procedural questions
- Benefit and access questions

### Wikipedia Searches
✅ Works best with:
- Company names
- People and organizations
- Technology topics
- Historical information

### arXiv Searches
✅ Works best with:
- Academic and research topics
- Machine learning, AI, physics
- Technical papers
- Research-related queries

### Web Searches (DuckDuckGo)
✅ Works best with:
- News and current events
- General information
- Recent developments
- Trending topics

---

## 📝 Examples

### Getting Company Information
```python
from orchestrator.query_processor import process_query
import asyncio

async def main():
    # Ask about holidays
    response = await process_query("What are the company holidays this year?")
    print(response["message"])
    
    # Ask about HR policies
    response = await process_query("Tell me about time off policies")
    print(response["message"])

asyncio.run(main())
```

### Searching the Web
```python
async def main():
    # Search Wikipedia
    response = await process_query("Find information about SpaceX on Wikipedia")
    print(response["message"])
    
    # Search arXiv for papers
    response = await process_query("Search for machine learning papers on arXiv")
    print(response["message"])
    
    # General web search
    response = await process_query("What's the latest news about AI?")
    print(response["message"])

asyncio.run(main())
```

---

## ℹ️ How It Works

### Organization Questions
- **Data Source:** Internal company knowledge base (QWEN agent)
- **Processing:** LLM-based question answering
- **Response Time:** Immediate
- **Accuracy:** Based on company data fed to system

### Web Search
- **Wikipedia:** Curated encyclopedia data
- **arXiv:** Academic paper repository  
- **DuckDuckGo:** General web search engine
- **Processing:** Aggregated results with summaries
- **Response Time:** Depends on search source

---

## 🔧 Troubleshooting

### No Organization Data
- **Cause:** Company knowledge base not configured
- **Solution:** Check with IT/Admin to ensure company data is loaded

### Search Returns No Results
- **Cause:** Search term too specific or not found
- **Solution:** Try broader search terms or different keywords

### Search is Slow
- **Cause:** Multiple sources being queried
- **Solution:** Normal behavior; results will appear shortly

---

**Version:** 1.0  
**Last Updated:** 25 May 2026  
**Status:** Production Ready
