# Agnikul AXON Chatbot Service

This repository houses the **AXON-Server** orchestrator backend. Below is the detailed routing flow diagram of AXON query processing and orchestration, including all keyword matches, regex checks, and target functions.

---

## Query Processing & Routing Flow

```mermaid
flowchart TD
    %% Global styling
    classDef redBox fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#000000;
    classDef greenBox fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000000;
    classDef yellowBox fill:#fffde7,stroke:#fbc02d,stroke-width:2px,color:#000000;
    classDef blueBox fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#000000;
    classDef greyBox fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,color:#000000;
    classDef startNode fill:#eceff1,stroke:#607d8b,stroke-width:2px,color:#000000;

    Start([1. INPUT QUERY<br>Query String]) :::startNode --> UnrelatedCheck{Query contains<br>Verb from<br>ACTION_VERBS?} :::yellowBox

    subgraph UnrelatedFilter["2. UNRELATED QUERY FILTER"]
        UnrelatedCheck -- YES --> ContextCheck{Query contains<br>context keyword from<br>ALLOWED_ACTION_CONTEXTS?} :::yellowBox
        ContextCheck -- NO --> UnrelatedError["Unrelated Query Error:<br>'I'm sorry, I couldn't perform that action.'"] :::redBox
    end

    ContextCheck -- YES --> PrivacyCheck1{Unauthorized Names:<br>Query contains 'priya'<br>and not current user?} :::yellowBox
    UnrelatedCheck -- NO --> PrivacyCheck1

    subgraph PrivacyFilter["3. EMPLOYEE PRIVACY FILTER"]
        PrivacyCheck1 -- YES --> PrivacyError["Privacy Error:<br>'I cannot disclose information about other employees.'"] :::redBox
        PrivacyCheck1 -- NO --> PrivacyCheck2{"Check ID patterns:<br>emp ID digits do not match<br>logged-in user digits?<br>Regex: emp [-_]? d+"} :::yellowBox
        PrivacyCheck2 -- YES --> PrivacyError
        PrivacyCheck2 -- NO --> PrivacyCheck3{Email addresses:<br>email is not logged-in<br>employee's email?} :::yellowBox
        PrivacyCheck3 -- YES --> PrivacyError
    end

    PrivacyCheck3 -- NO --> CapabilitiesCheck{Query matches<br>'capabilities' or<br>'/capabilities'?} :::yellowBox

    subgraph CapCheck["4. SYSTEM CAPABILITIES CHECK"]
        CapabilitiesCheck -- YES --> ReturnCapabilities["Return list of capabilities directly"] :::greenBox
    end

    CapabilitiesCheck -- NO --> SlashCheck{Query starts with<br>command prefix?} :::yellowBox

    subgraph SlashCommands["5. FORCED SEARCH SLASH COMMANDS"]
        SlashCheck -- YES --> DispatchSlash["Extract query & dispatch directly to:<br>• /arxiv<br>• /wiki<br>• /ddgs"] :::greenBox --> SummarizeSlash["Summarize tool response using LLM"] :::greenBox --> SanitizeSlash["sanitize_or_block_response"] :::greenBox --> EndOutput([Output Response])
    end

    SlashCheck -- NO --> ActiveSessionCheck{Active session in<br>PENDING_ERP_SESSIONS?} :::yellowBox

    subgraph ActiveSession["6. ACTIVE FORM-FILLING SESSION"]
        ActiveSessionCheck -- YES --> CancelCheck{Input in Cancel list?<br>cancel, stop, abort,<br>nevermind, quit, exit} :::yellowBox
        CancelCheck -- YES --> CancelSession["Delete pending session.<br>Return: 'Okay, I've cancelled that request.'"] :::greenBox
        CancelCheck -- NO --> ParseInput["Parse key-value inputs<br>Regex: b(a-zA-Z_+)s*:s*(.*?)(?=s+b[a-zA-Z_]+s*:|$)"] :::greenBox --> MapFields["Map parameters & validate fields"] :::greenBox --> ResolvedCheck{All required parameters<br>are resolved?} :::yellowBox
        ResolvedCheck -- NO --> PromptFields["Prompt user for remaining missing fields"] :::greenBox
        ResolvedCheck -- YES --> ExecuteActiveERP["execute_erp_support_plan"] :::greenBox --> FormatActiveERP["format_erp_support_response"] :::greenBox --> SanitizeSlash
    end

    ActiveSessionCheck -- NO --> Rewriter["contextualize_query_with_history<br>(rewrites if history & pronouns matched<br>and no KNOWN_ENTITIES present)"] :::greenBox --> HowToCheck{Query is a<br>'How-to' query?} :::yellowBox

    subgraph HowToFlow["7. CONTEXTUALIZATION & HOW-TO CHECK"]
        HowToCheck -- YES --> HowToRAG["Run RAG search (rag_search)"] :::greenBox --> HowToRAGCheck{RAG finds information?} :::yellowBox
        HowToRAGCheck -- YES --> SanitizeSlash
        HowToRAGCheck -- NO --> HowToERP["Match against ERP routes (route_query)"] :::greenBox --> HowToERPCheck{Matches ERP route?} :::yellowBox
        HowToERPCheck -- YES --> GuideOutput["Stream guide from ERP_INSTRUCTIONAL_GUIDES<br>(lost_found_create/list, erp_tickets_create/list,<br>erp_feedback_create, erp_suggestion_create,<br>track_request, food_log_list)"] :::greenBox
    end

    HowToERPCheck -- NO --> NormalizeQuery["Run typo-normalization using _ERP_VOCAB"] :::greenBox
    HowToCheck -- NO --> NormalizeQuery

    subgraph SemanticRouting["8. SEMANTIC ROUTING CLASSIFICATION (HYBRID MATCHING)"]
        NormalizeQuery --> ExactMatchCheck{Exact match with<br>SIMPLE_GREETINGS or<br>MODEL_KEYWORDS?} :::yellowBox
        ExactMatchCheck -- YES --> ReturnDirect["Return greetings or identity answer directly"] :::greenBox
        ExactMatchCheck -- NO --> CosineSim["Embed query using 'nomic-embed-text'<br>Compare with cached route embeddings<br>Calculate Confidence"] :::greenBox --> ConfidenceCheck{Confidence >= 0.45?} :::yellowBox
        
        ConfidenceCheck -- YES --> ConfirmRoute["Confirm & Disambiguate route with LLM<br>Extract parameters (extract_parameters)<br>using fallback keyword matching"] :::greenBox --> ParamsCheck{All required parameters<br>for the route are found?} :::yellowBox
        
        ParamsCheck -- NO --> CreatePending["Save state to PENDING_ERP_SESSIONS"] :::greenBox --> PromptFields
        ParamsCheck -- YES --> ExecuteERP["execute_erp_support_plan"] :::greenBox --> FormatERP["format_erp_support_response"] :::greenBox --> SanitizeSlash
        
        ConfidenceCheck -- NO --> PolicyRAG["Run RAG search (rag_search)<br>checking for company rules<br>(POLICY_KEYWORDS & POLICY_DOMAINS)"] :::greenBox --> PolicyRAGCheck{RAG finds info?} :::yellowBox
        PolicyRAGCheck -- YES --> ReturnRAG["Return sanitized RAG summary"] :::greenBox --> SanitizeSlash
        PolicyRAGCheck -- NO --> InferSearchTool["Infer search tool using LLM:<br>'wiki', 'arxiv', or 'ddgs'"] :::greenBox --> DispatchSearch["Dispatch query to search tool"] :::greenBox --> SummarizeSearch["Summarize tool response using LLM"] :::greenBox --> SanitizeSlash
    end
```

