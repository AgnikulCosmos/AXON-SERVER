# AXON System Capabilities

This document details the system capabilities, frontend markdown rendering mechanisms, and the 13 defined system use cases for the AXON chatbot.

## System Capabilities

AXON is an internal enterprise AI assistant integrated with the organization's ERP and knowledge bases. Its primary capabilities include:

1. **ERP Support Management**: Users can create support tickets, submit suggestions, and provide feedback. AXON also tracks the status of these submissions.
2. **Canteen & Food Log Management**: Users can retrieve temporal food booking logs and canteen meal consumption records.
3. **Lost and Found Tracking**: Users can report lost/found items, list active items, and mark existing items as found (resolved).
4. **Internal RAG Retrieval**: Fetches factual corporate policies, leave guidelines, canteen menus, holidays, and company milestones from Agnikul's curated knowledge base.
5. **General Reasoning**: Answers academic, coding, math, or general knowledge questions using LLM reasoning without document retrieval.
6. **External Tool Integration**: Performs live external search queries via DuckDuckGo, Wikipedia, or arXiv when requested by the user.
7. **Tracking Requests**: Tracks the status and details of existing support requests using ticket prefixes (e.g., PC-, MM-, MT-, or ERP_I_).

## Frontend Markdown Rendering Mechanisms

The user interface uses custom Markdown renderers to format responses dynamically:

1. **Action Links**: Links starting with `action:mark_found:` are rendered as emerald-colored buttons with a checkmark symbol, allowing users to mark a lost item as found directly from the chat.
2. **External Links**: Links pointing to external domains (such as arXiv, Wikipedia, or other web resources) are rendered with a diagonal arrow indicator (↗) next to the anchor text.
3. **Source Badges**: External links are accompanied by a rounded, pill-shaped source badge displaying the friendly label or domain of the source (e.g., arXiv, Wikipedia, or the base domain like mountroutes.com).

## System Use Cases

The system defines 13 core use cases, listed below:

### Use Case 1: Create ERP Support Ticket (Direct Request)
Submit an ERP support ticket directly by specifying details (application, priority, module, and description).

### Use Case 2: Track ERP Support Request (By Prefix)
Check the status of an existing ticket by searching for prefix IDs (such as PC-, MM-, MT-, or ERP_I_).

### Use Case 3: Submit ERP Feedback
Initiate feedback submission and provide feedback text.

### Use Case 4: Submit ERP Suggestion
Initiate suggestion submission and provide improvement ideas.

### Use Case 5: List ERP Support Tickets
Retrieve and display all support tickets submitted by the currently logged-in user.

### Use Case 6: List ERP Suggestions and Feedback
Retrieve and list the feedback and suggestions submitted by the logged-in user.

### Use Case 7: View Food Booking Logs
View food booking or meal consumption records for today, yesterday, this week, or a specific month.

### Use Case 8: Food Log Summary
Retrieve a structured summary of canteen bookings for a selected period.

### Use Case 9: RAG Factual Retrieval
Retrieve internal company policy information (e.g., leave rules, holidays, and canteen menus) from the Agnikul knowledge base.

### Use Case 10: General Domain Reasoning
Ask questions on general concepts, coding, math, or public topics that require reasoning without internal document search.

### Use Case 11: Create Lost and Found Report (Lost Item)
Report a new lost or found item with details (item name, description, date, and location).

### Use Case 12: List Active Lost and Found Items
Show all active lost and found items that have not yet been marked as found.

### Use Case 13: Resolve Lost and Found Item
Mark a lost and found record as found using its reference ID (either via natural language or by clicking the Mark Found button).
