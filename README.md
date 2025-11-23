# Multi-Tenant SaaS Platform

A production-grade, realistic multi-tenant Software-as-a-Service (SaaS) platform built with Python, FastAPI, and PostgreSQL. This codebase demonstrates enterprise-level patterns for tenant isolation, role-based access control (RBAC), rate limiting, and API design.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Key Features](#key-features)
- [Multi-Tenancy Strategy](#multi-tenancy-strategy)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [API Endpoints](#api-endpoints)
- [Security Considerations](#security-considerations)
- [Performance & Scalability](#performance--scalability)
- [Known Limitations & Technical Debt](#known-limitations--technical-debt)
- [Development Notes](#development-notes)

---

## Architecture Overview

This platform uses a **shared database, shared schema** multi-tenancy model where:

1. **Single Database**: All tenants share the same database instance
2. **Tenant Isolation**: Every data model includes a `tenant_id` foreign key
3. **Middleware-Based Routing**: Tenant context is extracted from subdomain or headers
4. **Row-Level Security**: Application enforces tenant filtering on all queries
5. **Per-Tenant Rate Limiting**: Redis-based token bucket rate limiter

### Why This Architecture?

We evaluated three multi-tenancy approaches:

| Approach | Pros | Cons | Our Choice |
|----------|------|------|------------|
| **Separate databases per tenant** | Best isolation, easy backup | Complex management, resource waste | ❌ Too complex |
| **Shared DB, shared schema** | Efficient, manageable, scales well | Requires careful query filtering | ✅ **Chosen** |
| **Shared DB, separate schemas** | Good isolation, shared resources | Schema management overhead | ❌ Middle ground |

### Request Flow

```
1. HTTP Request
   ↓
2. CORS Middleware (security headers)
   ↓
3. TenantMiddleware (extract tenant from subdomain/header)
   ↓
4. RateLimitMiddleware (check per-tenant rate limits)
   ↓
5. Authentication (JWT validation + tenant verification)
   ↓
6. Authorization (RBAC checks)
   ↓
7. Endpoint Handler (tenant-scoped queries)
   ↓
8. Response
```

---

## Key Features

### 1. **Tenant Isolation**
- Every database model includes `tenant_id` column with indexed foreign key
- Middleware extracts tenant context on every request
- Multi-layered isolation: middleware → dependencies → query filters
- Defense-in-depth: redundant tenant checks prevent data leaks

### 2. **Authentication & Authorization**
- JWT-based authentication with token expiration
- Bcrypt password hashing (intentionally slow to prevent brute force)
- Token payload includes `tenant_id` to prevent cross-tenant token reuse
- Three-tier RBAC: Admin > Member > Viewer

### 3. **Rate Limiting**
- Redis-backed token bucket algorithm
- Per-tenant rate limits (configurable by subscription tier)
- Graceful degradation if Redis unavailable
- Burst capacity handling

### 4. **API Design**
- RESTful endpoints with proper HTTP verbs
- Pagination support (prevents large result sets)
- Soft delete pattern for projects (allows recovery)
- Comprehensive error handling with custom exceptions

### 5. **Production-Ready Patterns**
- Connection pooling (20 base connections + 40 overflow)
- Structured logging with JSON output for production
- Health check endpoints for load balancers
- Request timing middleware for monitoring

---

## Multi-Tenancy Strategy

### Tenant Identification

The platform supports three methods for tenant identification (in priority order):

1. **X-Tenant-Slug Header**: Explicit header (best for API clients)
   ```
   X-Tenant-Slug: acme-corp
   ```

2. **Subdomain Routing**: Extract from hostname (best for web UIs)
   ```
   acme.saas.com → tenant slug "acme"
   ```

3. **X-Tenant-ID Header**: Direct ID (legacy support)
   ```
   X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000
   ```

### Data Isolation Guarantees

**Database Level:**
- Foreign key constraints with `ON DELETE CASCADE`
- Indexed `tenant_id` columns for query performance
- Composite unique constraints scoped to tenant (e.g., `tenant_id + email`)

**Application Level:**
- Every query filtered by `request.state.tenant_id`
- JWT tokens include `tenant_id` and are validated on each request
- Middleware enforces tenant context before endpoints execute

**Critical Code Pattern:**
```python
# ALWAYS include tenant filter
project = db.query(Project).filter(
    Project.id == project_id,
    Project.tenant_id == tenant.id  # CRITICAL: Prevents cross-tenant access
).first()
```

### Tenant Model Schema

```python
class Tenant:
    id: UUID (PK)
    slug: str (unique, indexed)  # URL-friendly identifier
    subdomain: str (unique, indexed)  # For routing
    is_active: bool
    subscription_tier: str  # free, basic, premium, enterprise
    rate_limit_per_minute: int (nullable)  # Override defaults
    rate_limit_burst: int (nullable)
```

---

## Technology Stack

| Component | Technology | Reasoning |
|-----------|-----------|-----------|
| **Framework** | FastAPI | Modern, async, automatic docs, fast |
| **Database** | PostgreSQL | Robust, ACID, excellent for multi-tenant |
| **ORM** | SQLAlchemy 2.0 | Mature, flexible, supports complex queries |
| **Auth** | python-jose + passlib | Industry-standard JWT and bcrypt |
| **Cache/Rate Limit** | Redis | Fast, atomic operations, distributed |
| **Validation** | Pydantic v2 | Type safety, automatic validation |
| **Server** | Uvicorn | ASGI server, production-ready |

---

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, middleware, routes
│   ├── config.py                 # Settings management
│   ├── database.py               # SQLAlchemy setup, connection pooling
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── tenant.py            # Tenant (isolation boundary)
│   │   ├── user.py              # User (with RBAC roles)
│   │   ├── project.py           # Project (tenant-scoped resource)
│   │   └── resource.py          # Resource (nested tenant scope)
│   │
│   ├── schemas/                  # Pydantic models (request/response)
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── project.py
│   │   └── resource.py
│   │
│   ├── api/
│   │   ├── deps.py              # Reusable dependencies (auth, tenant)
│   │   └── endpoints/
│   │       ├── auth.py          # Login, registration
│   │       ├── users.py         # User CRUD
│   │       ├── projects.py      # Project CRUD
│   │       └── resources.py     # Resource CRUD
│   │
│   ├── middleware/
│   │   ├── tenant.py            # Tenant context extraction
│   │   └── rate_limit.py        # Per-tenant rate limiting
│   │
│   ├── core/
│   │   ├── security.py          # JWT, password hashing
│   │   ├── permissions.py       # RBAC logic
│   │   └── exceptions.py        # Custom exceptions
│   │
│   └── utils/
│       └── logging.py           # Structured logging setup
│
├── requirements.txt
├── .env.example
└── README.md
```

**Lines of Code:** ~2,800 lines across all modules

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 6+

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd multi-tenant-saas
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

   Key settings:
   ```ini
   DATABASE_URL=postgresql://user:password@localhost:5432/saas_platform
   SECRET_KEY=your-secret-key-change-in-production
   REDIS_URL=redis://localhost:6379/0
   ```

5. **Initialize database**
   ```bash
   # In development mode, tables auto-create on startup
   # In production, use Alembic migrations:
   # alembic upgrade head
   ```

6. **Run the application**
   ```bash
   python -m uvicorn app.main:app --reload
   ```

   Access API docs: http://localhost:8000/docs

### Creating Test Data

```python
# Use the registration endpoint or create directly in DB
# Example: Create a tenant and user

import requests

# Register tenant and first user
response = requests.post("http://localhost:8000/api/v1/auth/register", json={
    "email": "admin@acme.com",
    "password": "securepass123",
    "full_name": "Admin User",
    "tenant_slug": "acme-corp"
})

# Login
response = requests.post("http://localhost:8000/api/v1/auth/login", json={
    "email": "admin@acme.com",
    "password": "securepass123",
    "tenant_slug": "acme-corp"
})
token = response.json()["access_token"]

# Make authenticated request
headers = {
    "Authorization": f"Bearer {token}",
    "X-Tenant-Slug": "acme-corp"
}
response = requests.get("http://localhost:8000/api/v1/projects", headers=headers)
```

---

## API Endpoints

### Authentication

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/api/v1/auth/login` | POST | Authenticate user, get JWT | No |
| `/api/v1/auth/register` | POST | Register new user in tenant | No |

### Users

| Endpoint | Method | Description | Auth Required | Role |
|----------|--------|-------------|---------------|------|
| `/api/v1/users` | GET | List users in tenant | Yes | Any |
| `/api/v1/users/{id}` | GET | Get user details | Yes | Any |
| `/api/v1/users` | POST | Create new user | Yes | Admin |
| `/api/v1/users/{id}` | PATCH | Update user | Yes | Admin or self |
| `/api/v1/users/{id}` | DELETE | Delete user | Yes | Admin |

### Projects

| Endpoint | Method | Description | Auth Required | Role |
|----------|--------|-------------|---------------|------|
| `/api/v1/projects` | GET | List projects | Yes | Any |
| `/api/v1/projects/{id}` | GET | Get project | Yes | Any |
| `/api/v1/projects` | POST | Create project | Yes | Member+ |
| `/api/v1/projects/{id}` | PATCH | Update project | Yes | Member+ |
| `/api/v1/projects/{id}` | DELETE | Delete project | Yes | Admin or owner |
| `/api/v1/projects/{id}/restore` | POST | Restore deleted project | Yes | Admin |

### Resources

| Endpoint | Method | Description | Auth Required | Role |
|----------|--------|-------------|---------------|------|
| `/api/v1/resources` | GET | List resources | Yes | Any |
| `/api/v1/resources/{id}` | GET | Get resource | Yes | Any |
| `/api/v1/resources` | POST | Create resource | Yes | Member+ |
| `/api/v1/resources/{id}` | PATCH | Update resource | Yes | Member+ |
| `/api/v1/resources/{id}` | DELETE | Delete resource | Yes | Member+ |

### System

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/health` | GET | Health check | No |
| `/docs` | GET | Swagger UI docs | No |

---

## Security Considerations

### 1. **Tenant Isolation**

**Threat**: User from Tenant A accessing Tenant B's data

**Mitigations**:
- ✅ Middleware enforces tenant context on every request
- ✅ JWT tokens include tenant_id, validated on each request
- ✅ All database queries filter by tenant_id
- ✅ Foreign key constraints prevent orphaned data
- ✅ Composite indexes enforce tenant-scoped uniqueness

**Vulnerability Areas** (monitor closely):
- ⚠️ Raw SQL queries (avoid - use ORM)
- ⚠️ Background jobs (must explicitly pass tenant context)
- ⚠️ Admin endpoints (extra validation needed)

### 2. **Authentication**

**Password Security**:
- Bcrypt hashing with default work factor (12 rounds)
- Intentionally slow (~100ms) to prevent brute force
- No password reset implemented (would need email verification)

**Token Security**:
- JWT with 30-minute expiration
- Tokens include tenant_id to prevent cross-tenant reuse
- ⚠️ No refresh tokens implemented (should be added)
- ⚠️ No token revocation (requires Redis blacklist)

### 3. **Rate Limiting**

**Current Implementation**:
- Token bucket algorithm per tenant
- Configurable limits by subscription tier
- Graceful degradation if Redis fails

**Limitations**:
- ⚠️ Single Redis instance (should use cluster in production)
- ⚠️ No per-user rate limiting (only per-tenant)
- ⚠️ No distributed rate limiting across API servers

### 4. **Input Validation**

- ✅ Pydantic validates all request bodies
- ✅ Path parameters validated
- ✅ SQL injection prevented by ORM
- ⚠️ No CAPTCHA on registration (allows bot signups)
- ⚠️ No file upload validation (if implementing file uploads)

---

## Performance & Scalability

### Database Performance

**Connection Pooling**:
```python
pool_size=20          # Base connections
max_overflow=40       # Additional connections under load
pool_pre_ping=True    # Verify connections before use
```

**Indexes**:
- All `tenant_id` columns indexed
- Composite indexes for common query patterns
- Example: `idx_project_tenant_status` on `(tenant_id, is_deleted, status)`

**Query Optimization**:
- Pagination on all list endpoints (max 100 items/page)
- `select_related` for N+1 query prevention (can be added)
- Soft delete instead of hard delete (faster, allows recovery)

### Bottlenecks

**Identified Performance Issues**:

1. **Tenant loading on every request** (line 94 in `app/middleware/tenant.py`)
   ```python
   # This hits DB on EVERY request
   tenant = self._load_tenant(db, tenant_identifier)
   ```
   **Solution**: Cache tenants in Redis with 5-minute TTL

2. **User loading on every authenticated request** (line 52 in `app/api/deps.py`)
   ```python
   user = db.query(User).filter(...)
   ```
   **Solution**: Cache user data in Redis or use short-lived sessions

3. **View count increment** (line 95 in `app/api/endpoints/projects.py`)
   ```python
   project.view_count += 1  # DB write on every view!
   ```
   **Solution**: Buffer view counts in Redis, flush periodically

4. **Rate limiting Redis calls**
   - Every request makes 2-3 Redis calls
   **Solution**: Acceptable for now, but monitor Redis latency

### Scaling Strategies

**Horizontal Scaling**:
- ✅ Stateless API servers (can add more instances)
- ✅ Redis for shared state (rate limiting)
- ⚠️ Need session affinity if caching in-memory

**Database Scaling**:
- ✅ Read replicas can be added (need to update connection strings)
- ✅ Tenant-based sharding possible (shard by tenant_id)
- ⚠️ No connection pooling proxy (consider PgBouncer)

**Caching Strategy**:
- ⚠️ No application-level caching yet
- Consider: Redis cache for tenant data, user profiles, project lists

---

## Known Limitations & Technical Debt

### High Priority

1. **No email verification** (`app/api/endpoints/auth.py:99`)
   - Users can register without verifying email
   - Security risk: fake accounts

2. **No refresh tokens** (`app/api/endpoints/auth.py:147`)
   - Users must re-login every 30 minutes
   - Poor UX for long sessions

3. **No token revocation** (`app/core/security.py`)
   - Can't invalidate tokens before expiration
   - Security risk: compromised tokens valid until expiry

4. **Subscription tier limits not enforced** (`app/models/tenant.py:46`)
   - `subscription_tier` field exists but not used
   - Should limit: users per tenant, projects, API calls

### Medium Priority

5. **No database migrations** (`app/database.py:63`)
   - Using `create_all()` in development
   - Production needs Alembic migrations

6. **Feature flags in database** (`app/models/tenant.py:58`)
   - Boolean columns instead of proper feature flag system
   - Should use LaunchDarkly or similar

7. **Password reset not implemented** (`app/models/user.py:59`)
   - Columns exist but no endpoints
   - Would need email service integration

8. **No audit logging** (system-wide)
   - Can't track who changed what when
   - Critical for compliance (GDPR, SOC2)

### Low Priority (Nice to Have)

9. **No resource versioning** (`app/models/resource.py:67`)
   - Version number increments but no version history
   - Could implement with `resource_versions` table

10. **No background job system** (system-wide)
    - All operations synchronous
    - Would benefit from Celery for: emails, cleanup, analytics

11. **No metrics/monitoring** (system-wide)
    - Should add Prometheus metrics
    - Track: request latency, error rates, tenant activity

---

## Development Notes

### Code Patterns

**Tenant Isolation Pattern**:
```python
# Always filter by tenant_id
resource = db.query(Resource).filter(
    Resource.id == resource_id,
    Resource.tenant_id == tenant.id  # NEVER forget this!
).first()
```

**Permission Checking Pattern**:
```python
# Use dependencies for common checks
@router.post("/admin-action")
async def admin_action(
    current_user: User = Depends(require_admin)  # Enforces admin role
):
    pass
```

**Soft Delete Pattern**:
```python
# Projects use soft delete
project.soft_delete()  # Sets is_deleted=True, deleted_at=now()

# Resources use hard delete
db.delete(resource)  # Actually removes from DB
```

### Testing Considerations

**What to Test**:
1. ✅ Tenant isolation (critical!)
   - User from Tenant A cannot access Tenant B's data
   - Token from Tenant A doesn't work for Tenant B

2. ✅ RBAC enforcement
   - Viewers can't modify resources
   - Non-admins can't delete users

3. ✅ Rate limiting
   - Requests are limited per tenant
   - Burst handling works correctly

4. ✅ Authentication flow
   - Invalid credentials rejected
   - Tokens expire correctly

**Test Setup**:
```python
# Create isolated test database
# Use different tenant for each test
# Clean up data after tests
```

### Common Development Tasks

**Adding a new endpoint**:
1. Create Pydantic schemas in `app/schemas/`
2. Add route in appropriate `app/api/endpoints/` file
3. Add tenant filter to all queries: `.filter(Model.tenant_id == tenant.id)`
4. Add RBAC check: `Depends(require_admin)` or check manually
5. Update this README's API section

**Adding a new model**:
1. Create model in `app/models/` with `tenant_id` foreign key
2. Add indexes: `Index('idx_model_tenant', 'tenant_id')`
3. Add relationship to `Tenant` model
4. Create Alembic migration (production) or restart app (dev)

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Change `SECRET_KEY` to strong random value
- [ ] Set `DEBUG=False`
- [ ] Configure `allowed_origins` for CORS
- [ ] Set up database connection pooling (PgBouncer)
- [ ] Configure Redis Cluster for high availability
- [ ] Set up log aggregation (ELK, Datadog, etc.)
- [ ] Configure metrics and monitoring
- [ ] Set up alerts for:
  - Tenant isolation violations
  - High error rates
  - Rate limit violations
  - Database connection pool exhaustion
- [ ] Enable HTTPS only
- [ ] Configure trusted host middleware
- [ ] Set up automated backups
- [ ] Implement health check monitoring
- [ ] Add request ID tracking across services
- [ ] Configure proper CORS policies
- [ ] Set up CDN for static assets
- [ ] Implement proper secret management (Vault, AWS Secrets Manager)
- [ ] Add CAPTCHA to registration
- [ ] Implement email verification
- [ ] Set up audit logging
- [ ] Configure database read replicas
- [ ] Load test with expected tenant count

---

## Architecture Decisions & Tradeoffs

### Decision 1: Shared Database vs Separate Databases

**Chosen**: Shared database with row-level tenant filtering

**Reasoning**:
- **Cost**: Separate databases expensive at scale (100+ tenants)
- **Management**: Schema changes across 100 databases is operational nightmare
- **Performance**: Modern databases handle millions of rows with proper indexes
- **Backup**: Single backup process vs managing 100+ backups

**Tradeoff**: Requires vigilant tenant filtering in all queries

### Decision 2: JWT vs Session-Based Auth

**Chosen**: JWT tokens

**Reasoning**:
- **Stateless**: No server-side session storage needed
- **Scalability**: Works across multiple API servers
- **Mobile-friendly**: Easy to use in mobile apps

**Tradeoff**: Can't revoke tokens (would need Redis blacklist)

### Decision 3: Soft Delete for Projects

**Chosen**: Soft delete (set `is_deleted=True`)

**Reasoning**:
- **User expectation**: Users expect to recover deleted items
- **Audit trail**: Can see what was deleted and when
- **Data integrity**: Related resources remain intact

**Tradeoff**: Queries must always filter `is_deleted=False`

### Decision 4: Token Bucket Rate Limiting

**Chosen**: Token bucket algorithm in Redis

**Reasoning**:
- **Burst handling**: Allows short bursts of traffic
- **Smooth**: Better UX than fixed window
- **Distributed**: Works across multiple API servers

**Tradeoff**: Requires Redis (additional infrastructure)

---

## Questions for Deeper Understanding

After reading this codebase, you should be able to answer:

1. **How is tenant isolation enforced at multiple levels?**
   - Middleware, JWT validation, query filters, database constraints

2. **What happens if the Redis server goes down?**
   - Rate limiting gracefully degrades (allows all requests)
   - Could be configured to fail closed instead

3. **Why duplicate `tenant_id` in both Resource and Project models?**
   - Query performance (avoid joins)
   - Defense-in-depth (redundant isolation check)

4. **How would you prevent the last admin from deleting themselves?**
   - Count admins in tenant before delete
   - See TODO in `app/api/endpoints/users.py:217`

5. **What's the performance impact of tenant lookup on every request?**
   - Database query on every request
   - Mitigation: Cache tenants in Redis

6. **How would you implement per-user rate limiting on top of per-tenant?**
   - Add user_id to rate limit Redis key
   - Would need two buckets: tenant and user

7. **What prevents a token from Tenant A being used for Tenant B?**
   - Token includes `tenant_id` in payload
   - Validated in `get_current_user` dependency

8. **Why use composite indexes like (tenant_id, email)?**
   - Enforce uniqueness within tenant
   - Same email can exist across tenants

---

## Contact & Contributing

This is a demonstration codebase for educational purposes.

For questions about specific implementation details, refer to the inline comments in the code—they explain architectural decisions and tradeoffs at the point of implementation.

---

**Total Lines of Code**: ~2,800 lines
**Estimated Reading Time**: 30-45 minutes
**Architecture Complexity**: Production-grade with realistic tradeoffs
