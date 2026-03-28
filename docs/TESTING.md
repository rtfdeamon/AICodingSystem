# Testing Guide

## Overview

| Layer | Framework | Tests | Coverage |
|-------|-----------|-------|----------|
| Backend | pytest + pytest-asyncio | 3272 | 96% |
| Frontend | Vitest + React Testing Library | 138 | - |
| E2E | Playwright | 8 | - |
| Lint | ruff (backend), ESLint (frontend) | 0 issues | - |
| Types | mypy (backend), tsc (frontend) | 0 errors | - |

## Running Tests

### Backend

```bash
# All tests
backend/.venv/bin/pytest -q

# With coverage report
backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q

# Specific test file
backend/.venv/bin/pytest backend/tests/test_api/test_webhooks.py -v

# Linting
backend/.venv/bin/ruff check backend/app backend/tests

# Type checking
backend/.venv/bin/mypy backend/app --ignore-missing-imports
```

### Frontend

```bash
cd frontend

# All tests
npx vitest run

# Watch mode
npx vitest

# Build (includes TypeScript check)
npm run build

# TypeScript only
npx tsc --noEmit
```

### E2E

```bash
cd e2e

# Install browsers
npx playwright install chromium

# Run tests
npx playwright test
```

## Backend Test Structure

```
backend/tests/
├── conftest.py              # Shared fixtures (async_client, db_session, auth)
├── test_config.py           # Application configuration and security checks
├── test_database.py         # Database initialization and connection
├── test_main.py             # App factory, health check, WebSocket, exception handlers
├── test_redis.py            # Redis pool lifecycle
├── test_agents/             # AI agent tests (planning, coding, review, security, router)
├── test_api/                # API endpoint tests (all v1 routes)
├── test_ci/                 # CI/CD component tests (builder, deployer, scanner, runner)
├── test_context/            # Code indexing and search tests
├── test_git/                # GitHub client and repo manager tests
├── test_middleware/          # Rate limiter and logging middleware tests
├── test_quality/            # Quality modules (PII, duplication, feedback, test selector, guardrail, sandbox, optimizer, consensus, gateway)
├── test_services/           # Business logic tests (auth, kanban, dashboard, WebSocket)
└── test_workflows/          # Pipeline orchestrator and state machine tests
```

### Key Coverage Targets

| Module | Coverage | Notes |
|--------|----------|-------|
| config.py | 100% | Production secrets validation |
| kanban_service.py | 100% | All transitions, RBAC, prerequisites |
| notification_service.py | 100% | All channels (in-app, Slack, Telegram) |
| state_machine.py | 100% | All transition rules and side effects |
| websocket_manager.py | 100% | Subscribe, publish, Redis failure handling |
| rate_limiter.py | 100% | Sliding window, profiles, Redis errors |
| auth_service.py | 100% | Token creation, verification, password hashing |
| pipeline_orchestrator.py | 99% | All workflow stages, retry handling |

### Test Conventions

- All async tests use `@pytest.mark.asyncio` decorator (not module-level `pytestmark`)
- Test data uses factory functions in each test file (no `factory_boy` dependency)
- Database tests use SQLite in-memory for speed
- AI agent tests mock external API calls
- Hardcoded test secrets use constants with `# noqa: S105`/`# noqa: S106` suppression
- Classes that collide with pytest collection use `__test__ = False`

## Frontend Test Structure

```
frontend/src/test/
├── components/
│   ├── auth/         # LoginPage, RegisterPage tests
│   ├── kanban/       # KanbanBoard tests (DnD, WebSocket, project init)
│   ├── tickets/      # TicketDetail tests (tabs, artifact fetch)
│   ├── dashboard/    # MetricsDashboard tests (project_id verification)
│   └── common/       # Badge, Button, Spinner tests
└── setup.ts          # Test environment setup
```

### Frontend Test Conventions

- Use React Testing Library (`@testing-library/react`)
- Mock stores with Zustand's `create()` in test setup
- Mock API calls with `vi.mock('../../api/...')`
- Test component rendering, user interactions, and error states
- Verify no hardcoded `project_id='default'` is sent to API

## Security Tests

Security-specific test coverage:

- **Path traversal**: `test_upload_sanitises_path_traversal_filename`, `test_upload_sanitises_null_byte_filename`
- **Webhook verification**: `test_github_webhook_no_secret_set` (503), `test_github_webhook_invalid_signature` (401), `test_github_webhook_valid_signature` (200)
- **RBAC enforcement**: developer cannot deploy to production, viewer cannot create tickets
- **Auth**: invalid credentials rejected, token expiry handled, password hashing verified
- **Config validation**: production secrets warning on startup
- **PII monitoring**: 28 tests covering 10 PII types, redaction, allowlist, confidence filtering
- **Duplication detection**: 10 tests for block detection, metrics, edge cases
- **Feedback tracking**: 14 tests for record/retrieve/aggregate/clear
- **Test selection**: 13 tests for source-to-test mapping, conftest, fallback, metrics
- **Agent sandbox**: 38 tests for filesystem, network, command, env, quota, rollback
- **Prompt optimizer**: 35 tests for A/B testing, regression detection, improvement suggestions
- **Multi-agent consensus**: 40 tests for voting strategies, deliberation, diversity scoring
- **Tool gateway**: 19 tests for circuit breaker, rate limiting, auth, schema validation
