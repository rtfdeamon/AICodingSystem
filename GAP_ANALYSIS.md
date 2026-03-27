# GAP Analysis: AI Coding Pipeline MVP (Iteration 1)

**Date:** 2026-03-26
**Status:** Scaffold complete, iteration 1 not yet acceptance-ready

## Current State

| Gate | Before | After Fixes |
|------|--------|-------------|
| `pytest -q` | 26 failed / 11 passed | **37 passed / 0 failed** |
| `npm run build` | TS errors | **Build OK** |
| Auth flow | 500 on register | **Working (register + login + /me)** |
| Frontend preview | Crash | **Loads, auth works** |

---

## P0 - Must Fix Before MVP Acceptance

### 1. Missing Projects API
- **Problem:** No `/api/v1/projects` endpoint. Entire MVP (tickets, kanban, dashboard) depends on project context.
- **Evidence:** `router.py:24` has no projects module; `test_tickets.py:28` expects projects.
- **Fix:** Create `api/v1/projects.py` with CRUD, wire into router. Frontend needs project selector.

### 2. Domain Contract Mismatch (Frontend <-> Backend)
- **Problem:** Roles, columns, priorities, field names, and URLs don't match between frontend and backend.
- **Evidence:**
  - `types/index.ts:2` vs `ticket.py:33` - different column/priority enums
  - `constants.ts:4` - frontend column names vs backend ColumnName enum
  - `tickets.ts:28`, `kanban.ts:20`, `dashboard.ts:55` - URL/field mismatches
- **Fix:** Backend OpenAPI is source of truth. Generate or manually align frontend types from it.

### 3. Hardcoded `projectId='default'`
- **Problem:** `KanbanBoard.tsx:25` hardcodes `projectId='default'`, backend expects UUID.
- **Fix:** After Projects API exists, use real project selection with UUID.

---

## P1 - Critical for Pipeline Functionality

### 4. AI Provider Graceful Degradation
- **Problem:** `route_task()` instantiates live agents and crashes without API keys.
- **Evidence:** `router.py:104`, `claude_agent.py:29`, `codex_agent.py:27`
- **Fix:** Wrap agent instantiation in try/catch, return mock/stub responses when keys missing. Unit tests must pass without real API keys.

### 5. WebSocket Protocol Incompatibility
- **Problem:** Frontend and backend WS protocols don't match. Services don't publish board events.
- **Evidence:** `ws.ts:26` vs `main.py:99`; `kanban_service.py:117`, `comment_service.py:19` don't emit events.
- **Fix:** Define shared WS message schema. Add event publishing to kanban/comment/ticket services.

### 6. AI Review Not Grounded in Code Diff
- **Problem:** Review endpoint sends PR URL/description to AI model, not actual code diff.
- **Evidence:** `reviews.py:214`, `git_ops.py:207` (git-diff API exists but unused by review).
- **Fix:** Wire review service to fetch diff via git_ops, include in AI prompt context.

### 7. AI Logs Endpoint Returns Empty/404
- **Problem:** AiLog model and recording exist, but `/ai-logs` API returns nothing useful.
- **Evidence:** `ai_logs.py:63`, `base.py:175`
- **Fix:** Ensure ai_logs endpoint queries and returns real AiLog records with proper filtering.

---

## P2 - Compliance / Polish

### 8. Production Gate Role Mismatch
- **Problem:** Backend allows both `owner` and `pm_lead` to deploy to production. TZ specifies PM only.
- **Evidence:** `deployments.py:182`, `kanban_service.py:73`
- **Fix:** Restrict production transitions to `pm_lead` role only per TZ spec.

---

## TZ Documentation Gaps

| Section | Gap | Acceptance Criteria |
|---------|-----|-------------------|
| 1.3 RBAC | Empty, roles diverged | Single role->screen->endpoint->column matrix, unified enum, negative tests |
| 2.1-2.2 Architecture | Pipeline phases underdefined | Per-column: trigger, actor, side effects, human gate, reject-loop, retry, WS event |
| 4.1 MVP Contracts | No formal API contracts | OpenAPI as source of truth, frontend types generated, pytest + build green |
| 3.1-3.4 UI/UX | Screens not tied to real API | Each screen bound to API responses/events, no placeholders, responsive/empty/error states |
| 4.2 Context Engine | No quality benchmarks | Clone lifecycle, indexing, dependency graph, search quality dataset |
| 4.3-4.7 AI Stages | No measurable criteria | Per-stage: input/output artifact, timeout, cost cap, fallback, human gate, retry |
| 5.* Metrics/SLA | No formulas | Formula, source, measurement window, threshold, owner per metric |
| 8 Tech Stack | Not pinned | Approved tech/versions/integrations |
| 10 Glossary | Missing | Unambiguous definitions for all entities |

---

## Recommended Order

1. **TZ completion:** 1.3 RBAC, 2.2 Pipeline, 4.1 Contracts
2. **Unified contract:** Align backend/frontend enums, types, URLs
3. **Projects API + real project flow**
4. **AI pipeline with graceful degradation**
5. **WebSocket + real-time events**
6. **AI logs observability**
