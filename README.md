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
| Router | Dynamic agent selection per task type | N/A |

## Project Structure

```
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── agents/            # AI agent implementations (13 modules)
│   │   ├── api/v1/            # REST API routes (24 endpoints)
│   │   ├── ci/                # CI/CD: builder, deployer, scanner, test runner
│   │   ├── context/           # Code embeddings, AST parser, vector store
│   │   ├── git/               # GitHub client, repo manager, diff parser
│   │   ├── middleware/        # Logging, rate limiting
│   │   ├── models/            # SQLAlchemy ORM models (19 models)
│   │   ├── schemas/           # Pydantic validation schemas
│   │   ├── services/          # Business logic (auth, kanban, dashboard...)
│   │   └── workflows/         # Pipeline orchestrator, state machine, retry
│   ├── tests/                 # 831 tests, 96% coverage
│   └── alembic/               # Database migrations
├── frontend/                   # React + TypeScript frontend
│   └── src/
│       ├── components/        # Auth, Kanban, Tickets, Planning, Review...
│       ├── api/               # Axios API client modules
│       ├── stores/            # Zustand state management
│       ├── hooks/             # Custom React hooks
│       └── test/              # 54 Vitest tests
├── infra/                      # Infrastructure
│   ├── docker-compose.yml     # Full stack: PG, Redis, n8n, Nginx
│   ├── k8s/                   # Kubernetes manifests
│   ├── monitoring/            # Grafana dashboards
│   └── nginx/                 # Reverse proxy config
├── docs/                       # Documentation
│   └── API_REFERENCE.md       # REST API reference
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
.venv/bin/pytest -q                    # Run all 831 tests
.venv/bin/pytest --cov=backend/app     # With coverage report (96%)
.venv/bin/ruff check backend/app backend/tests  # Lint check
.venv/bin/mypy backend/app --ignore-missing-imports  # Type check
```

### Frontend

```bash
cd frontend
npx vitest run       # Run 54 tests
npm run lint         # ESLint check
npm run build        # TypeScript build check
```

### Test Coverage Summary

| Component | Tests | Coverage |
|-----------|-------|----------|
| Backend | 831 | 96% |
| Frontend | 54 | - |
| Lint (ruff) | 0 issues | 100% clean |
| Type check (mypy) | 96 files | 0 issues |

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
