.PHONY: up down logs ps test lint migrate seed contention-test clean

# ── Stack ─────────────────────────────────────────────────────────────────────
up:
	docker compose up --build -d
	@echo "API      → http://localhost:8000/docs"
	@echo "Grafana  → http://localhost:3000  (admin/admin)"
	@echo "Prometheus → http://localhost:9090"

down:
	docker compose down

logs:
	docker compose logs -f api

ps:
	docker compose ps

# ── DB ────────────────────────────────────────────────────────────────────────
migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed.py

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest tests/ -v --tb=short

# ── Benchmarks ───────────────────────────────────────────────────────────────
benchmark:
	k6 run k6/scripts/benchmark.js

contention-test:
	@echo "Usage: make contention-test SLOT_ID=<uuid> TOKEN=<jwt>"
	k6 run \
	  -e SLOT_ID=$(SLOT_ID) \
	  -e TOKEN=$(TOKEN) \
	  k6/scripts/contention_test.js

# ── Dev ───────────────────────────────────────────────────────────────────────
lint:
	docker compose exec api ruff check app/

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
