.PHONY: dev dev-down migrate migration test lint build clean logs shell-backend shell-db

COMPOSE := docker compose -f infra/docker-compose.yml
BACKEND_EXEC := $(COMPOSE) exec backend

dev:
	$(COMPOSE) up --build

dev-down:
	$(COMPOSE) down

migrate:
	$(BACKEND_EXEC) alembic upgrade head

migration:
	$(BACKEND_EXEC) alembic revision --autogenerate -m "$(msg)"

test:
	$(BACKEND_EXEC) pytest -v --tb=short

lint:
	$(BACKEND_EXEC) ruff check .
	$(BACKEND_EXEC) ruff format --check .

lint-fix:
	$(BACKEND_EXEC) ruff check --fix .
	$(BACKEND_EXEC) ruff format .

build:
	$(COMPOSE) build

clean:
	$(COMPOSE) down -v --remove-orphans

logs:
	$(COMPOSE) logs -f

shell-backend:
	$(BACKEND_EXEC) /bin/sh

shell-db:
	$(COMPOSE) exec postgres psql -U aicoding -d aicoding