---

## Complete Keyword Lists & Reference Index

### 1. Action Verbs Filter (`ACTION_VERBS`)
Searched when checking for unrelated actions:
* `send`, `mail`, `email`, `post`, `tweet`, `slack`, `schedule`, `delete`, `remove`, `download`, `install`, `execute`, `run`, `book`, `reserve`, `order`

### 2. Allowed Context Keywords (`ALLOWED_ACTION_CONTEXTS`)
Bypasses unrelated queries filter if any of the following match:
* `lost`, `found`, `food`, `log`, `ticket`, `feedback`, `suggestion`, `track`, `tracking`

### 3. Employee Privacy Checks
* **Block Target Names**: `priya` (unless user's email starts with "priya")
* **Allowed Bypass Names**: `srinath`, `moin`, `satyanarayanan`, `janardhana`, `ravichandran`, `spm`
* **ID Regex Pattern**: `\bemp\s*[-_]?\s*(\d+)\b`
* **Email Regex Pattern**: `\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b`

### 4. Direct Slash Commands
Query prefix checks:
* `/arxiv`, `/wiki`, `/ddgs`

### 5. Active Session Cancel Keywords
* `cancel`, `stop`, `abort`, `nevermind`, `quit`, `exit`

### 6. Contextualizer Check
* **Ambiguous Pronouns**: `it`, `he`, `she`, `they`, `this`, `that`, `him`, `her`, `them`, `its`, `his`, `their`, `these`, `those`
* **Bypass Known Entities**: `agnikul`, `cosmos`, `agnibaan`, `agnilet`, `dhanush`, `sorted`, `launchpad`, `sdsc`, `shar`, `isro`, `axon`, `erp`, `srinath`, `moin`, `satyanarayanan`, `janardhana`, `ravichandran`, `spm`, `raju`, `chakravarthy`

### 7. How-To Indicators
* `how to`, `how do i`, `how can i`, `how should i`, `how does`, `how do we`, `how is`, `steps to`, `procedure to`, `guideline for`, `guide to`, `how do we go about`, `steps for`, `instruction for`, `instructions for`, `how do we do`

### 8. Typo Normalization Vocabulary (`_ERP_VOCAB`)
* `leave`, `balance`, `track`, `food`, `canteen`, `booking`, `log`, `meal`, `dinner`, `lunch`, `breakfast`, `ticket`, `feedback`, `suggestion`, `create`, `submit`, `raise`, `report`, `lost`, `found`, `item`, `management`, `support`, `erp`, `fleet`, `hr`, `payroll`, `finance`, `inventory`, `procurement`, `casual`, `sick`, `allocated`, `remaining`, `taken`

### 9. Greetings & Model Keywords
* **Greetings (`SIMPLE_GREETINGS`)**: `hi`, `hello`, `hey`, `hii`, `hola`, `hiya`, `yo`, `sup`, `greetings`
* **Identity Check (`MODEL_KEYWORDS`)**: `base model`, `model are you`, `llm are you`, `model you are using`, `llm you are using`, `what model`, `which model`, `which llm`, `what llm`, `model is this`, `model you use`, `llm you use`, `based on which`, `based on what`, `are you based on`, `are you llama`, `are you qwen`, `are you gpt`, `are you claude`, `are you gemini`, `are you deepseek`, `are you using llama`, `are you using qwen`, `are you using gpt`, `are you using deepseek`, `are you using gemini`, `are you using claude`

### 10. Parameter Extraction Helpers
* **Temporal Keywords**: `last week`, `this week`, `last month`, `this month`, `last year`, `this year`, `today`, `yesterday`, `tomorrow`
* **Priority Alias Map**: `critical` (P0), `urgent` (P0), `high` (P1), `medium` (P2), `moderate` (P2), `low` (P3), `minor` (P3)
* **Docname Match Prefix Regex**: `(?:PC|MM|MT|DL|LF|ERP_I|ERP-SF|FBSG|SUG|ERP-RU|ERP-FAQ|ERP-M|ERP_SF)[-_]\w+`
* **Ratings Match Patterns**: 
  - `\bratings?\s*[:=]?\s*([1-5](?:\.\d+)?)\b`
  - `\brate\s+(?:it\s+)?([1-5](?:\.\d+)?)\b`
  - `\b([1-5](?:\.\d+)?)\s*stars?\b`
  - `\bgive\s+(?:it\s+)?([1-5](?:\.\d+)?)\b`
* **Suggestion Benefit Indicators**: `would`, `helps to`, `helps`, `so that`, `to help`, `in order to`

### 11. Policy Rules Check
* **Keywords (`POLICY_KEYWORDS`)**: `policy`, `policies`, `guideline`, `guidelines`, `rules`, `rule`, `handbook`
* **Domains (`POLICY_DOMAINS`)**: `leave`, `leaves`, `food`, `canteen`, `cafeteria`, `meal`, `meals`, `breakfast`, `lunch`, `dinner`, `beverage`, `beverages`, `menu`, `catering`
