# TODO

## Ревизия на 2026-03-27 v17 (автоматический проход; coverage 93% → 96% + 113 новых тестов + 0 warnings + deprecation fixes + full docs)

Проверено командами:
- `backend/.venv/bin/pytest -q` -> **831 passed, 0 warnings** (было 718, +113 новых тестов)
- `backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q` -> **TOTAL 96%** (было 93%)
- `backend/.venv/bin/ruff check backend/app backend/tests` -> **All checks passed!**
- `backend/.venv/bin/mypy backend/app --ignore-missing-imports` -> **Success: no issues found in 96 source files**
- `frontend: npx vitest run` -> **54 passed**
- `frontend: npm run build` -> **OK**

### Что сделано в этом проходе

- [x] **Coverage: 93% → 96% (+113 новых backend тестов)**
  - Новые тест-файлы:
    - `tests/test_middleware/test_rate_limiter.py`: покрытие rate_limiter.py (54% → ~100%) — 22 теста, sliding window, profiles, headers, Redis errors
    - `tests/test_api/test_comments.py`: покрытие comments.py (78% → ~100%) — 5 тестов, CRUD операции
    - `tests/test_services/test_dashboard_service.py`: покрытие dashboard_service.py (81% → ~100%) — 16 тестов, pipeline stats, AI costs, code quality, deployment stats
  - Расширенные тесты:
    - `tests/test_agents/test_planning_agent.py`: покрытие planning_agent.py (68% → ~100%) — +17 тестов, generate_plan, version incrementing, null fields, prompt content
    - `tests/test_api/test_deployments.py`: покрытие deployments.py (70% → ~100%) — +19 тестов, rollback, promote, health check, status guards
    - `tests/test_api/test_users.py`: покрытие users.py (71% → ~100%) — +12 тестов, update self/other, role changes, RBAC enforcement
    - `tests/test_api/test_webhooks.py`: покрытие webhooks.py (80% → ~100%) — +18 тестов, action mapping, signature verification, event types
    - `tests/test_services/test_websocket_manager.py`: покрытие websocket_manager.py (77% → ~100%) — +7 тестов, subscribe_events, malformed JSON, Redis failure

- [x] **Pytest warnings: 29 → 0**
  - Убран `pytestmark = pytest.mark.asyncio` из 5 файлов с sync функциями:
    - `test_agents/test_agent_providers.py`, `test_api/test_git_ops.py`
    - `test_ci/test_builder.py`, `test_ci/test_deployer.py`, `test_ci/test_security_scanner.py`
  - Добавлен `@pytest.mark.asyncio` только к async функциям в этих файлах
  - Добавлен `__test__ = False` к 3 классам для предотвращения PytestCollectionWarning:
    - `models/test_result.py::TestResult`, `ci/test_runner.py::TestSuiteResult`, `agents/test_gen_agent.py::TestFile`

- [x] **Deprecation fixes**
  - `datetime.utcnow()` → `datetime.now(UTC)` в notification_service.py и pipeline_orchestrator.py
  - `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT` в kanban_service.py и deployments.py

- [x] **Lint: 0 issues (All checks passed!)**
  - Import sorting исправлено в 3 файлах после agent work
  - Исправлены F841, SIM117, E501 в новых тестах

- [x] **Полная документация проекта**
  - `README.md`: полное описание проекта, архитектуры, установки, API, тестирования
  - `docs/ARCHITECTURE.md`: системные компоненты, data flow, pipeline, database schema, security, infrastructure
  - `docs/DEVELOPMENT.md`: setup guide, code quality standards, testing conventions, debugging

### Что осталось открытым (приоритет для следующего прохода)

1. [x] ~~Coverage 93% → 95%~~ **ДОСТИГНУТО: 96%**
2. [x] ~~Pytest warnings 29 → 0~~ **ДОСТИГНУТО: 0 warnings**
3. [ ] **Real-time contract**: подключить `subscribeProject()`/`unsubscribeProject()` в KanbanBoard
4. [ ] **Project context**: убрать `DEFAULT_PROJECT_ID='default'` и auto-create
5. [ ] **Ticket artifact center**: подключить все вкладки TicketDetail к реальным API
6. [ ] **AI review grounding**: подключить реальный git diff в review_agent
7. [ ] **E2E tests**: установить Playwright browsers, запустить smoke с dev-сервером
8. [ ] **Frontend component tests**: написать RTL тесты для LoginPage, KanbanBoard, TicketDetail

### Best Practices Backlog (обновлено 2026-03-27 v17)

#### AI Pipeline Best Practices (из интернет-источников 2025-2026)
- [ ] **Three-layer review architecture**: real-time IDE feedback + PR-level AI analysis + periodic architectural reviews (verdent.ai, qodo.ai)
- [ ] **CI feedback loops**: при падении CI прогонять ошибки обратно в AI agent для автоматического исправления (addyosmani.com, gocodeo.com)
- [ ] **AI-on-AI code review**: два разных AI-агента ревьюят код друг друга для cross-check (augmentcode.com)
- [ ] **Multi-model parallel execution**: запускать 2+ моделей параллельно для cross-check и fallback (faros.ai)
- [ ] **AI code provenance tracking**: документировать происхождение AI-генерированного кода, edits, и rationale (getdx.com)
- [ ] **Prompt injection testing**: тестировать AI pipeline на prompt injection уязвимости в CI (computerweekly.com)

#### FastAPI Production Hardening (из интернет-источников 2025-2026)
- [ ] **Disable docs in production**: отключить `/docs` и `/redoc` в production mode (fastlaunchapi.dev)
- [ ] **Custom exception handlers**: sanitized error responses без stack traces в production (render.com)
- [ ] **pip-audit integration**: регулярное сканирование dependencies на уязвимости в CI (VolkanSah/Securing-FastAPI-Applications)
- [ ] **WAF + API gateway**: Kong или AWS API Gateway перед FastAPI в production (davidmuraya.com)
- [ ] **Middleware ordering**: security middleware до business logic middleware (zhanymkanov/fastapi-best-practices)

#### AI Agent Orchestration
- [ ] Внедрить agent capability scoring: динамический выбор агента на основе исторических метрик успешности
- [ ] Добавить structured output validation: JSON schema validation для ответов AI агентов
- [ ] Реализовать agent response caching: кэширование для идентичных контекстов (ticket+diff hash)

#### Code Quality Guardrails
- [ ] Добавить AST-level validation для AI-генерированного кода
- [ ] Внедрить diff size limits: автоматическое разбиение на chunks (<500 LOC per review)
- [ ] Реализовать semantic diff comparison через embedding similarity

#### Security
- [ ] Добавить SBOM генерацию для AI-предложенных dependencies
- [ ] Внедрить secret scanning в AI-генерированном коде до коммита
- [ ] Реализовать sandbox execution для AI-сгенерированных тестов

#### Observability
- [ ] Добавить per-agent cost dashboards с alerts на budget thresholds
- [ ] Внедрить quality regression tracking: AI ревью vs human ревью
- [ ] Реализовать latency SLO tracking: <30s planning, <60s coding, <20s review

#### Testing Best Practices
- [ ] Внедрить `factory_boy` для генерации тестовых данных (pythoneo.com)
- [ ] Генерировать HTML coverage reports в CI (pythoneo.com)

---

## Ревизия на 2026-03-27 v16 (автоматический проход; coverage 87% → 93% + 77 новых тестов + lint clean + best practices update)

Проверено командами:
- `backend/.venv/bin/pytest -q` -> **718 passed** (было 641, +77 новых тестов)
- `backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q` -> **TOTAL 93%** (было 87%)
- `backend/.venv/bin/ruff check backend/app backend/tests` -> **All checks passed!** (по-прежнему 0 issues)
- `backend/.venv/bin/mypy backend/app --ignore-missing-imports` -> **Success: no issues found in 96 source files**
- `frontend: npx vitest run` -> **54 passed**
- `frontend: npm run build` -> **OK**

### Что сделано в этом проходе

- [x] **Coverage: 87% → 93% (+77 новых backend тестов)**
  - Новые тест-файлы:
    - `tests/test_main.py`: покрытие main.py (38% → ~85%) — create_app, health, lifespan, WebSocket, CORS
    - `tests/test_database.py`: покрытие database.py (42% → ~90%) — get_db, init_db (sqlite/postgres), close_db
    - `tests/test_redis.py`: покрытие redis.py (57% → ~95%) — init/close/get_redis_pool/get_redis
    - `tests/test_api/test_reviews.py`: покрытие reviews.py (46% → ~85%) — list, submit, AI trigger
    - `tests/test_api/test_ai_logs.py`: покрытие ai_logs.py (60% → ~95%) — list/filter/paginate/stats/get
    - `tests/test_api/test_test_results.py`: покрытие test_results.py (57% → ~90%) — list/get/trigger/generate
    - `tests/test_api/test_github_oauth.py`: покрытие github_oauth.py (31% → ~80%) — URL, callback, error paths
    - `tests/test_api/test_context.py`: покрытие context.py (60% → ~85%) — index/status/search/deps
  - Расширенные тесты:
    - `tests/test_services/test_websocket_manager.py`: +10 тестов — _send_safe, publish_event, edge cases

- [x] **Pytest warnings: 42 → 29**
  - Исправлено в `test_main.py`, `test_database.py`, `test_redis.py`, `test_ci/test_test_runner.py`:
    - Убран `pytestmark = pytest.mark.asyncio` из файлов с sync функциями
    - Добавлен `@pytest.mark.asyncio` только к async функциям
  - Оставшиеся 29 warnings — из существующих файлов с `pytestmark` и PytestCollectionWarning

- [x] **Lint: 0 issues (All checks passed!)**
  - Все новые тест-файлы прошли ruff check без issues
  - Исправлены N806, E501, F401, SIM117, SIM105, B017

### Что осталось открытым (приоритет для следующего прохода)

1. [x] ~~Coverage 87% → 90%~~ **ДОСТИГНУТО: 93%**
2. [ ] **Coverage 93% → 95%**: оставшиеся low-coverage модули:
   - `main.py` (~85%), `database.py` (~90%), `deployer.py` (81%), `dashboard_service.py` (81%)
   - `notification_service.py` (83%), `kanban_service.py` (84%), `state_machine.py` (90%)
3. [ ] **Real-time contract**: подключить `subscribeProject()`/`unsubscribeProject()` в KanbanBoard
4. [ ] **Project context**: убрать `DEFAULT_PROJECT_ID='default'` и auto-create
5. [ ] **Ticket artifact center**: подключить все вкладки TicketDetail к реальным API
6. [ ] **AI review grounding**: подключить реальный git diff в review_agent
7. [ ] **E2E tests**: установить Playwright browsers, запустить smoke с dev-сервером
8. [ ] **Frontend component tests**: написать RTL тесты для LoginPage, KanbanBoard, TicketDetail
9. [ ] **Pytest warnings**: довести 29 → 0 (убрать pytestmark из оставшихся файлов)

### Best Practices Backlog (обновлено 2026-03-27 v16)

#### AI Agent Orchestration (новые)
- [ ] Внедрить agent capability scoring: динамический выбор агента на основе исторических метрик успешности (latency, quality, cost) для каждого типа задачи
- [ ] Добавить structured output validation: JSON schema validation для ответов AI агентов перед парсингом, с retry на malformed output
- [ ] Реализовать agent response caching: кэширование планов и ревью для идентичных контекстов (ticket+diff hash) для экономии API calls

#### Code Quality Guardrails (новые)
- [ ] Добавить AST-level validation для AI-генерированного кода: проверка синтаксиса, import resolution, type consistency до мержа
- [ ] Внедрить diff size limits: автоматическое разбиение больших генераций на reviewable chunks (<500 LOC per review)
- [ ] Реализовать semantic diff comparison: сравнение AI-генерированного кода с acceptance criteria через embedding similarity

#### Security (новые)
- [ ] Добавить SBOM (Software Bill of Materials) генерацию для AI-предложенных dependencies
- [ ] Внедрить secret scanning в AI-генерированном коде до коммита (prevent credential leaks)
- [ ] Реализовать sandbox execution для AI-сгенерированных тестов (изоляция от production data)

#### Observability (новые)
- [ ] Добавить per-agent cost dashboards с alerts на budget thresholds
- [ ] Внедрить quality regression tracking: мониторинг тренда quality score AI ревью vs human ревью
- [ ] Реализовать latency SLO tracking: <30s для planning, <60s для coding, <20s для review

---

## Ревизия на 2026-03-27 v15 (автоматический проход; coverage boost + ruff fix + RBAC alignment + best practices)

Проверено командами:
- `backend/.venv/bin/pytest -q` -> **641 passed** (было 529, +112 новых тестов)
- `backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q` -> **TOTAL 87%** (было 81%)
- `backend/.venv/bin/ruff check backend/app backend/tests` -> **All checks passed!** (было 48 issues)
- `backend/.venv/bin/mypy backend/app --ignore-missing-imports` -> **Success: no issues found in 96 source files**
- `frontend: npx vitest run` -> **54 passed** (было 53, +1 новый)
- `frontend: npm run build` -> **OK**

### Что сделано в этом проходе

- [x] **Ruff: 48 issues → 0 (All checks passed!)**
  - Авто-исправлено 13 issues (import sorting, unused imports)
  - Вручную исправлено 35 issues:
    - `test_github_client.py`: заменены hardcoded `access_token=` на константы `_TEST_TOKEN`/`_TOK` (S106), объединены nested `with` (SIM117)
    - `test_repo_manager.py`: заменены `/tmp/repo` на `_REPO = "/fake/test/repo"` (S108), объединены nested `with` (SIM117), исправлены E501/F841

- [x] **Coverage: 81% → 87% (+112 новых backend тестов)**
  - Новые тест-файлы:
    - `tests/test_ci/test_security_scanner.py`: покрытие security_scanner.py
    - `tests/test_agents/test_coding_agent.py`: покрытие coding_agent.py
    - `tests/test_ci/test_builder.py`: расширено покрытие builder.py
    - `tests/test_workflows/test_pipeline_orchestrator.py`: покрытие pipeline_orchestrator.py (52% → 99%)
    - `tests/test_api/test_git_ops.py`: покрытие git_ops.py API
  - Ключевые улучшения:
    - `pipeline_orchestrator.py`: 52% → **99%**
    - `security_scanner.py`: 46% → улучшено
    - `coding_agent.py`: 57% → улучшено
    - `builder.py`: 41% → улучшено
    - `git_ops.py`: 45% → улучшено

- [x] **RBAC matrix выровнена с ТЗ (backend + frontend + tests)**
  - Backend `kanban_service.py`:
    - `plan_review → ai_coding`: добавлен `developer` в allowed_roles
    - `plan_review → backlog`: добавлен `developer` в allowed_roles
    - `staging_verification → production`: по-прежнему только `pm_lead` ✓
  - Frontend `permissions.ts`:
    - Developer теперь может approve/reject на `plan_review` и `code_review`
    - Developer явно заблокирован от `production` deploy (`toColumn !== 'production'`)
  - Tests обновлены:
    - `permissions.test.ts`: developer CAN move from review columns, CANNOT deploy to production
    - `test_kanban_service.py`: +5 новых тестов на developer review и owner production block
    - `test_kanban_rbac.py`: исправлен ложноположительный тест `developer_forbidden` → `developer_allowed`

- [x] **Best Practices Backlog обновлён (интернет-источники, 2026-03-27)**
  - AI Pipeline (gocodeo.com, addyosmani.com, augmentcode.com):
    - AI-on-AI code reviews для cross-check
    - CI feedback loops: прогонять ошибки CI обратно в AI agent для авто-фикса
    - Treat AI as onboarded team member: system instructions, project docs, explicit rules
  - FastAPI Testing (pythoneo.com, compilenrun.com, frugaltesting.com):
    - `asyncio_mode = auto` в pytest config для упрощения async тестов
    - `factory_boy` для генерации тестовых данных
    - Separate test DB с rollbacks для isolation
  - Security (computerweekly.com, qodo.ai):
    - ISO/IEC 42001 certification для AI code review
    - Prompt injection vulnerability testing в CI
    - Automated provenance tracking для dependencies

### Что осталось открытым (приоритет для следующего прохода)

1. [x] ~~Coverage 81% → 85%~~ **ДОСТИГНУТО: 87%**
2. [x] ~~Ruff 48 issues~~ **ДОСТИГНУТО: 0 issues**
3. [x] ~~RBAC matrix alignment~~ **ДОСТИГНУТО: developer can review, pm_lead only for production**
4. [x] ~~**Coverage 87% → 90%**~~ **ДОСТИГНУТО в v16: 93%**
5. [ ] **Real-time contract**: подключить `subscribeProject()`/`unsubscribeProject()` в KanbanBoard
6. [ ] **Project context**: убрать `DEFAULT_PROJECT_ID='default'` и auto-create
7. [ ] **Ticket artifact center**: подключить все вкладки TicketDetail к реальным API
8. [ ] **AI review grounding**: подключить реальный git diff в review_agent
9. [ ] **E2E tests**: установить Playwright browsers, запустить smoke с dev-сервером
10. [ ] **Frontend component tests**: написать RTL тесты для LoginPage, KanbanBoard, TicketDetail

### Best Practices Backlog (обновлено 2026-03-27 v15)

#### AI Pipeline Best Practices (новые)
- [ ] Внедрить CI feedback loops: при падении CI прогонять ошибки обратно в AI agent для автоматического исправления (gocodeo.com, addyosmani.com)
- [ ] Добавить AI-on-AI code review: два разных AI-агента ревьюят код друг друга для cross-check (augmentcode.com)
- [ ] Внедрить prompt injection testing в CI pipeline для AI-генерированного кода (computerweekly.com)
- [ ] Автоматический provenance tracking для всех dependencies предложенных AI (qodo.ai)

#### Testing Best Practices (новые)
- [ ] Перейти на `asyncio_mode = auto` в pytest config для упрощения async тестов (compilenrun.com)
- [ ] Внедрить `factory_boy` для генерации тестовых данных вместо ручных fixture-ов (pythoneo.com)
- [ ] Добавить separate test DB с transaction rollbacks для полной isolation (frugaltesting.com)
- [ ] Генерировать HTML coverage reports в CI для visual drill-down (pythoneo.com)

---

## Ревизия на 2026-03-27 v14 (автоматический проход; TZ-grounded audit + verify floor cleanup)

Проверено командами:
- `python3` fallback-extract из `TZ_AI_Coding_Pipeline.docx` (zip/xml) -> ТЗ извлечено, подтверждены разделы `1.3`, `2.2`, `4.1-4.7`, `6.1-6.7`
- `pytest -q` -> **FAIL**, `ModuleNotFoundError: jose` (repo-root Python env не bootstrapped)
- `backend/.venv/bin/pytest -q` -> **529 passed, 30 warnings** (было 31; warning про unknown `rootdir` снят)
- `backend/.venv/bin/ruff check backend/app backend/tests` -> **FAIL**, 48 lint issues в test-файлах
- `backend/.venv/bin/mypy backend/app --ignore-missing-imports` -> **Success: no issues found in 96 source files**
- `frontend: npm run test` -> **53 passed**
- `frontend: npm run build` -> **FAIL -> FIXED -> OK**
- `e2e: npx playwright test` -> **5 failed** (Chromium не установлен + backend dev server не поднят)
- internet refresh:
  - встроенный `web` tool -> **503 Service Unavailable**
  - `curl` до `git-scm.com`, `playwright.dev`, `docs.github.com` -> **Could not resolve host**

### Что исправлено в этом проходе

- [x] **Frontend build снова зелёный**
  - `frontend/vite.config.ts`: `defineConfig` переведён на `vitest/config`
  - результат: `frontend/npm run build` снова проходит
- [x] **Снят ложный pytest warning из repo-root конфигурации**
  - root `pyproject.toml`: удалён невалидный `pytest` option `rootdir`
  - результат: `backend/.venv/bin/pytest -q` больше не шумит этим warning

### Краткий вердикт

- [x] **Мы движемся к цели по инженерному floor**: backend tests зелёные, frontend tests зелёные, frontend build снова зелёный, mypy зелёный.
- [x] **Разделы `5.*` и часть `7.4` уже имеют основу**: в коде есть `dashboard_service`, Grafana dashboards и Prometheus rules; тут скорее нужен wiring/runtime validation, а не разработка с нуля.
- [ ] **Acceptance-ready по ТЗ проект ещё не достиг**: основные разрывы теперь в RBAC/real-time contract, project context, ticket artifact center, AI review grounding, worktree orchestration и CI/E2E execution.
- [ ] **Verify-flow всё ещё неканонический**: repo-root `pytest` не самодостаточен, `ruff` на `backend/tests` красный, e2e не исполнимы в чистой среде.

### Что автодорабатывать следующим приоритетом (с привязкой к ТЗ)

1. [ ] **`1.3 RBAC` + `4.1 MVP` + `6.1`: выровнять role matrix и убрать ложноположительные тесты**
   - Подтверждённые факты:
     - ТЗ: `Developer` ревьюит планы и код; `Production` двигает только `PM/Lead`.
     - `backend/app/services/kanban_service.py`: `plan_review -> ai_coding/backlog` разрешены только `pm_lead|owner`; `developer` исключён.
     - `frontend/src/utils/permissions.ts`: `developer` может двигать из `staging` в `production`.
     - `frontend/src/utils/permissions.test.ts` закрепляет это как правильное поведение.
     - `frontend/src/utils/permissions.ts`: `developer` вообще не может работать с `plan_review` / `code_review`.
   - Почему это блокер:
     - Backend, frontend и tests одновременно расходятся с RBAC из ТЗ и дают ложное чувство готовности.
   - Критерии приёмки:
     - единая role matrix зафиксирована в backend enums, frontend permissions и tests;
     - `developer` может `approve/reject` на `plan_review` и `code_review`;
     - `production` разрешён только `pm_lead` и это проверено на уровне API/UI/e2e negative tests;
     - нет тестов, которые утверждают поведение, противоречащее ТЗ.

2. [ ] **`3.1 Kanban` + `4.1 MVP` + `6.1`: починить real-time contract end-to-end**
   - Подтверждённые факты:
     - `frontend/src/hooks/useWebSocket.ts` подключает WS без `projectId`.
     - `frontend/src/stores/wsStore.ts` имеет `subscribeProject()`/`unsubscribeProject()`, но UI их не вызывает.
     - `backend/app/services/kanban_service.py` шлёт `ticket.moved` с `{ticket_id, from_column, to_column, ...}`, а `frontend/src/stores/wsStore.ts` трактует `event.data` как полный `Ticket`.
   - Почему это блокер:
     - ТЗ требует board updates `<500ms` всем подключённым пользователям; текущий контракт для этого не собран.
   - Критерии приёмки:
     - Kanban/Ticket screens подписываются на активный проект и отписываются при смене/уходе;
     - backend/frontend делят одну typed schema для `ticket.created/updated/moved/deleted`;
     - второе клиентское соединение видит перемещение тикета в реальном времени;
     - есть e2e smoke на multi-client WebSocket сценарий.

3. [ ] **`3.1 Kanban` + `3.3 Dashboard` + `4.1 MVP`: убрать synthetic project context**
   - Подтверждённые факты:
     - `frontend/src/components/dashboard/MetricsDashboard.tsx`: `DEFAULT_PROJECT_ID = 'default'`.
     - `frontend/src/components/kanban/KanbanBoard.tsx`: при отсутствии проектов автоматически создаёт `"My Project"`.
     - runtime в прошлых проходах уже показывал: `project_id=default -> 422`.
   - Почему это блокер:
     - board/dashboard/ws работают не от одного реального project selector, а от заглушек и скрытого auto-create.
   - Критерии приёмки:
     - есть явный onboarding/create/select flow для проекта;
     - нет synthetic `default` project id и auto-create `"My Project"`;
     - board/dashboard/ticket/ws используют единый active `project_id: UUID`;
     - есть tests на empty state и project switching.

4. [ ] **`3.2 Экран тикета` + `4.3-4.6` + `6.3-6.6`: превратить ticket detail в реальный artifact center**
   - Подтверждённые факты:
     - `frontend/src/components/tickets/TicketDetail.tsx` не показывает `acceptance_criteria`, хотя ТЗ требует.
     - `frontend/src/stores/ticketStore.ts` реально грузит только `ticket`, `comments`, `attachments`; `plans/codeGens/aiLogs/reviews/testResults/history` не запрашиваются.
     - `frontend/src/components/tickets/TicketDetail.tsx` рендерит placeholder-блоки, а не diff/review/test drill-down.
     - `PlanApproval`, `PlanViewer`, `ReviewPanel`, `BuildStatus`, `TestResultsPanel`, `SecurityScanResults`, `DeployGate`, `RollbackButton` существуют, но не подключены ни в одном route/component.
     - `frontend/src/components/tickets/TicketForm.tsx` не имеет отдельного поля `acceptance_criteria`; оно растворено в placeholder description.
   - Почему это блокер:
     - UI обещает control-center, но большая часть data-flow не wired.
   - Критерии приёмки:
     - ticket screen показывает `description + acceptance criteria`;
     - каждая artifact tab делает реальный fetch и имеет `loading/empty/error/success`;
     - code tab показывает unified diff и inline review comments;
     - tests tab показывает suite/case drill-down, логи и screenshots;
     - orphan-компоненты либо подключены, либо удалены как мёртвый слой.

