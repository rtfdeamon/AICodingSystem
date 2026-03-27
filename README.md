# AI Coding Pipeline

An AI-driven software development pipeline that automates ticket-to-production workflows using multiple AI providers (Claude, GPT-4, Gemini). The system orchestrates planning, code generation, review, testing, and deployment through an 8-column Kanban board with human gates at critical decision points.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   React UI  │────▶│  FastAPI     │────▶│ PostgreSQL  │
│  (Vite/TS)  │◀────│  Backend    │◀────│  + pgvector │
└─────────────┘     └──────┬──────┘     └─────────────┘
       │                   │
       │ WebSocket         │ AI SDKs
       │                   ▼
       │            ┌─────────────┐     ┌─────────────┐
       └───────────▶│   Redis     │     │   n8n       │
                    │ Cache/PubSub│     │  Workflows  │
                    └─────────────┘     └─────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | FastAPI + SQLAlchemy 2.0 (async) | Python 3.12+ |
| Frontend | React 19 + TypeScript + Zustand | Vite 6+ |
| Database | PostgreSQL 16 + pgvector | Alembic migrations |
| Cache | Redis 7 | hiredis |
| AI | Anthropic, OpenAI, Google GenAI | Latest SDKs |
| Orchestration | n8n | Webhook-driven |
| Infrastructure | Docker Compose, Nginx, K8s | Production-ready |

## Pipeline Overview

The system implements an 8-stage Kanban pipeline:

```
Backlog → AI Planning → Plan Review* → AI Coding → Code Review* → Staging → Staging Verification → Production*
                         (human)                     (human)                                        (PM only)
```

Stages marked with `*` are human gates requiring explicit approval.

### AI Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| PlanningAgent | Decomposes tickets into implementation steps | Claude/GPT-4 |
| CodingAgent | Generates code from approved plans | Claude/GPT-4 |
| ReviewAgent | Automated code review with inline findings | Claude/GPT-4 |
| SecurityAgent | SAST scanning and vulnerability detection | Claude/GPT-4 |
| TestGenAgent | Auto-generates unit/integration tests | Claude/GPT-4 |
| GeminiAgent | Alternative provider for any stage | Gemini Pro |
| MetaReviewAgent | AI-on-AI review consolidation (3-layer review) | Claude |
| NegotiationAgent | Proposes alternatives on developer pushback | N/A |
| Router | Dynamic agent selection per task type | N/A |
| ModelRouter | Cost-aware multi-model routing with circuit breakers | N/A |

## Project Structure

