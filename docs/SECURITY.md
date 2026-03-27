# Security Guide

## Authentication

### JWT Tokens
- Access tokens: 15-minute expiry (configurable via `JWT_EXPIRE_MINUTES`)
- Refresh tokens: 7-day expiry (configurable via `JWT_REFRESH_EXPIRE_DAYS`)
- Algorithm: HS256 (configurable via `JWT_ALGORITHM`)
- Password hashing: bcrypt via passlib

### GitHub OAuth
- Optional alternative login flow via `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
- OAuth callback validates state parameter to prevent CSRF

### WebSocket Authentication
- Token-based: `ws://host/ws?token=<JWT>`
- Legacy path-based: `ws://host/ws/{user_id}` (deprecated, for backward compatibility)

## Authorization (RBAC)

Four roles with hierarchical permissions:

| Operation | Owner | PM Lead | Developer | Viewer |
|-----------|-------|---------|-----------|--------|
| Create tickets | Yes | Yes | Yes | No |
| Move tickets | Yes | Yes | Yes* | No |
| Approve plans | Yes | Yes | Yes | No |
| Approve code | Yes | Yes | Yes | No |
| Deploy to production | Yes | Yes | No | No |
| Manage users | Yes | No | No | No |

*Developers cannot move tickets to the production column.

## Production Configuration

### Required Environment Variables

Before deploying to production, ensure these are set:

| Variable | Description | Risk if Missing |
|----------|-------------|-----------------|
| `JWT_SECRET` | Strong random secret for JWT signing | **CRITICAL**: Default value is insecure |
| `GITHUB_CLIENT_SECRET` | GitHub webhook signature verification | Webhooks will be rejected (503) |
| `DATABASE_URL` | PostgreSQL connection string | Falls back to SQLite (not suitable for production) |
| `ENVIRONMENT` | Must be set to `production` | Docs exposed, verbose error messages |

### Startup Validation

The application runs `check_production_secrets()` on startup and logs warnings for:
- `JWT_SECRET` still using the default `change-me-in-production` value
- Missing `GITHUB_CLIENT_SECRET` (webhooks will fail with 503)

## Security Measures

### File Upload Protection
- Maximum file size: 10 MB
- Filename sanitization: path traversal sequences (`../../`) are stripped
- Null bytes in filenames are removed
- Files stored with UUID prefix to prevent name collisions

### Webhook Verification
- GitHub webhooks require valid HMAC-SHA256 signature (`X-Hub-Signature-256`)
- **Fail-closed**: if `GITHUB_CLIENT_SECRET` is not configured, webhooks return 503
- Timing-safe comparison via `hmac.compare_digest()`

### Rate Limiting
- Redis-backed sliding window algorithm
- Default: 100 requests/minute per IP
- AI endpoints: 10 requests/minute per IP
- Fail-open on Redis unavailability (logged as warning)

### Error Handling
- **Production**: sanitized 500 responses (no stack traces, no internal details)
- **Development**: full traceback included for debugging
- Validation errors: structured 422 with field-level detail (safe in all environments)

### CORS
- Origins configurable via `CORS_ORIGINS` environment variable
- Accepts comma-separated list or JSON array
- Default: `http://localhost:3000` (development only)

### Middleware Ordering
```
Request -> CORS (origin check) -> Rate Limiter (throttle) -> Logging -> Route
```
Security middleware runs before business logic, rejecting malicious/over-limit requests early.

## Known Limitations

- JWT tokens in WebSocket URLs appear in server logs and browser history
- No CSRF token mechanism for state-changing API calls (mitigated by JWT auth)
- Rate limiter fails open when Redis is unavailable
- Frontend stores JWT in localStorage (vulnerable to XSS; consider httpOnly cookies)
