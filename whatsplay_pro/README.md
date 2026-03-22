# WhatsPlay Pro v1.0.0 🚀
### Professional-Grade WhatsApp Automation & AI-Powered CRM Desktop System

WhatsPlay Pro is a production-grade PyQt6 application designed for advanced WhatsApp automation. It integrates Playwright-based browser automation with AI chatbots, bulk messaging engines, and a full CRM for message logging and contact management.

---

## 🧱 Key Features

- **Robust WhatsApp Client (WhatsPlay Engine)**: Built on Playwright for stable and anti-ban browser automation.
- **AI Chatbot Integration**: Pluggable architecture supporting OpenAI GPT-4 for context-aware auto-replies.
- **Advanced CRM**: SQLite-backed contact and message management with SQL querying.
- **Bulk Messaging Engine**: CSV-based campaigns with variable templates and random delays for safety.
- **Async Scheduler**: Schedule one-time or recurring messages in a background thread.
- **Modern UI/UX**: Dark mode PyQt6 interface with sidebar navigation and dashboard monitoring.
- **Anti-Ban Safety**: Human-like interaction modeling with configurable delay randomness.

---

## 🛠️ System Architecture

The project follows a clean, modular, and layered architecture:

- `bot/`: The core WhatsApp engine and event handling layer.
- `ai/`: Pluggable AI chatbot system with context tracking.
- `crm/`: Data persistence layer (SQLAlchemy/SQLite).
- `automation/`: Bulk sending and scheduling engines.
- `gui/`: Professional PyQt6 UI components and background workers.
- `core/`: Configuration, centralized signaling, and structured logging.

---

## 🚀 Setup Instructions

### 1. Prerequisites
- Python 3.9 - 3.12
- Node.js (for Playwright engine)

### 2. Clone and Install
```bash
# Clone the repository (if applicable)
# Navigate to project directory
cd whatsplay_pro

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 3. Configuration
1. Copy `.env.example` to `.env`.
2. Configure your `OPENAI_API_KEY` and other settings in the `.env` file.

### 4. Run Application
```bash
python main.py
```

---

## ⚙️ Concurrency Model

WhatsPlay Pro uses a sophisticated concurrency model to ensure a smooth UI experience:
- **Main Thread**: Dedicated to the PyQt6 event loop and UI rendering.
- **Background Worker (QThread)**: Manages a dedicated `asyncio` event loop.
- **Asyncio Loop**: Orchestrates the Playwright browser, outgoing message queues, and AI processing without blocking the GUI.
- **PyQt Signals**: Used for safe cross-thread communication between the async backend and the UI frontend.

---

## 🔐 Security & Compliance
- This tool is designed for **legitimate business automation** and CRM management.
- Always respect WhatsApp's Terms of Service.
- Avoid aggressive bulk messaging which can lead to account bans.
- Use the built-in **Anti-Ban Safety** settings (random delays) to simulate human behavior.

---

## 📝 License
Proprietary / Commercial License. See LICENSE file for details.
