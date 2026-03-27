# Architecture Overview

## System Components

### Backend (FastAPI)

The backend is a Python 3.12+ FastAPI application with async SQLAlchemy ORM, organized by domain:

```
backend/app/
├── agents/          # AI provider integrations
├── api/v1/          # REST endpoint handlers
├── ci/              # CI/CD automation
├── context/         # Code indexing and search
├── git/             # Git/GitHub operations
├── middleware/       # Cross-cutting concerns
├── models/          # Database models
├── quality/         # QA: PII monitoring, duplication, metrics, feedback
├── schemas/         # Request/response validation
├── services/        # Business logic layer
└── workflows/       # Pipeline orchestration
```

**Key design decisions:**
- Async-first: All database operations use SQLAlchemy 2.0 async sessions
- Dependency injection: FastAPI `Depends()` for database sessions, auth, rate limiting
- Multi-provider AI: Router pattern selects Claude/GPT-4/Gemini based on task type
- Graceful degradation: Fallback agent returns mock responses when API keys are missing

### Frontend (React)

Single-page application with component-based architecture:

```
frontend/src/
├── components/      # Feature-organized React components
├── api/             # Axios HTTP client modules
├── stores/          # Zustand state management
├── hooks/           # Custom React hooks (WebSocket, auth)
├── types/           # TypeScript type definitions
└── utils/           # Permissions, formatters, helpers
```

**Key design decisions:**
- Zustand for lightweight state management (auth, projects, tickets, WebSocket)
- React Query for server state caching and cache invalidation
- dnd-kit for drag-and-drop Kanban board interactions
- Tailwind CSS for utility-first styling

### Data Flow

```
User Action
    │
    ▼
React Component → Zustand Store → Axios API Client
    │                                      │
    │ (WebSocket)                           ▼
    │                              FastAPI Router
    │                                      │
    │                              Dependency Injection
    │                              (Auth + DB Session)
    │                                      │
    │                              Service Layer
    │                              (Business Logic)
    │                                      │
    ▼                              ┌───────┴───────┐
WebSocket Manager ◀────────────────│               │
    │                        SQLAlchemy        AI Agents
    │                        (PostgreSQL)      (External APIs)
    ▼
Real-time UI Update
```

## Pipeline Architecture

### State Machine

The ticket lifecycle follows a strict state machine with validated transitions:

```
backlog ──────────────▶ ai_planning
ai_planning ──────────▶ plan_review
plan_review ──────────▶ ai_coding        (requires developer/pm_lead approval)
plan_review ──────────▶ backlog          (rejection path)
ai_coding ────────────▶ code_review
code_review ──────────▶ staging          (requires developer/pm_lead approval)
code_review ──────────▶ ai_coding        (revision path)
staging ──────────────▶ staging_verification
staging_verification ──▶ production      (requires pm_lead only)
staging_verification ──▶ staging         (re-deploy path)
```

### AI Agent Pipeline

```
Ticket Created
    │
    ▼
┌─────────────────────┐
│  PlanningAgent       │  Generates implementation plan with subtasks
│  (Claude/GPT-4)      │  Input: ticket + project context + code embeddings
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  Human Review Gate   │  Developer/PM reviews and approves plan
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  CodingAgent         │  Generates code for each subtask
│  (Claude/GPT-4)      │  Input: approved plan + relevant code context
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  Three-Layer Review  │
│  Layer 1: Specialist │  ReviewAgent + SecurityAgent run in parallel
│  agents (parallel)   │  Inline findings + SAST scanning
│  Layer 2: Meta-      │  MetaReviewAgent consolidates, filters
│  review (AI-on-AI)   │  false positives, validates severity
│  Layer 3: Human      │  Developer reviews consolidated findings
│  review gate         │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  CI/CD + Feedback    │  Build, test, deploy to staging
│  Inner loop: local   │  Fast validation (lint, type, unit tests)
│  tests + self-fix    │  Auto-fix up to 3 iterations on failure
│  Outer loop: full CI │  Full pipeline via n8n workflows
│  (Builder/Deployer)  │  Health checks, canary promotion
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  Production Gate     │  PM-only approval for production deploy
└─────────────────────┘
```

