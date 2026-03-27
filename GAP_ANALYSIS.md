# GAP Analysis: AI Coding Pipeline MVP (Iteration 1)

**Date:** 2026-03-27 (updated v19)
**Status:** MVP feature-complete, iteration 5

## Current State

| Gate | Before | After v19 |
|------|--------|-----------|
| `pytest -q` | 26 failed / 11 passed | **899 passed / 0 failed** |
| `npm run build` | TS errors | **Build OK** |
| `vitest run` | 0 tests | **138 passed** |
| Auth flow | 500 on register | **Working (register + login + /me)** |
| Frontend preview | Crash | **Loads, auth works** |
| Coverage | 0% | **96%** |
| Lint | 48 issues | **0 issues** |

---

## P0 - Must Fix Before MVP Acceptance

### 1. ~~Missing Projects API~~ **RESOLVED v15**
- **Status:** Projects API implemented with full CRUD. KanbanBoard auto-creates project on first load.

### 2. ~~Domain Contract Mismatch~~ **RESOLVED v15-v16**
- **Status:** Frontend types aligned with backend enums. Shared constants in `/shared/constants.py`.

### 3. ~~Hardcoded `projectId='default'`~~ **RESOLVED v19**
- **Status:** Removed `DEFAULT_PROJECT_ID='default'` from MetricsDashboard. Now uses `kanbanStore.currentProjectId` (real UUID). KanbanBoard auto-creates/selects project with UUID. Test confirms no screen sends `project_id='default'`.

---

## P1 - Critical for Pipeline Functionality

### 4. ~~AI Provider Graceful Degradation~~ **RESOLVED v15**
- **Status:** Agents wrapped with try/catch fallback. Tests pass without real API keys.

### 5. ~~WebSocket Protocol Incompatibility~~ **RESOLVED v18**
- **Status:** Shared WS event types in `shared/event_types.py`. KanbanBoard subscribes to project events. WebSocket manager broadcasts board events.

### 6. ~~AI Review Not Grounded in Code Diff~~ **RESOLVED v18**
- **Status:** `GitHubClient.get_branch_diff()` fetches real diffs via GitHub Compare API. Graceful fallback when token unavailable.

### 7. ~~AI Logs Endpoint Returns Empty/404~~ **RESOLVED v16**
- **Status:** AI logs endpoint returns real records with ticket_id, agent, status filtering. 96% coverage on ai_logs module.

---

## P2 - Compliance / Polish

### 8. ~~Production Gate Role Mismatch~~ **RESOLVED v15**
- **Status:** RBAC aligned with TZ spec. Developer can review but cannot deploy. Production gate restricted to owner/pm_lead. Negative RBAC tests verify enforcement.

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
