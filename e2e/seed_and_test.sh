#!/bin/bash
# ============================================================
# AI Coding Pipeline — Seed Data & Integration Test Script
# ============================================================
set -e

BASE="http://127.0.0.1:8010/api/v1"
PASS=0
FAIL=0
ERRORS=""

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); ERRORS="$ERRORS\n  - $1"; }
info()  { echo -e "\033[36m→ $1\033[0m"; }
header(){ echo -e "\n\033[1;35m══════════════════════════════════════\033[0m"; echo -e "\033[1;35m  $1\033[0m"; echo -e "\033[1;35m══════════════════════════════════════\033[0m"; }

# Helper: extract JSON field
jq_field() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$1',''))" 2>/dev/null; }
jq_nested() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

# ============================================================
header "1. AUTHENTICATION"
# ============================================================

info "Registering users with different roles..."

# Register owner first
OWNER_RESP=$(curl -s -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@devbot.su","password":"demo1234","full_name":"Demo User"}')
OWNER_TOKEN=$(echo "$OWNER_RESP" | jq_field access_token)
if [ -z "$OWNER_TOKEN" ]; then
  # Already registered — try login
  OWNER_TOKEN=$(curl -s -X POST $BASE/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"demo@devbot.su","password":"demo1234"}' | jq_field access_token)
fi
[ -n "$OWNER_TOKEN" ] && green "Owner registered/logged in OK" || red "Owner auth FAILED"

# Register developer
DEV_RESP=$(curl -s -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@devbot.su","password":"dev12345","full_name":"Alex Developer"}')
DEV_TOKEN=$(echo "$DEV_RESP" | jq_field access_token)
if [ -z "$DEV_TOKEN" ]; then
  DEV_TOKEN=$(curl -s -X POST $BASE/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"dev@devbot.su","password":"dev12345"}' | jq_field access_token)
fi
[ -n "$DEV_TOKEN" ] && green "Developer registered/logged in" || red "Developer auth FAILED"

# Register PM Lead
PM_RESP=$(curl -s -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"pm@devbot.su","password":"pm123456","full_name":"Maria PM Lead"}')
PM_TOKEN=$(echo "$PM_RESP" | jq_field access_token)
if [ -z "$PM_TOKEN" ]; then
  PM_TOKEN=$(curl -s -X POST $BASE/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"pm@devbot.su","password":"pm123456"}' | jq_field access_token)
fi
[ -n "$PM_TOKEN" ] && green "PM Lead registered/logged in" || red "PM Lead auth FAILED"

# Test duplicate registration (should fail with 409)
DUP_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@devbot.su","password":"demo1234","full_name":"Duplicate"}')
[ "$DUP_RESP" = "409" ] && green "Duplicate registration blocked (409)" || red "Duplicate registration: expected 409, got $DUP_RESP"

# Test invalid credentials
BAD_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@devbot.su","password":"wrongpassword"}')
[ "$BAD_RESP" = "401" ] && green "Invalid password rejected (401)" || red "Invalid password: expected 401, got $BAD_RESP"

# Test /auth/me
ME_NAME=$(curl -s $BASE/auth/me -H "Authorization: Bearer $OWNER_TOKEN" | jq_field full_name)
[ "$ME_NAME" = "Demo User" ] && green "GET /auth/me returns correct user" || red "GET /auth/me wrong: $ME_NAME"

# ============================================================
header "2. RBAC — ASSIGN ROLES"
# ============================================================

# Get user IDs
USERS_JSON=$(curl -s $BASE/users -H "Authorization: Bearer $OWNER_TOKEN")
DEV_ID=$(echo "$USERS_JSON" | python3 -c "import sys,json; users=json.load(sys.stdin); print(next((u['id'] for u in users if u['email']=='dev@devbot.su'),''))")
PM_ID=$(echo "$USERS_JSON" | python3 -c "import sys,json; users=json.load(sys.stdin); print(next((u['id'] for u in users if u['email']=='pm@devbot.su'),''))")

info "Assigning developer role to dev@devbot.su..."
curl -s -X PATCH "$BASE/users/$DEV_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role":"developer"}' > /dev/null
DEV_ROLE=$(curl -s "$BASE/users/$DEV_ID" -H "Authorization: Bearer $OWNER_TOKEN" | jq_field role)
[ "$DEV_ROLE" = "developer" ] && green "Developer role assigned" || red "Developer role: $DEV_ROLE"

info "Assigning pm_lead role to pm@devbot.su..."
curl -s -X PATCH "$BASE/users/$PM_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role":"pm_lead"}' > /dev/null
PM_ROLE=$(curl -s "$BASE/users/$PM_ID" -H "Authorization: Bearer $OWNER_TOKEN" | jq_field role)
[ "$PM_ROLE" = "pm_lead" ] && green "PM Lead role assigned" || red "PM Lead role: $PM_ROLE"

