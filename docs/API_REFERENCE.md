# AI Coding Pipeline - API Reference for Coding Agents

Base URL: `http://localhost:8001/api/v1`

All endpoints (except auth) require `Authorization: Bearer <access_token>` header.

---

## Authentication

### Register
```
POST /auth/register
Content-Type: application/json

{
  "email": "agent@example.com",
  "password": "securepass123",
  "full_name": "AI Coding Agent"
}

Response 201:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Login
```
POST /auth/login
Content-Type: application/json

{
  "email": "agent@example.com",
  "password": "securepass123"
}

Response 200: same as register
```

### Refresh Token
```
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}

Response 200: same as register
```

### Get Current User
```
GET /auth/me
Authorization: Bearer <token>

Response 200:
{
  "id": "uuid",
  "email": "agent@example.com",
  "full_name": "AI Coding Agent",
  "role": "developer",
  "avatar_url": null,
  "is_active": true,
  "created_at": "2026-03-27T00:00:00Z"
}
```

---

## Tickets (CRUD)

### Create Ticket
```
POST /projects/{project_id}/tickets
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Implement user authentication",
  "description": "Add JWT-based auth with login/register",
  "acceptance_criteria": "- Users can register\n- Users can login\n- JWT tokens are issued",
  "priority": "P1",
  "labels": ["auth", "backend"]
}

Response 201:
{
  "id": "uuid",
  "project_id": "uuid",
  "ticket_number": 1,
  "title": "Implement user authentication",
  "description": "...",
  "acceptance_criteria": "...",
  "priority": "P1",
  "column_name": "backlog",
  "assignee_id": null,
  "reporter_id": "uuid",
  "story_points": null,
  "labels": ["auth", "backend"],
  "branch_name": null,
  "pr_url": null,
  "retry_count": 0,
  "position": 0,
  "created_at": "...",
  "updated_at": "..."
}
```

### List Tickets
```
GET /projects/{project_id}/tickets?column=backlog&priority=P1&page=1&per_page=50
Authorization: Bearer <token>

Response 200:
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 50,
  "pages": 1
}
```

### Get Single Ticket
```
GET /tickets/{ticket_id}
Authorization: Bearer <token>

Response 200: ticket object
```

### Update Ticket
```
PATCH /tickets/{ticket_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Updated title",
  "description": "Updated description",
  "priority": "P0",
  "assignee_id": "uuid",
  "labels": ["urgent", "backend"],
  "story_points": 5,
  "acceptance_criteria": "Updated criteria"
}

Response 200: updated ticket object
```

### Delete Ticket
```
DELETE /tickets/{ticket_id}
Authorization: Bearer <token>

Response 204: No Content
```

---

## Kanban Board - Moving Tickets Through Pipeline

### Pipeline Columns (in order)
1. `backlog` - New tickets
2. `ai_planning` - AI generates implementation plan
3. `plan_review` - Human reviews AI plan (HUMAN GATE)
4. `ai_coding` - AI writes code
5. `code_review` - Human reviews code (HUMAN GATE)
6. `staging` - Deploy to staging
7. `staging_verification` - Verify staging works
8. `production` - Deploy to production

### Move Ticket to Next Column
```
POST /tickets/{ticket_id}/move
Authorization: Bearer <token>
Content-Type: application/json

{
  "to_column": "ai_coding",
  "comment": "Plan approved, proceeding to coding"
}

Response 200: updated ticket object with new column_name
```

### Get Full Board
```
GET /projects/{project_id}/board
Authorization: Bearer <token>

Response 200:
{
  "columns": {
    "backlog": [ticket1, ticket2],
    "ai_planning": [ticket3],
    "plan_review": [],
    "ai_coding": [ticket4],
    "code_review": [],
    "staging": [],
    "staging_verification": [],
    "production": [ticket5]
  },
  "project_id": "uuid"
}
```

### Reorder Ticket Within Column
```
PATCH /tickets/{ticket_id}/position
Authorization: Bearer <token>
Content-Type: application/json

{
  "position": 0
}

Response 200: updated ticket object
```

---

## Agent Workflow: Complete Pipeline Example

Here is the full flow a coding agent should follow:

### Step 1: Authenticate
```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"agent@example.com","password":"pass123"}' \
  | jq -r '.access_token')