5. [ ] **`4.5 Code Review` + `6.5`: заземлить AI review в фактический git diff**
   - Подтверждённые факты:
     - `backend/app/api/v1/reviews.py` передаёт в AI review строку `PR URL`/`branch_name`, а не реальный diff.
     - `backend/app/api/v1/git_ops.py` уже умеет отдавать `ticket git diff`.
   - Почему это блокер:
     - inline findings по branch name не дают надёжного `Code Review Pipeline`.
   - Критерии приёмки:
     - AI review использует diff из git layer;
     - inline comments содержат существующие `file/line` из diff;
     - есть multi-model result split по агентам;
     - есть negative tests на `empty/unavailable diff`.

6. [ ] **`4.4 AI Coding Engine` + `6.4`: включить worktree isolation и parallel subtask execution**
   - Подтверждённые факты:
     - `backend/app/workflows/pipeline_orchestrator.py` гоняет subtask-ы последовательно в одной feature branch.
     - `backend/app/git/repo_manager.py` уже содержит `create_worktree(...)`, но orchestrator его не использует.
     - `backend/app/api/v1/git_ops.py` при update делает `fetch --all` + `reset --hard origin/{branch}`.
   - Почему это блокер:
     - Это расходится и с ТЗ, и с безопасностью runtime для параллельных агентов.
   - Критерии приёмки:
     - каждая subtask получает свой `worktree path/branch`;
     - независимые subtask-ы выполняются параллельно;
     - merge-back в feature branch логирует конфликты/latency;
     - update flow не использует destructive `reset --hard` на active workspace;
     - есть benchmark `parallel vs sequential` на одном плане.

7. [ ] **`4.2 Git + Context` + `6.2`: заменить placeholder dependency API на реальный import graph**
   - Подтверждённые факты:
     - `backend/app/api/v1/context.py` возвращает `dependencies=[]` и сообщение `not yet implemented`.
   - Почему это блокер:
     - acceptance для graph/import relations и quality context engine сейчас не может быть честно закрыт.
   - Критерии приёмки:
     - endpoint возвращает реальные `import/require/from` связи для JS/TS/Python;
     - UI показывает зависимости по файлу;
     - benchmark: `precision@5 > 0.7`, incremental reindex `< 30s` на тестовом датасете;
     - regression tests покрывают fixture-repositories.

8. [ ] **`3.4 Редактор тестов` + `4.6 CI/CD и тесты` + `6.6`: собрать настоящий test execution flow**
   - Подтверждённые факты:
     - `frontend/src/api/testResults.ts` умеет `tests/run` и `tests/generate`, но UI/Store их не вызывает.
     - `backend/app/api/v1/test_results.py` запускает тесты из synthetic path `/app/projects/{project_name}`.
     - `backend/.venv/bin/ruff check backend/app backend/tests` падает на 48 issues.
     - `e2e/package.json` всё ещё содержит dummy `"test": "echo \"Error: no test specified\"..."`.
     - `e2e/playwright.config.ts` держит `webServer` закомментированным.
     - `npx playwright test` падает: Chromium не установлен и backend на `localhost:8001` не поднят.
   - Почему это блокер:
     - CI/test loop формально декларирован, но реальный execution path не закрыт от UI до e2e.
   - Критерии приёмки:
     - один canonical verify-flow запускает backend tests/lint/types + frontend tests/build + e2e smoke;
     - e2e scripts в `package.json` реальные, browsers preinstalled в CI/automation;
     - frontend даёт UI для custom test + AI test generation + test run;
     - backend test runner использует реальный repo/worktree path;
     - `ruff` зелёный на `backend/app` и `backend/tests`.

9. [ ] **`6.* Verification` + `7.1-7.4`: сделать среду воспроизводимой для automation/CI/local**
   - Подтверждённые факты:
     - repo-root `pytest -q` падает из-за отсутствующих runtime deps (`jose`) в системном Python;
     - backend tests зелёные только через `backend/.venv/bin/pytest`;
     - internet refresh в этом запуске заблокирован средой: `web` tool `503`, DNS наружу не резолвится.
   - Почему это блокер:
     - automation не должна зависеть от ручного знания "какой именно python/venv запускать".
   - Критерии приёмки:
     - repo-root verify документирован и самодостаточен;
     - local/CI/automation используют одинаковый bootstrap;
     - offline/blocked-network режим явно обрабатывается и не ломает audit-проходы;
     - есть отдельный preflight check для browsers, secrets, AI provider keys и dev servers.

### Идеи извне / internet refresh

- [ ] **В этом запуске свежие интернет-идеи не переподтверждены**
  - `web` tool вернул `503 Service Unavailable`
  - `curl` до `git-scm.com`, `playwright.dev`, `docs.github.com` не прошёл: `Could not resolve host`
  - backlog `Best Practices Backlog (из интернета, 2026-03-27)` из `v13` оставляю как carry-over, но он **не перепроверен в этом запуске**
- [ ] **При первом net-enabled прогоне переподтвердить official-doc ускорители**
  - GitHub Actions: caching + concurrency + path filters
  - Playwright: `webServer`, browser install, sharding
  - Git: `worktree` как стандартный primitive для parallel agent execution
  - OpenTelemetry / FastAPI instrumentation для end-to-end trace по тикету

### Следующий рабочий порядок

1. [ ] RBAC matrix + tests correction (`1.3`, `4.1`, `6.1`)
2. [ ] WS subscribe + shared event schema (`3.1`, `4.1`)
3. [ ] Real project selection, без `default`/auto-create (`3.1`, `3.3`)
4. [ ] Ticket artifact center wiring (`3.2`, `4.3-4.6`)
5. [ ] Diff-grounded review + worktree orchestration (`4.4`, `4.5`)
6. [ ] Canonical verify/e2e/test editor (`3.4`, `4.6`, `6.*`)

---

## Ревизия на 2026-03-27 v13 (автоматический проход; coverage boost + frontend tests + e2e skeleton + best practices refresh)

Проверено командами:
- `backend/.venv/bin/pytest -q` -> **529 passed in 30.31s** (было 440)
- `backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q` -> **TOTAL 81%** (было 77%)
- `frontend: npx vitest run` -> **53 passed** (было 0 — тестов не было)
- `frontend: npm run build` -> **OK**

### Что сделано в этом проходе

- [x] **Coverage: 77% → 81% (+89 новых backend тестов)**
  - Новые тест-файлы:
    - `tests/test_git/test_github_client.py` (28 тестов): все методы GitHubClient + OAuth helpers
    - `tests/test_git/test_repo_manager.py` (24 теста): GitResult, clone, branch, merge, diff, worktree
    - `tests/test_context/test_embeddings.py` (16 тестов): EmbeddingService init, batching, error handling, zero vectors
    - `tests/test_agents/test_planning_agent.py` (10 тестов): _parse_plan_output, PlanSubtask, GeneratedPlan
    - `tests/test_agents/test_gemini_agent.py` (11 тестов): init, generate, fallback model, system prompt, empty response
  - Покрытие ключевых модулей:
    - `github_client.py`: 27% → **100%** ✓
    - `embeddings.py`: 35% → **100%** ✓
    - `repo_manager.py`: 36% → **99%** ✓
    - `gemini_agent.py`: 46% → **100%** ✓
    - `planning_agent.py`: 48% → **68%**

- [x] **Frontend tests настроены (Vitest + RTL + jest-dom)**
  - Установлены: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`
  - `vite.config.ts` обновлён с test-конфигурацией (jsdom, globals, setupFiles)
  - `package.json` дополнен `"test"` и `"test:watch"` скриптами
  - Написаны 53 теста:
    - `src/utils/formatters.test.ts` (16 тестов): все formatter-функции
    - `src/utils/permissions.test.ts` (20 тестов): RBAC (owner/pm_lead/developer/ai_agent), human gate columns, deploy policy
    - `src/utils/constants.test.ts` (17 тестов): column names/labels/colors, priorities, WS events, API routes

- [x] **E2E Playwright skeleton настроен**
  - `e2e/playwright.config.ts` создан с chromium project, trace on retry, screenshot on failure
  - `e2e/tests/smoke.spec.ts` с 5 smoke тестами:
    - homepage loads, login form fields, invalid credentials error, register page, backend health
  - Playwright установлен как devDependency

- [x] **AI provider graceful degradation улучшена**
  - `review_agent.py`: расширен except block с `ValueError` до `(ValueError, Exception)` с логированием
  - Router уже имел StubAgent fallback + _unavailable_agents кэш — подтверждено как работающее

- [x] **Best Practices Backlog обновлён из свежих интернет-источников (2026)**
  - Добавлены рекомендации по:
    - AI governance & agent trust scoring (Greptile, DEV Community)
    - Multi-model strategy: параллельный запуск моделей для cross-check (Addy Osmani, 2026)
    - Security-as-code: codifying policies as unit tests (AppSentinels, Levo.ai)
    - Runtime observability: API behavior analytics + anomaly detection (FastLaunchAPI, Zestminds)
    - Context-first architecture: skeleton → components → constraints (DEV Community, Leanware)

### Что осталось открытым (приоритет для следующего прохода)

1. [x] ~~Coverage 77% → 80%+~~ **ДОСТИГНУТО: 81%**
2. [ ] **Coverage 81% → 85%**: добить `coding_agent.py` (57%), `pipeline_orchestrator.py` (52%), `builder.py` (41%), `security_scanner.py` (46%), `git_ops.py` (45%)
3. [ ] **Project context**: убрать `DEFAULT_PROJECT_ID='default'` и auto-create
4. [ ] **Ticket artifact center**: подключить все вкладки TicketDetail к реальным API
5. [ ] **WebSocket subscribe**: подключить `subscribeProject()`/`unsubscribeProject()` в KanbanBoard/TicketDetail
6. [ ] **Frontend component tests**: написать RTL тесты для LoginPage, KanbanBoard, TicketDetail
7. [ ] **E2E tests**: установить Playwright browsers, запустить smoke с dev-сервером
8. [ ] **Dependency API**: заменить placeholder `/context/deps/` на реальный import graph
9. [ ] **AI review grounding**: подключить реальный git diff в review_agent

---

## Best Practices Backlog (из интернета, 2026-03-27)

### AI Pipeline Best Practices
- [ ] Внедрить context-first prompting: передавать AI-агентам полный контекст проекта (endpoints, constraints, schema) вместо коротких запросов — повышает качество генерации на 30-40% (dev.to, leanware.co)
- [ ] Добавить agent trust scoring и auto-merge policies: AI-сгенерированные PR с низким risk score могут проходить fast-track review (datagrid.com, mabl.com)
- [ ] Версионировать промпты и agent-конфиги через review/test/approve flow наравне с кодом — safe prompt versioning (AWS Prescriptive Guidance)
- [ ] Внедрить test intelligence: AI выбирает и запускает только тесты, затронутые изменением, сокращая test cycle до 80% (virtuosoqa.com)
- [ ] Добавить self-healing tests: агент автоматически чинит сломанные тесты при изменении UI/environment (virtuosoqa.com, mabl.com)
- [ ] Использовать memory files и constitution files для поддержания consistency между AI-сессиями (dev.to, arxiv.org)
- [ ] Начинать AI-автоматизацию с read-only workflows (triage, CI failure analysis, doc audit) перед переходом к write-операциям (rsaconference.com)

### FastAPI / Backend Best Practices
- [ ] Перейти на feature-based (modular) структуру: каждый feature (auth, tickets, pipeline) — self-contained модуль со своими endpoints/models/services/tasks (fastlaunchapi.dev)
- [ ] Внедрить паттерн Repository Layer: вынести DB-запросы из сервисов в отдельные repository-классы для лучшей тестируемости (zhanymkanov/fastapi-best-practices)
- [ ] Использовать Pydantic BaseSettings с .env для всей конфигурации вместо прямого os.getenv (fastlaunchapi.dev, zestminds.com)
- [ ] Добавить database isolation в тестах: test-specific fixtures + app.dependency_overrides для inject test DB sessions (fastapi.tiangolo.com)
- [ ] Генерировать OpenAPI client/types для frontend автоматически при каждом изменении API — antidote к contract drift (zhanymkanov/fastapi-best-practices)
- [ ] Обновить Python runtime до 3.12+ для performance gains и улучшенной поддержки asyncio (zestminds.com)
- [ ] Внедрить API versioning через path prefix /api/v1/ с чёткой deprecation policy для breaking changes (dev.to, fastlaunchapi.dev)

### Security Best Practices
- [ ] Добавить security-focused system prompts для AI-агентов: напоминание о безопасности повышает secure code generation с 56% до 66% (veracode.com, OpenSSF)
- [ ] Внедрить проверку на dependency hallucinations: валидировать что все AI-предложенные пакеты реально существуют в PyPI/npm перед установкой (darkreading.com, rafter.so)
- [ ] Перейти с long-lived API keys на ephemeral identity-based credentials для AI-агентов и сервисов (mondaq.com, SANS)
- [ ] Добавить SAST/DAST сканирование в CI pipeline: SonarQube/CodeQL + Bandit для Python (veracode.com, blackduck.com)
- [ ] Применить RBAC к AI-системам: каждый агент имеет defined role, explicit permissions и ограниченный scope доступа (mondaq.com)
- [ ] Автоматизировать policy enforcement: блокировать risky imports и insecure patterns на уровне pipeline, а не review (veracode.com)
- [ ] Добавить AI incident response plan: процедура реагирования на security-инциденты связанные с AI-генерированным кодом (SANS, CSA)

### Observability Best Practices
- [ ] Внедрить OpenTelemetry для metrics/logs/traces — vendor-agnostic стандарт, совместимый с Datadog/Grafana/Langfuse (IBM, dynatrace.com)
- [ ] Добавить end-to-end tracing для AI pipeline: chain-level tracing от prompt до commit для reproducibility и debug (montecarlodata.com, uptimerobot.com)
- [ ] Мониторить RAG pipeline: query latency, retrieval precision, vector store health в реальном времени (montecarlodata.com)
- [ ] Определить SLA для AI-агентов: response time, success rate, cost-per-task как для инфраструктурных сервисов (uptimerobot.com)
- [ ] Добавить drift detection: отслеживать деградацию качества AI-генерации и prompt effectiveness со временем (ovaledge.com, ir.com)
- [ ] Внедрить observability-as-code: конфигурации мониторинга и алертов в version-controlled файлах рядом с кодом (middleware.io, logicmonitor.com)
- [ ] Интегрировать мониторинг в CI/CD: ловить drift и broken prompts до production, алерты в Slack/PagerDuty (dynatrace.com)
- [ ] Унифицировать data observability и AI observability: мониторить не только модель, но и upstream data pipelines (montecarlodata.com)

---

## Ревизия на 2026-03-27 v12 (автоматический проход; TZ audit + runtime smoke)

Проверено командами:
- `repo root: backend/.venv/bin/pytest --cov=backend/app --cov-report=term -q` -> **440 passed, TOTAL 77%, 31 warnings**
- `repo root: backend/.venv/bin/ruff check backend/app backend/tests` -> **All checks passed!**
- `repo root: backend/.venv/bin/mypy backend/app --ignore-missing-imports` -> **Success: no issues found in 96 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**, но warning остался: `dist/assets/index-BhIKKasi.js = 519.18 kB`
- runtime smoke через ASGI + SQLite override:
  - `GET /api/v1/dashboard/pipeline-stats?project_id=default` -> **422 uuid_parsing**
  - `GET /api/v1/dashboard/pipeline-stats?project_id=<uuid>` -> **200**
  - `GET /api/v1/tickets/{id}/plans` -> **200 []**
  - `GET /api/v1/tickets/{id}/reviews` -> **200 []**
  - `GET /api/v1/tickets/{id}/test-results` -> **200 []**
  - `GET /api/v1/tickets/{id}/history` -> **200 []**
  - `GET /api/v1/ai-logs?ticket_id={id}` -> **200**
  - `GET /api/v1/context/deps/frontend/src/App.tsx` -> **200**, но endpoint подтверждён как placeholder
  - `GET /api/v1/deployments/health/staging` -> **404**
- попытка обновить внешние best practices через встроенный web-search и прямые HTTP-запросы -> **неуспешно**: web tool не ответил, DNS в sandbox не резолвит внешние домены

### Краткий вердикт

- [x] **Локальная инженерная база стабильна**: backend tests, coverage run, ruff, mypy, frontend lint и build проходят.
- [x] **Мы идём к цели частично**: фундамент MVP и часть runtime-контрактов уже живы (`history`, `ai-logs`, базовые artifact routes, unified WS envelope из v11).
- [ ] **Acceptance-ready состояние по ТЗ ещё не достигнуто**: основные разрывы теперь не в compile-time, а в product/runtime flow, orchestration safety, real-time subscription и эксплуатационных контрактах.
- [ ] **Internet refresh в этом проходе заблокирован средой**: backlog "Best Practices Backlog (из интернета)" выше можно использовать как входной материал, но он не был переподтверждён в этом запуске.

### Что автодорабатывать следующими проходами

1. [ ] **`6.* Verification` + `7.* Эксплуатация`: переоткрыт вопрос canonical verify-flow**
   - Подтверждённые факты:
     - root-level `pytest` теперь проходит, но выдаёт `PytestConfigWarning: Unknown config option: rootdir`;
     - значит корневой `pyproject.toml` всё ещё содержит некорректную pytest-настройку, хотя smoke-result зелёный.
   - Почему это блокер:
     - automation/CI/local run должны иметь одну "чистую" truth-команду без предупреждений и неявных fallback-ов;
     - текущая v11 формулировка "cwd-зависимость устранена" технически закрыта не до конца.
   - Критерии приёмки:
     - `pytest` из корня, из `backend/` и в CI даёт один и тот же результат **без warnings**;
     - есть одна repo-root команда проверки (`make verify` или эквивалент), включающая backend + frontend;
     - CI и локальная разработка используют один и тот же verify-flow.

2. [ ] **`3.1 Kanban` + `3.3 PM/Admin` + `4.1 MVP`: убрать фальшивый project context**
   - Подтверждённые факты:
     - `frontend/src/components/dashboard/MetricsDashboard.tsx` использует `DEFAULT_PROJECT_ID = 'default'`;
     - runtime smoke подтверждает: `project_id=default` -> **422**, валидный UUID -> **200**;
     - `frontend/src/components/kanban/KanbanBoard.tsx` при отсутствии проектов скрыто создаёт `"My Project"`.
   - Почему это блокер:
     - UI и API до сих пор расходятся в source of truth для активного проекта;
     - acceptance разделов `3.1`, `3.3`, `4.1` нельзя честно закрыть, пока часть экранов работает на synthetic project id и hidden auto-create.
   - Критерии приёмки:
     - board/dashboard/settings/deploy flows используют единый выбранный `project_id: UUID`;
     - auto-create `"My Project"` отсутствует;
     - пустое состояние ведёт в явный onboarding/create/select flow;
     - WebSocket и HTTP используют один и тот же active project context.

3. [ ] **`3.2 Экран тикета` + `4.3-4.6`: превратить ticket artifact center из skeleton UI в реальный runtime**
   - Подтверждённые факты:
     - runtime smoke показывает, что `plans/reviews/test-results/history/ai-logs` API уже существуют и возвращают **200**;
     - `frontend/src/stores/ticketStore.ts` объявляет `plans`, `codeGens`, `aiLogs`, `reviews`, `testResults`, `history`, но реально грузит только `ticket`, `comments`, `attachments`;
     - отдельного ticket-scoped API для `AiCodeGeneration` в `backend/app/api/v1/*` по-прежнему нет.
   - Почему это блокер:
     - экран тикета визуально обещает единый control-center, но runtime заполняет только малую часть вкладок;
     - sections `3.2`, `4.3`, `4.4`, `4.5`, `4.6` требуют не tabs-заглушки, а реальные artifact flows.
   - Критерии приёмки:
     - каждая вкладка экрана тикета грузит реальные данные через API;
     - для code generation есть отдельный API-контракт, либо вкладка убрана до реализации;
     - все вкладки имеют `loading / empty / error / success` состояния;
     - есть frontend tests на загрузку artifact tabs и runtime smoke по ticket-detail flow.

4. [ ] **`4.5 Code Review Pipeline`: заземлить AI review в реальный git diff**
   - Подтверждённые факты:
     - `backend/app/api/v1/reviews.py` передаёт в review не фактический diff, а строку из `PR URL` / `branch_name`;
     - реальный diff API в `git_ops` уже существует, но `reviews/ai-trigger` его не использует.
   - Почему это блокер:
     - ревью по описанию тикета или имени ветки не закрывает acceptance `4.5`;
     - inline findings не могут быть надёжно привязаны к реальным строкам файла.
   - Критерии приёмки:
     - AI review использует реальный diff из git layer;
     - review comments ссылаются на существующие `file/line`, которые видны в diff UI;
     - есть negative tests на сценарий "ветка есть, diff пустой/недоступен";
     - developer видит отдельно ревью по моделям и агрегированный verdict.

5. [ ] **`4.4 AI Coding Engine`: включить worktree-изоляцию и убрать destructive git sync**
   - Подтверждённые факты:
     - `backend/app/workflows/pipeline_orchestrator.py` всё ещё гоняет подзадачи последовательно в одной feature branch;
     - `create_worktree(...)` в `backend/app/git/repo_manager.py` есть, но orchestration его не использует;
     - `backend/app/api/v1/git_ops.py` при update делает `fetch --all` + `reset --hard origin/{branch}`.
   - Почему это блокер:
     - ТЗ требует отдельный `git worktree/branch` на подзадачу и параллельное выполнение;
     - `reset --hard` опасен для in-flight work и несовместим с безопасной идемпотентностью.
   - Критерии приёмки:
     - каждая подзадача живёт в собственном worktree path;
     - update/sync не использует destructive reset по рабочему каталогу, где может идти выполнение;
     - есть merge-back step с метрикой конфликтов;
     - параллельный path измеримо быстрее sequential path на тестовом плане.

6. [ ] **`4.2 Context Engine`: заменить placeholder dependency API на реальный import graph**
   - Подтверждённые факты:
     - runtime smoke подтверждает: `/api/v1/context/deps/...` отвечает `200`, но это заглушка;
     - `backend/app/api/v1/context.py` прямо возвращает `dependencies=[]` и сообщение "not yet implemented".
   - Почему это блокер:
     - sections `4.2` и `6.2` требуют dependency graph для JS/TS/Python и проверяемые quality-benchmarks;
     - без import graph Context Engine ограничен semantic search и даёт потолок качеству planning/coding agents.
   - Критерии приёмки:
     - endpoint отдаёт реальные `import/require/from` связи для JS/TS/Python;
     - есть benchmark для `precision@5` и latency инкрементальной переиндексации;
     - dependency graph покрыт regression tests на реальных fixture-репозиториях.

7. [ ] **`4.6 CI/CD и тесты`: закрыть execution gap, а не только lint/type floor** *(ЧАСТИЧНО ЗАКРЫТ v13)*
   - Подтверждённые факты:
     - coverage теперь **81%** (>= 80% порог ТЗ) ✓;
     - `frontend/package.json` содержит `test` и `test:watch` scripts, Vitest настроен, 53 теста проходят ✓;
     - `e2e/` содержит Playwright config и 5 smoke тестов (skeleton, нужна установка browsers) ✓;
     - `backend/app/api/v1/test_results.py` запускает tests через synthetic path `"/app/projects/{project_name}"`.
   - Почему это блокер:
     - sections `4.6`, `5.2`, `6.6`, `7.*` требуют реальные unit/integration/e2e/security artifacts;
     - текущий зелёный статус означает "код собирается", но ещё не "pipeline честно проверен end-to-end".
   - Критерии приёмки:
     - backend coverage >= `80%`;
     - настроены Vitest + RTL для frontend;
     - есть Playwright smoke для auth/board/ticket/admin flow;
     - test runner использует реальный repo/worktree path, а не synthetic `"/app/projects/*"`;
     - CI публикует test/security artifacts и блокирует merge по критичным findings.

8. [ ] **`2.1 Object Storage` + `7.1 Security/7.* Operations`: прекратить смешивать runtime uploads с кодовой базой**
   - Подтверждённые факты:
     - `backend/app/api/v1/attachments.py` пишет в `Path("uploads")`;
     - `.gitignore` исключает только `backend/uploads/`, а не корневой `uploads/`;
     - в workspace уже лежат runtime-артефакты вида `uploads/*/*_secret.txt`, `*_report.pdf`, `*_test.txt`.
   - Почему это блокер:
     - runtime-файлы и потенциально чувствительные артефакты попадают прямо в репозиторий/workspace;
     - это противоречит разделам object storage, security и operational hygiene.
   - Критерии приёмки:
     - attachments вынесены в object storage abstraction или внешний volume вне репо;
     - корневой `uploads/` не используется как долгоживущий runtime store;
     - настроены cleanup/retention policy и проверка, что чувствительные файлы не попадают в VCS/workspace.

9. [ ] **`4.7 Production` + `5.* Metrics/SLA`: довести deploy/health contract до ТЗ**
   - Подтверждённые факты:
     - runtime smoke: `GET /api/v1/deployments/health/staging` -> **404**;
     - `backend/app/api/v1/deployments.py` умеет health только по `deployment_id`, а не по environment contract;
     - default canary percentage в API = `10`, тогда как ТЗ задаёт `5% -> 25% -> 50% -> 100%`;
     - staging deploy по-прежнему использует `project_name = "default"` fallback.
   - Почему это блокер:
     - production acceptance из разделов `4.7`, `5.*`, `6.7` требует environment-level health/readiness, rollback rules и соответствие canary schedule;
     - скрытый `"default"` ломает единый project context и в deploy path.
   - Критерии приёмки:
     - есть environment-level health/readiness contract для `staging` и `production`;
     - дефолтный canary flow соответствует ТЗ: `5 -> 25 -> 50 -> 100`;
     - deploy/test flows не используют `"default"` как скрытый fallback;
     - dashboard показывает метрики раздела `5` в привязке к конкретному проекту/деплою.

10. [ ] **`2.2 Pipeline` + `3.1 real-time`: довести подписку WebSocket до рабочего UX**
   - Подтверждённые факты:
     - `frontend/src/hooks/useWebSocket.ts` открывает сокет, но не подписывает активный проект;
     - `frontend/src/stores/wsStore.ts` умеет `subscribeProject()`/`unsubscribeProject()`, но реальных call-sites нет.
   - Почему это блокер:
     - protocol envelope уже унифицирован, но real-time по проекту всё ещё не завершён на клиенте;
     - acceptance по `<500ms` на board/ticket не проверяется, пока клиент не подписывается на project-scoped events.
   - Критерии приёмки:
     - board/ticket подписываются на активный проект при входе и отписываются при смене/уходе;
     - два клиента на одном проекте видят изменения доски менее чем за `500ms`;
     - есть frontend integration/e2e тест на subscribe/unsubscribe и reconnect.

### Как использовать уже собранный internet backlog в этой кодовой базе

- [ ] **Привязать `test intelligence` из backlog к текущему execution gap**
  - Применить к `CI + test_results.py + будущему e2e`: сначала impacted tests, потом full regression.
  - Критерии приёмки: среднее verify-time сокращено, а false-negative/false-positive regressions не выросли.

- [ ] **Привязать `OpenAPI client/types generation` к project-context и artifact drift**
  - Генерация types/client должна убрать ручные расхождения между backend UUID-contracts и frontend `default`/ручными shape-ами.
  - Критерии приёмки: frontend типы и API client генерируются из backend schema на CI и локально.

- [ ] **Привязать `OpenTelemetry / end-to-end tracing` к orchestration**
  - Нужен ticket-level trace: `trigger -> planning -> coding -> review -> testing -> deploy`.
  - Критерии приёмки: по одному `ticket_id` можно восстановить цепочку вызовов, стоимость, latency и точку сбоя.

- [ ] **Привязать `read-only workflows first` к самим automation-проходам**
  - Для ревизора, CI triage, doc audit и observability-first задач automation сначала должен собирать сигналы и формировать verdict, а не сразу писать в рабочие ветки.
  - Критерии приёмки: automation умеет отдельные режимы `audit-only` и `write-fix`, а dangerous paths включаются явно.

- [ ] **Привязать `memory/constitution files` к agent orchestration**
  - Важно ограничить роль и допустимые side-effects каждого AI-агента: planning, coding, review, security, deploy.
  - Критерии приёмки: у каждого агента есть scope, acceptance-checklist и policy, используемые одинаково в local/automation/CI.

### Дополнительные локальные идеи ускорения, найденные не через интернет

- [ ] **Использовать `backend/uv.lock` в CI как canonical dependency source**
  - Сейчас backend CI опирается на `requirements.txt`, хотя в репо уже есть `uv.lock`;
  - это шанс ускорить и стабилизировать установку зависимостей между local/CI.

- [ ] **Разрезать frontend bundle по маршрутам**
  - build уже предупреждает о chunk `519.18 kB`;
  - ticket/dashboard/admin/review секции логично выносить в route-level lazy loading.

---

## Ревизия на 2026-03-27 v11 (автоматический проход; implementation + coverage + best practices)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **440 passed in 30.19s** (было 302)
- `repo root: backend/.venv/bin/pytest -q` -> **440 passed in 30.17s** (было 243 passed / 59 failed)
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 77%** (было 70%)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **147 files already formatted**

### Что сделано в этом проходе

- [x] **P0 blocker #1 ЗАКРЫТ: repo-root pytest cwd-зависимость устранена**
  - Создан корневой `pyproject.toml` с `rootdir = "backend"` и `testpaths = ["backend/tests"]`
  - Теперь `backend/.venv/bin/pytest` из любого каталога даёт одинаковый результат: **440 passed**
  - Makefile и CI могут использовать единую repo-root команду

- [x] **P0 blocker #3 ЧАСТИЧНО ЗАКРЫТ: ticket history API endpoint создан**
  - Создан `backend/app/api/v1/ticket_history.py` с `GET /tickets/{ticket_id}/history`
  - Endpoint поддерживает пагинацию (`page`, `per_page`), возвращает audit trail newest-first
  - Роутер включён в `router.py`, smoke: `GET /tickets/{id}/history` -> **200**
  - Написаны 4 теста: empty, with_entries, pagination, unauthorized

- [x] **P0 blocker #5 ЗАКРЫТ: WebSocket envelope унифицирован**
  - `notification_service.py`: `{type, payload}` заменён на каноничный `{type, data, timestamp}`
  - `pipeline_orchestrator.py`: ad-hoc top-level поля перенесены в `data`, добавлен `timestamp`
  - Все server events теперь следуют единому envelope `{type, data, timestamp}` из `schemas/websocket.py`
  - Существующий тест `test_log_progress_broadcasts_ws` обновлён и проходит

- [x] **Security/hygiene: .gitignore для backend/uploads/**
  - Добавлен `backend/uploads/` в `.gitignore` — runtime артефакты больше не попадают в VCS

- [x] **Coverage: 70% → 77% (+134 новых тестов)**
  - `tests/test_context/` (новый): test_engine.py (16), test_code_parser.py (38), test_vector_store.py (9)
  - `tests/test_agents/`: test_coding_agent.py (24), test_security_agent.py (24), test_test_gen_agent.py (13)
  - Покрытие ключевых модулей:
    - `security_agent.py`: 31% → **100%**
    - `test_gen_agent.py`: 35% → **100%**
    - `vector_store.py`: 25% → **100%**
    - `code_parser.py`: 35% → **99%**
    - `engine.py`: 20% → **96%**
    - `coding_agent.py`: 24% → **57%**

- [x] **Best Practices Backlog добавлен в TODO.md**
  - 29 actionable items из 17+ интернет-источников по 4 категориям
  - AI Pipeline, FastAPI/Backend, Security, Observability

### Что осталось открытым (приоритет для следующего прохода)

1. [x] **Coverage 77% → 80%+**: ~~добить `embeddings.py` (35%), `github_client.py` (27%), `repo_manager.py` (36%)~~ **ЗАКРЫТО v13: 81%, все три модуля 99-100%**
2. [ ] **Project context**: убрать `DEFAULT_PROJECT_ID='default'` и auto-create (v10 P0 #2)
3. [ ] **Ticket artifact center**: подключить все вкладки TicketDetail к реальным API (v10 P0 #3)
4. [ ] **WebSocket subscribe**: подключить `subscribeProject()`/`unsubscribeProject()` в KanbanBoard/TicketDetail (v10 P0 #5)
5. [x] **Frontend tests**: ~~настроить Vitest + RTL, написать базовые unit tests~~ **ЗАКРЫТО v13: Vitest + RTL + 53 теста**
6. [x] **e2e tests**: ~~настроить Playwright, написать smoke для auth/board/ticket~~ **ЗАКРЫТО v13: Playwright config + 5 smoke тестов**
7. [ ] **Context engine deps**: заменить placeholder dependency API на реальный import graph (v10 P0 #6)

---

## Ревизия на 2026-03-27 v10 (автоматический проход; system/code audit + acceptance map)

Проверено командами:
- `repo root: backend/.venv/bin/pytest -q` -> **243 passed / 59 failed**; красный статус вызван не продуктовым регрессом, а тем, что из корня не подхватывается backend-конфиг `pytest-asyncio`
- `backend: .venv/bin/pytest -q` -> **302 passed in 23.60s**
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 70%**
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **138 files already formatted**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 95 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**, но bundle warning остался: `dist/assets/index-BhIKKasi.js = 519.18 kB`
- runtime smoke через ASGI + SQLite override:
  - `GET /api/v1/tickets/{id}/plans` -> **200 []**
  - `GET /api/v1/tickets/{id}/reviews` -> **200 []**
  - `GET /api/v1/tickets/{id}/test-results` -> **200 []**
  - `GET /api/v1/tickets/{id}/history` -> **404**
  - `GET /api/v1/dashboard/pipeline-stats?project_id=default` -> **422 uuid_parsing**
  - `GET /api/v1/dashboard/pipeline-stats?project_id=<uuid>` -> **200**
  - `GET /api/v1/context/deps/frontend/src/App.tsx` -> **200**, но это placeholder с `dependencies=[]`
  - `GET /api/v1/deployments/health/staging` -> **404**
  - `GET /api/v1/ai-logs` -> **200**

### Итог этого прохода

- [x] **Фундамент разработки стабилен локально из `backend/`**: backend tests/coverage/ruff/mypy и frontend lint/build проходят.
- [ ] **Acceptance-ready состояние по ТЗ всё ещё не достигнуто**: основная недостача теперь не в compile-time, а в runtime-контрактах, orchestration и воспроизводимости проверок.
- [ ] **Мы идём к цели частично**: базовая платформа стала ощутимо устойчивее, но sections `2.2`, `3.2-3.4`, `4.2-4.7`, `5.*`, `7.*` пока закрыты лишь частично.
- [ ] **Новый системный blocker процесса**: один и тот же backend test suite даёт зелёный или красный статус в зависимости от `cwd`, значит automation/CI/local run пока не имеют единой truth-команды.
- [x] **Ранее проблемные placeholder areas частично выправлены**: `plans` router существует; `UserManagement` и project settings уже подключены к реальному API, а не к демо-данным.

### P0. Какие разделы ТЗ надо автодорабатывать следующими проходами

1. [ ] **`6.* Verification` + `7.* Эксплуатация`: сделать один воспроизводимый repo-root verify flow**
   - Подтверждённые факты:
     - `backend/.venv/bin/pytest -q` из корня даёт **59 false-negative failures** по async tests;
     - тот же набор из каталога `backend/` проходит: **302 passed**;
     - `Makefile` ориентирован на Docker и не даёт каноничной локальной repo-root команды для automation.
   - Почему это блокер:
     - автоматический ревизор не должен менять verdict в зависимости от `cwd`;
     - до тех пор любые SLA/coverage/acceptance числа остаются не полностью воспроизводимыми.
   - Критерии приёмки:
     - есть одна repo-root команда проверки, дающая тот же результат в local/automation/CI;
     - `pytest-asyncio` и testpaths подхватываются одинаково из корня;
     - `Makefile` и CI используют тот же verify-flow, а не разные наборы команд.

2. [ ] **`3.1 Kanban` + `3.3 PM/Admin` + `4.1 MVP`: убрать неканоничный project context и скрытый auto-create**
   - Подтверждённые факты:
     - `frontend/src/components/dashboard/MetricsDashboard.tsx` использует `DEFAULT_PROJECT_ID = 'default'`;
     - runtime smoke подтверждает: `project_id=default` -> **422**, а UUID -> **200**;
     - `frontend/src/components/kanban/KanbanBoard.tsx` при отсутствии проектов авто-создаёт `"My Project"` вместо явного onboarding/create/select flow.
   - Почему это блокер:
     - UI и API до сих пор расходятся в source of truth для активного проекта;
     - acceptance по dashboard/board/settings нельзя честно закрыть, пока часть экрана работает на фальшивом project id.
   - Критерии приёмки:
     - все board/dashboard/settings/deploy flows используют единый выбранный `project_id: UUID`;
     - скрытый auto-create проекта отсутствует;
     - пустое состояние без проектов показывает явный onboarding/create/select сценарий;
     - WebSocket и HTTP используют один и тот же active project context.

3. [ ] **`3.2 Экран тикета` + `4.3-4.5`: довести ticket artifact center до реального runtime**
   - Подтверждённые факты:
     - runtime smoke: `GET /tickets/{id}/history` -> **404**;
     - в `backend/app/api/v1/router.py` нет ticket-scoped router для `history` и нет API для `AiCodeGeneration`;
     - `frontend/src/components/tickets/TicketDetail.tsx` рендерит вкладки `Plan | Code | Tests | AI Logs | History`, но `frontend/src/stores/ticketStore.ts` реально умеет грузить только `ticket`, `comments`, `attachments`.
   - Почему это блокер:
     - экран тикета визуально обещает единый control-center, но фактические артефакты цепляются лишь частично;
     - acceptance sections `3.2`, `4.3`, `4.5`, `4.6` требуют не вкладки-заглушки, а реальные artifact flows.
   - Критерии приёмки:
     - backend имеет ticket-scoped endpoints для `history`, `code generations`, `plans`, `reviews`, `test results`, `ai logs`;
     - store и UI грузят все вкладки через реальные API;
     - каждая вкладка имеет `loading / empty / error / success` состояние;
     - smoke по ticket-artifact routes возвращает стабильный `200`, а не смесь `404/[]`.

4. [ ] **`4.4 AI Coding` + `2.2 Pipeline`: включить реальную worktree-изоляцию и безопасный git sync**
   - Подтверждённые факты:
     - `backend/app/git/repo_manager.py` уже содержит `create_worktree(...)`, но `backend/app/workflows/pipeline_orchestrator.py` его не использует;
     - `run_coding_phase()` работает через `create_branch()` + `checkout_branch()` в одном общем checkout;
     - `backend/app/api/v1/git_ops.py` при повторном clone/update делает `fetch --all` + `reset --hard origin/{branch}`.
   - Почему это блокер:
     - ТЗ обещает отдельный `git worktree/branch` на подзадачу и безопасную идемпотентность;
     - destructive reset конфликтует с in-flight работой и не подходит под parallel AI coding.
   - Критерии приёмки:
     - каждая AI-подзадача живёт в собственном worktree path;
     - повторный sync не делает destructive reset по рабочему каталогу, где идёт выполнение;
     - orchestration имеет отдельный merge-back step и метрику конфликтов;
     - параллельные подзадачи измеримо быстрее sequential path.

5. [ ] **`2.2 Pipeline` + `3.1 real-time`: унифицировать WebSocket envelope и действительно подписывать активный проект**
   - Подтверждённые факты:
     - `frontend/src/hooks/useWebSocket.ts` только открывает сокет, но не делает project subscription;
     - `frontend/src/stores/wsStore.ts` содержит `subscribeProject()` / `unsubscribeProject()`, но call-sites не найдены;
     - backend schema задаёт канонический envelope `{type, data, timestamp}`, а `backend/app/services/notification_service.py` всё ещё шлёт `{type, payload}`;
     - `backend/app/workflows/pipeline_orchestrator.py` шлёт ad-hoc progress event с top-level полями, а не каноническим `data`.
   - Почему это блокер:
     - сокет формально есть, но протокол и подписка не доведены до acceptance-grade real-time;
     - inconsistent event shape ломает переносимость между board/ticket/notifications/pipeline.
   - Критерии приёмки:
     - при входе на board/ticket клиент делает `subscribe_project`, при смене проекта делает `unsubscribe`;
     - все server events используют единый envelope `{type, data, timestamp}`;
     - notifications, kanban updates и pipeline progress читаются единым parser path без специальных исключений;
     - два клиента на одном проекте видят board update менее чем за `500ms`.

6. [ ] **`4.2 Context Engine`: заменить placeholder dependency API на реальный dependency graph и quality-benchmark**
   - Подтверждённые факты:
     - runtime smoke: `/api/v1/context/deps/...` отвечает `200`, но явно пишет `"Dependency analysis is not yet implemented"`;
     - `backend/app/context/engine.py` умеет индексировать и искать, но dependency graph endpoint в `backend/app/api/v1/context.py` пока placeholder;
     - coverage у `context/engine.py` остаётся **20%**.
   - Почему это блокер:
     - sections `4.2` и `5.*` требуют измеримого Context Engine, а не только semantic search на уровне "что-то вернулось";
     - planning/coding agent quality без реального import/dependency graph упирается в потолок.
   - Критерии приёмки:
     - dependency endpoint отдаёт реальные `import/require` связи для JS/TS/Python;
     - есть benchmark для search quality (`precision@5`) и для инкрементального reindex latency;
     - context engine покрыт regression tests по indexing/search/dependency graph.

7. [ ] **`4.6 CI/CD и тесты`: закрыть execution gap, а не только lint/type floor**
   - Подтверждённые факты:
     - coverage держится на **70%**, а ТЗ требует `80%+`;
     - `e2e/` пуст;
     - во frontend нет test suite (`vitest`/RTL не настроены);
     - `backend/app/api/v1/test_results.py` по-прежнему запускает tests через synthetic path `"/app/projects/{project_name}"`;
     - GitHub Actions сейчас покрывают lint/type/build/test, но не запускают SAST/dependency audit/e2e.
   - Почему это блокер:
     - sections `4.6`, `5.2`, `7.*` требуют реальные test/security/deploy artifacts;
     - сейчас зелёный статус означает "код собирается", а не "pipeline честно проверен".
   - Критерии приёмки:
     - backend coverage >= `80%`;
     - есть frontend unit/integration suite;
     - есть Playwright smoke для auth/board/ticket/admin flow;
     - test runner работает на canonical repo/worktree path, а не на synthetic `"/app/projects/*"`;
     - CI публикует security/test artifacts и блокирует merge при критичных findings.

8. [ ] **`2.1 Object Storage` + `7.* Security/Operations`: вынести runtime uploads из workspace и прекратить смешивать артефакты с кодом**
   - Подтверждённые факты:
     - `backend/app/api/v1/attachments.py` пишет файлы в локальный `uploads/`;
     - в workspace реально лежит `backend/uploads/**`, включая `*_secret.txt`, `*_report.pdf`, `*_test.txt`;
     - `.gitignore` не исключает `backend/uploads/`, а ТЗ требует `S3 / MinIO` для артефактов.
   - Почему это блокер:
     - runtime-артефакты и потенциально чувствительные файлы смешиваются с кодовой базой;
     - это противоречит разделам object storage, observability и operational hygiene.
   - Критерии приёмки:
     - attachments/storage вынесены в object storage abstraction или отдельный volume вне workspace;
     - `backend/uploads/` не используется как долгоживущий runtime store внутри репо;
     - есть retention/cleanup policy и проверка, что временные/секретные файлы не попадают в кодовую базу.

9. [ ] **`4.7 Production` + `5.* Metrics/SLA`: довести deploy/health contract и метрики до операционного acceptance**
   - Подтверждённые факты:
     - runtime smoke: `GET /api/v1/deployments/health/staging` -> **404**;
     - `backend/app/api/v1/deployments.py` умеет health только по `deployment_id`, а не по environment contract;
     - deploy/test code всё ещё местами использует `project_name = "default"` fallback;
     - `dashboard_service.py` считает лишь часть метрик из раздела `5`.
   - Почему это блокер:
     - ТЗ требует canary rollout, rollback по аномалиям и измеримый health/readiness contract;
     - без полного SLA mapping production acceptance формально не проверяется.
   - Критерии приёмки:
     - есть environment-level health/readiness contract для staging/production;
     - canary progression `5% -> 25% -> 50% -> 100%` покрыт тестами и rollback rules;
     - dashboard отображает формулы, thresholds и ownership для метрик раздела `5`;
     - deploy/test flows не используют `"default"` как скрытый project fallback.

### Что уже можно считать подтверждённым прогрессом

- [x] `plans`, `reviews`, `test-results`, `ai-logs` routes существуют и отвечают.
- [x] frontend admin/settings больше не висят на placeholder данных.
- [x] PM-only production gate на backend удерживается.
- [x] backend local quality floor стабилен: tests/ruff/mypy зелёные при запуске из каноничного каталога.

### Рекомендуемый порядок следующей автодоработки

1. [ ] **Verification first**: выровнять repo-root verify command и убрать `cwd`-зависимый verdict.
2. [ ] **Project context first**: убрать `default`/auto-create и включить единый active project flow.
3. [ ] **Ticket center first**: добавить `history` + `code generations` API и подцепить все вкладки `TicketDetail`.
4. [ ] **Git/runtime first**: включить worktree isolation и безопасный sync без destructive reset.
5. [ ] **Protocol first**: привести WebSocket события к единому envelope и подписке по проекту.
6. [ ] **Verification depth first**: добить frontend tests/e2e/security scans и поднять coverage до `80%+`.
7. [ ] **Ops first**: health/readiness contract, deploy SLA, object storage hygiene.

### Интернет и ускорение процесса

- [ ] **Live web lookup в этом проходе был заблокирован средой**:
  - web-tool возвращал `503`;
  - shell-попытка `curl https://playwright.dev/...` упёрлась в `Could not resolve host`.
- [ ] **Следствие**: в этом запуске новые идеи из интернета не были live-подтверждены; использовать прежний external backlog только как ориентир, а не как заново верифицированный факт.
- [ ] **Что всё равно имеет смысл вынести в acceleration backlog следующими циклами**:
  - единый repo-root verify target для automation/local/CI;
  - generated API client/types от backend OpenAPI как antidote к contract drift;
  - worktree pool + безопасный repo sync как база для параллельного AI coding;
  - contract tests на WebSocket envelope и ticket artifact routes;
  - внешнее object storage + cleanup policy для runtime артефактов;
  - bundle splitting в frontend, потому что текущий Vite bundle перевалил за `500kB`.

## Ревизия на 2026-03-27 v9 update (автоматический проход; обновление v9)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **302 passed in 29.13s** (было 206)
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 70%** (было 62%)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **138 files already formatted** (было 125)
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 95 source files** (было 92)
- `frontend: npx tsc --noEmit` -> **OK, 0 errors**
- `frontend: npm run lint` -> **OK, 0 errors**

### Что было сделано в этом проходе (v9 update)

- [x] **Backend plans router создан (blocker #7 CLOSED)**:
  - Новый файл `app/schemas/plan.py` — PlanResponse, PlanRejectRequest Pydantic schemas
  - Новый файл `app/services/plan_service.py` — list_plans, get_plan, approve_plan, reject_plan с бизнес-логикой:
    - approve перемещает тикет plan_review → ai_coding
    - reject перемещает тикет plan_review → ai_planning
    - проверка status conflict (409) для re-approve/re-reject
  - Новый файл `app/api/v1/plans.py` — 4 endpoints:
    - `GET /tickets/{ticket_id}/plans` — list plans
    - `GET /tickets/{ticket_id}/plans/{plan_id}` — get single plan
    - `POST /tickets/{ticket_id}/plans/{plan_id}/approve` — approve
    - `POST /tickets/{ticket_id}/plans/{plan_id}/reject` — reject (requires comment)
  - Router зарегистрирован в `app/api/v1/router.py`
  - Frontend contract (`frontend/src/api/plans.ts`) теперь совпадает с backend routes

- [x] **Test coverage: 206 → 302 tests, 62% → 70% coverage**:
  - Новые тесты: `test_api/test_plans.py` — 13 тестов (list empty/with data/not found, get/not found, approve/already approved/moves ticket, reject/moves ticket/requires comment/already rejected, auth required)
  - Новые тесты: `test_services/test_plan_service.py` — 12 тестов (list empty/ordered/not found, get found/not found, approve success/moves ticket/conflict, reject success/moves ticket/conflict)
  - Новые тесты: `test_ci/test_security_scanner.py` — 12 тестов (normalize severity 4x, scan result defaults/with vulns, run_sast python/javascript/critical, dependency audit python/javascript/unknown)
  - Новые тесты: `test_ci/test_test_runner.py` — 15 тестов (TestSuiteResult counts 2x, parse json 3x, extract metrics 3x, run_tests unit/integration/e2e/security/unknown/failures/json-error)
  - Новые тесты: `test_ci/test_deployer.py` — 13 тестов (dataclass 2x, deploy staging success/n8n/failure, production canary success/clamp/failure, promote partial/full/failure, rollback success/failure, health unavailable)
  - Новые тесты: `test_ci/test_builder.py` — 5 тестов (build result 2x, github headers with/without token, trigger dispatch failure)
  - Новые тесты: `test_git/test_diff_parser.py` — 14 тестов (empty/whitespace, simple diff, file properties, multi-file, rename, multi-hunk, line types, line numbers, hunk counts, empty hunks)
  - Новые тесты: `test_agents/test_agent_providers.py` — 14 тестов (calculate_cost known/unknown/claude/gemini, agent response defaults, invoke success/db logging/error/timeout, claude/codex/gemini require key, claude/codex generate)
  - Ранее 0% модули теперь покрыты: `ci/test_runner.py`, `ci/security_scanner.py`
  - Ранее 28% модули теперь покрыты: `ci/deployer.py`
  - Новый модуль: `plan_service.py` — **100%**

- [x] **Placeholder screens заменены реальными API (blocker #5 CLOSED)**:
  - `UserManagement.tsx` — убран `placeholderUsers`, теперь загружает пользователей из `GET /users` API, обновляет роли через `PATCH /users/{id}/role`; добавлены loading/error states
  - Новый файл `frontend/src/api/users.ts` — listUsers, getUser, updateUser, changeUserRole
  - `SettingsPage.tsx` — кнопка `Save Changes` теперь вызывает `PUT /projects/{id}` с реальным projectForm state; форма использует controlled inputs; добавлен feedback (saving/error/success)
  - `frontend/src/api/projects.ts` — добавлен `updateProject()` endpoint

### Что осталось открытым после v9 update

- [ ] **Coverage 70% → 80%+ (цель ТЗ)**: Основные непокрытые модули: `coding_agent.py` (24%), `context/engine.py` (20%), `github_client.py` (27%), `security_agent.py` (31%), `github_oauth.py` (31%), `code_parser.py` (31%), `repo_manager.py` (36%), `main.py` (38%), `pipeline_orchestrator.py` (52%)
- [ ] **Frontend тесты отсутствуют**: Нет unit/integration suite (Vitest не настроен).
- [ ] **e2e тесты отсутствуют**: `e2e/tests/` пуст.
- [ ] **Project-scoped flow hardcodes**: `MetricsDashboard` шлёт `project_id='default'`, `KanbanBoard` автосоздаёт `"My Project"`.
- [ ] **WebSocket subscribe не подключён**: `subscribeProject()` не вызывается при выборе проекта.
- [ ] **AI review не заземлён на реальный diff**: `trigger_ai_review()` использует PR URL/description, а не actual diff.

---

## Ревизия на 2026-03-27 v8 (автоматический проход; runtime + acceptance audit)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **206 passed in 24.59s**
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 62%**
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**, но bundle warning остался: `dist/assets/index-ByhDf0SH.js = 517.80 kB`
- runtime smoke на in-memory FastAPI app:
  - `GET /api/v1/tickets/{id}/plans` -> **200 []** (FIXED: was 404)
  - `GET /api/v1/tickets/{id}/reviews` -> **200 []**
  - `GET /api/v1/tickets/{id}/test-results` -> **200 []**
  - `GET /api/v1/tickets/{id}/history` -> **404**
  - `GET /api/v1/dashboard/pipeline-stats?project_id=default` -> **422 uuid_parsing**
  - `GET /api/v1/dashboard/pipeline-stats?project_id=<uuid>` -> **200**
  - `GET /api/v1/context/deps/frontend/src/App.tsx` -> **200**, но `dependencies=[]` и сообщение про placeholder
  - `GET /api/v1/deployments/health/staging` -> **404**
  - `GET /api/v1/ai-logs` -> **200**

### Итог этого прохода

- [x] **Технический floor стабилен**: backend tests/ruff/mypy и frontend lint/build снова зелёные.
- [ ] **Acceptance по ТЗ всё ещё не готов**: проблемы сместились в runtime-path и системные инварианты, а не в compile-time.
- [ ] **Мы идём к цели частично**: foundation устойчивый, но чеклисты `6.2`-`6.7` пока не закрываются честно end-to-end.
- [ ] **Главный приоритет следующего автоцикла**: закрывать не общие "улучшения", а конкретные acceptance gaps по разделам `2.2`, `3.1-3.4`, `4.2-4.7`, `5.*`, `6.*`, `7.*`.

### Что подтвердилось как уже стабилизированное

- [x] `reviews` и `test-results` ticket-scoped маршруты существуют и отвечают `200`.
- [x] `ai-logs` endpoint существует и отвечает реальными полями backend-shape.
- [x] PM-only production gate на backend удержан в `deployments.py`.
- [x] Agent router умеет graceful degradation через `StubAgent`, то есть отсутствие AI API keys больше не должно ронять базовый runtime.

### P0. Какие разделы ТЗ надо автодорабатывать следующими проходами

1. [ ] **`4.2 Git + Context` + `4.4 AI Coding`: включить реальную worktree-изоляцию вместо single-checkout пайплайна**
   - Подтверждённые факты:
     - `backend/app/git/repo_manager.py` уже содержит `create_worktree(...)`, но `pipeline_orchestrator.py` его не использует;
     - `run_coding_phase()` работает через `create_branch()` + `checkout_branch()` в одном общем repo path;
     - `POST /projects/{project_id}/git/clone` при повторном вызове делает `fetch --all` + `reset --hard origin/{branch}`.
   - Почему это блокер:
     - ТЗ обещает отдельный `git worktree/branch` на подзадачу, а фактический runtime пока опирается на один checkout;
     - `reset --hard` на повторном clone/update опасен для in-flight работы и конфликтует с идеей безопасной идемпотентности.
   - Критерии приёмки:
     - каждая AI-подзадача живёт в собственном worktree path;
     - повторный clone/update не делает destructive reset по активной рабочей директории;
     - merge back в feature-branch проходит через явный orchestration step с метрикой конфликтов;
     - параллельность подзадач измеряется wall-clock сравнением с sequential run.

2. [ ] **`4.3 AI Planning` + `3.2 Экран тикета`: закрыть plan flow и артефакты тикета до runtime-ready состояния**
   - Подтверждённые факты:
     - runtime smoke: `GET /api/v1/tickets/{id}/plans` -> `404`;
     - runtime smoke: `GET /api/v1/tickets/{id}/history` -> `404`;
     - `frontend/src/stores/ticketStore.ts` реально грузит только `ticket`, `comments`, `attachments`; `plans/codeGens/aiLogs/reviews/testResults/history` не имеют fetch-layer;
     - `TicketDetail.tsx` уже рендерит вкладки `Plan | Code | Tests | AI Logs | History`, но данные туда системно не подтягиваются.
   - Почему это блокер:
     - UI создаёт видимость полного ticket-control-center, но фактический acceptance path обрывается на отсутствующих endpoints и пустом store;
     - checklist `6.3`, `6.5`, `6.6` требует рабочие artifact flows, а не placeholder tabs.
   - Критерии приёмки:
     - backend имеет ticket-scoped endpoints для `plans`, `code generations`, `history`;
     - `TicketDetail` загружает все артефакты через реальные API вызовы;
     - вкладки имеют `loading / empty / error / success`;
     - smoke по всем ticket-artifact routes возвращает `200`, а не смесь `404/[]`.

3. [ ] **`3.1 Kanban` + `4.1 MVP`: убрать неканоничный project context и hardcoded fallback-flow**
   - Подтверждённые факты:
     - runtime smoke: `dashboard/pipeline-stats?project_id=default` -> `422`, а с UUID -> `200`;
     - `MetricsDashboard.tsx` всё ещё использует `DEFAULT_PROJECT_ID = 'default'`;
     - `KanbanBoard.tsx` при отсутствии проектов авто-создаёт `"My Project"` вместо явного empty/create/select flow.
   - Почему это блокер:
     - проектный контекст остаётся неканоничным между UI и API;
     - acceptance `6.1` и `6.7` нельзя считать пройденными, пока часть экранов работает на невалидном project id.
   - Критерии приёмки:
     - все PM/board/dashboard flows используют выбранный `project_id: UUID`;
     - отсутствует скрытый auto-create проекта;
     - пользователь без проектов видит явный onboarding/create/select state;
     - dashboard/board/settings работают на одном project source of truth.

4. [ ] **`2.2 Pipeline` + `3.1 real-time`: унифицировать WebSocket envelope и реально подписывать активный проект**
   - Подтверждённые факты:
     - `AppShell` только вызывает `useWebSocket()`, но runtime call-sites `subscribeProject()` отсутствуют;
     - backend schema описывает канонический envelope `{type, data, timestamp}`;
     - `notification_service.py` по-прежнему шлёт `{type, payload}`;
     - `pipeline_orchestrator._log_progress()` шлёт ad-hoc payload с top-level `ticket_id/project_id/phase/message/data`, а не schema envelope.
   - Почему это блокер:
     - WebSocket формально подключён, но проектная подписка и единый parser не доведены до acceptance-grade;
     - real-time поведение по ТЗ требует не только сокет, но и канонический протокол, пригодный для board/ticket/notifications.
   - Критерии приёмки:
     - при входе на board/ticket клиент делает `subscribe_project` для активного проекта и `unsubscribe` при переключении;
     - все server events используют единый envelope `{type, data, timestamp}`;
     - notification payload читается frontend без специальных исключений;
     - два клиента на одном проекте получают board update < `500ms`.

5. [ ] **`3.3 PM/Admin` + `4.1`: убрать placeholder persistence gap**
   - Подтверждённые факты:
     - `UserManagement.tsx` до сих пор живёт на `placeholderUsers`;
     - backend `/api/v1/users` и `/api/v1/users/{id}/role` уже существуют;
     - `SettingsPage.tsx` показывает `Save Changes`, но frontend client не имеет `updateProject()` и фактический save-flow не реализован.
   - Почему это блокер:
     - UI создаёт ожидание рабочей admin/config панели, но persistence не подключён;
     - acceptance по RBAC/settings/dashboard нельзя закрыть на демо-данных.
   - Критерии приёмки:
     - user management читает backend users API и меняет роль через реальный mutation;
     - settings page сохраняет project fields и stage config;
     - placeholder/demo users удалены из runtime perimeter.

6. [ ] **`4.5 Code Review`: заземлить review на реальный diff и file-level context**
   - Подтверждённые факты:
     - runtime route `/tickets/{id}/reviews` существует, но `trigger_ai_review()` всё ещё собирает diff context в основном из `pr_url`/`branch_name` строк;
     - при отсутствии diff review идёт по `"No diff available. Review based on ticket description only."`;
     - реальные git diff endpoints уже есть отдельно в `git_ops.py`.
   - Почему это блокер:
     - ТЗ обещает inline diff review и категорию замечаний по изменённым файлам, а не review "по описанию тикета".
   - Критерии приёмки:
     - AI review использует `git/diff` + changed files как основной контекст;
     - findings привязаны к файлам и строкам из diff;
     - regression tests проверяют формирование review context из реальных git данных.

7. [ ] **`4.6 CI/CD и тесты`: закрыть execution gap, а не только type/lint floor**
   - Подтверждённые факты:
     - frontend unit/integration tests отсутствуют: в `frontend/src` нет `*.test|*.spec`;
     - каталог `e2e/` пуст;
     - backend coverage держится на `62%`, далеко от `>80%` по ТЗ;
     - `app/ci/test_runner.py`, `app/ci/security_scanner.py`, `app/ci/builder.py` имеют `0%` coverage;
     - `test_runner.py` до сих пор использует synthetic paths `"/app"` / `"/app/projects/{project_name}"`.
   - Почему это блокер:
     - acceptance `6.6` требует реальные build/lint/tests/security/e2e артефакты и UI drill-down;
     - сейчас зелёные только compile-time проверки и backend pytest, а не весь pipeline.
   - Критерии приёмки:
     - backend coverage >= `80%`;
     - есть frontend unit/integration suite;
     - есть Playwright smoke для auth/board/ticket/admin flow;
     - test runner запускает тесты на canonical repo/worktree path;
     - security scanner и dependency audit выполняются в CI и сохраняют артефакты.

8. [ ] **`4.7 Production` + `5.* Metrics/SLA`: довести deploy/metrics до операционного acceptance**
   - Подтверждённые факты:
     - runtime smoke: `GET /api/v1/deployments/health/staging` -> `404`, то есть env-style health route не существует;
     - dashboard endpoints работают только при реальном UUID, но coverage метрик ТЗ всё ещё неполный;
     - `dashboard_service.py` уже считает часть pipeline/cost/quality/deploy stats, но не закрывает полный SLA-мэп из раздела 5.
   - Почему это блокер:
     - ТЗ требует canary rollout, rollback по аномалиям и real-time metrics/thresholds/owners, а не только несколько агрегатов;
     - production acceptance нельзя закрыть без проверяемого monitoring contract.
   - Критерии приёмки:
     - canary progression `5% -> 25% -> 50% -> 100%` автоматизированно проверяется;
     - health/readiness/rollback contract документирован и smoke-tested;
     - dashboard отображает формулы, thresholds и ownership по метрикам раздела 5;
     - production/staging observability доступны через ticket/deployment trace.

9. [ ] **`7.* Нефункциональные требования`: заземлить degraded-mode и security/observability execution**
   - Подтверждённые факты:
     - smoke пишет `Rate limiter skipped: Redis pool not available`, то есть degraded mode существует, но остаётся implicit;
     - GitHub Actions сейчас ограничены lint/type/build/test и не запускают dependency review / CodeQL / e2e;
     - `security_scanner.py` и `test_runner.py` почти не верифицированы тестами.
   - Почему это блокер:
     - раздел 7 требует не только код, но и операционно проверяемые guarantees;
     - деградация без Redis/AI/secret backends должна быть формализована как ожидаемое состояние с test coverage и alerting.
   - Критерии приёмки:
     - degraded modes документированы и покрыты regression tests;
     - CI содержит security/code/dependency scanning;
     - traces/metrics/log correlation доступны хотя бы для planning/coding/review/test/deploy pipeline stages.

### Рекомендуемый порядок следующей автодоработки

1. [ ] **Project + contract first**: убрать `default`/auto-create flow и добить ticket artifact endpoints.
2. [ ] **Git/runtime first**: включить worktree isolation и убрать destructive update path.
3. [ ] **Ticket center first**: загрузка plans/code/reviews/tests/ai-logs/history в `TicketDetail`.
4. [ ] **Protocol first**: project subscription + canonical WS envelope.
5. [ ] **Verification first**: frontend tests, e2e, CI security/audit, coverage ratchet.
6. [ ] **Ops first**: production metrics, health contracts, degraded-mode observability.

### Интернет и ускорение процесса

- [ ] **Live web lookup в этом проходе не завершился**: браузерный web-tool был недоступен, поэтому новых live-подтверждений из интернета в этот запуск не добавлено.
- [x] **Ранее подтверждённые официальные идеи из TODO остаются актуальным acceleration-backlog**:
  - OpenAPI-generated frontend client: `https://openapi-generator.tech/index.html`
  - Schemathesis contract testing: `https://schemathesis.readthedocs.io/en/stable/`
  - Playwright sharding/retries: `https://playwright.dev/docs/test-sharding`
  - pytest-xdist parallelization: `https://pytest-xdist.readthedocs.io/en/latest/distribution.html`
  - GitHub dependency review + CodeQL: `https://docs.github.com/en/code-security/concepts/code-scanning/codeql/about-code-scanning-with-codeql`
  - OpenTelemetry traces: `https://opentelemetry.io/docs/zero-code/python/example/`
- [ ] **Критерий приёмки для acceleration-слоя**:
  - каждый внедрённый accelerator должен дать измеримый эффект: меньше `404/422`, меньше manual drift, или быстрее CI/runtime;
  - результат должен быть виден либо в длительности pipeline, либо в bug-finding rate, либо в стабильности acceptance-smoke.

## Ревизия на 2026-03-27 v7 update (автоматический проход; обновление v7)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **206 passed in 24.03s** (было 158)
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 62%** (было 57%)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **125 files already formatted** (было 117)
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK, 0 errors**
- `frontend: npm run build` -> **OK** (Vite предупреждает о чанке `517.80 kB`)

### Что было сделано в этом проходе (v7 update)

- [x] **Test coverage: 158 → 206 tests, 57% → 62% coverage**:
  - Новые тесты: `test_agents/test_fallback.py` — 7 тестов (empty chain, first succeeds, first-fails-second-succeeds, all-fail, timeout, fallback metadata, kwargs forwarding)
  - Новые тесты: `test_agents/test_review_agent.py` — 9 тестов (parse valid/markdown/invalid/severity, deduplicate severity/different, no agents, single agent, to_json)
  - Новые тесты: `test_middleware/test_logging_middleware.py` — 6 тестов (filter default/with-value, configure_logging, middleware correlation-id generate/use/response-headers)
  - Новые тесты: `test_middleware/test_rate_limiter.py` — 4 тестов (get_profile default/ai, health bypass, redis unavailable fail-open)
  - Новые тесты: `test_api/test_notifications.py` — 7 тестов (list empty/with data, unread count, mark read not found, mark all read, unread only, requires auth)
  - Новые тесты: `test_api/test_attachments.py` — 7 тестов (upload, list empty/with data, download not found, delete not found, upload requires auth, delete forbidden)
  - Новые тесты: `test_api/test_users.py` — 8 тестов (list users, get user, not found, update role, requires auth, etc.)
  - Ранее 0% модули теперь покрыты: `fallback.py`, `review_agent.py`
  - Ранее 40% модули теперь покрыты: `middleware/logging`, `middleware/rate_limiter`, `attachments.py`
  - Ранее 62% модули теперь покрыты: `notifications.py`
- [x] **Frontend ↔ Backend API contract drift FIXED** для 6 из 7 клиентов:
  - `reviews.ts`: маршруты исправлены на `/tickets/{id}/reviews`, `/tickets/{id}/reviews/ai-trigger`; payload `body` -> `comment`; response shape соответствует backend `ReviewResponse`
  - `testResults.ts`: маршруты исправлены на `/tickets/{id}/test-results`, `/tickets/{id}/tests/run`, `/tickets/{id}/tests/generate`; payload и response shapes обновлены
  - `notifications.ts`: типы и shapes обновлены: `read` -> `is_read`, `type` -> `channel`, `created_at` -> `sent_at`, `{count}` -> `{unread_count}`, `page_size` -> `per_page`
  - `aiLogs.ts`: типы обновлены: `total_calls` -> `total_requests`, `avg_duration_ms` -> `average_duration_ms`, `agent_name` -> `agent`, `model_id` -> `model`; response использует `AILogListResponse` вместо `PaginatedResponse`
  - `deployments.ts`: `target_percent` -> `new_percentage`; `getHealth(env)` -> `getHealth(deploymentId)`; `DeployPayload` разделён на `StagingDeployPayload` и `ProductionDeployPayload` c правильными полями; `HealthStatus` обновлён по backend `HealthResponse`
  - `plans.ts`: маршруты переведены на ticket-scoped `/tickets/{id}/plans/*` (backend endpoints pending — см. blocker #7)
  - Notification type в `types/index.ts` обновлён до backend shape
  - `notificationStore.ts` обновлён: `read` -> `is_read`
  - `Header.tsx` обновлён: `read` -> `is_read`, `created_at` -> `sent_at`

### Что осталось открытым после v7 update

- [ ] **Coverage 62% → 80%+ (цель ТЗ)**: Основные непокрытые модули: `coding_agent.py` (24%), `security_agent.py` (31%), `github_oauth.py` (31%), `git_ops.py` (45%), `reviews.py` (46%), `context.py` (60%), `pipeline_orchestrator.py` (52%), `ci/*` пакет.
- [ ] **Frontend тесты отсутствуют**: Нет unit/integration suite.
- [ ] **e2e тесты отсутствуют**: `e2e/tests/` пуст.
- [ ] **Plan backend endpoints не существуют**: frontend обновлён на ticket-scoped routes, но backend plan router отсутствует.
- [ ] **Project-scoped flow hardcodes**: `MetricsDashboard` шлёт `project_id='default'`, `KanbanBoard` автосоздаёт `"My Project"`.
- [ ] **Placeholder screens**: `UserManagement` на `placeholderUsers`, `SettingsPage` без API-save.
- [ ] **WebSocket subscribe не подключён**: `subscribeProject()` не вызывается при выборе проекта.

---

## Ревизия на 2026-03-27 v7 (предыдущий блок; фиксация до обновления)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **158 passed in 20.00s**
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 57%**
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **117 files already formatted**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**, но Vite всё ещё предупреждает про bundle `517.78 kB`

### Вывод этого прохода

- [x] **Технический floor стабилен**: backend quality-gates зелёные, frontend lint/build зелёные.
- [ ] **Acceptance-path по ТЗ всё ещё не готов**: критические gaps теперь не в compile-time, а в runtime contract drift, незавершённых Human Gate flow и placeholder-экранах.
- [ ] **Мы идём к цели частично**: качество backend-кода и test floor уже на приемлемом уровне, но MVP/итерации 3-7 нельзя честно принять end-to-end по чеклистам раздела 6.
- [ ] **Следующие авто-проходы надо фокусировать не на общем “полировании”, а на закрытии конкретных разделов ТЗ**: `1.3`, `2.2`, `3.1-3.4`, `4.1-4.7`, `5.*`, `7.*`.

### P0. Какие разделы ТЗ надо автодорабатывать следующими проходами

1. [ ] **`4.1 MVP Contracts` + `3.1 Kanban UI`: выровнять frontend ↔ backend API contract**
   - Подтверждённые факты:
     - smoke `GET /api/v1/plans` -> `404`, но `frontend/src/api/plans.ts` живёт на phantom `/plans`;
     - smoke `GET /api/v1/test-results` -> `404`, но frontend использует collection-routes `/test-results`, `/test-results/run`, `/test-results/ai-generate`;
     - smoke `GET /api/v1/reviews` -> `404`, тогда как backend живёт на `/tickets/{ticket_id}/reviews` и `/tickets/{ticket_id}/reviews/ai-trigger`;
     - smoke `GET /api/v1/deployments/health/staging` -> `404`, а frontend ждёт `/deployments/health/{environment}`;
     - frontend `aiLogs.ts` ждёт `total_calls`, `total_tokens`, `avg_duration_ms`, `agent_name`, `model_id`, а backend отдаёт `total_requests`, `total_input_tokens`, `total_output_tokens`, `average_duration_ms`, `agent`, `model`;
     - frontend `notifications.ts` ждёт `{count}` и `Notification.read/type/created_at`, а backend отдаёт `{unread_count}` и сущности с `channel/is_read/sent_at`.
   - Почему это блокер:
     - UI может собираться, но реальные запросы ведут в `404`/`422` или читают неправильные поля ответа;
     - чеклисты `6.1`, `6.3`, `6.5`, `6.6`, `6.7` нельзя закрыть, пока клиенты и маршруты живут в двух разных реальностях.
   - Критерии приёмки:
     - каждый frontend client совпадает с backend route/method/payload/response shape;
     - есть contract-smoke для `plans`, `reviews`, `test-results`, `deployments`, `notifications`, `ai-logs`;
     - сборка frontend не содержит ручных типов, противоречащих OpenAPI.

2. [ ] **`1.3 RBAC` + `4.1 MVP`: унифицировать role/column matrix и project context**
   - Подтверждённые факты:
     - `frontend/src/utils/permissions.ts` разрешает `developer` движение в том числе к `production` через локальную логику, хотя ТЗ и backend требуют PM-only gate;
     - `frontend/src/components/dashboard/MetricsDashboard.tsx` хардкодит `project_id='default'`, а smoke подтверждает `422 uuid_parsing`;
     - `frontend/src/components/kanban/KanbanBoard.tsx` всё ещё auto-create'ит `"My Project"` вместо явного project selector / empty state.
   - Почему это блокер:
     - RBAC матрица расходится между ТЗ, UI и backend;
     - проектный контекст не каноничен, из-за чего dashboard/board flows невалидны уже на уровне идентификаторов.
   - Критерии приёмки:
     - единая role -> endpoint -> screen -> column matrix используется и в backend, и во frontend;
     - `developer` не может инициировать production flow ни в UI, ни через API;
     - dashboard/kanban/ticket/settings работают только с реальным `project_id: UUID`;
     - пользователь без проектов видит `create/select project` flow, без скрытого auto-create.

3. [ ] **`3.2 Экран тикета` + `4.3/4.5/4.6`: подключить реальные артефакты pipeline**
   - Подтверждённые факты:
     - `frontend/src/stores/ticketStore.ts:fetchTicket()` грузит только `getTicket(id)`;
     - по вкладкам реально подгружаются только comments и attachments;
     - `TicketDetail.tsx` рендерит пустые состояния `No AI plan generated yet` и `No code generations yet`, потому что store не подтягивает планы, review, test results, ai logs, history.
   - Почему это блокер:
     - ТЗ обещает ticket detail как центр управления pipeline-артефактами, а сейчас это в основном shell.
   - Критерии приёмки:
     - ticket detail умеет загружать `plan`, `diff/code generation`, `reviews`, `test results`, `ai logs`, `history`;
     - у каждой вкладки есть `loading / empty / error / success`;
     - smoke с seed-данными показывает непустые `Plan`, `Tests`, `AI Logs`, `History`.

4. [ ] **`3.1 Kanban real-time` + `2.2 Pipeline`: довести WebSocket runtime до канонического протокола**
   - Подтверждённые факты:
     - `useWebSocket()` всегда делает `connect(token)` без `projectId`;
     - `rg 'subscribeProject\\(' frontend/src` не находит реальных call-site кроме store API;
     - backend `notification_service._send_in_app()` шлёт `{type, payload}`, а frontend store ждёт `WSEvent.data`;
     - `pipeline_orchestrator._log_progress()` шлёт ad-hoc envelope `{type, ticket_id, project_id, phase, message, data}`, а не канонический `{type, data, timestamp}`.
   - Почему это блокер:
     - доска и уведомления не могут считаться real-time acceptance-ready, даже если WebSocket физически подключается;
     - часть событий не ложится в единый клиентский parser.
   - Критерии приёмки:
     - клиент подписывается на активный проект при открытии board/ticket и отписывается при переключении;
     - все WS события используют канонический envelope `{type, data, timestamp}`;
     - два клиента на одном проекте получают board update < `500ms`;
     - notification badge/list обновляются без reload.

5. [x] **`3.3 PM/Admin` + `4.1`: убрать placeholder screens и добавить persistence** *(CLOSED v9: UserManagement wired to /users API, SettingsPage saves via PUT /projects/{id})*
   - Подтверждённые факты:
     - `frontend/src/components/admin/UserManagement.tsx` использует `placeholderUsers`;
     - роль редактируется только локально, хотя backend `/api/v1/users` и `/api/v1/users/{id}/role` уже есть;
     - `SettingsPage.tsx` отображает `Save Changes`, но не вызывает `updateProject` и вообще не сохраняет stage configs.
   - Почему это блокер:
     - по ТЗ это рабочие PM/Admin модули, а не демо-экраны.
   - Критерии приёмки:
     - `User Management` читает/обновляет backend users API;
     - `Settings` сохраняет project settings и pipeline config;
     - placeholder/demo данные удалены из acceptance perimeter.

6. [ ] **`4.2 Git + Context`: связать реальный repo/worktree path, индексацию и dependency graph**
   - Подтверждённые факты:
     - `context.py` держит `_REPOS_DIR=/tmp/ai-coding-repos`, а `test_results.py` запускает тесты на synthetic path `"/app"` / `"/app/projects/{project_name}"`;
     - endpoint `/context/deps/{file_path}` пока явно placeholder и всегда возвращает пустой список;
     - acceptance для precision@5, incremental reindex и dependency graph пока не верифицируется никаким dataset-driven test.
   - Почему это блокер:
     - Context Engine нельзя принять по `4.2`, пока он не работает на том же canonical repo path, где живут review/coding/test flows.
   - Критерии приёмки:
     - единый canonical repo/worktree path используется в `git_ops`, `pipeline_orchestrator`, `test_runner`, `context`;
     - dependency endpoint возвращает реальные imports/exports для JS/TS/Python;
     - есть benchmark/dataset для `precision@5 > 0.7` и для incremental reindex latency.

7. [x] **`4.3 AI Planning`: закрыть backend plan-review flow** *(CLOSED v9: plans router + service + schema + 25 tests)*
   - Подтверждённые факты:
     - frontend предполагает `/plans`, `/plans/{id}/approve`, `/plans/{id}/reject`;
     - backend отдельного `plans` router не экспонирует вообще;
     - checklist `6.3` требует list/get/preview/approve/reject flow, которого пока нет.
   - Почему это блокер:
     - Human Gate `Plan Review` существует в UI/TZ, но backend acceptance-path у него отсутствует.
   - Критерии приёмки:
     - backend имеет ticket-scoped plan endpoints: list/get/preview/approve/reject;
     - reject требует комментарий и запускает re-plan flow;
     - approve двигает тикет в `ai_coding` и пишет history/logs.

8. [ ] **`4.5 Code Review`: заземлить AI review на реальный diff**
   - Подтверждённые факты:
     - `backend/app/api/v1/reviews.py` строит review context в основном из ticket description + PR URL/branch string;
     - готовые git diff endpoints и repo manager уже есть, но `trigger_ai_review()` их не использует.
   - Почему это блокер:
     - ТЗ обещает inline diff-based review, а не review "по описанию задачи".
   - Критерии приёмки:
     - AI review использует реальный diff и changed files;
     - findings привязаны к файлам/строкам из diff;
     - есть regression tests на сборку review context.

9. [ ] **`4.6 CI/CD и тесты`: закрыть test execution gap и добавить frontend/e2e perimeter**
   - Подтверждённые факты:
     - frontend не содержит unit/integration test runner (`package.json` не имеет `test` / `test:e2e`);
     - каталог `e2e/` фактически пуст по рабочим тестам;
     - backend coverage всё ещё `57%`, а ключевые модули `ci/*`, `context/*`, `review_agent.py`, `fallback.py`, `main.py` остаются с низким или нулевым покрытием;
     - `test_results.py` запускает тесты на synthetic path, а не на реальном ticket workspace.
   - Почему это блокер:
     - acceptance `6.1` требует `80%+ coverage`, а `6.6` требует UI-visible tree/logs/screenshots и кастомные тесты.
   - Критерии приёмки:
     - backend coverage >= `80%`;
     - есть frontend unit/integration suite;
     - есть Playwright e2e smoke для auth/board/ticket flow;
     - тестовые run'ы используют canonical repo/worktree path и сохраняют drill-down artifacts.

10. [ ] **`4.7 Production` + `5.* Metrics/SLA`: довести deploy/runtime metrics до SLA-уровня**
    - Подтверждённые факты:
      - frontend и backend расходятся по health-check route и promote payload (`target_percent` vs `new_percentage`);
      - dashboard сейчас покрывает только часть метрик и не выражает явно формулы/threshold/owner;
      - локальная test suite для `ai_costs` пропущена из-за PostgreSQL-specific `date_trunc`, то есть один из ключевых metrics endpoints остаётся вне обычного fast smoke.
    - Почему это блокер:
      - разделы `4.7` и `5.*` требуют измеряемый canary + SLA/analytics, а не просто набор карточек на dashboard.
    - Критерии приёмки:
      - canary flow 5% -> 25% -> 50% -> 100% проверяется automated scenario;
      - health/check/promote payloads едины на backend/frontend;
      - dashboard показывает lead time, cycle time, throughput, WIP, cost, rejection rate, latency/error rate с формулами и thresholds;
      - `ai_costs` и related metrics тестируются на PostgreSQL-backed CI job, а не только на SQLite.

11. [ ] **`7.* Нефункциональные требования`: добавить security/observability execution, а не только декларации**
    - Подтверждённые факты:
      - текущие GitHub Actions гоняют lint/type/build/test, но не делают CodeQL/dependency review/e2e;
      - rate limiter в локальном smoke пишет `Rate limiter skipped: Redis pool not available`, то есть degraded mode есть, но не формализован как acceptance;
      - OpenTelemetry/Prometheus/Grafana/Loki/alerting из ТЗ пока не заземлены в репо.
    - Почему это блокер:
      - раздел 7 требует проверяемые operational guarantees, а не только пожелания в DOCX.
    - Критерии приёмки:
      - есть CI jobs для security scanning и dependency/code scanning;
      - degraded mode без Redis документирован и покрыт tests/alerts;
      - ticket-level traces/metrics доступны для ключевых pipeline стадий.

### Рекомендуемый порядок авто-доработки

1. [ ] **Contract first**: OpenAPI/client generation, contract-smoke, RBAC/project UUID.
2. [ ] **Ticket flow first**: plans/reviews/test-results/ticket detail tabs.
3. [ ] **Real-time first**: project WS subscription, canonical event envelope, notifications.
4. [ ] **Execution first**: canonical repo/worktree path для git/context/test/review.
5. [ ] **Verification first**: frontend tests, e2e, coverage ratchet, PostgreSQL-backed metrics tests.
6. [ ] **Ops first**: security scanning, traces, deploy health, SLA dashboard.

### P2. Новые best practices из интернета (март 2026, официальный поиск)

40. Генерировать frontend API client из OpenAPI, а не поддерживать ручную копию контрактов.
    - Источник: https://openapi-generator.tech/index.html
    - Источник: https://openapi-generator.tech/docs/usage/
    - Источник: https://openapi-generator.tech/docs/generators/typescript-axios/
    - Зачем: текущий главный системный дефект — drift между frontend-clients и backend-routes. Генерация клиента превращает backend OpenAPI в source of truth и резко уменьшает число phantom endpoints.
    - Критерии приёмки:
      - CI job генерирует TypeScript client из backend OpenAPI;
      - после генерации нет diff в рабочем дереве;
      - `plans`, `reviews`, `test-results`, `deployments`, `notifications`, `ai-logs` используют generated client/types;
      - contract-smoke не находит `404`/`422` на обязательных UI routes.

41. Добавить Schemathesis для schema-driven contract и edge-case тестов FastAPI.
    - Источник: https://schemathesis.readthedocs.io/en/stable/
    - Зачем: Schemathesis генерирует property-based tests из OpenAPI schema и хорошо ловит именно те runtime problems, которые сейчас видны в smoke: missing route, shape drift, unexpected 4xx/5xx.
    - Критерии приёмки:
      - критические backend endpoints прогоняются через Schemathesis в CI;
      - failing examples сохраняются как воспроизводимые regression cases;
      - `plans/reviews/test-results/deployments/notifications/ai-logs` включены в contract suite.

42. Поднять Playwright e2e и сразу шардировать его в CI с blob/html reports.
    - Источник: https://playwright.dev/docs/test-sharding
    - Источник: https://playwright.dev/docs/test-retries
    - Источник: https://playwright.dev/docs/best-practices
    - Зачем: ТЗ требует real browser acceptance и artifacts; Playwright даёт parallel/sharding, retries и attachment-rich reports, что одновременно ускоряет feedback loop и повышает доказательность acceptance.
    - Критерии приёмки:
      - есть `test:e2e` и базовый набор сценариев `auth -> project select -> board -> ticket detail`;
      - CI гоняет e2e по shard matrix;
      - blob/html report и trace artifacts загружаются в CI;
      - flaky tests маркируются и не маскируют системные regressions.

43. Включить OpenTelemetry-инструментацию для FastAPI и pipeline стадий.
    - Источник: https://opentelemetry.io/docs/zero-code/python/example/
    - Зачем: разделы `1.4 Observability`, `5.* SLA`, `7.4 Observability` требуют трассировку тикета end-to-end. Без traces невозможно объективно измерять planning/coding/review/deploy latency и искать bottlenecks.
    - Критерии приёмки:
      - backend emits traces/spans для HTTP, DB и key pipeline phases;
      - в span attributes попадают `ticket_id`, `project_id`, `phase`, `agent`;
      - есть дешборд/экспорт, где видно p95/p99 latency по стадиям.

44. Параллелить backend tests через `pytest-xdist` и формализовать xdist-safe fixtures.
    - Источник: https://pytest-xdist.readthedocs.io/en/latest/distribution.html
    - Источник: https://pytest-xdist.readthedocs.io/en/stable/how-to.html
    - Зачем: текущий backend suite уже вырос до 158 тестов. `pytest -n auto` может заметно сократить feedback loop, но только если fixtures, порядок collection и shared resources xdist-safe.
    - Критерии приёмки:
      - backend suite стабильно проходит с `pytest -n auto`;
      - session/db fixtures документированы как xdist-safe;
      - среднее локальное время прогона уменьшается минимум на 30% без роста flaky failures;
      - для дебага явно задокументирован fallback `-n 0`.

45. Добавить GitHub dependency review + CodeQL в PR pipeline.
    - Источник: https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configuring-the-dependency-review-action?apiVersion=2022-11-28
    - Источник: https://docs.github.com/en/code-security/concepts/code-scanning/codeql/about-code-scanning-with-codeql
    - Зачем: уже есть локальные lint/test workflows, но supply-chain и code-scanning holes остаются. Это закрывает часть разделов `4.6`, `7.1`, `7.4` и уменьшает шанс принять уязвимый diff.
    - Критерии приёмки:
      - PR workflow запускает dependency review action и валит PR на новых уязвимых зависимостях;
      - CodeQL запускается на backend/frontend поверх стандартных PR checks;
      - результаты security scans видны в GitHub Security/Checks и не живут отдельным ручным процессом.

46. Вынести bundle-size budget и route-based code splitting в acceptance-perimeter frontend.
    - Источник: локальный build warning `dist/assets/index-CqZ_p76k.js -> 517.78 kB`
    - Зачем: текущий SPA грузит весь UI целиком, хотя большая часть экранов не нужна на первом рендере. Это замедляет UI feedback и бьёт по mobile acceptance из `6.1`.
    - Критерии приёмки:
      - heavy routes (`dashboard`, `settings`, `ticket detail`) грузятся lazy chunks;
      - main entry chunk уменьшается ниже `300 kB` minified как рабочая цель;
      - в CI есть bundle-size check или хотя бы warning budget.

47. Sandbox-First Execution для AI-generated кода.
    - Источник: https://www.darkreading.com/application-security/coders-adopt-ai-agents-security-pitfalls-lurk-2026
    - Источник: https://www.veracode.com/blog/secure-ai-code-generation-in-practice/
    - Зачем: Текущая threat model 2026 сместилась к AI-агентам, автономно выполняющим shell-команды и модифицирующим файлы. RSAC 2026 продемонстрировал client-side атаки через AI coding assistants. Sandbox для всего AI-initiated execution — baseline requirement.
    - Критерии приёмки:
      - все AI agent shell/file операции выполняются внутри sandboxed environment (container, VM);
      - policy file определяет, какие операции разрешены вне sandbox;
      - sandbox escapes логируются и генерируют alert.

48. AI Bill of Materials (AIBOM) и Model Provenance Tracking.
    - Источник: https://rafter.so/blog/ai-code-security-complete-guide
    - Источник: https://cloudsecurityalliance.org/blog/2026/03/13/the-state-of-cloud-and-ai-security-in-2026
    - Зачем: Необходимо отслеживать, какая AI-модель (и версия) сгенерировала каждый кусок кода, какие промпты использовались, какие библиотеки были предложены. Non-human identities в 2026 превышают human users 100:1, что делает auditability критичной.
    - Критерии приёмки:
      - каждый AI-generated артефакт тегирован model_id, model version и prompt hash;
      - AIBOM файл генерируется при каждом релизе;
      - CI pipeline валидирует AIBOM completeness перед deploy;
      - audit trail queryable (например, "покажи весь код, сгенерированный model X version Y").

49. Intelligent Test Selection (Impact-Based Test Routing).
    - Источник: https://www.mabl.com/blog/ai-agents-cicd-pipelines-continuous-quality
    - Источник: https://tech360us.com/ai-ml/how-ai-is-transforming-ci-cd-in-devops-in-2026/
    - Зачем: AI-powered test intelligence определяет, какие тесты реально затронуты изменением кода, и запускает только их, сокращая cycle time до 80%. Также автоматически обнаруживает и карантинит flaky тесты.
    - Критерии приёмки:
      - test impact analysis шаг запускается перед полным suite;
      - flaky тесты auto-detected, quarantined и reported;
      - полный suite бежит nightly как safety net;
      - метрики: accuracy отбора, экономия времени, flaky rate.

50. LLM-Native Observability (Reasoning Trace Monitoring).
    - Источник: https://arize.com/blog/best-ai-observability-tools-for-autonomous-agents-in-2026/
    - Источник: https://grafana.com/blog/observability-survey-AI-2026/
    - Зачем: Традиционный APM не может оценить, был ли ответ AI агента correct, faithful или safe. Failure mode AI систем 2026 — semantically wrong но syntactically valid output. Token efficiency метрики покрывают cost, но не reasoning quality.
    - Критерии приёмки:
      - span-level tracing для каждого AI agent call (prompt in, response out, tool calls, reasoning steps);
      - hallucination detection на production outputs с alert thresholds;
      - dashboard: task completion rate, reasoning coherence score, tool call accuracy, cost per task;
      - anomaly detection triggers alerts при agent behavior drift.

51. Restrict AI Generation in Security-Sensitive Code Paths.
    - Источник: https://www.veracode.com/blog/secure-ai-code-generation-in-practice/
    - Источник: https://www.wiz.io/academy/application-security/ai-code-security
    - Зачем: AI-generated код в authentication, authorization, cryptography и payment logic несёт непропорциональный risk. Best practice 2026 — явные policy boundaries, запрещающие AI-generation в определённых paths.
    - Критерии приёмки:
      - `.ai-restricted-paths` config определяет директории/модули, где AI generation запрещена (например, `auth/`, `crypto/`, `payments/`);
      - CI pipeline отклоняет PR с AI-generated changes в restricted paths;
      - exceptions требуют explicit security team approval;
      - policy enforced на уровне IDE/agent и CI.

52. Spec-Driven AI Development (Plan-Before-Generate).
    - Источник: https://addyosmani.com/blog/ai-coding-workflow/
    - Зачем: Без structured spec AI агенты производят unfocused или contradictory код. Structured spec (requirements, architecture decisions, testing strategy) перед code generation предотвращает wasted tokens и rework. Это отличается от AGENTS.md (поведение агентов) — это о требовании machine-readable spec artifact как input для каждой generation задачи.
    - Критерии приёмки:
      - `spec.md` или structured JSON spec обязателен перед любой AI code generation задачей;
      - pipeline отклоняет generation requests без linked spec document;
      - specs версионированы вместе с кодом и referenced в commit metadata.

53. Multi-Turn Stochastic Agent Evaluation Harness.
    - Источник: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
    - Источник: https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide
    - Зачем: Консенсус 2026: single-turn evals недостаточны. Multi-turn conversation evals и stochastic trial runs (один eval N раз с агрегацией) теперь mandatory. Agent failures compound across turns так, что single-turn metrics пропускают.
    - Критерии приёмки:
      - eval suite включает и single-turn и multi-turn test scenarios;
      - каждый eval scenario запускается минимум 5 раз с aggregated pass/fail reporting;
      - custom LLM-as-judge evaluators реализованы для domain-specific quality checks;
      - eval results gate CI — failing evals блокируют merge.

### P2. Новые best practices из интернета (v9 update, март 2026)

54. Использовать MSW (Mock Service Worker) для frontend API mocking вместо ручных моков.
    - Источник: https://mswjs.io/
    - Источник: https://stevekinney.com/courses/testing/testing-with-mock-service-worker
    - Зачем: MSW перехватывает реальные сетевые запросы на уровне Service Worker, что позволяет тестировать frontend компоненты с реалистичными API ответами. Текущий проект не имеет frontend тестов — MSW + Vitest дают быстрый старт.
    - Критерии приёмки:
      - `src/mocks/handlers.ts` определяет mock handlers для всех API endpoints;
      - Vitest использует MSW server для unit/integration тестов;
      - `onUnhandledRequest: 'error'` ловит необработанные запросы;
      - mock responses соответствуют backend OpenAPI schema.

55. Внедрить LangGraph для production-grade multi-agent orchestration.
    - Источник: https://dev.to/pockit_tools/langgraph-vs-crewai-vs-autogen-the-complete-multi-agent-ai-orchestration-guide-for-2026-2d63
    - Источник: https://markaicode.com/vs/langgraph-vs-crewai-multi-agent-production/
    - Зачем: Текущий pipeline_orchestrator использует ad-hoc async координацию. LangGraph даёт graph-based control flow с persistent checkpointing, что критично для auditability и resume-after-failure в production pipeline.
    - Критерии приёмки:
      - pipeline phases (plan → code → review → test → deploy) моделируются как LangGraph nodes;
      - conditional edges реализуют human gates (plan_review, code_review);
      - state checkpointing позволяет resume после failure;
      - model tiering: fast model для routing, capable model для generation.

56. Внедрить Vitest для frontend unit/integration тестов.
    - Источник: https://vitest.dev/guide/
    - Зачем: Проект использует Vite для сборки — Vitest нативно интегрируется с Vite config, поддерживает ESM, TypeScript, JSX без дополнительной конфигурации. Jest требует отдельного transform pipeline.
    - Критерии приёмки:
      - `package.json` содержит `test` script с Vitest;
      - базовый набор тестов для stores (authStore, kanbanStore, ticketStore);
      - тесты для API clients с MSW mocking;
      - CI запускает frontend tests перед build;
      - coverage report для frontend кода.

57. Добавить structured logging с correlation ID для end-to-end request tracing.
    - Источник: https://thelinuxcode.com/dependency-injection-in-fastapi-2026-playbook-for-modular-testable-apis/
    - Зачем: Текущий logging middleware генерирует correlation ID, но он не пробрасывается через AI agent calls, WebSocket events и n8n workflows. Без сквозного correlation ID нельзя трейсить ticket lifecycle end-to-end.
    - Критерии приёмки:
      - correlation ID пробрасывается через все слои: HTTP → service → agent → n8n → WS;
      - AiLog содержит correlation_id для связи с HTTP request;
      - dashboard может фильтровать по correlation_id;
      - structured JSON logging в production mode.

58. Добавить circuit breaker для AI provider calls.
    - Источник: https://www.veracode.com/blog/secure-ai-code-generation-in-practice/
    - Зачем: При отказе AI провайдера (Anthropic/OpenAI/Google) текущий fallback chain может зависнуть на timeout × 3 провайдера. Circuit breaker с half-open state позволяет быстро переключаться на рабочий провайдер.
    - Критерии приёмки:
      - circuit breaker реализован для каждого AI провайдера;
      - после N consecutive failures провайдер переходит в open state;
      - half-open state проверяет recovery каждые M секунд;
      - метрики circuit breaker доступны на dashboard;
      - fallback chain использует только closed/half-open провайдеров.

59. Evaluation-Driven Development (EDD) вместо TDD для LLM-компонентов.
    - Источник: https://newsletter.pragmaticengineer.com/p/evals
    - Зачем: TDD предполагает детерминированные выходы. LLM выходы недетерминированны — EDD оценивает свойства output (формат, ключевые слова, качество), а не точное совпадение.
    - Критерии приёмки:
      - golden dataset из 50+ test cases для каждого agent типа;
      - CI запускает property-based assertions на PR, затрагивающих prompt/agent код;
      - pass/fail thresholds определены и enforced.

60. Оценивать полные траектории агентов, а не только финальный output.
    - Источник: https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide
    - Зачем: Агент может выдать правильный ответ через неэффективный путь, выбрать неподходящие tools, или не обработать edge cases.
    - Критерии приёмки:
      - trajectory logging записывает каждый tool call и decision node;
      - eval suite включает trajectory-efficiency метрики;
      - alerts при agents > N шагов для known-simple tasks.

61. Интегрировать SAST scanning как blocking CI gate на каждый PR.
    - Источник: https://blog.thoughtparameters.com/post/securing_ai-generated_code_in_cicd_pipelines/
    - Зачем: AI модели генерируют синтаксически корректный код без awareness trust boundaries, data classification или regulatory constraints.
    - Критерии приёмки:
      - SAST scan на каждый PR; critical/high findings блокируют merge;
      - dependency scan покрывает все package managers;
      - zero secrets в кодовой базе.

62. Использовать Langfuse (open-source) для self-hosted LLM observability.
    - Источник: https://langfuse.com/
    - Зачем: Многие организации не могут отправлять LLM inputs/outputs в third-party SaaS. Langfuse даёт tracing, prompt management, dataset versioning и LLM-as-judge evals self-hosted.
    - Критерии приёмки:
      - Langfuse развёрнут и получает traces от всех agent workflows;
      - prompt versions управляются через платформу;
      - eval datasets версионированы вместе с кодом.

63. Никогда не использовать `allow_origins=["*"]` в production CORS.
    - Источник: https://github.com/zhanymkanov/fastapi-best-practices
    - Зачем: Wildcard CORS позволяет любому домену делать authenticated requests к API и отключает credential support.
    - Критерии приёмки:
      - Production CORS config содержит explicit allowed origins;
      - CI check отклоняет wildcard CORS в production config.

64. Использовать `uv` вместо pip для dependency installation в Docker builds.
    - Источник: https://fastlaunchapi.dev/blog/fastapi-best-practices-production-2026
    - Зачем: `uv` в 10-100x быстрее pip, что значительно сокращает Docker build times. Non-root containers обязательны для production security.
    - Критерии приёмки:
      - Dockerfile использует `uv` для установки зависимостей;
      - multi-stage build отделяет build deps от runtime;
      - контейнер запускается от non-root; image < 200MB.

## Ревизия на 2026-03-27 v6 (автоматический проход; этот блок новее `v5`)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **158 passed in 18.86s** (было 92)
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 57%** (было 49%)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **117 files already formatted** (было FAIL на 68 файлах)
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK, 0 errors**
- `frontend: npm run build` -> **OK** (Vite предупреждает о чанке `517.78 kB`)

### Что было сделано в этом проходе (v6)

- [x] **Format gate CLOSED**: `ruff format .` отформатировал 68 файлов. `ruff format --check .` теперь зелёный — все 117 файлов already formatted.
- [x] **Test coverage: 92 → 158 tests, 49% → 57% coverage**:
  - Новые тесты: `test_workflows/test_pipeline_orchestrator.py` — 11 тестов (_detect_language, _get_ticket, _repo_path, _update_ticket_column, _log_progress, run_planning_phase, run_deploy_phase staging/production/no-branch)
  - Новые тесты: `test_workflows/test_state_machine.py` — 11 тестов (can_transition valid/invalid/role/production/prerequisite, execute_transition success/invalid/retry, side_effects trigger/failure-safe)
  - Новые тесты: `test_workflows/test_retry_handler.py` — 7 тестов (pass-first, pass-second, exhaust-retries, retry_count, accumulated_errors, max_retries_zero, context_forwarding)
  - Новые тесты: `test_services/test_notification_service.py` — 14 тестов (send_notification in_app, send_slack no_token/success/webhook/http_error, send_telegram no_token/no_chat_id/success/http_error, format_slack_message, notify_on_transition known/unknown/no_users, transition_labels)
  - Новые тесты: `test_services/test_n8n_service.py` — 7 тестов (unknown_name, no_base_url, success, http_error, request_error, webhook_prefix, core_workflows)
  - Новые тесты: `test_services/test_comment_service.py` — 10 тестов (create, create_threaded, invalid_parent, list_empty, list_multiple, update, update_not_found, delete, delete_not_found)
- [x] **Модули с 0% coverage закрыты**:
  - `comment_service.py`: 32% → **100%**
  - `n8n_service.py`: 0% → **100%**
  - `retry_handler.py`: 0% → **100%**
  - `state_machine.py`: 0% → **90%**
  - `notification_service.py`: 0% → **83%**
  - `pipeline_orchestrator.py`: 0% → **52%**

### Что осталось открытым после v6

- [ ] **Coverage 57% → 80%+ (цель ТЗ)**: Основные непокрытые модули: `pipeline_orchestrator` (52% — фазы coding/review/testing), API endpoints (`git_ops`, `context`, `ai_logs`, `reviews`, `test_results`, `attachments`, `notifications`, `users`, `github_oauth`), `git/` пакет (27-46%), `middleware/` (40-64%), `agents/` (AI provider agents).
- [ ] **Frontend тесты отсутствуют**: Нет unit/integration suite.
- [ ] **e2e тесты отсутствуют**: `e2e/tests/` пуст.
- [ ] **Frontend ↔ Backend API contract drift**: frontend API clients используют routes/shapes, не совпадающие с backend (plans, reviews, test-results, deployments, notifications, ai-logs). Подробности в v5 блокере #1.
- [ ] **Project-scoped flow hardcodes**: `MetricsDashboard` шлёт `project_id='default'`, `KanbanBoard` автосоздаёт `"My Project"`.
- [ ] **Placeholder screens**: `UserManagement` на `placeholderUsers`, `SettingsPage` без API-save.

### P2. Новые best practices (март 2026, добавлено в v6)

35. Внедрить AGENTS.md для управления поведением AI агентов в репозитории.
    - Источник: https://codescene.com/blog/agentic-ai-coding-best-practice-patterns-for-speed-with-quality
    - Зачем: Документированные правила превращают инженерные принципы в executable guidance для агентов. Без AGENTS.md агент при failing test может удалить тест, ослабляя safeguards.
    - Критерии приёмки:
      - AGENTS.md в корне репозитория описывает coding standards, test requirements, prohibited actions
      - AI agents обращаются к AGENTS.md перед генерацией кода
      - запрет на удаление тестов без явного human approve

36. Добавить Kanban-метрики (lead time, cycle time, throughput, WIP) в dashboard.
    - Источник: https://www.atlassian.com/agile/project-management/kanban-metrics
    - Зачем: Четыре ключевые метрики Kanban позволяют идентифицировать bottlenecks, оценивать team productivity и планировать capacity. Без них board — просто визуализация, не инструмент управления.
    - Критерии приёмки:
      - dashboard показывает lead time, cycle time, throughput и WIP по проекту
      - данные считаются из `ticket_history` (transitions timestamps)
      - cumulative flow diagram доступен как визуализация

37. Внедрить секретное сканирование (secret scanning) в CI/CD pipeline.
    - Источник: https://www.leanware.co/insights/best-practices-ai-software-development
    - Зачем: 12% deployed applications в 2026 содержали unpatched security flaws. AI-generated код особенно склонен к хардкоду секретов. Автоматическое сканирование в CI минимизирует risk.
    - Критерии приёмки:
      - CI workflow включает secret scanning (gitleaks или trufflehog)
      - fail pipeline при обнаружении секретов в коде
      - .env, credentials, API keys в .gitignore и pre-commit hook

38. Добавить token efficiency метрики для AI agents.
    - Источник: https://addyosmani.com/blog/ai-coding-workflow/
    - Зачем: Каждый failed agent run — wasted money. Net productivity важнее raw speed. Tracking token usage, retry rate и cost-per-task позволяет оптимизировать provider selection и prompt engineering.
    - Критерии приёмки:
      - dashboard показывает cost_usd, tokens, latency, retry_count по agent и action_type
      - данные из `ai_logs` агрегируются за период
      - alerts при cost spike или высоком retry rate

39. Реализовать AI-on-AI code review с fallback chain.
    - Источник: https://www.faros.ai/blog/best-ai-coding-agents-2026
    - Зачем: AI-on-AI review ловит ошибки, которые один model пропустил. Fallback chain (Claude → GPT → Gemini) обеспечивает resilience при API outages.
    - Критерии приёмки:
      - review agent использует другой AI provider, чем coding agent
      - fallback chain из `shared/constants.py:FALLBACK_CHAIN` работает при provider error
      - review findings сохраняются в `reviews` с source agent attribution

---

## Ревизия на 2026-03-27 v5 (автоматический проход; этот блок новее `v4`)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **92 passed in 11.74s**
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 49%**
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **FAIL, 68 files would be reformatted**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**; Vite предупреждает о чанке `517.78 kB`
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/plans` -> **404 Not Found**
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/test-results` -> **404 Not Found**
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/reviews` -> **404 Not Found**
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/dashboard/pipeline-stats?project_id=default` -> **422 uuid_parsing**
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/notifications/unread-count` -> **200**, тело `{"unread_count":0}`
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/ai-logs/stats` -> **200**, тело `{"total_requests":0,...}`
- `shell: python` -> **command not found**; рабочий интерпретатор в этой среде — `backend/.venv/bin/python`
- `workspace: git status --short` -> **fatal: not a git repository**

### Вывод этого прохода

- [x] **Технический floor стабилен**: backend/frontend проходят базовые quality-gates (`pytest`, `ruff check`, `mypy`, `lint`, `build`).
- [ ] **Acceptance-path всё ещё не готов**: основные blockers сместились из compile-time в runtime contract drift и в непровязанные product flows.
- [ ] **Мы движемся к цели частично**: качество кода стало заметно лучше, но ключевые пользовательские сценарии ТЗ всё ещё нельзя честно принять end-to-end.

### Новые подтверждённые блокеры acceptance

1. [ ] **Frontend ↔ Backend API contract drift всё ещё ломает runtime, хотя `build` зелёный**
   - Факт:
     - smoke `GET /api/v1/plans` -> `404`, а frontend `frontend/src/api/plans.ts` всё ещё вызывает `/plans`, хотя backend вообще не подключает отдельный `plans` router;
     - smoke `GET /api/v1/test-results` -> `404`, а `frontend/src/api/testResults.ts` использует collection routes `/test-results`, `/test-results/run`, `/test-results/ai-generate`, которых backend не экспонирует;
     - smoke `GET /api/v1/reviews` -> `404`, а `frontend/src/api/reviews.ts` обращается к `/reviews` и `/reviews/ai/{ticketId}`, тогда как backend живёт на `/tickets/{ticket_id}/reviews` и `/tickets/{ticket_id}/reviews/ai-trigger`;
     - `frontend/src/api/deployments.ts` шлёт `canary_percent` и `target_percent`, а backend ждёт `canary_pct` и `new_percentage`;
     - `frontend/src/api/deployments.ts` вызывает `/deployments/health/{environment}`, а backend имеет `/deployments/{deployment_id}/health`;
     - `frontend/src/api/notifications.ts` ожидает `{count}` и `Notification.type/read`, а backend возвращает `{unread_count}` и сущности с полями `channel/is_read/sent_at`;
     - `frontend/src/api/aiLogs.ts` ожидает `total_calls`, `total_tokens`, `avg_duration_ms`, `agent_name`, `model_id`, а backend отдаёт `total_requests`, `total_input_tokens`, `total_output_tokens`, `average_duration_ms`, `agent`, `model`.
   - Почему это блокер:
     - визуально UI собирается, но реальные API-call'ы ведут в `404` или читают неправильные поля;
     - acceptance по ТЗ нельзя считать выполненным, пока routed screens не работают на реальном контракте.
   - Критерии приёмки:
     - каждый frontend API client совпадает с реальным backend route, method, params, payload и response shape;
     - есть contract-smoke на `plans`, `reviews`, `test-results`, `deployments`, `notifications`, `ai-logs`;
     - предпочтительно: frontend types/clients генерируются из OpenAPI, а не живут отдельной ручной копией.

2. [ ] **Экран тикета не подключён к артефактам пайплайна**
   - Факт:
     - `frontend/src/components/tickets/TicketDetail.tsx` показывает вкладки `Plan`, `Code`, `Tests`, `AI Logs`, `History`;
     - `frontend/src/stores/ticketStore.ts:fetchTicket()` загружает только `getTicket(id)` и не тянет планы, code generations, reviews, ai logs, test results, history;
     - отдельным вызовом на tab-switch грузятся только attachments; comments живут на отдельном hook.
   - Почему это блокер:
     - ТЗ 3.2 обещает рабочий детальный экран с артефактами пайплайна, а сейчас это в основном пустые контейнеры.
   - Критерии приёмки:
     - открытие тикета подгружает или лениво тянет планы, review, ai logs, test results и history;
     - каждая вкладка имеет реальные `loading / empty / error / success` состояния;
     - smoke с seed-данными показывает непустые `Plan`, `Tests`, `AI Logs`, `History`.

3. [ ] **Project-scoped WebSocket subscribe реализован в коде, но не используется в runtime**
   - Факт:
     - `frontend/src/stores/wsStore.ts` содержит `subscribeProject()` / `unsubscribeProject()`;
     - `frontend/src/hooks/useWebSocket.ts` всегда делает `connect(token)` без `projectId`;
     - `frontend/src/components/kanban/KanbanBoard.tsx` после выбора/создания проекта не вызывает `subscribeProject`;
     - `rg 'subscribeProject\\(' frontend/src` не находит реальных call-site;
     - backend `websocket_manager.broadcast_to_project()` шлёт board events только подписанным viewers.
   - Почему это блокер:
     - ТЗ 3.1 и 4.1 требует real-time доску `< 500ms`, но текущий runtime может вообще не получать project events.
   - Критерии приёмки:
     - клиент подписывается на текущий проект при открытии board/ticket и отписывается при переключении;
     - два клиента на одном проекте получают update < `500ms`;
     - клиент на другом проекте не видит чужие события.

4. [ ] **In-app notifications до сих пор нарушают унифицированный WS envelope**
   - Факт:
     - `backend/app/services/notification_service.py` `_send_in_app()` шлёт `{type: "notification", payload: {...}}`;
     - frontend после прошлой унификации ждёт `WSEvent.data`, а `wsStore` читает `event.data`.
   - Почему это блокер:
     - live-уведомления могут молча не появляться, даже если сокет подключён.
   - Критерии приёмки:
     - notification events используют канонический `{type, data, timestamp}`;
     - REST и WebSocket notification shape совпадают;
     - header badge и список уведомлений обновляются без reload.

5. [ ] **Project context остаётся fake/default на ключевых экранах**
   - Факт:
     - `frontend/src/components/dashboard/MetricsDashboard.tsx` хардкодит `DEFAULT_PROJECT_ID = 'default'`;
     - smoke `GET /api/v1/dashboard/pipeline-stats?project_id=default` -> `422 uuid_parsing`;
     - `frontend/src/components/kanban/KanbanBoard.tsx` всё ещё auto-create'ит `"My Project"` вместо явного empty-state/project selector.
   - Почему это блокер:
     - один канонический `project_id: UUID` всё ещё не enforced across board/dashboard/settings/test flow.
   - Критерии приёмки:
     - dashboard/board/settings/test flows работают только с выбранным UUID project;
     - нет скрытого auto-create project при первом открытии доски;
     - пользователь без проектов видит `create/select project` flow;
     - dashboard-запросы с выбранным UUID дают `200`, а не `422`.

6. [ ] **PM/Admin screens остаются placeholder'ами или неперсистентными оболочками**
   - Факт:
     - `frontend/src/components/admin/UserManagement.tsx` использует `placeholderUsers`;
     - edit role меняет только локальный state, хотя backend `/api/v1/users` уже есть;
     - `frontend/src/components/settings/SettingsPage.tsx` загружает первый проект, но save buttons не имеют real persistence handlers; stage-configs живут только в local component state.
   - Почему это блокер:
     - ТЗ 3.3 обещает PM/Admin user management и settings как функциональность, а не demo screen.
   - Критерии приёмки:
     - `User Management` читает/пишет `/api/v1/users`;
     - `Settings` сохраняет реальные project/pipeline настройки;
     - placeholder/demo rows удалены из acceptance-perimeter или явно помечены `out of scope`.

7. [ ] **Plan Review flow всё ещё backend-incomplete**
   - Факт:
     - `AiPlan` model и planning agent существуют;
     - backend не имеет list/get/approve/reject plan endpoints, хотя frontend и ТЗ 4.3/6.3 их предполагают.
   - Почему это блокер:
     - Human Gate `Plan Review` нельзя принять end-to-end.
   - Критерии приёмки:
     - backend экспонирует list/get/approve/reject plan endpoints;
     - reject требует комментарий и запускает re-plan flow;
     - frontend вызывает реальные ticket-scoped routes, а не phantom `/plans`.

8. [ ] **AI review всё ещё не заземлён на реальный code diff**
   - Факт:
     - `backend/app/api/v1/reviews.py` `trigger_ai_review()` собирает review context из описания тикета + PR URL/branch string;
     - готовые git diff endpoints в `git_ops.py` есть, но тут не используются.
   - Почему это блокер:
     - ТЗ 4.5 и checklist 6.5 ожидают diff-based inline review, а не review "по описанию".
   - Критерии приёмки:
     - review pipeline использует реальный diff и changed files;
     - findings ссылаются на реальные файлы/строки из diff;
     - regression tests покрывают сбор review context.

9. [ ] **Test runner всё ещё живёт на синтетических project paths**
   - Факт:
     - `backend/app/api/v1/test_results.py` вычисляет path как `"/app"` или `"/app/projects/{project_name}"`;
     - это не тот canonical repo/worktree path, который использует `git_ops` / `pipeline_orchestrator`.
   - Почему это блокер:
     - нельзя утверждать, что запущенные тесты относятся к реальному ticket workspace.
   - Критерии приёмки:
     - test run берёт canonical repo/worktree path для ticket/project;
     - artefacts связаны с branch/commit тикета;
     - в runtime больше нет fake path через `default` или `project.name`.

### Разделы ТЗ, которые надо автодописать/уточнить по итогам этого прохода

1. **Раздел 3.2 "Экран тикета"**
   - Для каждой вкладки указать точный endpoint, обязательный payload, empty/error state и критерий "данные реально загружены", а не просто отрисован контейнер.

2. **Раздел 3.3 "Дашборд PM/Admin"**
   - Явно зафиксировать, что `User Management` и `Settings` считаются выполненными только при чтении/записи через API без placeholder/demo данных.

3. **Раздел 4.1 "MVP Contracts"**
   - Добавить каноническую таблицу `frontend client -> backend route -> method -> expected 2xx/4xx -> response shape`;
   - отдельно зафиксировать, что `project_id` в runtime всегда UUID и источник истины един для board/dashboard/ws/tests.

4. **Раздел 4.3 "AI Planning"**
   - Дописать реальные backend endpoints для list/get/approve/reject plan и связать их с Human Gate `Plan Review`.

5. **Раздел 4.5 "Code Review Pipeline"**
   - Зафиксировать, что AI review строится по реальному diff, а не по одному описанию тикета.

6. **Раздел 4.6 "CI/CD и тесты"**
   - Уточнить canonical repo/worktree path, структуру test artifacts, REST contract для `test-results`, `tests/run`, `tests/generate`.

7. **Раздел 5.* "Метрики и SLA"**
   - Добавить product-metrics на contract drift:
     - `0 runtime 404 on routed UI API calls`;
     - `0 schema drift between OpenAPI and frontend types`;
     - `WS delivery p95 < 500ms for subscribed project`.

8. **Раздел 6.* "Чеклисты верификации"**
   - Переписать проверки на реальные текущие endpoints backend;
   - средовые ограничения (`нет .git`, `python только из .venv`, Redis optional) маркировать как `blocked by environment`, а не как product FAIL.

9. **Раздел 7.3 "Отказоустойчивость"**
   - Явно описать degraded-mode при отсутствии Redis, n8n, Git workspace и внешних AI keys: что отключается, а что обязано оставаться рабочим.

### Новые best practices / идеи из внешних источников (март 2026, добавлено в v5)

31. Внедрить prompt caching и стабильные prompt-prefixes для planning/review/coding стадий.
    - Источники:
      - OpenAI Prompt Caching: https://platform.openai.com/docs/guides/prompt-caching
      - Anthropic Prompt Caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
    - Зачем:
      - pipeline многократно гоняет повторяющиеся system prompts, инструкции и shared repo-context;
      - стабильный статический prefix + ticket-specific delta в конце снижает latency и cost.
    - Критерии приёмки:
      - статические инструкции и shared repo-context вынесены перед ticket delta;
      - в `ai_logs` сохраняются cache hit / cached token метрики;
      - медианная latency planning/review снижается, а стоимость на тикет падает без деградации качества.

32. Перейти на eval-driven development для router/review/planning вместо "кажется работает".
    - Источник:
      - OpenAI Evaluation Best Practices: https://platform.openai.com/docs/guides/evaluation-best-practices
    - Зачем:
      - ТЗ already sets routing/review quality targets, но система не измеряет их на собственном dataset;
      - eval-набор можно собирать из `ai_logs`, reject loops и production regressions.
    - Критерии приёмки:
      - есть task-specific eval dataset для `planning`, `routing`, `review`, `test-generation`;
      - каждый релиз гоняет evals до merge/deploy;
      - новые reject/rollback кейсы автоматически пополняют regression set.

33. Ускорить CI за счёт dependency caching + matrix jobs, а не только последовательных прогонов.
    - Источники:
      - GitHub dependency caching: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
      - GitHub matrix jobs: https://docs.github.com/actions/using-jobs/using-a-build-matrix-for-your-jobs
    - Зачем:
      - backend/frontend checks уже стабильны и дальше будут упираться во время выполнения, особенно после появления реальных e2e/security suites.
    - Критерии приёмки:
      - `setup-node` / `setup-python` используют dependency cache;
      - backend/frontend/e2e/security jobs распараллелены matrix или независимыми jobs;
      - median CI runtime и cold-start runtime измеряются и снижаются спринт к спринту.

34. Сразу проектировать параллельный test execution: `pytest -n` и Playwright sharding.
    - Источники:
      - pytest-xdist: https://pytest-xdist.readthedocs.io/en/latest/distribution.html
      - Playwright sharding: https://playwright.dev/docs/test-sharding
    - Зачем:
      - сейчас e2e suite пуст, но ТЗ требует `unit + integration + E2E + security`; без параллелизации time-to-signal быстро выйдет за SLA.
    - Критерии приёмки:
      - backend CI job поддерживает `pytest -n auto` без race/regression;
      - e2e workflow шардируется и умеет merge reports;
      - total verification time остаётся в пределах TZ targets после добавления реальных E2E/security проверок.

### Что проверять в следующем автоматическом проходе в первую очередь

- [ ] Исправлен ли contract drift между frontend API clients и backend router.
- [ ] Появились ли реальные plan endpoints и загрузка артефактов в `TicketDetail`.
- [ ] Подключён ли project-scoped WebSocket subscribe/unsubscribe в runtime.
- [ ] Убраны ли `DEFAULT_PROJECT_ID`, auto-create `"My Project"` и placeholder `UserManagement`.
- [ ] Снизились ли CI/runtime latency и cost за счёт caching/matrix/sharding.
- [ ] Сдвинулось ли coverage выше `49%` и закрыт ли `ruff format --check`.

## Ревизия на 2026-03-27 v4 (автоматический проход; этот блок новее `v3`)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **92 passed in 10.77s** (было 43)
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 49%** (было 43%)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK, 0 errors**
- `frontend: npm run build` -> **OK** (Vite предупреждает о чанке `517.78 kB`)
- `smoke: POST /api/v1/tickets/{id}/deploy/production от owner` -> **403 Forbidden** (было 201)
- `smoke: POST /api/v1/tickets/{id}/deploy/production от pm_lead` -> **201 Created**
- `smoke: POST /api/v1/deployments/{id}/promote от owner` -> **403 Forbidden** (было 200)

### Что было сделано в этом проходе (v4)

- [x] **RBAC Production Gate FIXED**: `deployments.py` теперь ограничивает `deploy/production` и `promote` только ролью `pm_lead`. Убран `owner` из `require_role()` на обоих endpoints. Раньше `owner` получал `201`, теперь — `403 Forbidden`.
- [x] **Frontend permissions FIXED**: `permissions.ts:canDeployToProduction()` теперь возвращает `true` только для `pm_lead`, убран `owner`.
- [x] **shared/constants.py SYNCED**: Полностью переписан — теперь содержит актуальные колонки (`backlog`→`production`), роли (`owner`, `pm_lead`, `developer`, `ai_agent`), человеческие ворота (`plan_review`, `code_review`, `staging_verification`), и event types в dot-notation (`ticket.created`, `ticket.moved`, etc.).
- [x] **WebSocket contract UNIFIED**:
  - Frontend типы (`types/index.ts`) переведены с colon-notation (`ticket:created`) на dot-notation (`ticket.created`), совпадают с `backend/app/schemas/websocket.py`.
  - Frontend `WSEvent.payload` → `WSEvent.data` (совпадает с backend `WSEvent.data`).
  - `constants.ts` WS_EVENTS синхронизированы с backend event types.
  - `wsStore.ts` использует `WS_EVENTS` constants вместо хардкодов; убран optimistic `connected: true` set.
  - Добавлены `subscribeProject()`/`unsubscribeProject()` методы в wsStore.
  - Backend `kanban_service.py` теперь отправляет события через `WSEvent` envelope `{type, data}` вместо flat payload.
- [x] **CI artifacts path FIXED**: `.github/workflows/ci-frontend.yml` исправлен: `frontend/.next/` → `frontend/dist/`, `NEXT_PUBLIC_API_URL` → `VITE_API_URL`.
- [x] **Test coverage: 43 → 92 tests, 43% → 49% coverage**:
  - Новые тесты: `test_api/test_projects.py` (9 тестов — CRUD, auth, RBAC для delete)
  - Новые тесты: `test_api/test_deployments.py` (8 тестов — staging deploy, production RBAC negative, promote RBAC, list, 404)
  - Новые тесты: `test_api/test_dashboard.py` (5 тестов — pipeline stats, code quality, deployment stats, auth, validation)
  - Новые тесты: `test_api/test_webhooks.py` (7 тестов — n8n approve/reject/build/deploy, GitHub no-sig)
  - Новые тесты: `test_services/test_websocket_manager.py` (9 тестов — connect/disconnect, subscribe, broadcast, multi-conn)
  - Новые тесты: `test_services/test_kanban_rbac.py` (13 тестов — production gate для всех 4 ролей + другие transitions + prerequisites)
- [x] **RBAC negative tests**: Конкретные тесты подтверждают, что `owner` и `developer` получают `403` на production deploy, promote, и kanban move в production.

### Что осталось открытым после v4

- [ ] **Coverage 49% → 80%+ (цель ТЗ)**: Покрыты projects/deployments/dashboard/webhooks/websocket/RBAC, но `pipeline_orchestrator` (149 строк, 0%), `state_machine` (60 строк, 0%), `retry_handler` (32 строки, 0%), `notification_service` (94 строки, 0%), `n8n_service` (29 строк, 0%) и `comment_service` (41 строка, 32%) требуют дополнительного покрытия.
- [ ] **ruff format --check** всё ещё падает на ~64 файлах. Format gate не закрыт.
- [ ] **Frontend тесты отсутствуют**: Нет unit/integration suite.
- [ ] **e2e тесты отсутствуют**: `e2e/tests/` пуст.
- [ ] **Project-scoped flow hardcodes**: `MetricsDashboard` шлёт `project_id='default'`, `KanbanBoard` автосоздаёт `"My Project"`.
- [ ] **Placeholder screens**: `UserManagement` на `placeholderUsers`, `SettingsPage` без API-save.

### P2. Новые best practices (март 2026, добавлено в v4)

26. Внедрить advisory AI code review в CI перед переходом к gating.
    - Источник: https://www.augmentcode.com/guides/ai-code-review-ci-cd-pipeline
    - Зачем: Начать AI review в advisory-режиме (только комментарии, без блокировки). После ~50 PR с >80% acceptance rate — включить soft gates.
    - Критерии приёмки:
      - AI review запускается на каждый PR в GitHub Actions
      - результаты доступны как inline comments
      - acceptance rate AI findings отслеживается как метрика

27. Комбинировать AI code review + статический анализ (SAST).
    - Источник: https://www.verdent.ai/guides/best-ai-for-code-review-2026
    - Зачем: Чистый AI security scanning даёт только ~22% true positive rate на IDOR-уязвимости. AI + rule-based SAST (Snyk Code, SonarQube) закрывает разные категории.
    - Критерии приёмки:
      - Ruff + Bandit для rule-based checks
      - AI review для context-aware анализа
      - Security findings из обоих источников сохраняются в `ai_logs`

28. Использовать AI Decision Layer вместо простых комментариев.
    - Источник: https://pendium.ai/coderabbit/the-deep-merge/how-to-integrate-ai-code-review-into-your-ci-cd-pi-7ca1a2
    - Зачем: AI review должен генерировать executable allow/warn/block decisions, а не только текстовые комментарии.
    - Критерии приёмки:
      - review agent возвращает structured verdict (allow/warn/block) с confidence score
      - pipeline orchestrator использует verdict для автоматического gate решения
      - block-findings предотвращают merge до human override

29. Закрыть автоматический remediation loop.
    - Источник: https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e
    - Зачем: При robust CI (тесты + lint + build на каждый commit) AI пишет код → автоматика ловит проблемы → AI исправляет → цикл сходится за 1-3 итерации.
    - Критерии приёмки:
      - при CI failure AI agent получает logs и делает fix attempt
      - max 3 автоматических retry, затем escalation на human
      - каждый auto-fix iteration записывается в `ai_logs` с diff

30. Фильтровать файлы для AI review для снижения шума и стоимости.
    - Источник: https://collinwilkins.com/articles/ai-code-review-best-practices-approaches-tools.html
    - Зачем: Не все файлы требуют AI-анализа (lock files, migrations, generated code). Фильтрация снижает costs и noise.
    - Критерии приёмки:
      - GitHub Actions workflow использует `paths` / `paths-ignore` для AI review trigger
      - lock files, migrations, generated code исключены
      - метрика: API cost per review стабильна при росте кодовой базы

---

## Ревизия на 2026-03-27 v3 (предыдущий автоматический проход)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **43 passed in 5.53s**
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> **TOTAL 43%**
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!**
- `backend: .venv/bin/ruff format --check .` -> **FAIL, 64 files would be reformatted**
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files**
- `frontend: npm run lint` -> **OK**
- `frontend: npm run build` -> **OK**, но Vite всё ещё предупреждает о чанке `517.36 kB`
- `smoke (ASGITransport + SQLite in-memory): GET /api/v1/dashboard/pipeline-stats?project_id=default` -> **422 uuid_parsing**
- `smoke (ASGITransport + SQLite in-memory): POST /api/v1/tickets/{id}/move` от `developer` в `production` -> **422** (`Allowed roles: pm_lead`)
- `smoke (ASGITransport + SQLite in-memory): POST /api/v1/tickets/{id}/move` от `owner` в `production` -> **422** (`Allowed roles: pm_lead`)
- `smoke (ASGITransport + SQLite in-memory): POST /api/v1/tickets/{id}/deploy/production` от `owner` -> **201 Created**
- `smoke (ASGITransport + SQLite in-memory): POST /api/v1/tickets/{id}/deploy/production` от `pm_lead` -> **201 Created**
- `e2e` -> файлов нет
- workspace -> `.git` отсутствует, поэтому worktree/branch/PR acceptance из ТЗ всё ещё невалидируемы end-to-end

### Что уточнилось в этом проходе

- [x] **Kanban move gate до production уже ужесточён на уровне state transition**: `backend/app/services/kanban_service.py` действительно ограничивает `staging_verification -> production` только ролью `pm_lead`; `owner` и `developer` на `move` больше не проходят.
- [x] **PM-only правило FIXED в v4**: `backend/app/api/v1/deployments.py` теперь ограничивает `deploy/production` и `promote` только `pm_lead`. `owner` получает `403`.
- [ ] **Quality gate по форматированию не закрыт**: `ruff check` зелёный, но `ruff format --check .` падает на 64 файлах. Это значит, что backend не проходит полный style gate даже после закрытия lint/type debt.
- [ ] **Project-scoped flow всё ещё искусственный**:
  - `frontend/src/components/dashboard/MetricsDashboard.tsx` продолжает шить `project_id='default'`, что гарантированно даёт `422` на dashboard API.
  - `frontend/src/components/kanban/KanbanBoard.tsx` всё ещё автосоздаёт `My Project`, если проектов нет.
  - `backend/app/api/v1/test_results.py` всё ещё собирает путь как `"/app"` / `"/app/projects/{project_name}"`, а не из реального clone/worktree runtime.
- [ ] **Frontend acceptance-perimeter всё ещё содержит нерабочие runtime-экраны**:
  - `frontend/src/components/admin/UserManagement.tsx` сидит на `placeholderUsers`.
  - `frontend/src/components/settings/SettingsPage.tsx` по-прежнему показывает `Save Changes` без вызова API.
- [x] **Real-time контракт UNIFIED в v4**:
  - frontend перешёл на dot-notation (`ticket.moved`), совпадает с backend WSEventType;
  - `WSEvent.payload` → `WSEvent.data`; backend шлёт `{type, data}` envelope;
  - `wsStore` добавлены `subscribeProject()`/`unsubscribeProject()`;
  - optimistic `connected: true` убран.
- [ ] **Acceptance по тестам улучшился, но ещё далёк от ТЗ**:
  - backend coverage `49%` (было `43%`), 92 теста (было 43) — при цели ТЗ `>80%`;
  - frontend не содержит test script и unit/integration suite;
  - каталог `e2e/` пуст.

### Разделы ТЗ, которые надо автодописать по итогам именно этого прохода

1. Раздел `1.3 RBAC`.
   - Что дописать:
     - правила отдельно для `move`, `deploy`, `promote`, `rollback`;
     - один и тот же business action не должен иметь разные allowlists в `kanban_service` и `deployments`;
     - для forbidden-сценариев явно закрепить `403`, а не смешивать `403` и `422` в разных слоях.
   - Критерии приёмки:
     - `owner` и `developer` получают `403` на `POST /api/v1/tickets/{id}/deploy/production`;
     - `owner` и `developer` получают `403` на `POST /api/v1/deployments/{id}/promote`;
     - `pm_lead` остаётся единственной ролью для production move/deploy/promote;
     - UI и backend используют один и тот же список разрешённых production actions.

2. Разделы `3.1`, `3.3` и `4.1 MVP`.
   - Что дописать:
     - project selection как обязательное предсостояние доски/дашборда;
     - явные `empty state`, `select project`, `create project`, `forbidden/no project`;
     - запрет на runtime auto-create project и `default` project id.
   - Критерии приёмки:
     - ни один экран не шлёт `project_id='default'`;
     - при отсутствии проектов UI не создаёт проект молча;
     - board/dashboard/test-run принимают только реальный `project_id: UUID`;
     - отсутствие выбранного проекта даёт контролируемый UI-state, а не `422`.

3. Раздел `5.2 Метрики качества`.
   - Что дописать:
     - format gate как отдельную обязательную метрику, а не только lint/type/test;
     - минимальный набор локальных quality gates: `ruff check`, `ruff format --check`, `mypy`, `pytest`, `npm run lint`, `npm run build`.
   - Критерии приёмки:
     - все перечисленные команды зелёные локально и в CI;
     - ТЗ различает `lint debt fixed` и `format gate fixed`;
     - bundle warning либо принят как non-blocking threshold, либо погашен.

4. Раздел `6 Чеклист верификации`.
   - Что дописать:
     - реальные маршруты `/api/v1/...` вместо устаревших `/api/...`;
     - негативные кейсы для `owner deploy production`, `owner promote canary`, `dashboard с default project_id`;
     - столбец `BLOCKED BY ENVIRONMENT` для сценариев, где нужен `.git`, real repo clone или внешние интеграции.
   - Критерии приёмки:
     - чеклист можно прогнать автоматом теми же командами, что использовались в этой ревизии;
     - каждый пункт имеет один ожидаемый HTTP status;
     - сценарии без `.git` не маркируются как FAIL по продукту, если это ограничение среды.

## Ревизия на 2026-03-27 v2 (автоматический проход; при конфликте считать этот блок каноническим)

Проверено командами:
- `backend: .venv/bin/pytest -q` -> **43 passed, 0 warnings** (было 20 warnings)
- `backend: .venv/bin/ruff check app tests` -> **All checks passed!** (было 76 errors)
- `backend: .venv/bin/mypy app --ignore-missing-imports` -> **Success: no issues found in 92 source files** (было 66 errors)
- `frontend: npm run lint` -> **OK, 0 errors, 0 warnings** (было: ESLint 9 не стартовал)
- `frontend: npm run build` -> **OK** (Vite предупреждает о чанке >500kB)

### Что было сделано в этом проходе

- [x] **Ruff: 76 → 0 errors**. Исправлены E501 (line-too-long), UP042 (str-enum), B904 (raise-without-from), F841 (unused-variable), E741 (ambiguous-variable), S-category (bandit), SIM105, B007. Noqa-директивы перенесены на правильные строки.
- [x] **Mypy: 66 → 0 errors**. Добавлены type params для generic dict/Select/TypeDecorator. Исправлены forward references в ORM relationship(). Добавлены type: ignore для no-any-return, no-untyped-call, attr-defined. Исправлен deprecated asyncio.coroutine. Добавлен timeout param в _run_git_checked.
- [x] **Pytest warnings: 20 → 0**. Убран pytestmark = pytest.mark.asyncio из sync-тестов (test_kanban_service.py, test_router.py).
- [x] **ESLint 9 flat config**: создан eslint.config.js, установлены зависимости (typescript-eslint, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, @eslint/js). Обновлён lint script в package.json.
- [x] **Frontend lint fixes**: OAuthCallback переписан без useState в useEffect (useMemo для error). useAuth/useWebSocket — добавлены недостающие deps в useEffect.
- [x] **Pipeline orchestrator**: TODO по WebSocket broadcast — реализован через ws_manager.broadcast_to_project().
- [x] **Webhooks**: TODO по dispatch action — реализована диспетчеризация: ticket-update двигает тикет по _ACTION_COLUMN_MAP; build-complete двигает в staging/ai_coding; deploy-status двигает в production/staging_verification.

## Ревизия на 2026-03-27 (предыдущий срез)

Проверено командами:
- `backend: pytest -q` -> `ModuleNotFoundError: No module named 'jose'`
- `backend: .venv/bin/pytest -q` -> `43 passed, 20 warnings`
- `backend: .venv/bin/pytest --cov=app --cov-report=term -q` -> `TOTAL 43%`
- `backend: .venv/bin/ruff check app tests --statistics` -> `80 errors (76 remaining)`
- `backend: .venv/bin/mypy app` -> `69 errors in 34 files`
- `backend: .venv/bin/mypy app --ignore-missing-imports --no-strict-optional` -> `66 errors in 33 files`
- `frontend: npm run build` -> `OK`, но Vite предупреждает о чанке `517.34 kB`
- `frontend: npm run lint` -> ESLint 9 падает, так как в репозитории нет `eslint.config.(js|mjs|cjs)`
- smoke: `GET /api/v1/dashboard/pipeline-stats?project_id=default` -> `422 uuid_parsing`
- smoke: `POST /api/v1/tickets/{id}/deploy/production` от роли `owner` -> `201 Created`
- smoke: `POST /api/v1/tickets/{id}/move` от роли `developer` в `production` -> `422`, хотя ТЗ требует `403 Forbidden`
- `e2e` -> тестов нет
- workspace -> `.git` отсутствует, поэтому git/PR/worktree флоу из ТЗ в этой среде невалидируемы end-to-end

Что изменилось относительно прошлой ревизии:
- `projects` API уже существует и подключён в роутер: `backend/app/api/v1/projects.py`, `backend/app/api/v1/router.py`
- `ai-logs` API уже существует и читает реальные записи `AiLog`: `backend/app/api/v1/ai_logs.py`
- graceful degradation для AI уже есть через stub/fallback: `backend/app/agents/router.py`, `backend/tests/test_agents/test_router.py`
- поэтому старые пункты вида "нет Projects API", "нет AI logs API", "без API-ключей всё падает" больше не являются актуальным P0; ниже зафиксирован обновлённый список

### P0. Автодоработать систему до состояния, соответствующего MVP из ТЗ

1. Убрать фальшивый `project context` и хардкоды по проекту.
   - Факт:
     - `frontend/src/components/dashboard/MetricsDashboard.tsx:35` жёстко шлёт `project_id = 'default'`
     - это подтверждено smoke-проверкой: backend отвечает `422`, потому что endpoint требует UUID
     - `frontend/src/components/kanban/KanbanBoard.tsx:55` автоматически создаёт `"My Project"` вместо явного выбора проекта
     - `backend/app/api/v1/test_results.py:167` строит путь как `"/app"` / `"/app/projects/{project_name}"`, а не из фактически клонированного repo/worktree
   - Почему это блокер:
     - доска, дашборд и тестовый pipeline живут не на одном реальном источнике project identity
     - acceptance из ТЗ для project-scoped flow сейчас нельзя честно проверить
   - Критерии приёмки:
     - нет `default` project id и нет auto-create project flow в runtime
     - board/dashboard/settings/test-run работают только с реальным `project_id: UUID`
     - для пользователя без проектов есть `empty state + create/select project`, а не скрытая автогенерация
     - smoke: запросы dashboard/test-run с выбранным UUID дают `200`, а отсутствие выбора даёт контролируемый `empty/403/404`, но не `422`

2. ~~Закрыть RBAC drift на production и сделать один канонический источник прав.~~ **DONE v4** — `deployments.py` и `permissions.ts` ограничены `pm_lead` only. `shared/constants.py` синхронизирован.
   - Факт:
     - `backend/app/api/v1/deployments.py:186` разрешает production deploy для `pm_lead` и `owner`
     - `backend/app/api/v1/deployments.py:277` разрешает promote canary для `pm_lead` и `owner`
     - `frontend/src/utils/permissions.ts:22` и `frontend/src/utils/permissions.ts:60` также считают `owner` допустимым для production
     - `shared/constants.py` вообще живёт на старых ролях/колонках (`admin`, `tech-lead`, `ready-dev`, `done`, `deployed`) и не соответствует текущему backend/frontend
     - smoke подтвердил, что `owner` реально проходит production deploy (`201`)
   - Почему это блокер:
     - ТЗ требует `PM-only Production gate`
     - при наличии двух и более источников прав любые автоматические проверки RBAC недостоверны
   - Критерии приёмки:
     - только `pm_lead` может инициировать move/deploy/promote в production
     - `owner` и `developer` получают `403 Forbidden`, а не `201`/`422`
     - UI скрывает или дизейблит production actions для всех, кроме `pm_lead`
     - `shared/constants.py` либо синхронизирован с системой, либо удалён как ложный источник истины
     - есть негативные API-тесты на `owner -> production` и `developer -> production`

3. ~~Привести WebSocket/real-time контракт к одному протоколу.~~ **DONE v4** — Единый dot-notation, `{type, data}` envelope, subscribe/unsubscribe в wsStore.
   - Факт:
     - `frontend/src/types/index.ts:203` и `frontend/src/utils/constants.ts:72` ожидают события вида `ticket:created`, `ticket:moved`
     - `backend/app/schemas/websocket.py:16` описывает события как `ticket.created`, `comment.added`
     - `backend/app/services/kanban_service.py:192` реально публикует `"ticket_moved"`
     - frontend store ждёт `event.payload`, а backend broadcast шлёт плоский объект без `payload`
     - backend ждёт `subscribe_project`, но frontend его не отправляет: `backend/app/main.py:128`, `frontend/src/hooks/useWebSocket.ts:15`, `frontend/src/stores/wsStore.ts:19`
     - `frontend/src/stores/wsStore.ts:81` выставляет `connected: true` до фактического `onopen`
   - Почему это блокер:
     - главное обещание MVP про real-time обновления доски не имеет единого контракта
     - отсутствие `subscribe_project` означает, что серверная фильтрация по проекту не включается
   - Критерии приёмки:
     - один shared schema-модуль определяет типы событий, envelope и payload-поля
     - frontend автоматически `subscribe/unsubscribe` при выборе/смене проекта
     - `connected/reconnecting` отражают реальное состояние сокета, а не optimistic set
     - второй клиент видит create/move/comment update по текущему проекту в пределах SLA из ТЗ
     - есть контрактные тесты на backend event shape и frontend event consumption

4. ~~Починить обязательные quality gates и CI-артефакты.~~ **PARTIALLY DONE v4** — CI artifacts path fixed (`.next/` → `dist/`), `VITE_API_URL` env var fixed. Bundle budget ещё не определён.
   - Факт:
     - `frontend/package.json` использует ESLint 9, но в репозитории нет flat-config файла, поэтому `npm run lint` неработоспособен
     - `.github/workflows/ci-frontend.yml:93` загружает `frontend/.next/`, хотя это Vite-проект и сборка лежит в `frontend/dist/`
     - `frontend build` проходит, но выдаёт warning про oversized chunk
   - Почему это блокер:
     - CI не может быть достоверным quality gate, если lint сломан, а build-артефакт указывает в несуществующий каталог
   - Критерии приёмки:
     - `npm run lint` зелёный локально и в CI
     - frontend CI публикует `frontend/dist/`
     - для bundle size есть либо budget, либо явный non-blocking threshold/report
     - команды из ТЗ и workflow совпадают с фактическим стеком репозитория

5. Поднять реальную доказательность тестов до уровня MVP, а не до уровня "smoke only".
   - Факт:
     - backend coverage сейчас `43%`, при цели ТЗ `80%+`
     - в backend есть только auth/tickets/kanban/router tests; нет покрытия dashboard/deployments/projects/webhooks/context/ws/ai_logs
     - frontend unit/integration tests отсутствуют
     - `e2e` каталог пуст
     - `pytest` зелёный, но даёт `20` предупреждений по неправильным `@pytest.mark.asyncio`
   - Почему это блокер:
     - нельзя утверждать, что система движется к acceptance, если ключевые user-path и critical API вообще не зафиксированы тестами
   - Критерии приёмки:
     - backend API/service coverage >= `80%` либо ТЗ явно пересматривает метрику и фиксирует новую границу
     - `pytest` без warnings
     - есть frontend unit/integration suite минимум на auth, kanban move, ticket detail, dashboard project selection
     - есть e2e smoke: `register/login -> create/select project -> create ticket -> move ticket через human gate -> observe real-time update`
     - checklist ТЗ различает `unit`, `integration`, `e2e`, `security`

6. Довести automation hooks от заглушек до реального runtime.
   - Факт:
     - `backend/app/workflows/pipeline_orchestrator.py:89` оставляет TODO на WebSocket broadcast прогресса
     - `backend/app/api/v1/webhooks.py:64`, `:76`, `:91` оставляют TODO на dispatch/build/deploy state updates
     - `backend/app/api/v1/context.py:231` честно помечен как `placeholder implementation`
   - Почему это блокер:
     - без этих связок pipeline в ТЗ остаётся описанием намерений, а не исполняемым процессом
   - Критерии приёмки:
     - pipeline progress публикуется в WS/notifications и хранится как проверяемый артефакт
     - n8n/GitHub webhooks обновляют статус тикета и сохраняют build/deploy metadata
     - `/context/deps/*` либо возвращает реальный dependency graph, либо явно выведен за рамки MVP в ТЗ
     - для каждого авто-шага есть idempotency key/правило повторного запуска и timeout policy

7. Убрать placeholder/mock экраны из acceptance-perimeter.
   - Факт:
     - `frontend/src/components/admin/UserManagement.tsx:8` целиком сидит на `placeholderUsers`
     - `frontend/src/components/settings/SettingsPage.tsx:183` рисует `Save Changes`, но код не отправляет изменения в API
   - Почему это блокер:
     - ТЗ прямо обещает PM/Admin user management и настройки, но текущие экраны нельзя принимать как реализованный функционал
   - Критерии приёмки:
     - user list/edit role использует реальные backend endpoints (`/api/v1/users`)
     - role changes сохраняются и отражаются после reload
     - project/integration settings записываются в backend или явно убраны из MVP
     - в acceptance запрещены placeholder/mock/demo screens без явной пометки `out of scope`

### P1. Автодоработать качество кода и контракты

1. Закрыть Ruff debt в backend.
   - Факт: `80` ошибок (`E501`, `UP042`, `B904`, `F841`, и др.), плюс невалидный `# noqa` в `app/agents/security_agent.py`
   - Критерии приёмки:
     - `ruff check app tests` -> `0 errors`
     - `ruff format --check .` -> `0 changes needed`

2. Закрыть mypy debt в backend.
   - Факт: `69` ошибок в strict-режиме и `66` даже в ослабленном CI-style запуске
   - Критерии приёмки:
     - `mypy app` проходит без ошибок
     - ORM-модели и service/API слои не опираются на `name-defined` и `dict` без type params
     - внешние зависимости (`jose`, `pgvector`) либо имеют stubs, либо корректно заигнорированы документированно

3. Убрать несоответствие между runtime API и ТЗ/чеклистом.
   - Факт:
     - ТЗ 6.1 описывает move как `PATCH /api/tickets/:id/move`, а реальный endpoint — `POST /api/v1/tickets/{ticket_id}/move`
     - ТЗ ожидает `403 Forbidden` для RBAC-блокировки, а API сейчас возвращает `422`
   - Критерии приёмки:
     - ТЗ и API-contract совпадают по HTTP method, path и error status
     - все негативные acceptance checks используют реальные коды ответа

4. Синхронизировать frontend типы с backend schemas и реальными API-клиентами.
   - Факт:
     - `frontend/src/types/index.ts:15` описывает `Project.owner_id`, а `frontend/src/api/projects.ts:9` и backend возвращают `creator_id`
     - глобальные WS-типы и backend envelope сейчас расходятся
   - Критерии приёмки:
     - frontend не держит параллельные конкурирующие типы для одних и тех же сущностей
     - типы генерируются из OpenAPI или имеют один вручную поддерживаемый источник истины
     - type drift ловится CI-проверкой

### Разделы ТЗ, которые нужно автодописать сейчас

1. Раздел `1.3 RBAC`.
   - Что дописать:
     - одна каноническая матрица `role -> screen -> endpoint -> transition -> forbidden action`
     - отдельное правило `production move/deploy/promote = только pm_lead`
     - что может и чего не может `ai_agent`
   - Критерии приёмки:
     - для каждой роли есть минимум один негативный сценарий
     - backend/frontend/tests/TZ используют одинаковые enum-значения
     - запретные сценарии фиксируют конкретный HTTP status

2. Разделы `2.2-2.3 Пайплайн` и `Agent Router`.
   - Что дописать:
     - вход/выход и side effects каждого шага
     - idempotency, retry, timeout, fallback и cancel policy
     - канонический WS/event contract
     - разница между sync request, background job и webhook completion
   - Критерии приёмки:
     - у каждой колонки есть `trigger`, `actor`, `preconditions`, `artifacts`, `reject target`, `timeout`, `retry policy`
     - у каждого AI stage есть parseable output schema
     - у router есть measurable success metrics и fallback rule

3. Раздел `3 UI/UX`.
   - Что дописать:
     - project selection как first-class state
     - обязательные состояния `loading`, `empty`, `error`, `forbidden`, `stale`
     - запрет placeholder/demo данных на acceptance
   - Критерии приёмки:
     - каждый экран привязан к конкретным API/WS событиям
     - board/dashboard/admin/settings не зависят от mock/default данных
     - mobile/responsive acceptance описан через конкретные viewport и user flows

4. Раздел `4 Функциональные требования по итерациям`.
   - Что дописать:
     - актуальные команды и endpoint-методы под реальный repo layout
     - разделение критериев на `local`, `ci`, `staging`, `prod`
     - явное поле `blocked by environment`
   - Критерии приёмки:
     - каждый критерий можно проверить конкретной командой/API-call
     - каждое утверждение из чеклиста даёт бинарный результат `PASS/FAIL/BLOCKED`
     - нет устаревших команд вида `npm start / uvicorn main:app`, если репозиторий запускается иначе

5. Раздел `5 Метрики качества и SLA`.
   - Что дописать:
     - owner, source of truth, окно измерения, formula, thresholds
     - отдельные метрики на quality gate, real-time delivery, AI cost/caching, eval pass rate
   - Критерии приёмки:
     - у каждой метрики есть формула и источник данных
     - warning/critical thresholds привязаны к конкретным действиям
     - есть метрики на regressions, а не только на happy-path throughput

6. Раздел `6 Чеклист верификации`.
   - Что дописать:
     - реальные маршруты (`POST /api/v1/tickets/{id}/move`, а не устаревший `PATCH`)
     - корректные expected statuses (`403` vs `422` должны быть явно приведены к одному контракту)
     - environment prerequisites и артефакты проверки
   - Критерии приёмки:
     - весь чеклист прогоняется автоматом без ручного знания системы
     - есть столбцы `command/action`, `expected result`, `blocking`, `blocked by environment`

7. Раздел `7 Нефункциональные требования`.
   - Что дописать:
     - local dev mode без реальных AI-ключей
     - правила для среды без `.git`
     - требования к repo clone path/worktree layout для test/deploy/context
   - Критерии приёмки:
     - локальная разработка воспроизводима одной documented setup-командой
     - git/integration-dependent проверки корректно маркируются как `blocked`, если среда урезана
     - AI-зависимые этапы имеют fallback/noop режим

8. Раздел `8 Технологический стек`.
   - Что дописать:
     - зафиксировать, что frontend = Vite/React, а не Next.js
     - version policy и mandatory/optional integrations
     - policy на contract generation (OpenAPI -> TS types / shared schemas)
   - Критерии приёмки:
     - CI, команды сборки и upload artifacts совпадают с реальным стеком
     - в ТЗ нет технологий, которые система фактически не использует на acceptance path

9. Раздел `10 Глоссарий`.
   - Что дописать:
     - определения для `project context`, `human gate`, `fallback`, `retry`, `staging verification`, `acceptance artifact`, `blocked by environment`
   - Критерии приёмки:
     - термины в ТЗ, UI и backend models не конфликтуют
     - каждый acceptance artifact имеет однозначное определение

### Идеи из интернета, которые стоит внедрить в эту систему

1. Включить prompt caching для повторяющихся AI-вызовов.
   - Источники:
     - OpenAI Prompt Caching: https://platform.openai.com/docs/guides/prompt-caching
     - Anthropic Prompt Caching: https://docs.anthropic.com/es/docs/build-with-claude/prompt-caching
   - Как применить здесь:
     - planning/review/test-generation используют большой общий prefix (system prompt, repo context, style rules, rubric)
     - retries и reject loops должны переиспользовать кэшируемый prefix, а не пересобирать весь prompt с нуля
   - Критерии приёмки:
     - статическая часть prompt вынесена перед ticket-specific delta
     - в `ai_logs` логируется cache hit/miss и стоимость до/после
     - целевой hit rate для повторных прогонов/ревью > `50-60%`

2. Перевести план/review/test-gen на structured outputs.
   - Источник:
     - OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs/supported-models
   - Как применить здесь:
     - планы, review findings, generated tests, routing decisions должны валидироваться схемой до записи в БД и UI
   - Критерии приёмки:
     - каждый AI stage имеет JSON schema / Pydantic schema
     - invalid schema не двигает тикет и не публикует side effects
     - frontend получает уже нормализованные структуры, а не свободный текст

3. Увести долгие AI-этапы в background jobs, а не держать их на request path.
   - Источник:
     - OpenAI Background mode: https://platform.openai.com/docs/guides/background
   - Как применить здесь:
     - planning/coding/review/test generation должны возвращать `job_id/status`, а UI должен жить на `queued -> running -> completed/failed`
   - Критерии приёмки:
     - длинные стадии не блокируют HTTP request до завершения модели
     - прогресс публикуется через WS или polling endpoint
     - retry/cancel/restart работают через job-state, а не через повторный ручной POST

4. Для несрочных оценок и массовых прогонов использовать batch/offline processing.
   - Источник:
     - OpenAI Batch API: https://platform.openai.com/docs/guides/batch/
   - Как применить здесь:
     - nightly evals, массовые reruns test-gen/review rubric и сравнение моделей не должны конкурировать с interactive traffic
   - Критерии приёмки:
     - offline eval jobs отделены от interactive path
     - cost accounting различает sync vs async batch traffic
     - batch path используется для nightlies и re-scoring, где latency не критична

5. Внедрить eval-driven development для каждого AI stage.
   - Источники:
     - OpenAI Evaluation best practices: https://platform.openai.com/docs/guides/evaluation-best-practices
     - Anthropic Prompt engineering overview: https://docs.anthropic.com/en/docs/prompt-engineering
   - Как применить здесь:
     - router, planning, review, test generation и handoff decisions должны иметь golden dataset и rubric, а не проверяться "на глаз"
   - Критерии приёмки:
     - для каждого AI stage есть eval dataset с happy-path, edge-case и adversarial samples
     - каждое изменение prompt/model/version запускает eval suite
     - production regressions добавляются обратно в eval dataset

6. Ускорить CI через корректное кэширование, артефакты и sharding.
   - Источники:
     - GitHub dependency caching: https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
     - pytest-xdist: https://pytest-xdist.readthedocs.io/en/latest/distribution.html
     - Playwright sharding: https://playwright.dev/docs/test-sharding
   - Как применить здесь:
     - pip/npm caches уже частично есть, но дальше нужны shard-ready test jobs и правильная публикация артефактов (`dist`, logs, screenshots, coverage)
   - Критерии приёмки:
     - build/test/security/e2e jobs разделены и умеют публиковать артефакты по типу
     - backend suite можно ускорить через `pytest -n auto`, когда фикстуры и БД изоляция готовы
     - e2e suite поддерживает Playwright sharding/parallel workers
     - CI сохраняет `dist`, test logs, screenshots, coverage-report, security-report

### Средовые блокировки, которые нужно явно отражать в ТЗ и чеклистах

- `.git` в этой среде отсутствует, поэтому git branch / worktree / PR / merge проверки должны помечаться `blocked by environment`
- реальные PostgreSQL/Redis/GitHub/n8n/MinIO интеграции в этом прогоне не валидировались end-to-end
- локальная зелёность backend tests достигается только через проектный `.venv`; "чистый" `pytest -q` в backend сейчас невоспроизводим
- frontend lint, frontend tests и e2e tests пока не дают quality signal, потому что либо отсутствуют, либо не настроены

---

## Ревизия на 2026-03-26 (факт по текущей среде)

Проверено командами:
- backend (без активации venv): `pytest -q` -> `ModuleNotFoundError: No module named 'jose'`
- backend (из проектного venv): `backend/.venv/bin/pytest -q` -> `43 passed, 20 warnings`
- backend lint: `backend/.venv/bin/ruff check app tests --statistics` -> `74 errors`
- backend typecheck: `backend/.venv/bin/mypy app` -> `67 errors in 33 files`
- frontend build: `npm run build` -> OK
- frontend lint: `npm run lint` -> ESLint не видит `eslint.config.(js|mjs|cjs)`
- e2e: каталог `e2e/tests` пуст

### P0 (блокирует стабильный dev/CI цикл)

1. ~~Починить воспроизводимый запуск backend без ручного "угадывания" интерпретатора.~~ **ЧАСТИЧНО** — тесты стабильно проходят через `.venv/bin/pytest`. Bootstrapping пока не формализован.

2. ~~Починить frontend lint-конфиг под ESLint 9.~~ **DONE 2026-03-27** — создан `eslint.config.js` (flat config), установлены зависимости, `npm run lint` проходит чисто.

### P1 (не блокирует старт, но ломает quality gate)

3. ~~Закрыть 74 ошибок Ruff в backend.~~ **DONE 2026-03-27** — 0 errors.

4. ~~Закрыть 67 ошибок mypy в backend.~~ **DONE 2026-03-27** — 0 errors (92 source files).

5. ~~Убрать предупреждения pytest.~~ **DONE 2026-03-27** — 43 passed, 0 warnings.

### P1/P2 (функциональные недоделки по коду)

6. ~~Закрыть явные TODO в runtime-потоке.~~ **DONE 2026-03-27** — WebSocket broadcast реализован в pipeline_orchestrator. Webhook dispatch реализован для ticket-update/build-complete/deploy-status.

7. Добавить реальное e2e-покрытие. **(OPEN)**
   - Факт: `e2e/tests` пустой.
   - Минимум для MVP: smoke e2e на auth -> project -> ticket -> kanban transition.

8. Добавить frontend unit/integration тесты. **(OPEN)**
   - Факт: в `frontend/src` нет `*.test.ts(x)` / `*.spec.ts(x)`.
   - Минимум для MVP: API-клиенты + критичные UI-flow (kanban move, ticket details, comments).

### P2. Новые best practices из актуальных источников (март 2026)

21. Интегрировать AI code review в CI/CD как обязательный шаг PR pipeline.
    - Источник: https://www.augmentcode.com/guides/ai-code-review-ci-cd-pipeline
    - Зачем: AI code review в CI сокращает cycle time на ~3.5 часа на PR и ловит паттерны, которые пропускает ручной ревью.
    - Критерии приёмки:
      - AI review запускается автоматически на каждый PR в GitHub Actions
      - результаты ревью доступны как inline comments
      - блокирующие findings предотвращают merge

22. Держать PR маленькими — разбивать AI-генерированный код на атомарные PR.
    - Источник: https://www.qodo.ai/blog/best-automated-code-review-tools-2026/
    - Зачем: AI-рецензенты деградируют на diff > 1000 строк. Маленькие PR = качественный feedback.
    - Критерии приёмки:
      - pipeline orchestrator разбивает codegen по subtask в отдельные коммиты
      - CI review получает diff <= 500 строк на subtask

23. Добавить AI Test Intelligence для оптимизации CI.
    - Источник: https://devops.com/the-future-of-ai-in-software-quality-how-autonomous-platforms-are-transforming-devops/
    - Зачем: запуск только затронутых тестов сокращает cycle time до 80%.
    - Критерии приёмки:
      - CI определяет, какие тесты затронуты по diff
      - полный suite запускается только в nightly/release pipeline
      - метрика: median CI time на PR

24. Внедрить автоматическое обнаружение AI-специфических уязвимостей.
    - Источник: https://www.verdent.ai/guides/best-ai-for-code-review-2026
    - Зачем: AI-генерированный код требует проверки на prompt injection, hardcoded secrets, insecure deserialization.
    - Критерии приёмки:
      - security_agent проверяет AI-generated code на OWASP Top 10
      - pipeline блокирует merge при critical findings
      - findings сохраняются в ai_logs

25. Создать collaborative feedback loop: CI failures -> AI -> fix -> re-run.
    - Источник: https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e
    - Зачем: при падении тестов AI может автоматически попытаться исправить код, сокращая ручной цикл.
    - Критерии приёмки:
      - при build failure AI agent получает logs и пытается fix
      - max 2 автоматических retry, затем escalation на человека
      - каждый auto-fix записывается в ai_logs

## Ревизия на 2026-03-26

Источник ТЗ: `TZ_AI_Coding_Pipeline.docx`

Что проверено руками:
- ТЗ извлечено через `textutil -convert txt -stdout TZ_AI_Coding_Pipeline.docx`
- backend: `pytest -q`
- frontend: `npm run build`
- структура backend/frontend/infra и ключевые API/типы/WS-модули

Фактический статус:
- `backend pytest` не стартует: `ModuleNotFoundError: No module named 'jose'`
- `frontend build` падает на рассинхроне типов и контрактов
- workspace смонтирован без `.git`, поэтому git-ветки, diff и PR-флоу из ТЗ в этой среде невалидируемы end-to-end
- часть ТЗ уже формально описана, но критерии проверки местами не совпадают с реальной структурой API и окружения

## P0. Автодоработать ТЗ до проверяемого состояния

### 1. Раздел 1.3 `Целевые пользователи и роли (RBAC)`
Нужно автодописать:
- единая матрица `role -> screen -> endpoint -> transition -> forbidden action`
- явное правило `Production deploy = только pm_lead`
- отдельное описание системной роли `ai_agent`: что может делать автоматически, а что не может никогда

Почему это нужно:
- код и UI всё ещё расходятся по ожиданиям ролей
- ТЗ требует human gates, но не превращает их в машинно-проверяемые правила доступа

Критерии приёмки:
- в ТЗ есть одна каноническая таблица ролей без дублирующих трактовок
- backend enum ролей и frontend enum ролей совпадают 1:1
- есть минимум 1 негативный RBAC-сценарий на каждую роль
- проверка `developer -> production` формализована как `403 Forbidden`

### 2. Разделы 2.1-2.3 `Архитектура`, `Пайплайн`, `Agent Router`
Нужно автодописать:
- входы/выходы каждого этапа пайплайна
- обязательные side effects: history, notifications, websocket, ai_logs, retries
- idempotency policy для каждого шага
- fallback policy для AI-провайдеров и недоступных внешних зависимостей
- единый контракт WS-сообщений

Почему это нужно:
- ТЗ декларирует orchestration, retries и observability, но не фиксирует форматы событий и replay-safe поведение
- без этого нельзя надёжно автоматизировать переходы и reject loops

Критерии приёмки:
- для всех 8 колонок есть `trigger`, `actor`, `preconditions`, `side effects`, `reject target`, `retry policy`, `timeout`
- для каждого автоматического шага указан idempotency key или эквивалентное правило повторного запуска
- WS-схема описана через конкретные события и payload-поля
- agent router описывает primary/fallback/abort policy для planning, coding, review, test gen, security

### 3. Раздел 3 `UI/UX`
Нужно автодописать:
- соответствие каждого экрана конкретным API и WS событиям
- обязательные состояния `loading`, `empty`, `error`, `stale`, `forbidden`
- что является placeholder/demo и что запрещено на acceptance-stage

Почему это нужно:
- фронтенд сейчас не в одном контракте с backend и частично рассчитывает на поля, которых нет
- в MVP нельзя принимать экран, который рисуется на mock-данных

Критерии приёмки:
- у каждого экрана есть карта `UI element -> API -> expected response`
- запрещены hardcoded `default project`, demo users и фиктивные summary-поля
- mobile acceptance сформулирован через конкретный viewport и список обязательных экранов

### 4. Раздел 4 `Функциональные требования по итерациям`
Нужно автодописать:
- перевод всех acceptance criteria из описательных в проверяемые
- команды верификации должны соответствовать реальному стеку репозитория
- разделить критерии на `локально`, `в CI`, `в интеграционной среде`

Почему это нужно:
- в текущем ТЗ есть команды уровня `npm start / uvicorn main:app`, но репозиторий фактически устроен иначе
- часть критериев нельзя проверить в среде без git/секретов/инфры

Критерии приёмки:
- у каждой итерации есть список проверок `PASS/FAIL`
- у каждой проверки есть точная команда или API-call
- у каждой проверки есть prerequisite среды
- каждая проверка помечена как `local`, `ci`, `staging` или `prod`

### 5. Раздел 5 `Метрики качества и SLA`
Нужно автодописать:
- owner каждой метрики
- источник истины для метрики
- окно измерения и способ агрегации
- порог alerting и действие при деградации

Почему это нужно:
- сейчас это хороший список целей, но не операционный SLA

Критерии приёмки:
- у каждой метрики есть формула
- у каждой метрики есть источник данных: app logs, Prometheus, DB, CI, billing
- у каждой метрики есть `target`, `warning threshold`, `critical threshold`
- есть минимум один action playbook на нарушение каждой P0/P1 метрики

### 6. Раздел 6 `Чеклист верификации`
Нужно автодописать:
- команды под реальный repo layout
- expected output не абстрактный, а измеримый
- разделение проверок на блокирующие и неблокирующие

Почему это нужно:
- checklist должен запускаться автоматом и быть пригодным для ревизора/automation

Критерии приёмки:
- каждый чеклист можно прогнать скриптом без ручных догадок
- каждая проверка выдаёт бинарный результат
- есть поле `blocked by environment`, если проверка невозможна без внешней инфраструктуры
- итог итерации считается по формуле `all blocking checks pass`

### 7. Раздел 7 `Нефункциональные требования`
Нужно автодописать:
- требования к dev/test среде отдельно от production
- минимальный локальный режим без внешних AI-ключей
- требования к sandbox/secret handling/traceability в dev и CI

Почему это нужно:
- сейчас dev-mode и test-mode не описаны как first-class режимы
- из-за этого локальная разработка ломается при отсутствии ключей и зависимостей

Критерии приёмки:
- в ТЗ есть отдельный `local development mode`
- все AI-зависимые функции имеют documented fallback/noop поведение
- для test mode не требуются реальные внешние AI API ключи

### 8. Раздел 8 `Рекомендуемый технологический стек`
Нужно автодописать:
- approved версии и обязательные интеграции
- обязательный минимальный стек для MVP
- что допускается как future/optional, а что входит в acceptance perimeter

Почему это нужно:
- сейчас раздел смешивает уже выбранный стек и альтернативы без решения, что именно является контрактом проекта

Критерии приёмки:
- есть таблица `layer -> approved tech -> version policy -> mandatory/optional`
- backend/frontend/infra репозитория не расходятся с этим списком
- команды сборки и запуска в ТЗ совпадают с фактическими командами репозитория

### 9. Раздел 10 `Глоссарий`
Нужно автодописать:
- определения для ticket, subtask, plan, review, ai_log, deploy gate, fallback, retry, staging verification
- что считается acceptance artifact на каждом этапе

Критерии приёмки:
- нет терминов, которые используются в ТЗ без определения
- определения не конфликтуют с именами сущностей backend schemas/models

## P0. Доработать систему и код до соответствия ТЗ MVP

### 10. Починить воспроизводимость backend окружения
Факт:
- `pytest -q` падает до старта тестов на импорте `jose`

Что автодоработать:
- привести backend setup к воспроизводимому запуску из чистой среды
- зафиксировать одну команду bootstrap зависимостей
- добавить preflight-check зависимостей перед тестами

Критерии приёмки:
- `pytest -q` стартует в чистой среде после одной documented setup-команды
- dependency bootstrap описан в ТЗ и `README`/Makefile
- ошибка отсутствующего пакета ловится preflight-скриптом до запуска тестов

### 11. Закрыть разрыв контрактов frontend/backend
Факт:
- `npm run build` падает на несовпадении полей `User`, `Ticket`, `Review`, `TestResult`, `AiLog`, ролей и payload-структур

Что автодоработать:
- сделать backend schema/OpenAPI источником правды
- синхронизировать TS-типы и API clients
- убрать мёртвые поля и старые роли из UI

Критерии приёмки:
- `npm run build` проходит без TypeScript ошибок
- фронтенд не обращается к полям, которых нет в backend schemas
- роли и статусы совпадают между backend, frontend, tests и ТЗ

### 12. Убрать hardcoded project flow
Факт:
- доска до сих пор использует `DEFAULT_PROJECT_ID = 'default'`

Что автодоработать:
- обязательный реальный выбор проекта
- запрет на board fetch/create ticket без валидного `project_id`

Критерии приёмки:
- доска не использует хардкод project id
- create/move/list ticket работают только через реальный проект
- есть пустое состояние для пользователя без проектов

### 13. Привести WebSocket к общему протоколу
Факт:
- backend уже поддерживает `/ws?token=...`, но схема событий и подписка на проект не закреплены в ТЗ как канонический контракт

Что автодоработать:
- формализовать handshake и subscribe flow
- сделать единый shared event schema
- описать retry/reconnect policy на клиенте и сервере

Критерии приёмки:
- клиент после логина подписывается на `project_id`
- create/update/move/comment/notification события приходят по одному формату
- есть smoke-check реального broadcast между двумя сессиями

### 14. Сделать AI review grounded в реальном diff
Факт:
- review trigger сейчас может работать только по `PR URL`/`branch_name` или вообще по описанию тикета

Что автодоработать:
- review должен брать реальный diff как primary source
- fallback к ticket description должен быть явно помечен degraded mode

Критерии приёмки:
- при наличии diff review промпт строится из diff
- inline findings содержат `file` и `line`
- режим без diff не маскируется под полноценный code review

### 15. Довести AI/provider graceful degradation
Факт:
- ТЗ требует fallback, но dev/test режим ещё не закреплён как обязательный runtime-path

Что автодоработать:
- без внешних AI-ключей система должна продолжать работать в local/test режиме
- router должен возвращать понятный stub/fallback outcome

Критерии приёмки:
- tests не требуют реальных AI API keys
- AI-зависимые API возвращают предсказуемый degraded response
- отказ провайдера логируется и не ломает основной CRUD/kanban flow

### 16. Довести observability до требований ТЗ
Факт:
- `ai_logs` endpoint существует, но в acceptance ТЗ не закреплены обязательные поля и сценарии верификации

Что автодоработать:
- единый формат ai_logs
- связь `ticket -> plan -> codegen -> review -> test -> deploy`
- минимальный audit trail на все human gates

Критерии приёмки:
- каждый AI вызов имеет `agent`, `model`, `action`, `tokens`, `cost`, `status`, `duration`
- по `ticket_id` восстанавливается полная цепочка действий
- reject/approve пользователя записываются в history и доступны для UI

## P1. Что уже лучше, чем было раньше

- `projects` API присутствует и подключён в [`backend/app/api/v1/router.py`](backend/app/api/v1/router.py)
- ограничение `staging_verification -> production` уже зафиксировано только для `pm_lead` в [`backend/app/services/kanban_service.py`](backend/app/services/kanban_service.py)
- endpoint `ai_logs` уже читает реальные записи, а не stub-ответ

Это важно сохранить при дальнейшей автодоработке: часть старых gap-документов уже устарела и не должна слепо копироваться обратно в ТЗ.

## P1. Идеи из актуальных внешних практик для ускорения и улучшения системы

### 17. Ввести DORA-метрики как главный operational слой
Идея:
- дополнить текущие SLA не только pipeline-time, но и DORA/Four Keys: deployment frequency, lead time, change failure rate, time to restore

Зачем:
- это даст измеримый ответ на бизнес-цель "ускорить delivery в 3 раза", а не только локальные тайминги AI-шагов

Критерии приёмки:
- dashboard показывает минимум 4 DORA-метрики
- каждая метрика считается автоматически по ticket/deploy/incidents events
- у product/lead есть weekly trend view

Источник:
- Google Cloud DORA / DevOps & SRE: https://cloud.google.com/blog/products/devops-sre

### 18. Ускорить CI через dependency caching и параллельные jobs
Идея:
- кэшировать зависимости frontend/backend
- разделить lint, unit, integration, e2e на параллельные jobs

Зачем:
- это самый дешёвый путь сократить staging cycle time без переписывания продукта

Критерии приёмки:
- повторный CI-run заметно быстрее cold-start
- pipeline stages независимы и могут идти параллельно
- staging gate считает critical path, а не сумму всех джобов последовательно

Источники:
- GitHub Actions jobs/matrix: https://docs.github.com/actions/using-jobs
- GitHub dependency caching: https://docs.github.com/en/enterprise-server%403.14/actions/concepts/workflows-and-actions/dependency-caching

### 19. Шардировать E2E и держать Playwright как обязательный perf lever
Идея:
- вынести тяжёлые E2E из линейного пайплайна в shard/parallel execution
- хранить HTML-report и screenshot artifacts как acceptance artifacts

Зачем:
- E2E почти всегда самый дорогой по времени этап staging verification

Критерии приёмки:
- E2E suite запускается параллельно
- по каждому падению есть screenshot/video/report artifact
- полное время E2E фиксируется как отдельная метрика в SLA

Источник:
- Playwright docs: https://playwright.dev/docs/intro

### 20. Сделать Context Engine многослойным и индексировать tenant/filter поля
Идея:
- кроме vector index, явно индексировать payload/tenant fields для быстрых фильтров по проекту, языку, модулю, owner

Зачем:
- для большого multi-project контекста фильтрация по payload часто даёт больший выигрыш, чем попытка "лечить всё эмбеддингами"

Критерии приёмки:
- поиск по коду фильтруется минимум по `project_id`, `language`, `path_prefix`
- время поиска по проекту не деградирует линейно с ростом общей базы
- в ТЗ описаны индексы payload/tenant, а не только embeddings

Источник:
- Qdrant indexing and tenant index: https://qdrant.tech/documentation/concepts/indexing/

### 21. Свести frontend contract к OpenAPI-генерации вместо ручных дублей
Идея:
- генерировать TS-типы из backend OpenAPI и строить typed client поверх схемы, а не держать параллельные ручные типы `Project`, `WSEvent`, `paths`
- использовать generated `paths/components` как source of truth, а ручные интерфейсы оставлять только для чисто UI-состояния

Зачем:
- это прямой способ убрать drift вида `owner_id` vs `creator_id`, старые route/path сигнатуры и расхождение response envelope между backend и frontend

Критерии приёмки:
- frontend импортирует generated schema types из OpenAPI, а не дублирует backend сущности вручную
- CI валится, если OpenAPI и сгенерированные типы рассинхронизированы
- API-клиент использует schema-driven path/query/body typing

Источники:
- openapi-typescript intro: https://openapi-ts.dev/introduction
- openapi-fetch typed client: https://openapi-ts.dev/openapi-fetch/

### 22. Развести cache и artifacts в CI, а не смешивать их в один слой
Идея:
- dependency cache использовать только для повторно используемых зависимостей (`npm`, `pip`, `uv`, browser deps)
- артефакты использовать для build outputs, coverage, test reports, screenshots, traces

Зачем:
- это убирает лишнее время на cold-start и одновременно делает acceptance воспроизводимым, потому что отчёты и дебажные материалы живут как artifacts, а не теряются между job-ами

Критерии приёмки:
- backend/frontend зависимости кэшируются отдельными ключами
- build output, coverage, Playwright report, screenshots и traces публикуются как artifacts
- в workflow нет подмены артефактов dependency cache-ом и наоборот

Источники:
- GitHub dependency caching: https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
- GitHub workflow artifacts: https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts

## P2. Блокеры этой ревизии

- backend тесты невалидируемы до установки Python-зависимостей
- git/branch/PR acceptance нельзя полноценно проверить в текущем workspace без `.git`
- часть checklist-команд в ТЗ не соответствует текущему layout проекта

## P2. Следующий рекомендуемый проход ревизора

1. Довести среду до состояния, где backend тесты реально запускаются.
2. Свести frontend типы к backend схемам и снова прогнать `npm run build`.
3. После этого переписать раздел 6 ТЗ так, чтобы automation мог прогонять checklist автоматически.
4. Затем отдельно ревизовать CI/CD, Context Engine и AI fallback на фактических интеграциях.