# Re-login to get tokens with updated roles
DEV_TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@devbot.su","password":"dev12345"}' | jq_field access_token)

PM_TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pm@devbot.su","password":"pm123456"}' | jq_field access_token)

# ============================================================
header "3. PROJECT SETUP"
# ============================================================

# Get existing project or create one
PROJECTS=$(curl -s "$BASE/projects" -H "Authorization: Bearer $OWNER_TOKEN")
PROJECT_ID=$(echo "$PROJECTS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'] if d.get('items') and len(d['items'])>0 else '')" 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
  info "No project found — creating one..."
  NEW_PROJ=$(curl -s -X POST "$BASE/projects" \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"AI Coding Pipeline","description":"Main project for the AI-driven development platform"}')
  PROJECT_ID=$(echo "$NEW_PROJ" | jq_field id)
fi
[ -n "$PROJECT_ID" ] && green "Project ready: $PROJECT_ID" || red "No project created"

# Update project with repo URL
curl -s -X PATCH "$BASE/projects/$PROJECT_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"AI Coding Pipeline","description":"Main project for the AI-driven development platform","github_repo_url":"https://github.com/rtfdeamon/AICodingSystem","default_branch":"main"}' > /dev/null
green "Project updated with GitHub repo URL"

# ============================================================
header "4. CREATE TICKETS"
# ============================================================

info "Creating 5 tickets for the pipeline..."

# Ticket 1: Auth Module
T1=$(curl -s -X POST "$BASE/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Implement JWT Authentication",
    "description":"Build complete JWT auth with bcrypt password hashing, access/refresh token rotation, and middleware",
    "business_task":"Secure user access to the platform",
    "decomposed_task":"1. Create auth models 2. Implement JWT service 3. Add middleware 4. Create login/register endpoints",
    "coding_task":"Implement auth_service.py with bcrypt + PyJWT, add auth middleware, create /auth/* endpoints",
    "ai_prompt":"Generate a complete JWT authentication module for FastAPI with bcrypt hashing, access+refresh tokens, and role-based middleware",
    "priority":"P0",
    "labels":["auth","security","backend"]
  }')
T1_ID=$(echo "$T1" | jq_field id)
[ -n "$T1_ID" ] && green "Ticket 1 created: JWT Authentication (P0)" || red "Ticket 1 creation failed"

# Ticket 2: Kanban UI
T2=$(curl -s -X POST "$BASE/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Build Kanban Board with Drag & Drop",
    "description":"Create a responsive Kanban board with 8 pipeline columns and drag-and-drop ticket management",
    "business_task":"Visualize the development pipeline for project managers",
    "priority":"P1",
    "labels":["frontend","ui","kanban"]
  }')
T2_ID=$(echo "$T2" | jq_field id)
[ -n "$T2_ID" ] && green "Ticket 2 created: Kanban Board (P1)" || red "Ticket 2 creation failed"

# Ticket 3: AI Planning Agent
T3=$(curl -s -X POST "$BASE/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Integrate Claude Planning Agent",
    "description":"Connect Anthropic Claude API for automatic plan generation from ticket descriptions",
    "business_task":"Automate development planning to reduce PM overhead",
    "coding_task":"Implement planning_agent.py with Claude SDK, structured output parsing, and plan persistence",
    "ai_prompt":"Create a planning agent that takes a ticket description and generates a structured development plan with subtasks, dependencies, and file list",
    "priority":"P1",
    "labels":["ai","backend","claude"]
  }')
T3_ID=$(echo "$T3" | jq_field id)
[ -n "$T3_ID" ] && green "Ticket 3 created: Claude Planning Agent (P1)" || red "Ticket 3 creation failed"

# Ticket 4: File Attachments
T4=$(curl -s -X POST "$BASE/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Add File Attachments to Tickets",
    "description":"Support drag-and-drop file upload on tickets with preview for images and download for documents",
    "priority":"P2",
    "labels":["frontend","backend","upload"]
  }')
T4_ID=$(echo "$T4" | jq_field id)
[ -n "$T4_ID" ] && green "Ticket 4 created: File Attachments (P2)" || red "Ticket 4 creation failed"

# Ticket 5: Dashboard Analytics
T5=$(curl -s -X POST "$BASE/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Dashboard Metrics & Analytics",
    "description":"Build a metrics dashboard with pipeline stats, AI costs, code quality, and deployment metrics",
    "priority":"P3",
    "labels":["frontend","analytics","dashboard"]
  }')
T5_ID=$(echo "$T5" | jq_field id)
[ -n "$T5_ID" ] && green "Ticket 5 created: Dashboard Analytics (P3)" || red "Ticket 5 creation failed"

# ============================================================
header "5. TICKET LIFECYCLE — MOVE THROUGH PIPELINE"
# ============================================================

info "Moving Ticket 1 through the pipeline..."

# Move T1: backlog -> ai_planning (PM/owner can do this)
M1=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_planning","comment":"Starting AI planning for auth module"}')
M1_COL=$(echo "$M1" | jq_field column_name)
[ "$M1_COL" = "ai_planning" ] && green "T1: backlog → ai_planning" || red "T1 move to ai_planning failed: $M1_COL"

# Move T1: ai_planning -> plan_review (owner can do this)
M2=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"plan_review","comment":"Plan generated, ready for review"}')
M2_COL=$(echo "$M2" | jq_field column_name)
[ "$M2_COL" = "plan_review" ] && green "T1: ai_planning → plan_review" || red "T1 move to plan_review failed: $M2_COL"

