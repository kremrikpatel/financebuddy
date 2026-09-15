# Contributing to FinanceBuddy

First off, thank you for considering contributing to FinanceBuddy! It's people like you that make this tool great. 

## 🚀 Getting Started

To get started with local development, the easiest method is to use the provided setup scripts. These handle Docker orchestration, virtual environments, dependency installation, and database migrations.

**Windows:**
```powershell
.\setup.ps1
```

**macOS/Linux:**
```bash
./setup.sh
```

If you prefer to set up manually, refer to the `README.md` for manual build instructions and the `Makefile` for handy aliases.

## 🛠️ Development Workflow

### Branching Strategy
- **`main`**: The stable, production-ready branch.
- **`feature/your-feature-name`**: Use this format for new features.
- **`bugfix/issue-description`**: Use this format for bug fixes.

### Making Changes
1. **Fork the repository** (if you don't have write access).
2. **Create a branch** for your feature or fix.
3. **Write tests** for your changes. We aim for high coverage, especially for financial domain logic.
4. **Implement your changes**. Keep commits atomic and descriptive.
5. **Run the test suite and linters** (see below) to ensure everything passes.
6. **Open a Pull Request** against the `main` branch. Provide a clear description of the problem solved and the approach taken.

## 🏗️ Project Structure Guidelines

When adding new code, please adhere to the existing architectural boundaries:

### Backend (`server/`)
- `app/api/`: All FastAPI routing and HTTP transport logic. Keep this thin.
- `app/services/`: Core business logic (budgeting, categorizing, importers). Services should be unit-testable independently of the API layer.
- `app/ai/`: LangGraph agents, RAG pipelines, LLM fallback logic, and PII masking.
- `app/models/`: SQLAlchemy ORM definitions.
- `app/schemas/`: Pydantic models for validation and serialization.

### Frontend (`apps/web/`)
- `src/components/`: Reusable, stateless UI primitives (Tailwind).
- `src/pages/`: Stateful, routed container components.
- `src/stores/`: Zustand state management.
- `src/lib/`: API clients and ZK Vault cryptographic logic.
- `src/i18n/`: Translation files. **Always externalize user-facing strings!**

## 🧪 Testing

We require tests for all new features and bug fixes. The test suite is designed to be 100% offline-capable (no LLM API keys required).

**Run the backend test suite:**
```bash
cd server
pytest -v
```

Tests are organized into tiers:
- **Tier 1:** Feature Coverage
- **Tier 2:** Boundaries & Corners
- **Tier 3:** Cross-feature interactions
- **Tier 4 & 5:** E2E Scenarios & Adversarial tests

## 📝 Coding Standards

### Backend (Python)
- We use **Ruff** for linting and formatting. 
- Run the linter before submitting code:
  ```bash
  cd server
  ruff check app tests
  ruff format app tests
  ```
- Use Python 3.11+ type hints religiously.

### Frontend (TypeScript/React)
- We use strict TypeScript. Ensure `npm run build` (which runs `tsc --noEmit`) passes without errors.
- Adhere to the existing Tailwind CSS design system.
- Use `react-i18next` for all strings. Do not hardcode English text into the JSX.

## 💬 Communication
If you're proposing a major architectural change or a large feature, please open an Issue first to discuss the design before writing code. This saves everyone time!

Thank you for contributing! 💰
