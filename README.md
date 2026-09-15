# 💰 FinanceBuddy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/React-18-blue.svg)](https://reactjs.org/)
[![Tauri](https://img.shields.io/badge/Tauri-2.0-orange.svg)](https://tauri.app/)

**FinanceBuddy** is an AI-powered, privacy-first personal finance platform. Designed with a single cohesive codebase, it runs natively on **Windows, macOS, Linux, iOS, Android, and the Web**. 

Backed by a production-grade FastAPI + LangGraph AI engine, FinanceBuddy acts as your intelligent financial co-pilot, categorizing spending, forecasting cash flow, detecting anomalies, and offering conversational money coaching.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🏦 **Bank Aggregation** | Sync via Plaid (US), GoCardless (EU/UK), Basiq (AU), or manual CSV/OFX import. Includes OCR receipt scanning. |
| 🤖 **Conversational AI** | LangGraph multi-agent supervisor offering WebSocket chat, Web Speech voice in/out, and custom financial prompts. |
| 🏷️ **Smart Categorization** | Rules + pgvector kNN embeddings + LLM fallback. Automatically learns from your manual edits and detects multi-item splits. |
| 📈 **Predictive Budgeting** | Holt-trend cash flow forecasting, envelope & zero-based budgeting, and overspend warnings via a real-time event pipeline. |
| 🎯 **Goals & Debt** | Auto-adjusting savings strategies, snowball/avalanche payoff simulators, and dynamic progress tracking. |
| 🚨 **Fraud Detection** | EWMA/z-score baselines detecting duplicate charges, redundant subscriptions, and sudden spending spikes. |
| 🎙️ **Expense Assistant** | Natural-language quick-add (e.g., *"12.40 coffee at Starbucks"*) with voice dictation support. |
| 🌍 **Global Support** | 150+ currencies, daily FX cache, per-account currency settings. Fully internationalized (EN/ES/FR/DE/HI/AR + RTL support). |

## 🔒 Security & Compliance

We take financial data seriously. FinanceBuddy is built on a **Zero-Knowledge Architecture**:
- **Client-Side Vault**: Your master password generates an Argon2id Key Encryption Key (KEK) which wraps a random data key via WebCrypto AES-GCM. The server *only* stores the wrapped key and salt.
- **End-to-End Encryption**: Sensitive free-text fields and notes are encrypted before leaving your device.
- **Authentication**: OAuth2 JWT (access + rotating refresh), TOTP MFA + recovery codes, WebAuthn passkeys (biometrics).
- **PII Masking**: Robust regex + Luhn detector masks emails, phones, cards, and IBANs before any data reaches an LLM.

## 🏗️ Architecture Stack

- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Zustand, react-i18next.
- **Desktop/Mobile**: Tauri 2 shell wrapping the web app.
- **Backend API**: FastAPI, SQLAlchemy (async).
- **AI Engine**: LangGraph, LangChain, Multi-provider fallback (OpenAI → Anthropic → Google → Ollama).
- **Infrastructure**: PostgreSQL + pgvector, Redis Streams (event pipeline), Docker.

---

## 🚀 Quick Start (One-Command Setup)

We have provided automated scripts that handle everything: checking prerequisites, starting Docker, creating virtual environments, installing dependencies, migrating the database, and seeding demo data.

### Windows (PowerShell)
```powershell
.\setup.ps1
```

### macOS / Linux (Bash)
```bash
./setup.sh
```

**What the script does:**
1. Starts PostgreSQL and Redis via Docker Compose.
2. Installs Python dependencies (Backend) and NPM packages (Frontend).
3. Applies database migrations and seeds demo data.
4. Launches the API at `http://localhost:8000` and the Web UI at `http://localhost:5173`.

**Demo Credentials:**
- **Email:** `demo@financebuddy.app`
- **Password:** `DemoPass123!`

---

## 🛠️ Manual Development Setup

If you prefer to run things manually, follow our detailed guides in the [Contributing Guidelines](CONTRIBUTING.md).

### Desktop/Mobile Build (Tauri)
```bash
cd apps/desktop
npm install
npm run tauri dev             # Desktop
npm run tauri ios dev         # iOS (macOS + Xcode required)
npm run tauri android dev     # Android
```

## 📊 Observability & LLMs

- **LLM Fallback**: The app requires at least one LLM key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`) for AI features, but **gracefully degrades** to deterministic local embedding and rules-based logic if no keys are provided.
- **Tracing**: Langfuse, Phoenix, or LangSmith can be activated via `.env`.
- **Evals**: Evaluation harnesses live in `server/evals/` (Ragas RAG faithfulness, Deepchecks).

## 🤝 Contributing

We welcome contributions! Whether it's reporting bugs, improving documentation, or writing code, please read our [Contributing Guidelines](CONTRIBUTING.md) to get started.

## 📄 License

This project is licensed under the MIT License.