# Move T1: plan_review -> ai_coding (developer/pm/owner can approve plan)
M3=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_coding","comment":"Plan approved, start coding"}')
M3_COL=$(echo "$M3" | jq_field column_name)
[ "$M3_COL" = "ai_coding" ] && green "T1: plan_review → ai_coding" || red "T1 move to ai_coding failed: $M3_COL"

# Move T1: ai_coding -> code_review
M4=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"code_review","comment":"Code generated, ready for review"}')
M4_COL=$(echo "$M4" | jq_field column_name)
[ "$M4_COL" = "code_review" ] && green "T1: ai_coding → code_review" || red "T1 move to code_review failed: $M4_COL"

# Move T1: code_review -> staging (approve code)
M5=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"staging","comment":"Code approved, deploying to staging"}')
M5_COL=$(echo "$M5" | jq_field column_name)
[ "$M5_COL" = "staging" ] && green "T1: code_review → staging" || red "T1 move to staging failed: $M5_COL"

# Move T1: staging -> staging_verification
M6=$(curl -s -X POST "$BASE/tickets/$T1_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"staging_verification","comment":"Staging deploy complete"}')
M6_COL=$(echo "$M6" | jq_field column_name)
[ "$M6_COL" = "staging_verification" ] && green "T1: staging → staging_verification" || red "T1 move failed: $M6_COL"

# Move T2 to ai_planning
curl -s -X POST "$BASE/tickets/$T2_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_planning"}' > /dev/null
green "T2: backlog → ai_planning"

# Move T3 to ai_planning
curl -s -X POST "$BASE/tickets/$T3_ID/move" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_planning"}' > /dev/null
green "T3: backlog → ai_planning"

# ============================================================
header "6. RBAC ENFORCEMENT"
# ============================================================

info "Testing that developer cannot move backlog → ai_planning..."
RBAC1_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/tickets/$T4_ID/move" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_planning"}')
[ "$RBAC1_CODE" = "422" ] && green "RBAC: Developer blocked from backlog→ai_planning (422)" || red "RBAC: expected 422, got $RBAC1_CODE"

info "Testing that PM can move backlog → ai_planning..."
RBAC2_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/tickets/$T4_ID/move" \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column":"ai_planning"}')
[ "$RBAC2_CODE" = "200" ] && green "RBAC: PM Lead can move backlog→ai_planning (200)" || red "RBAC: expected 200, got $RBAC2_CODE"

# ============================================================
header "7. COMMENTS"
# ============================================================

info "Adding comments to Ticket 1..."

