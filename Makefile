.PHONY: infra api worker web seed migrate test lint dev demo demo-down prod prod-down

infra:
	docker compose up -d postgres redis

migrate:
	cd server && alembic upgrade head

seed:
	cd server && python -m app.seed

api:
	cd server && uvicorn app.main:app --reload --port 8000

worker:
	cd server && python -m app.workers.event_consumer

web:
	cd apps/web && npm run dev

test:
	cd server && pytest -q

lint:
	cd server && ruff check app tests

dev: infra

# Demo stack: own DB/Redis, seeded demo@financebuddy.app / DemoPass123!
demo:
	./start-demo.sh

demo-down:
	./start-demo.sh --down

# Production stack: own DB/Redis, generated secrets, reference data only (no demo user)
prod:
	./start-prod.sh

prod-down:
	./start-prod.sh --down
