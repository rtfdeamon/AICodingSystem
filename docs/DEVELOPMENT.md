# Development Guide

## Environment Setup

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Required tools:
- `pytest` + `pytest-asyncio` + `pytest-cov` for testing
- `ruff` for linting and formatting
- `mypy` for type checking

### Frontend

```bash
cd frontend
npm install
```

Required tools:
- `vitest` for unit testing
- `eslint` for linting
- `vite` for development server and builds

### Database

For local development with Docker:
```bash
docker compose -f infra/docker-compose.yml up postgres redis -d
cd backend
alembic upgrade head
```

For testing, SQLite in-memory databases are used automatically (no setup needed).

## Code Quality Standards

### Backend

All code must pass these checks before committing:

```bash
# Tests (831 tests, target: 0 failures)
backend/.venv/bin/pytest -q

# Coverage (target: >= 95%)
backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q

# Lint (target: 0 issues)
backend/.venv/bin/ruff check backend/app backend/tests

# Type check (target: 0 issues)
backend/.venv/bin/mypy backend/app --ignore-missing-imports
```

### Frontend

```bash
cd frontend
npx vitest run       # Tests (54 tests)
npm run lint         # ESLint
npm run build        # TypeScript compilation check
```

### Ruff Configuration

The project uses ruff with these rule sets:
- `E`/`W`: pycodestyle
- `F`: pyflakes
- `I`: isort
- `N`: pep8-naming
- `UP`: pyupgrade
- `B`: flake8-bugbear
- `S`: flake8-bandit (security)
- `T20`: flake8-print
- `SIM`: flake8-simplify
- `PLW`: pylint warnings

Line length: 100 characters. Target: Python 3.12.

## Testing Conventions

### Backend Test Structure

```
backend/tests/
├── conftest.py              # Shared fixtures (db_session, async_client, factories)
├── test_main.py             # App factory, health check, WebSocket
├── test_database.py         # Database initialization
├── test_redis.py            # Redis connection
├── test_agents/             # AI agent tests
├── test_api/                # API endpoint tests (one file per endpoint module)
├── test_ci/                 # CI/CD module tests
├── test_context/            # Context engine tests
├── test_git/                # Git operation tests
├── test_middleware/          # Middleware tests
├── test_services/           # Service layer tests
└── test_workflows/          # Pipeline workflow tests
```

### Key Fixtures (conftest.py)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | function | In-memory SQLite async session |
| `async_client` | function | httpx AsyncClient wired to FastAPI app |
| `create_test_user` | function | Factory: creates User with configurable role |
| `create_test_project` | function | Factory: creates Project |
| `create_test_ticket` | function | Factory: creates Ticket |
| `auth_headers` | function | JWT Authorization headers |

### Test Patterns

```python
# Async test with database
@pytest.mark.asyncio
async def test_create_ticket(async_client: AsyncClient, auth_headers: dict):
    response = await async_client.post(
        "/api/v1/tickets",
        json={"title": "Test", "project_id": "..."},
        headers=auth_headers,
    )
    assert response.status_code == 201

# Mocking external services
@pytest.mark.asyncio
async def test_planning_agent(db_session):
    with patch("app.agents.router.route_task") as mock_route:
        mock_route.return_value = mock_agent
        result = await generate_plan(ticket, project_id, context, db_session)
```

### Important Notes

- Use `@pytest.mark.asyncio` only on async test functions (not sync ones)
- Classes named `Test*` in source code (not tests) need `__test__ = False` to prevent pytest collection warnings
- `asyncio_mode = "auto"` is configured in pyproject.toml
- filterwarnings ignores DeprecationWarning by default

## Adding New Features

### New API Endpoint

1. Create handler in `backend/app/api/v1/<module>.py`
2. Add Pydantic schemas in `backend/app/schemas/`
3. Register router in `backend/app/api/v1/router.py`
4. Write tests in `backend/tests/test_api/test_<module>.py`
5. Add frontend API client in `frontend/src/api/<module>.ts`

### New AI Agent

1. Subclass `BaseAgent` in `backend/app/agents/`
2. Implement `async def execute()` method
3. Register in `backend/app/agents/router.py`
4. Add fallback behavior for missing API keys
5. Write tests with mocked API responses

### New Database Model

1. Define model in `backend/app/models/<model>.py`
2. Add `__test__ = False` if class name starts with `Test`
3. Create Alembic migration: `alembic revision --autogenerate -m "description"`
4. Add Pydantic schemas
5. Write tests

## CI/CD Pipelines

### GitHub Actions

**Backend CI** (`.github/workflows/ci-backend.yml`):
- Python 3.12 setup
- Dependency installation
- Ruff lint check
- Mypy type check
- Pytest with coverage

**Frontend CI** (`.github/workflows/ci-frontend.yml`):
- Node.js 20 setup
- npm install
- ESLint check
- Vitest run
- Vite build

## Debugging

### Backend

```bash
# Run with auto-reload
uvicorn app.main:app --reload --port 8000

# Run specific test with verbose output
backend/.venv/bin/pytest backend/tests/test_api/test_tickets.py -v

# Run tests matching a pattern
backend/.venv/bin/pytest -k "test_create" -v
```

### Frontend

```bash
cd frontend
npm run dev          # Development server with HMR
npx vitest --ui      # Interactive test UI
```

### Docker

```bash
docker compose -f infra/docker-compose.yml logs -f backend   # Follow backend logs
docker compose -f infra/docker-compose.yml exec postgres psql -U ai_coding  # DB shell
docker compose -f infra/docker-compose.yml exec redis redis-cli  # Redis shell
```