## Database Schema

### Core Models

| Model | Table | Purpose |
|-------|-------|---------|
| User | users | Accounts with roles (owner/pm_lead/developer/viewer) |
| Project | projects | Container for tickets and configuration |
| Ticket | tickets | Work items with 8-column lifecycle |
| AiPlan | ai_plans | Generated implementation plans |
| AiCodeGeneration | ai_code_generations | Generated code artifacts |
| Review | reviews | Code review records (AI + human) |
| TestResult | test_results | Test execution results |
| Deployment | deployments | Staging/production deploy records |
| AiLog | ai_logs | Agent execution logs with cost tracking |
| Comment | comments | Ticket discussion threads |
| TicketHistory | ticket_history | Audit trail of all changes |
| Notification | notifications | User notification queue |
| CodeEmbedding | code_embeddings | Vector embeddings for semantic search |
| Attachment | attachments | File uploads |

### Key Relationships

```
Project 1──N Ticket 1──N AiPlan
                    1──N AiCodeGeneration
                    1──N Review
                    1──N TestResult
                    1──N Deployment
                    1──N Comment
                    1──N TicketHistory
                    1──N Attachment
```

## Security Architecture

### Authentication

- JWT-based with access/refresh token pair
- Access tokens: 15-minute expiry
- Refresh tokens: 7-day expiry
- GitHub OAuth as alternative login flow
- Password hashing: bcrypt via passlib

### Authorization (RBAC)

Four roles with hierarchical permissions enforced at both API and UI levels:

| Operation | Owner | PM Lead | Developer | Viewer |
|-----------|-------|---------|-----------|--------|
| Create tickets | Yes | Yes | Yes | No |
| Move tickets | Yes | Yes | Yes* | No |
| Approve plans | Yes | Yes | Yes | No |
| Approve code | Yes | Yes | Yes | No |
| Deploy to production | Yes | Yes | No | No |
| Manage users | Yes | No | No | No |

*Developers cannot move tickets to production.

### Rate Limiting

Redis-backed sliding window rate limiter:
- Default: 100 requests/minute
- AI endpoints: 10 requests/minute
- Per-client IP tracking

## Infrastructure

### Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| postgres | postgres:16 | 5432 | Primary database + pgvector |
| redis | redis:7-alpine | 6379 | Caching, rate limiting, pub/sub |
| backend | Custom | 8000 | FastAPI application |
| frontend | Custom | 3000 | React development server |
| n8n | n8nio/n8n | 5678 | Workflow automation |
| nginx | nginx:alpine | 80 | Reverse proxy, SSL termination |

### Monitoring

- Grafana dashboards for pipeline metrics and AI cost tracking
- Prometheus-compatible metrics
- Structured JSON logging via middleware
- Health check endpoint: `GET /health`

## Middleware Ordering

FastAPI applies middleware in reverse registration order (last added runs first on the inbound request). The application registers middleware so the final execution order is:

```
Inbound Request
    │
    ▼
┌──────────────────┐
│  CORS Middleware  │  Outermost — handles preflight, origin validation
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Rate Limiter    │  Redis-backed sliding window, per-IP tracking
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Request Logging │  Structured JSON logging with timing
└────────┬─────────┘
         ▼
    Route Handler
```

This ordering ensures security-related middleware (CORS, rate limiting) runs before business-logic middleware (logging), which means malicious or over-limit requests are rejected before any processing occurs.

## Structured Output Validation

AI agents return free-form JSON. To enforce contract guarantees without crashing the pipeline, each agent defines a Pydantic schema for its expected output:

| Agent | Schema | Key Fields |
|-------|--------|------------|
| PlanningAgent | `PlanOutput` | `plan_markdown: str`, `subtasks: list[PlanTaskItem]`, `file_list: list[str]` |
| ReviewAgent | `ReviewOutput` | `findings: list[ReviewFinding]`, `comments: list[ReviewFinding]`, `summary: str` |