```
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── agents/            # AI agent implementations (15 modules incl. model router)
│   │   ├── api/v1/            # REST API routes (24 endpoints)
│   │   ├── ci/                # CI/CD: builder, deployer, scanner, test runner, self-healing
│   │   ├── context/           # Code embeddings, AST parser, vector store, review context
│   │   ├── git/               # GitHub client, repo manager, diff parser
│   │   ├── middleware/        # Logging, rate limiting
│   │   ├── models/            # SQLAlchemy ORM models (19 models)
│   │   ├── observability/     # OpenTelemetry, agent tracing, eval tests, shadow A/B, drift detection
│   │   ├── quality/           # PII, hallucination, prompt versioning, token budget, escalation, cache
│   │   ├── schemas/           # Pydantic validation schemas
│   │   ├── services/          # Business logic (auth, kanban, dashboard...)
│   │   └── workflows/         # Pipeline orchestrator, state machine, retry
│   ├── tests/                 # 1425 tests, 96% coverage
│   └── alembic/               # Database migrations
├── frontend/                   # React + TypeScript frontend
│   └── src/
│       ├── components/        # Auth, Kanban, Tickets, Planning, Review...
│       ├── api/               # Axios API client modules
│       ├── stores/            # Zustand state management
│       ├── hooks/             # Custom React hooks
│       └── test/              # 138 Vitest tests
├── infra/                      # Infrastructure
│   ├── docker-compose.yml     # Full stack: PG, Redis, n8n, Nginx
│   ├── k8s/                   # Kubernetes manifests
│   ├── monitoring/            # Grafana dashboards
│   └── nginx/                 # Reverse proxy config
├── docs/                       # Documentation
│   ├── API_REFERENCE.md       # REST API reference
│   ├── ARCHITECTURE.md        # System architecture and design
│   ├── DEVELOPMENT.md         # Development setup and conventions
│   ├── SECURITY.md            # Security guide and hardening
│   └── TESTING.md             # Testing guide and coverage
├── e2e/                        # Playwright E2E tests
└── shared/                     # Shared constants and event types
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### Development Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd AiCodingSystem

# Copy environment configuration
cp .env.example .env
# Edit .env with your API keys and database credentials

# Start all services via Docker Compose
make dev

# Or run backend and frontend separately:

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Available Make Commands

```bash
make dev          # Start Docker Compose stack
make dev-down     # Stop all services
make migrate      # Run Alembic database migrations
make test         # Run backend pytest suite
make lint         # Run ruff linter
make lint-fix     # Auto-fix lint issues
make build        # Docker build
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | Secret for JWT tokens | (required) |
| `ANTHROPIC_API_KEY` | Claude API key | (optional) |
| `OPENAI_API_KEY` | OpenAI API key | (optional) |
| `GOOGLE_AI_API_KEY` | Google GenAI key | (optional) |
| `GITHUB_CLIENT_ID` | GitHub OAuth app ID | (optional) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth secret | (optional) |
| `N8N_WEBHOOK_URL` | n8n workflow trigger URL | (optional) |

AI provider keys are optional — the system gracefully degrades to mock/fallback responses when keys are not configured.

## Code Splitting

The frontend uses `React.lazy()` + `Suspense` to split every route-level page into its own chunk. Only the `AppShell` layout is loaded eagerly; everything else (LoginPage, KanbanBoard, TicketDetail, MetricsDashboard, etc.) is loaded on demand when the user navigates to that route.

```tsx
const KanbanBoard = lazy(() =>
  import('@/components/kanban/KanbanBoard').then((m) => ({ default: m.KanbanBoard })),
);
```

A shared `<FullPageSpinner />` is rendered as the `Suspense` fallback while chunks load. An `<ErrorBoundary>` at the root catches load failures and prevents blank screens.

## Production Hardening

The backend adapts its behaviour based on the `ENVIRONMENT` config variable (`development`, `staging`, or `production`):

| Behaviour | Development | Production |
|-----------|-------------|------------|
| OpenAPI docs (`/docs`, `/redoc`) | Enabled | Disabled |
| Exception detail in 500 responses | Full traceback | Sanitised `"Internal server error"` |
| Validation errors (422) | Field-level detail | Field-level detail (safe in all envs) |

Custom exception handlers are registered at application startup to enforce this.

## Structured Output Validation

AI agent responses are validated against Pydantic schemas before being consumed by the pipeline:

| Agent | Schema | Fields |
|-------|--------|--------|
| PlanningAgent | `PlanOutput` | `plan_markdown`, `subtasks` (list of `PlanTaskItem`), `file_list` |
| ReviewAgent | `ReviewOutput` | `findings`, `comments` (list of `ReviewFinding`), `summary` |

Validation is **graceful**: if the agent returns malformed JSON that does not match the schema, the system logs a warning and falls back to the raw parsed dict. This ensures the pipeline never crashes due to unexpected AI output while still enforcing structure when possible.

## API Overview

Base URL: `http://localhost:8000/api/v1`

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | User registration |
| `/auth/login` | POST | JWT login |
| `/auth/refresh` | POST | Token refresh |
| `/projects` | CRUD | Project management |
| `/tickets` | CRUD | Ticket management |
| `/kanban/move` | POST | Move ticket between columns |
| `/plans/{ticket_id}` | GET/POST | AI-generated plans |
| `/reviews/{ticket_id}` | GET/POST | Code reviews |
| `/deployments` | CRUD | Staging/production deployments |
| `/dashboard/stats` | GET | Pipeline metrics |
| `/context/index` | POST | Index project code |
| `/context/search` | POST | Semantic code search |

