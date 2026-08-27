# FinanceBuddy

AI-powered, privacy-first personal finance platform. One codebase → **Windows, macOS, Linux, iOS, Android, Web** (Tauri 2 + React), backed by a production-grade FastAPI + LangGraph AI engine.

## Feature Map

| Requirement | Implementation |
|---|---|
| Bank aggregation | Plaid (US) · GoCardless Bank Account Data (EU/UK) · Basiq (AU) · CSV / OFX import · OCR receipt scan |
| Conversational AI | LangGraph multi-agent supervisor, WebSocket chat, Web Speech voice in/out, custom prompts |
| Smart categorization | Rules + embedding kNN (pgvector) + LLM fallback, learns from every user edit; multi-item split detection |
| Predictive budgeting | Holt trend cash-flow forecast, envelope & zero-based budgets, overspend warnings via event pipeline |
| Goals & debt | Auto-adjusting savings strategies, snowball/avalanche payoff simulators, dynamic progress tracking |
| Anomaly/fraud | EWMA/z-score baselines, duplicate-charge & duplicate-subscription detection, real-time alerts |
| Cash-flow coach | Dedicated coach agent with forecasting/budget tools over chat and voice |
| Expense assistant | Natural-language quick-add (`"12.40 coffee at Starbucks"`) with voice dictation |
| Multi-currency | 150+ currencies, daily FX cache, per-account currency, minor-unit safe math |
| UI/UX | Tailwind design system, dark/light, motion, charts, accessible primitives |
| i18n | EN/ES/FR/DE/HI/AR (+RTL) via react-i18next |

## Security & Compliance
- **Zero-knowledge vault**: master password → Argon2id KEK → wraps a random data key client-side (WebCrypto AES-GCM). Server only ever stores the wrapped key + salt. Sensitive free-text fields are E2E encrypted.
- **Auth**: OAuth2 JWT access+rotating refresh, TOTP MFA + recovery codes, WebAuthn passkeys/biometrics.
- **PII masking**: regex+Luhn detector masks emails/phones/cards/IBANs/account numbers before anything reaches an LLM or log.
- **Server-side envelope encryption** (AES-256-GCM) for tokens/secrets at rest.

## Architecture
```
apps/web        React 18 + Vite + TS frontend (shared by web + Tauri)
apps/desktop    Tauri 2 shell (desktop + mobile targets)
server          FastAPI · SQLAlchemy async · PostgreSQL+pgvector · Redis Streams
  app/ai        LangGraph agents, RAG, multi-provider LLM fallback router
  app/services  Domain engines (categorization, budgeting, fraud, ...)
  workers       Event pipeline consumer (real-time alerts)
docker-compose.yml  postgres+pgvector, redis, api, worker, web
evals           Ragas / Deepchecks / Opik harnesses
```

## Quick Start (dev)

```bash
# 1. Infra
docker compose up -d postgres redis

# 2. Backend
cd server
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed                                   # demo data
uvicorn app.main:app --reload --port 8000            # http://localhost:8000/docs

# 3. Worker (event pipeline)
python -m app.workers.event_consumer

# 4. Frontend
cd ../apps/web
npm install
npm run dev                                          # http://localhost:5173
```

Demo login: `demo@financebuddy.app` / `DemoPass123!` (MFA off).

### Desktop/mobile build (Tauri)
```bash
cd apps/desktop
npm install
npm run tauri dev     # desktop
npm run tauri ios dev # iOS   (macOS + Xcode)
npm run tauri android init && npm run tauri android dev
```

## LLM providers (fallback chain, any subset works)
`OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` → `OLLAMA_BASE_URL` (local). With zero keys the app still runs: deterministic local embedder + rules-based categorization; chat degrades gracefully.

## Observability
Langfuse / Phoenix / LangSmith tracing activate by env vars (see `.env.example`). Eval harnesses live in `server/evals` (Ragas RAG faithfulness, Deepchecks data checks) and run against a running stack.

## Compliance notes
PII masking applies to every agent/tool boundary and log sink. Audit log records auth events and data exports. Field-level encryption for bank tokens; zero-knowledge vault for user-authored content.
