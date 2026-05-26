# ERP Support – Tickets, Feedback & Suggestions

**Complete guide for creating and managing ERP support tickets, feedback, and suggestions.**

---

## 📋 Creating Tickets

### Basic Syntax
```
Raise a <PRIORITY> ERP support ticket for app <APP_NAME> module <MODULE>. Description: <ISSUE>
```

### Priorities
- **P0** – System Down / Critical
- **P1** – Major Feature Broken
- **P2** – Performance Issue
- **P3** – Minor Bug / Request

### Examples

```
"Raise a P0 ticket for app Finance module Dashboard. Dashboard not loading."

"Create a P1 ticket for app HR module Payroll. Salary calculations incorrect."

"Lodge a P2 support ticket for app Inventory module Reports. Reports are slow."
```

### Response
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "Ticket created successfully. Doctype: ERP_Tickets - ID: ERP_I_0001"
}
```

### Missing Fields
```
"Raise a ticket."

Response:
{
    "query_type": "erp",
    "status": "missing",
    "missing_fields": ["app_name", "priority", "module", "description"],
    "message": "I just need: application name, priority, module, issue description"
}
```

---

## 💬 Creating Feedback

### Basic Syntax
```
Give feedback for app <APP_NAME> saying <FEEDBACK>. Rating <1-5>
```

### Rating Scale
- **1** – Poor
- **2** – Fair
- **3** – Good
- **4** – Very Good
- **5** – Excellent

### Examples

```
"Give feedback for app Finance. System is very responsive. Rating 5."

"Submit a review for HR app. Too many bugs. Rating 2."

"I want to give feedback for Inventory. Good but needs improvement. Rating 3."
```

### Response
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "Feedback created successfully. Doctype: ERP_Feedback_Suggestions - ID: FB_0001"
}
```

---

## 💡 Creating Suggestions

### Basic Syntax
```
Suggest an improvement for app <APP_NAME> priority <PRIORITY>. Feedback: <SUGGESTION>. Helps: <BENEFIT>
```

### Priorities
- **Low** – Nice-to-have
- **Medium** – Useful
- **High** – Important

### Examples

```
"Suggest an improvement for Finance priority High. Add export to PDF. Helps: users download reports."

"Submit an idea for Payroll priority Medium. Auto-calculate deductions. Helps: saves time."

"Suggest enhancement for HR priority Low. Dark mode theme. Helps: reduce eye strain."
```

### Response
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "Suggestion created successfully. Doctype: ERP_Feedback_Suggestions - ID: SUG_0001"
}
```

---

## 📊 List Operations

### List My Tickets
```
"Show my ERP tickets"
"List my support tickets"
"Show my ticket history"
```

**Response:**
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "Found 3 record(s). Showing 3:\nERP_I_0001 | Finance | P0 | Yet To Start | 2026-05-20\nERP_I_0002 | HR | P1 | In Progress | 2026-05-18\n..."
}
```

### List Feedback
```
"Show ERP feedback"
"List my feedback reviews"
"View feedback for ERP apps"
```

### List Suggestions
```
"Show my ERP suggestions"
"List suggestions I raised"
"Show my suggestion history"
```

### List Available Apps
```
"List available apps"
"What apps can I raise tickets for?"
"Show valid app names"
```

**Response:**
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "Found 8 ERP Support app(s):\nApp1 | modules: Module1, Module2\nApp2 | modules: Module3\n..."
}
```

---

## 👀 View Details

### View Single Record
```
"Show details for ERP_I_1234"
"View ticket ERP_I_0001"
"Get details for feedback FB_0001"
```

**Response:**
```json
{
    "query_type": "erp",
    "status": "ok",
    "message": "ID: ERP_I_1234\nApp: Finance\nType: Ticket\nPriority: P0\nStatus: Yet To Start\nModule: Dashboard\n..."
}
```

---

## ✅ Troubleshooting

### Error: "Could not find Application Name: XYZ"
- **Cause:** App doesn't exist in your system
- **Solution:** Run "List available apps" to see valid app names

### Error: Missing Fields
- **Cause:** Didn't provide required information
- **Solution:** Check error message for required fields, then provide them

### Error: "No tickets found"
- **Cause:** You haven't created any tickets yet
- **Solution:** Create a ticket first with "Raise a ticket..."

---

## 🎯 Field Reference

| Field | Required | Example | Notes |
|-------|----------|---------|-------|
| app_name | Yes | Finance | Check "List available apps" |
| priority | Yes | P0 | P0-P3 for tickets |
| module | Yes | Dashboard | Part of the app |
| description | Yes | Not loading | What's the issue? |
| feedback | Yes | Great system | User opinion |
| ratings | Yes | 5 | 1-5 stars |
| helps | Yes | Saves time | How does this help? |

---

**Version:** 1.0  
**Last Updated:** 25 May 2026  
**Status:** Production Ready
