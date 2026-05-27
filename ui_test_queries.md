# 🔍 Axon UI Testing Suite & Scenarios

Use this testing suite to manually verify all chatbot features, parameters, routing systems, and formatting styles directly inside the chat UI (accessible at `http://localhost:8000/chat`).

> [!NOTE]
> Ensure the **Axon orchestrator**, **Ollama service**, **Wiki**, **arXiv**, and **DuckDuckGo** containers are fully active before running these test queries.

---

## 📋 Scenarios and Test Queries

### 1. Lost and Found Items
Verify the multi-turn parameter extraction and greeting structures for lost and found reports.

| Step | User Query | Expected Behavior & UI Output |
| :--- | :--- | :--- |
| **1** | `I lost my item` | **Lost greeting is shown:** *"I'm sorry to hear you've lost your item..."* prompts for **Item Name**, **Lost Location**, and **Lost Description** with a codeblock text template. |
| **2** | `item_name: Access Card, lost_location: Cafeteria` | **Single missing parameter update:** Prompts politely for **Lost Description** only. |
| **3** | `It is a blue card with my employee photo.` | **Success message:** Returns a successful record creation prompt containing a reference ID: `LF-...` |

---

### 2. Found Item Report
Verify marking an item as found (this triggers the found item schema checklist).

| Step | User Query | Expected Behavior & UI Output |
| :--- | :--- | :--- |
| **1** | `I found a lost item` | **Found greeting is shown:** *"Thank you for reporting this found item!"* prompts for **Record Name**, **Found Location**, **Found Date**, and **Found Description**. |
| **2** | `name: LF-27-0526-00010, found_location: Cafeteria desk` | **Partial update:** Asks for **Found Date** and **Found Description** only. |
| **3** | `found_date: today, found_description: Left it at the reception.` | **Success message:** Confirms the update with a reference ID: `LF-...` |

---

### 3. ERP Support Tickets
Verify that general support ticket routing does NOT trigger the lost and found template.

| Step | User Query | Expected Behavior & UI Output |
| :--- | :--- | :--- |
| **1** | `I want to raise a support ticket` | **Ticket greeting is shown:** *"I'll help you raise a support ticket."* prompts for **Application Name**, **Priority**, **Module**, and **Description**. |
| **2** | `app_name: fleet_management, priority: High, module: Vehicle Tracking` | **Single missing parameter update:** Prompts politely for **Description** with a vehicle-related example. |
| **3** | `GPS coordination is lagging and updating only every 5 minutes` | **Success message:** Returns a successful ticket creation prompt containing a reference ID: `ERP_I_...` |

---

### 4. ERP App Feedback
Verify single-turn direct feedback submission with full parameters.

```text
Give feedback for app: fleet_management, feedback: The map display is incredibly smooth!, ratings: 5
```
* **Expected Output:** Immediately registers the feedback and outputs reference ID: `ERP-SF-...`

---

### 5. ERP App Suggestions
Verify suggestions flow with a multi-turn parameter schema.

| Step | User Query | Expected Behavior & UI Output |
| :--- | :--- | :--- |
| **1** | `I want to submit an ERP suggestion` | **Suggestion greeting is shown:** *"Thank you for your suggestion to improve the system!"* prompts for **Application Name**, **Priority**, **Feedback/Suggestion**, and **Helps**. |
| **2** | `app_name: fleet_management, priority: Medium, feedback: Add a night-mode theme, helps: It will reduce driver eye strain during night shifts` | **Success message:** Returns successful suggestion reference ID: `ERP-SF-...` |

---

### 6. arXiv Search & Qwen Formatting
Verify that academic searches display in a beautiful, structured Markdown card instead of unformatted escaped text.

```text
Search for machine learning papers on arXiv
```
* **Expected UI Output:** A clean, professional, and well-structured Markdown list:
  * **Bold headers** for each paper.
  * Bullet points showing **Authors**, **Year**, and a clean **Abstract/Summary**.
  * Clickable Markdown links: **`[Link](url)`**.
  * No raw `\n` characters or double quotes wrapping the entire response block.

---

### 7. Wikipedia & RAG Searches
Verify Wikipedia summarization and internal RAG policies.

*   **Wikipedia search query:** `Who is Nikola Tesla on Wikipedia?`
    *   *Expected output:* A concise, friendly summary of Tesla's life and inventions (no mention of raw tool logs).
*   **Company Policy query:** `What types of leave are available in the organization?`
    *   *Expected output:* Direct list of leave types (Casual, Sick, Earned/Privilege) sourced from Agnikul policy RAG documents.

---

> [!TIP]
> Use the **`Light / Dark`** toggle button in the bottom left of the chat window to see how beautifully the Markdown headings and list items stand out in both sleek themes!
