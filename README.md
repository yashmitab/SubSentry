# 🛡️ SubSentry — Intelligent Subscription, Price-Hike & Free-Trial Guardian

**SubSentry** is a smart personal finance web application designed to stop silent financial leaks. Every year, consumers lose money to forgotten auto-renewals, stealth subscription price increases buried in bank statements, and free trials that silently convert into paid plans. SubSentry brings reactive statement auditing, AI-powered financial insights, and proactive free-trial alerts into a single, intuitive dashboard.

🎥 **Video Walkthrough:** [Watch the 4-Minute Demo on YouTube](https://youtu.be/mGSfMN_A-uY)

---

## ✨ Key Features

### 1. 🔐 Secure Workspace & Quick-Jump Navigation
* **User Authentication:** Clean sign-in and sign-up flow (including instant demo access via `demo@subsentry.in`).
* **Interactive KPI Cards:** Top-level summary metrics act as smooth-scrolling quick-navigation anchors, letting users jump directly to detected recurring payments, price hikes, or trial alerts without endless scrolling.

### 2. 🔄 Automated Recurring Payment Detection
* **Statement Parsing:** Upload bank or credit card transaction statements (CSV/statement exports) for instant analysis.
* **Pattern Recognition:** Automatically filters out one-off purchases to isolate true recurring subscriptions, breaking down merchant names, billing cycles, and monthly/annual financial impact.

### 3. 📈 Price-Hike Detective
* **Historical Rate Comparison:** Compares recurring charges for the same merchant across billing cycles.
* **Stealth Increase Alerts:** Flags any subscription whose price quietly increased compared to its previous baseline, displaying the old rate, new rate, and exact jump so users never overpay unnoticed.

### 4. 🎛️ "What-If" Savings Simulator
* **Interactive Scenario Planning:** Toggle off underused subscriptions in real time to immediately calculate projected monthly and annual savings before making cancellation decisions.

### 5. 🤖 Built-in Gemini AI Financial Assistant
* **Natural-Language Q&A:** Powered by the Google Gemini API, users can ask plain-English questions about their uploaded statement—such as *"Which subscriptions should I cancel first?"* or *"Where am I spending the most?"*—and receive tailored, data-backed recommendations.

### 6. ⏳ Free-Trial Trap Catcher & Cancellation Guide
* **Proactive Protection:** Paste any free-trial confirmation email or SMS (whether it lists a specific calendar date or a relative window like *"7-day"* or *"14-day free trial"*).
* **Automated Extraction & Reminders:** Extracts the service name, post-trial recurring charge, exact expiry date, first expected bank charge date, and sets a 2-day advance cancellation reminder.
* **Guided Cancellation:** Provides clear cancellation tracking and actionable opt-out steps so users cancel before the billing deadline.

---

## 🛠️ Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend & UI** | Python, Streamlit (with custom CSS styling & smooth anchor navigation) |
| **Data Processing** | Pandas (transaction normalization, billing cycle & price-delta analysis) |
| **AI & NLP Engine** | Google Gemini API (`google-genai`) |
| **Deployment** | Streamlit Community Cloud & GitHub |

---