The shared `validate_output(response_dict, SchemaClass)` helper in `agents/base.py` calls `schema.model_validate(response)` and returns the coerced dict on success. On failure it logs a warning and returns the original dict unchanged — graceful degradation ensures the pipeline continues even when agents produce slightly non-conforming JSON.

Adding a new output schema follows the same pattern: define a `BaseModel` subclass, call `validate_output()` after parsing the agent response.

## Production Hardening

The application factory in `main.py` reads `settings.ENVIRONMENT` and adjusts behaviour:

- **OpenAPI docs** (`/docs`, `/redoc`) are disabled when `ENVIRONMENT=production` to avoid exposing internal API surface.
- **Generic exception handler** returns a sanitised `{"detail": "Internal server error"}` in production; in development it includes the full traceback for debugging.
- **Validation exception handler** returns field-level errors in all environments (safe to expose).
- **Lifespan hooks** catch and log database/Redis connection failures as warnings so the app can start even if infrastructure is temporarily unavailable.

## Project Selector UI

The Kanban board uses `kanbanStore.currentProjectId` to track the active project. On first load the store auto-creates or selects a project with a real UUID, ensuring no component ever sends `project_id='default'`. The `MetricsDashboard` and other project-scoped screens read the same store value so all views stay in sync.

## Security Hardening (v21)

### File Upload Protection
- Filenames are sanitized via `Path(filename).name` to prevent path traversal (`../../etc/passwd`)
- Null bytes stripped from filenames
- UUID prefix ensures uniqueness

### Webhook Fail-Closed
- GitHub webhook verification returns 503 when `GITHUB_CLIENT_SECRET` is missing (instead of silently skipping)
- HMAC-SHA256 signature verified via timing-safe `hmac.compare_digest()`

### Startup Validation
- `check_production_secrets()` runs on boot and warns about insecure defaults
- Logged at CRITICAL/WARNING level for monitoring integration

## Quality Assurance Modules (v23)

The `app/quality/` package provides AI-specific quality assurance capabilities:

### PII Leakage Monitor (`pii_monitor.py`)
Scans AI agent outputs for 10 PII types (email, phone, SSN, credit card, AWS keys, API keys, private keys, JWT tokens, IP addresses, password hashes). Uses regex-based detection with confidence scoring, allowlists for known safe patterns, and automatic redaction.

### Duplication Detector (`duplication_detector.py`)
Detects duplicated code blocks across AI-generated files. Uses a sliding-window approach with normalized line comparison and MD5 hashing. Reports duplication ratio, block count, and precise locations.

### Developer Feedback Tracker (`feedback_tracker.py`)
Tracks which AI review findings developers accept, reject, or defer. Aggregates acceptance/rejection rates and reasons for prompt fine-tuning. API endpoint: `POST /reviews/{id}/feedback`. Computes AI-human agreement rate from DB.

### Intelligent Test Selector (`test_selector.py`)
Maps changed source files to relevant test files using path conventions (e.g., `app/agents/X.py` → `tests/test_agents/test_X.py`). Detects broad-impact changes (config, database, models) and triggers wider test coverage. Falls back to full suite when no mapping found.

### AI Quality Metrics (`ai_metrics.py`)
Dashboard metrics specific to AI-generated code: regression rate, defect density, merge confidence, agent acceptance rates, AI vs human review comparison, and agent performance (latency, cost, success rate). Exposed via `GET /dashboard/ai-quality-metrics` and `GET /dashboard/review-feedback`.

## Context Engine

The context engine provides code-aware AI assistance:

1. **Code Parser**: AST analysis for Python/JS/TS files
2. **Embeddings**: Vector representations of code chunks
3. **Vector Store**: pgvector-based similarity search
4. **Engine**: Orchestrates indexing, search, and context retrieval

Used by AI agents to ground their responses in the actual codebase.
