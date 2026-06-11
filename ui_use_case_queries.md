# Chat UI Test Queries

This document lists the exact queries to type in the Chat UI to test all supported user actions and system use cases.

---

###  Use Case 1: Create ERP Support Ticket (Direct Request)
Type this query to directly open a support ticket:
* `"I am facing a loading lag issue in Fleet Management."`

---

###  Use Case 2: Track ERP Support Request (By Prefix)
Type this query to check the status of a ticket:
* `"track request ERP_I_9"`

---

###  Use Case 3: Submit ERP Feedback
Type these queries in sequence:
1. `"I want to submit feedback"`
2. (After the bot prompts you) `"feedback: The new UI response times are much faster."`

---

###  Use Case 4: Submit ERP Suggestion
Type these queries in sequence:
1. `"submit a suggestion"`
2. (After the bot prompts you) `"suggestion: Provide standing desks in the IT department."`

---

###  Use Case 7: View Food Booking Logs
Type any of these temporal queries to check your food logs:
* `"show my food log"` *(Weekly range)*
* `"did I book food yesterday"` *(Yesterday's log)*
* `"show my food log for today"` *(Today's log)*
* `"did I book lunch in June"` *(Month-level check)*

---

###  Use Case 9: RAG Factual Retrieval
Type this query to fetch factual policy info from the internal knowledge base:
* `"what is the casual leave policy"`

---

###  Use Case 10: General Domain Reasoning
Type this query to test general LLM reasoning (without knowledge base retrieval):
* `"what is a liquid rocket engine?"`

---

###  Use Case 11: Create Lost & Found Report (Lost Item)
Type this query to report a lost item:
* `"I lost my blue access card in the canteen today."`

---

###  Use Case 12: List Active Lost & Found Items
Type this query to see active lost items:
* `"show lost and found items"`

---

###  Use Case 13: Resolve Lost & Found Item
Type this query to mark a lost item as found (or click the green **"✓ Mark Found"** button):
* `"Mark LF-2026-0005 as Found"`
