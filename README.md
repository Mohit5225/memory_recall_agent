Skip to content
Mohit5225
memory_recall_agent
Repository navigation
Code
Issues
Pull requests
3
 (3)
Agents
Actions
Projects
Security
Insights
Settings
Add root-level README.md and .env.example
#3
Draft
Copilot
wants to merge 2 commits into
main2
from
copilot/create-readme-and-env-example
+219
Lines changed: 219 additions & 0 deletions
Conversation0 (0)
Commits2 (2)
Checks1 (1)
Files changed2 (2)
Pull Request Toolbar
Draft
Add root-level README.md and .env.example
#3
Copilot
wants to merge 2 commits into
main2
from
copilot/create-readme-and-env-example
0 / 2 viewed
Filter files…
File tree
.env.example
README.md
‎.env.example‎
+38
Lines changed: 38 additions & 0 deletions
Original file line number	Original file line	Diff line number	Diff line change
# ─────────────────────────────────────────────────────────────────────────────
# Memory Recall Agent — Environment Variables
# Copy this file to .env and fill in your actual values.
# Never commit .env to version control.
# ─────────────────────────────────────────────────────────────────────────────
# ── Google Gemini ──────────────────────────────────────────────────────────────
GOOGLE_API_KEY=your_google_ai_studio_api_key
# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGODB_CONNECTION_STRING=mongodb+srv://<user>:<password>@cluster.mongodb.net/
DB_NAME=your_llm_agent_db
COLLECTION_NAME=user_settings
# ── Session / JWT ──────────────────────────────────────────────────────────────
# Must be at least 32 characters
secret_key=your_super_secret_session_key_minimum_32_chars
# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_URL=redis://localhost:6379/0
# ── Upstash Redis (OTP storage) ────────────────────────────────────────────────
OTP_REDIS_URL=https://your-upstash-redis-url.upstash.io
OTP_REDIS_TOKEN=your_upstash_redis_token
# ── Twilio ─────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
# ── OpenRouter (fallback LLM) ──────────────────────────────────────────────────
OPENROUTER_SECRET_KEY=your_openrouter_secret_key
# ── Frontend ───────────────────────────────────────────────────────────────────
FRONTEND_BASE_URL=http://localhost:3000
‎README.md‎
+181
Lines changed: 181 additions & 0 deletions


Original file line number	Original file line	Diff line number	Diff line change
# Memory Recall Agent
An AI-powered chat agent with **persistent memory** built on FastAPI, LangGraph, and Google Gemini. Users authenticate via Google OAuth, chat with an agent that remembers past conversations, and can set up scheduled WhatsApp reminders.
---
## Features
- 🧠 **Persistent Memory** — Conversation history stored in MongoDB; the agent recalls prior exchanges across sessions.
- 🔀 **LangGraph Orchestration** — Agent control flow managed as a stateful graph (intent parsing → LLM call → response).
- ✨ **Google Gemini Integration** — Primary LLM via `google-genai`; OpenRouter acts as a fallback provider.
- 🔐 **JWT Authentication** — HTTP-only cookie-based JWT issued after Google OAuth, with token blacklisting in Redis.
- ⏰ **Celery / Redis Task Queue** — Background workers dispatch scheduled WhatsApp reminders via Twilio.
- 🖥️ **Next.js UI** — React front-end (`frontend-next/-app`) with Tailwind CSS.
---
## Tech Stack
| Layer | Technology |
|---|---|
| Backend framework | FastAPI + Uvicorn |
| Agent orchestration | LangGraph |
| Primary LLM | Google Gemini (`gemini-2.5-flash-lite`) |
| Fallback LLM | OpenRouter |
| Database | MongoDB (Motor async driver) |
| Cache / Broker | Redis |
| Task queue | Celery + Celery Beat |
| Auth | Google OAuth 2.0 + PyJWT |
| Notifications | Twilio (WhatsApp / SMS) |
| Frontend | Next.js 14, Tailwind CSS, TypeScript |
---
## Project Structure
```
memory_recall_agent/
├── main.py                  # FastAPI application entry point
├── requirements.txt
├── setup.py
├── celery_config/           # Celery app configuration
├── src/
│   ├── agent/               # LangGraph state + graph definition
│   ├── auth/                # Google OAuth, JWT utils, security helpers
│   ├── config/              # settings.py (env vars), constants
│   ├── core/                # Agent logic, scheduler, intent parser
│   ├── db/                  # MongoDB async client helpers
│   ├── llm/                 # Gemini & OpenRouter wrappers
│   ├── models/              # Pydantic models (Message, User, Schedule)
│   └── task.py              # Celery tasks
└── frontend-next/-app/      # Next.js frontend
```
---
## Environment Variables
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```
| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio API key for Gemini |
| `MONGODB_CONNECTION_STRING` | MongoDB Atlas (or local) connection URI |
| `DB_NAME` | MongoDB database name |
| `COLLECTION_NAME` | MongoDB collection for user settings |
| `secret_key` | Session secret (min 32 chars) |
| `REDIS_HOST` | Redis host (default: `localhost`) |
| `REDIS_PORT` | Redis port (default: `6379`) |
| `REDIS_URL` | Full Redis URL used by Celery broker/backend |
| `OTP_REDIS_URL` | Upstash Redis URL for OTP storage |
| `OTP_REDIS_TOKEN` | Upstash Redis auth token |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Twilio phone number (SMS) |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp sender number |
| `OPENROUTER_SECRET_KEY` | OpenRouter API key (fallback LLM) |
| `FRONTEND_BASE_URL` | Frontend origin, e.g. `http://localhost:3000` |
---
## Setup
### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis (running locally or via a managed service)
- MongoDB (Atlas or local)
### Backend
```bash
# 1. Clone the repository
git clone https://github.com/Mohit5225/memory_recall_agent.git
cd memory_recall_agent
# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
# 3. Install dependencies
pip install -r requirements.txt
# 4. Configure environment variables
cp .env.example .env
# Edit .env and fill in all required values
```
### Frontend
```bash
cd frontend-next/-app
# Install dependencies
npm install
# Configure environment (if needed)
# Create .env.local with NEXT_PUBLIC_API_URL=http://localhost:8000
# Start development server
npm run dev
```
---
## Running the Project
### 1. Start Redis
```bash
redis-server
```
### 2. Start the FastAPI backend
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
### 3. Start the Celery worker
```bash
celery -A celery_config.Celery_app.celery_app01 worker --loglevel=info
```
### 4. Start Celery Beat (scheduler)
```bash
celery -A celery_config.Celery_app.celery_app01 beat --loglevel=info
```
### 5. Start the Next.js frontend
```bash
cd frontend-next/-app
npm run dev
```
The API will be available at `http://localhost:8000` and the UI at `http://localhost:3000`.
---
## API Overview
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Welcome message |
| `GET` | `/api/v1/health` | Health check (DB ping) |
| `POST` | `/api/v1/chat` | Send a message to the agent |
| `GET` | `/api/v1/chat/history` | Retrieve recent chat history (JWT required) |
| `GET` | `/auth/google` | Initiate Google OAuth login |
| `GET` | `/auth/google/callback` | OAuth callback |
| `GET` | `/auth/me` | Get current user profile (JWT required) |
| `POST` | `/auth/logout` | Logout and revoke token |
| `POST` | `/auth/whatsapp` | Set / update WhatsApp number |
| `POST` | `/auth/verify-phone` | Verify WhatsApp OTP |