```

### Step 2: Pick a ticket from backlog
```bash
curl -s http://localhost:8001/api/v1/projects/{project_id}/tickets?column=backlog \
  -H "Authorization: Bearer $TOKEN" | jq '.items[0]'
```

### Step 3: Move ticket to ai_planning
```bash
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "ai_planning", "comment": "Starting AI planning phase"}'
```

### Step 4: Create a plan
```bash
# Plans are created via the plan service internally
# After planning, move to plan_review for human approval
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "plan_review", "comment": "Plan ready for review"}'
```

### Step 5: After human approves plan, move to ai_coding
```bash
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "ai_coding", "comment": "Plan approved, starting code generation"}'
```

### Step 6: After coding complete, move to code_review
```bash
# Update ticket with branch/PR info
curl -s -X PATCH http://localhost:8001/api/v1/tickets/{ticket_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"branch_name": "feat/ticket-123", "pr_url": "https://github.com/org/repo/pull/42"}'

# Move to code review
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "code_review", "comment": "Code ready for human review"}'
```

### Step 7: After code review approval, deploy to staging
```bash
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "staging", "comment": "Code approved, deploying to staging"}'

# Trigger staging deployment
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/deploy/staging \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"branch": "feat/ticket-123"}'
```

### Step 8: Verify staging and move to production
```bash
# Move to staging_verification
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "staging_verification", "comment": "Staging deployed, running verification"}'

# After verification, move to production (PM_LEAD only)
curl -s -X POST http://localhost:8001/api/v1/tickets/{ticket_id}/move \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_column": "production", "comment": "Verification passed, deploying to production"}'
```

---

## Reviews (Three-Layer Architecture)

The review system uses a three-layer AI-on-AI architecture:
- **Layer 1**: Specialist agents (code quality + security) run in parallel
- **Layer 2**: Meta-review agent consolidates, filters false positives, validates severity
- **Layer 3**: Human reviewer makes final decision via the Kanban UI

### List Reviews
```
GET /tickets/{ticket_id}/reviews
Authorization: Bearer <token>

Response 200: array of review objects
```

### Submit Human Review
```
POST /tickets/{ticket_id}/reviews
Authorization: Bearer <token>
Content-Type: application/json

{
  "decision": "approved|rejected|changes_requested",
  "body": "Review comments...",
  "inline_comments": [
    {"file": "main.py", "line": 42, "comment": "Fix null check", "severity": "warning"}
  ]
}

Response 201: review object
```

### Trigger AI Review (Three-Layer)
```
POST /tickets/{ticket_id}/reviews/ai-trigger
Authorization: Bearer <token>

Response 201:
{
  "review_id": "uuid",
  "summary": "Layer 1 + Layer 2 consolidated summary",
  "comment_count": 5,
  "total_cost_usd": 0.03,
  "agent_reviews": [
    {"agent_name": "claude", "model_id": "...", "summary": "...", "comment_count": 3}
  ],
  "meta_review": {
    "verdict": "approve|request_changes|needs_discussion",
    "confidence": 0.85,
    "consolidated_comments": [...],
    "filtered_count": 2,
    "missed_issues": ["Missing error handling in..."],
    "cost_usd": 0.01
  }
}
```

---

## Comments

### Add Comment to Ticket
```
POST /tickets/{ticket_id}/comments
Authorization: Bearer <token>
Content-Type: application/json

{
  "body": "Implementation complete. All tests pass.",
  "parent_id": null
}

Response 201:
{
  "id": "uuid",
  "ticket_id": "uuid",
  "author_id": "uuid",
  "author_type": "user",
  "body": "Implementation complete. All tests pass.",
  "parent_id": null,
  "created_at": "...",
  "updated_at": "..."
}
```

### List Comments
```
GET /tickets/{ticket_id}/comments
Authorization: Bearer <token>

Response 200: array of comment objects
```

---

## Attachments

### Upload File
```
POST /tickets/{ticket_id}/attachments
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <binary data, max 10MB>

Response 201:
{
  "id": "uuid",
  "ticket_id": "uuid",
  "uploader_id": "uuid",
  "filename": "screenshot.png",
  "content_type": "image/png",
  "file_size": 142857,
  "created_at": "..."
}
```

### List Attachments
```
GET /tickets/{ticket_id}/attachments
Authorization: Bearer <token>

Response 200:
{
  "items": [...],
  "total": 3
}
```

### Download File
```
GET /attachments/{attachment_id}/download
Authorization: Bearer <token>