# Owner adds comment
C1=$(curl -s -X POST "$BASE/tickets/$T1_ID/comments" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":"This auth module should use bcrypt with cost factor 12 and JWT RS256 for production"}')
C1_ID=$(echo "$C1" | jq_field id)
C1_USER=$(echo "$C1" | python3 -c "import sys,json; d=json.load(sys.stdin); u=d.get('user',{}); print(u.get('full_name','') if u else '')" 2>/dev/null)
[ -n "$C1_ID" ] && green "Comment 1 created by owner" || red "Comment 1 failed"
[ "$C1_USER" = "Demo User" ] && green "Comment shows correct user name: $C1_USER" || red "Comment user name wrong: '$C1_USER'"

# Developer adds comment
C2=$(curl -s -X POST "$BASE/tickets/$T1_ID/comments" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":"I recommend adding rate limiting on the login endpoint to prevent brute force attacks"}')
C2_ID=$(echo "$C2" | jq_field id)
[ -n "$C2_ID" ] && green "Comment 2 created by developer" || red "Comment 2 failed"

# Threaded reply
C3=$(curl -s -X POST "$BASE/tickets/$T1_ID/comments" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"body\":\"Good point! Let's add 5 attempts per minute per IP\",\"parent_id\":\"$C2_ID\"}")
C3_PARENT=$(echo "$C3" | jq_field parent_id)
[ "$C3_PARENT" = "$C2_ID" ] && green "Threaded reply created (parent_id matches)" || red "Threaded reply parent_id mismatch"

# List comments
COMMENTS_COUNT=$(curl -s "$BASE/tickets/$T1_ID/comments" \
  -H "Authorization: Bearer $OWNER_TOKEN" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COMMENTS_COUNT" -ge 3 ] && green "List comments: $COMMENTS_COUNT comments found" || red "Expected >=3 comments, got $COMMENTS_COUNT"

# ============================================================
header "8. BOARD STATE"
# ============================================================

info "Fetching Kanban board..."
BOARD=$(curl -s "$BASE/projects/$PROJECT_ID/board" -H "Authorization: Bearer $OWNER_TOKEN")
# Board may return {columns: {backlog: [...], ...}} or flat {backlog: [...], ...}
BACKLOG_COUNT=$(echo "$BOARD" | python3 -c "
import sys,json; d=json.load(sys.stdin)
cols = d.get('columns', d)  # handle both formats
if isinstance(cols, dict): print(len(cols.get('backlog',[])))
elif isinstance(cols, list): print(len([c for c in cols if c.get('name')=='backlog'][0].get('tickets',[])) if any(c.get('name')=='backlog' for c in cols) else 0)
else: print(0)
")
AI_PLANNING_COUNT=$(echo "$BOARD" | python3 -c "
import sys,json; d=json.load(sys.stdin)
cols = d.get('columns', d)
if isinstance(cols, dict): print(len(cols.get('ai_planning',[])))
elif isinstance(cols, list): print(len([c for c in cols if c.get('name')=='ai_planning'][0].get('tickets',[])) if any(c.get('name')=='ai_planning' for c in cols) else 0)
else: print(0)
")
STAGING_VERIF_COUNT=$(echo "$BOARD" | python3 -c "
import sys,json; d=json.load(sys.stdin)
cols = d.get('columns', d)
if isinstance(cols, dict): print(len(cols.get('staging_verification',[])))
elif isinstance(cols, list): print(len([c for c in cols if c.get('name')=='staging_verification'][0].get('tickets',[])) if any(c.get('name')=='staging_verification' for c in cols) else 0)
else: print(0)
")

echo "  Backlog: $BACKLOG_COUNT | AI Planning: $AI_PLANNING_COUNT | Staging Verification: $STAGING_VERIF_COUNT"
[ "$BACKLOG_COUNT" -ge 1 ] && green "Board: Backlog has tickets" || red "Board: Backlog empty"
[ "$AI_PLANNING_COUNT" -ge 2 ] && green "Board: AI Planning has $AI_PLANNING_COUNT tickets" || red "Board: AI Planning expected >=2, got $AI_PLANNING_COUNT"
[ "$STAGING_VERIF_COUNT" -ge 1 ] && green "Board: Staging Verification has ticket (T1)" || red "Board: Staging Verification empty"

# ============================================================
header "9. TICKET HISTORY (AUDIT TRAIL)"
# ============================================================

HISTORY=$(curl -s "$BASE/tickets/$T1_ID/history" -H "Authorization: Bearer $OWNER_TOKEN")
HIST_COUNT=$(echo "$HISTORY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$HIST_COUNT" -ge 6 ] && green "Ticket 1 has $HIST_COUNT history entries (6 moves)" || red "Expected >=6 history entries, got $HIST_COUNT"

# ============================================================
header "10. DASHBOARD METRICS"
# ============================================================

PIPELINE=$(curl -s "$BASE/dashboard/pipeline-stats?project_id=$PROJECT_ID" -H "Authorization: Bearer $OWNER_TOKEN")
TOTAL=$(echo "$PIPELINE" | jq_field total_tickets)
[ "$TOTAL" -ge 5 ] && green "Dashboard: $TOTAL total tickets" || red "Dashboard: expected >=5 tickets, got $TOTAL"

AI_COSTS=$(curl -s "$BASE/dashboard/ai-costs?project_id=$PROJECT_ID" -H "Authorization: Bearer $OWNER_TOKEN")
COST_STATUS=$(echo "$AI_COSTS" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if 'total_cost' in d else 'fail')")
[ "$COST_STATUS" = "ok" ] && green "Dashboard: AI costs endpoint works" || red "Dashboard: AI costs failed"

QUALITY=$(curl -s "$BASE/dashboard/code-quality?project_id=$PROJECT_ID" -H "Authorization: Bearer $OWNER_TOKEN")
Q_STATUS=$(echo "$QUALITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if 'lint_pass_rate' in d else 'fail')")
[ "$Q_STATUS" = "ok" ] && green "Dashboard: Code quality endpoint works" || red "Dashboard: Code quality failed"

DEPLOYS=$(curl -s "$BASE/dashboard/deployment-stats?project_id=$PROJECT_ID" -H "Authorization: Bearer $OWNER_TOKEN")
D_STATUS=$(echo "$DEPLOYS" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if 'deploy_count' in d else 'fail')")
[ "$D_STATUS" = "ok" ] && green "Dashboard: Deployment stats endpoint works" || red "Dashboard: Deployment stats failed"

# ============================================================
header "11. USER MANAGEMENT"
# ============================================================

USERS=$(curl -s "$BASE/users" -H "Authorization: Bearer $OWNER_TOKEN")
USER_COUNT=$(echo "$USERS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$USER_COUNT" -ge 3 ] && green "User management: $USER_COUNT users found" || red "Expected >=3 users, got $USER_COUNT"

# ============================================================
header "12. SEARCH & PAGINATION"
# ============================================================

# Search tickets
SEARCH=$(curl -s "$BASE/projects/$PROJECT_ID/tickets?search=JWT" -H "Authorization: Bearer $OWNER_TOKEN")
SEARCH_COUNT=$(echo "$SEARCH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))")
[ "$SEARCH_COUNT" -ge 1 ] && green "Search 'JWT': found $SEARCH_COUNT ticket(s)" || red "Search 'JWT' found 0"

# Pagination
PAGE=$(curl -s "$BASE/projects/$PROJECT_ID/tickets?per_page=2&page=1" -H "Authorization: Bearer $OWNER_TOKEN")
PAGE_SIZE=$(echo "$PAGE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('items',[])))")
[ "$PAGE_SIZE" -le 2 ] && green "Pagination: page 1 has $PAGE_SIZE items (max 2)" || red "Pagination: expected <=2, got $PAGE_SIZE"

# ============================================================
header "13. WEBHOOK ENDPOINTS"
# ============================================================

# n8n ticket-update webhook (no auth configured, should work in dev)
WH_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/webhooks/n8n/ticket-update" \
  -H "Content-Type: application/json" \
  -d "{\"ticket_id\":\"$T5_ID\",\"action\":\"approve_plan\",\"data\":{}}")
[ "$WH_RESP" = "200" ] && green "n8n webhook ticket-update: 200" || red "n8n webhook: $WH_RESP"

# ============================================================
header "14. HEALTH & PING"
# ============================================================

HEALTH=$(curl -s http://127.0.0.1:8010/health | jq_field status)
[ "$HEALTH" = "healthy" ] && green "Health check: healthy" || red "Health: $HEALTH"

PING=$(curl -s $BASE/ping | jq_field status)
[ "$PING" = "ok" ] && green "Ping: ok" || red "Ping: $PING"

# ============================================================
header "RESULTS"
# ============================================================

TOTAL=$((PASS + FAIL))
echo ""
echo -e "\033[1m  Total: $TOTAL tests\033[0m"
echo -e "\033[32m  Passed: $PASS\033[0m"
echo -e "\033[31m  Failed: $FAIL\033[0m"

if [ "$FAIL" -gt 0 ]; then
  echo -e "\n\033[31mFailed tests:$ERRORS\033[0m"
  exit 1
else
  echo -e "\n\033[32;1m  🎉 ALL TESTS PASSED!\033[0m"
fi