Full API reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
Security guide: [docs/SECURITY.md](docs/SECURITY.md)
Testing guide: [docs/TESTING.md](docs/TESTING.md)

### WebSocket

```
ws://localhost:8000/ws?token=<jwt>
```

Real-time events: `ticket.created`, `ticket.moved`, `ticket.updated`, `review.completed`, `deploy.status`, etc.

## RBAC Model

| Role | Permissions |
|------|------------|
| `owner` | Full access, all operations |
| `pm_lead` | Manage tickets, approve plans/reviews, deploy to production |
| `developer` | Create tickets, approve plans/code reviews, cannot deploy to production |
| `viewer` | Read-only access |

## Testing

### Backend

```bash
cd backend
.venv/bin/pytest -q                    # Run all 1425 tests
.venv/bin/pytest --cov=backend/app     # With coverage report (96%)
.venv/bin/ruff check backend/app backend/tests  # Lint check
.venv/bin/mypy backend/app --ignore-missing-imports  # Type check
```

### Frontend

```bash
cd frontend
npx vitest run       # Run 138 tests
npm run lint         # ESLint check
npm run build        # TypeScript build check
```

### Test Coverage Summary (v25)

| Component | Tests | Coverage |
|-----------|-------|----------|
| Backend | 1425 | 96% |
| Frontend | 138+ | — |
| E2E (Playwright) | 8 | smoke + auth |
| Lint (ruff) | 0 issues | 100% clean |
| Type check (mypy) | 96 files | 0 issues |
| Structured output | PlanOutput + ReviewOutput | Pydantic validated |

## Best Practices (20/20 Implemented)

The system implements all 20 industry best practices for AI coding systems (2025-2026):

| # | Practice | Module | Version |
|---|----------|--------|---------|
| 1 | Review Context Engine | `review_context.py` | v24 |
| 2 | Developer Feedback Loop | `feedback_tracker.py` | v23 |
| 3 | Negotiation Workflows | `negotiation.py` | v24 |
| 4 | Intelligent Test Selection | `test_selector.py` | v23 |
| 5 | Self-Healing Tests | `self_healing.py` | v24 |
| 6 | AI Quality Metrics Dashboard | `ai_metrics.py` | v23 |
| 7 | Duplication Detection | `duplication_detector.py` | v23 |
| 8 | Security Scanning | `security_agent.py` | v22 |
| 9 | OpenTelemetry Conventions | `otel_conventions.py` | v24 |
| 10 | Agent Tracing | `agent_tracing.py` | v24 |
| 11 | Automated Evaluation Tests | `eval_tests.py` | v24 |
| 12 | PII Leakage Monitoring | `pii_monitor.py` | v23 |
| 13 | Prompt Versioning | `prompt_versioning.py` | v25 |
| 14 | Semantic Response Cache | `semantic_cache.py` | v25 |
| 15 | Multi-Model Router | `model_router.py` | v25 |
| 16 | Hallucination Detection | `hallucination_detector.py` | v25 |
| 17 | Token Budget Enforcer | `token_budget.py` | v25 |
| 18 | Shadow A/B Testing | `shadow_testing.py` | v25 |
| 19 | Output Drift Detection | `drift_detector.py` | v25 |
| 20 | HITL Escalation Engine | `escalation_engine.py` | v25 |

## Monitoring

- **Grafana dashboards**: Pipeline overview and AI cost tracking (`infra/monitoring/`)
- **n8n workflows**: Automated pipeline triggers (`infra/n8n/`)
- Health check: `GET /health`

## Docker Services

```yaml
services:
  postgres:   # PostgreSQL 16 + pgvector (port 5432)
  redis:      # Redis 7 Alpine (port 6379)
  backend:    # FastAPI (port 8000)
  frontend:   # React/Vite (port 3000)
  n8n:        # Workflow engine (port 5678)
  nginx:      # Reverse proxy (port 80)
```

## License

MIT