Response 200: file binary stream
```

### Delete Attachment
```
DELETE /attachments/{attachment_id}
Authorization: Bearer <token>

Response 204: No Content
```

---

## AI Plans

### List Plans for Ticket
```
GET /tickets/{ticket_id}/plans
Authorization: Bearer <token>

Response 200: array of plan objects
```

### Approve Plan
```
POST /tickets/{ticket_id}/plans/{plan_id}/approve
Authorization: Bearer <token>

Response 200: plan object with status="approved"
```

### Reject Plan
```
POST /tickets/{ticket_id}/plans/{plan_id}/reject
Authorization: Bearer <token>
Content-Type: application/json

{
  "comment": "Need more detail on error handling approach"
}

Response 200: plan object with status="rejected"
```

---

## Deployments

### Deploy to Staging
```
POST /tickets/{ticket_id}/deploy/staging
Authorization: Bearer <token>
Content-Type: application/json

{
  "branch": "feat/ticket-123",
  "commit_sha": "abc123"
}

Response 201: deployment object
```

### Deploy to Production (PM_LEAD only)
```
POST /tickets/{ticket_id}/deploy/production
Authorization: Bearer <token>
Content-Type: application/json

{
  "commit_sha": "abc123",
  "canary_pct": 10
}

Response 201: deployment object
```

### Rollback
```
POST /deployments/{deployment_id}/rollback
Authorization: Bearer <token>
Content-Type: application/json

{
  "reason": "Error rate exceeded 5%"
}

Response 200: deployment object
```

---

## Projects

### Create Project
```
POST /projects
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My Project",
  "description": "Project description",
  "repo_url": "https://github.com/org/repo"
}

Response 201: project object
```

### List Projects
```
GET /projects?page=1&per_page=20
Authorization: Bearer <token>

Response 200: paginated project list
```

---

## RBAC (Role-Based Access Control)

| Role | Permissions |
|------|-------------|
| `owner` | Full access to everything |
| `pm_lead` | Full access + production deploys |
| `developer` | CRUD tickets, comments, staging deploys |
| `ai_agent` | Move tickets, add comments, create plans |

### Human Gate Columns
- `plan_review` - Only `owner` or `pm_lead` can approve/move forward
- `code_review` - Only `owner` or `pm_lead` can approve/move forward

---

## Quality & AI Metrics

### AI Quality Metrics
```
GET /dashboard/ai-quality-metrics?project_id={uuid}&days=30
Authorization: Bearer <token>

Response 200:
{
  "agent_acceptance_rates": {"multi-agent-3layer": {"total_reviews": 5, "approved": 3, "approval_rate": 60.0}},
  "ai_regression_rate": {"total_test_runs": 20, "failed_runs": 2, "regression_rate": 10.0},
  "ai_defect_density": {"defects_found": 3, "tickets_reviewed": 10, "defect_density": 0.3},
  "merge_confidence": {"approved_on_first_review": 7, "total_first_reviews": 10, "confidence_pct": 70.0},
  "ai_vs_human_stats": {"ai_agent": {"total_reviews": 15, "approved": 10, "approval_rate": 66.7}},
  "agent_performance": {"claude": {"total_calls": 50, "avg_latency_ms": 2500, "total_cost_usd": 1.25, "success_rate": 98.0}},
  "date_range_days": 30
}
```

### Review Feedback Metrics
```
GET /dashboard/review-feedback?project_id={uuid}&days=30
Authorization: Bearer <token>

Response 200:
{
  "ai_human_agreement_rate": 75.0,
  "total_comparisons": 8,
  "agreements": 6,
  "in_memory_feedback": {"total": 20, "accepted": 14, "rejected": 4, "acceptance_rate": 70.0},
  "top_rejection_reasons": {"false positive": 3, "not actionable": 1}
}
```

### Submit Finding Feedback
```
POST /reviews/{review_id}/feedback
Authorization: Bearer <token>
Content-Type: application/json

{
  "finding_index": 0,
  "action": "accepted",
  "reason": "good catch"
}

Response 201:
{
  "review_id": "uuid",
  "finding_index": 0,
  "action": "accepted",
  "reason": "good catch"
}
```

---

## Error Responses

All errors follow this format:
```json
{
  "detail": "Error description message"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request / validation error |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate email) |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |
