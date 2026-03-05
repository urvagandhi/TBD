---
name: universal-agent
description: Universal Full-Stack Hackathon Execution Prompt — the governing master specification for any project. Enforces modular architecture, scalable design, end-to-end implementation, strict coding standards, zero hardcoding, DSA thinking, clean responsive UI, reusable components, enterprise-grade security, and all practical unsaid engineering rules.
---

# Universal Full-Stack Hackathon Execution Prompt

> **This document is project-agnostic.** It works for any hackathon problem.
> It governs ALL agents. Every agent MUST read this FIRST before any project-specific reference.
> Last Updated: 2026-03-03

---

## System Philosophy

You are building a **production-grade, modular, scalable full-stack application**.

The system MUST follow:

- **Modular Monolith Architecture** — Domain-based modules, not flat routes/services directories
- **Rule-First Backend Validation** — Multi-layer: Zod (request) → Service (business rules) → DB (constraints)
- **Strict Separation of Concerns** — Route → Controller → Service → ORM. Zero logic in routes.
- **Zero Hardcoding** — All secrets via `.env`, all config via validated env loader, no magic numbers
- **Scalable Database Design** — 3NF minimum, BigInt PKs, indexed FKs, cursor-based pagination
- **Secure-by-Default Implementation** — JWT, bcrypt hashing, Helmet, rate limiting, strict CORS
- **Reusable Frontend Component System** — Atomic primitives → Composites → Pages. Zero duplicated UI code.
- **Deterministic State Management** — State machines enforced server-side with validated transitions
- **End-to-End Functional Integrity** — DB → ORM → Service → Controller → API → Frontend → UI

The application MUST be deployable, testable, and extensible.

---

## Stack Override Rule (READ FIRST)

> **This document specifies Node.js/TypeScript/Prisma as default stack patterns.**
> **When `PROJECT_ARCHITECTURE.md` defines a different stack, that ALWAYS takes precedence.**
>
> | Project Stack | Override Authority |
> |---------------|-------------------|
> | Python/FastAPI (Agent Paperpal) | `PROJECT_ARCHITECTURE.md` + `api-agent.md` override all Node.js/Prisma/TypeScript patterns below |
> | Node.js/Express/TypeScript | Use patterns below as-is |
>
> **For Agent Paperpal specifically**:
> - Backend = Python 3.11 + FastAPI (NOT Node.js/Express)
> - ORM = None (no database) — file I/O only
> - Validation = Pydantic v2 (NOT Zod)
> - AI = CrewAI + GPT-4o-mini (read `AI_AGENT.md` + `llm-agent.md`)
> - Type checks = `mypy` or `python -m pytest` (NOT `npx tsc --noEmit`)

---

## 1. Architecture Requirements

### Backend Architecture

- Node.js (LTS) + Express + TypeScript (strict mode) ← **DEFAULT — Python projects use FastAPI instead**
- Layered structure:

```
src/
 ├── modules/
 │     ├── <domain>/
 │     │     ├── routes.ts        → HTTP interface only
 │     │     ├── controller.ts    → Request parsing, response formatting
 │     │     ├── service.ts       → Business logic, orchestration
 │     │     ├── validator.ts     → Zod schemas for input contracts
 │     │     └── types.ts         → TypeScript interfaces & types
 ├── middleware/                   → Cross-cutting concerns
 │     ├── authenticate.ts        → JWT verify → attaches req.user
 │     ├── authorize.ts           → Role guard factory
 │     ├── validate.ts            → Zod validation middleware
 │     ├── errorHandler.ts        → Global error → HTTP code mapping
 │     └── auditLogger.ts         → Append-only audit trail
 ├── utils/                       → Pure utility functions
 ├── config/                      → Env loading, Swagger, constants
 └── app.ts                       → Express factory: middleware + routers
```

#### Hard Rules

- No business logic in routes — routes delegate to controllers/services immediately
- All business rules in service layer — never in controllers or routes
- All request validation in validator layer using Zod schemas
- Centralized error handler — every error flows through `errorHandler.ts`
- Global request logging — every HTTP request logged via Morgan or equivalent
- No raw SQL — ORM only (Prisma or equivalent)
- All DB calls async — no blocking operations
- Pagination mandatory — every list endpoint must paginate
- Use transactions for multi-entity updates — `$transaction` with row-level locks
- No inline `schema.parse()` — use `validate(schema)` middleware

---

### Database Architecture

- PostgreSQL (or equivalent RDBMS)
- Prisma ORM (or equivalent with migration support)
- Minimum 3NF normalization
- BigInt primary keys — `@db.BigInt` (Int overflows at 2.1B rows)
- `snake_case` for DB columns — `@map("snake_case")` in Prisma
- `@db.Timestamptz()` for all timestamps — timezone-aware, avoids DST bugs
- `Decimal(15,2)` for money — never Float (causes rounding errors)
- All FKs indexed — `@@index([fkColumn])` immediately after relation definition
- Unique constraints on login identifiers — email, username, phone
- `NOT NULL` discipline — optional fields require documented justification
- CHECK constraints where applicable — added via custom migration SQL
- Soft delete where business-critical — `isDeleted + deletedAt`, never hard delete historical data
- `created_at` / `updated_at` on ALL tables — no exceptions

#### Must Include

- Referential integrity rules — explicit `onDelete` action on every FK (`Restrict`, `Cascade`, `SetNull`)
- Indexing strategy justification — every index documents the query it optimises
- Constraint enforcement at DB level — CHECK constraints as last line of defence
- Migration discipline — never modify existing migrations, always create new ones
- `fn_set_updated_at()` trigger on all mutable tables — DB-level safety net

---

### Frontend Architecture

- React + TypeScript
- Vite build system
- Tailwind CSS (utility-first)
- Component-driven structure:

```
src/
 ├── components/
 │     ├── ui/             → Atomic primitives (Button, Card, Skeleton, Table, Badge)
 │     ├── common/         → Shared composites (SearchFilter, Pagination, EmptyState)
 │     ├── forms/          → Domain-specific form components
 │     ├── layout/         → DashboardLayout, AuthLayout
 │     └── feedback/       → Toast, ErrorBoundary, ProgressBar
 ├── pages/                → Route-level page components
 ├── hooks/                → Custom React hooks
 ├── context/              → React Context providers (Auth, Theme, Socket)
 ├── services/             → API service functions (typed Axios wrappers)
 ├── validators/           → Zod schemas for form validation
 ├── routes/               → Router configuration
 └── index.css             → Tailwind base + CSS design tokens
```

#### UX Rules

- Mobile-first responsive — `base:` → `sm:` → `md:` → `lg:` breakpoints
- 8px grid system — no arbitrary paddings like `px-[13px]`
- Consistent semantic color palette — all colors from defined design tokens
- WCAG AA contrast compliance — ≥ 4.5:1 body text, ≥ 3:1 large text
- Icons only — no emojis anywhere in the UI (use Lucide React exclusively)
- Skeleton loaders — no spinners as primary loading indicators
- Reusable Toast component — for global/server errors
- Reusable Modal component — for confirmations and dialogs
- Reusable FormField component — with integrated validation display
- Real-time inline validation — validate on `blur`, re-validate on `change`
- Optimistic UI where appropriate — mutate instantly, rollback on error
- No duplicated UI logic — extract repeated JSX immediately
- Single source of design tokens — all styling flows from `index.css` only

---

## 2. Functional Requirement

Implement complete end-to-end flow:

```
DB → ORM → Service → Controller → API → Frontend Service → UI → User Interaction
```

Every feature MUST:

- **Persist correctly** — data saved to DB and retrievable
- **Return structured responses** — consistent `{ success, data, message }` or `{ success, error_code, message, details }`
- **Handle errors gracefully** — structured error responses, never raw exceptions
- **Update UI predictably** — loading → data/error/empty states
- **Prevent inconsistent states** — transactions, state machine validation, concurrent access guards

---

## 3. Security (NON-NEGOTIABLE)

| Concern | Implementation |
| --- | --- |
| Authentication | JWT (HS256), short-lived access tokens (15 min), refresh tokens |
| Password hashing | `bcryptjs` with salt rounds ≥ 12 |
| Secrets management | All secrets via `.env.development` / `.env.production` — never hardcoded |
| Rate limiting | `express-rate-limit` on auth endpoints and all write endpoints |
| Security headers | Helmet middleware — CSP, HSTS, X-Frame-Options, etc. |
| Input sanitization | Zod schema validation at request boundary — reject malformed input |
| CORS | Configured with explicit allowed origins — never `origin: "*"` in production |
| Error responses | Never expose stack traces — structured error objects only |
| Password hygiene | Never return `passwordHash` in any API response |
| Mass assignment | Never pass raw `req.body` to ORM — always destructure validated fields |
| Object references | Never expose internal IDs in URLs without ownership checks |
| N+1 queries | Use ORM `include`/`select` — never loop queries in application code |
| Race conditions | Transactions + `FOR UPDATE` row locks for concurrent mutations |
| DB user privilege | Application user has `SELECT, INSERT, UPDATE, DELETE` only — no DDL |
| SQL injection | ORM only — never raw string interpolation in queries |
| XSS prevention | Sanitize all user-generated content before rendering — use `DOMPurify` or equivalent on the frontend; set `Content-Security-Policy` headers via Helmet; never use `dangerouslySetInnerHTML` without sanitization |
| Buffer overflow / payload abuse | Enforce `express.json({ limit: '1mb' })` on all JSON endpoints; validate `Content-Length` header; set `maxFieldSize` and `maxFileSize` on file uploads; Zod `.max()` on all string inputs |
| HTML injection | Strip or escape HTML tags in user inputs at the service layer — never store raw HTML from user submissions |
| ReDoS (regex DoS) | Avoid user-controllable regex patterns; use bounded `.max()` lengths in Zod before regex checks |

```typescript
// ✅ Mass assignment prevention
const { email, fullName, role } = validatedData;
await prisma.user.create({ data: { email, fullName, role, passwordHash } });

// ❌ NEVER — passes raw body to ORM
await prisma.user.create({ data: req.body });
```

---

## 4. Data Structures & Logical Thinking (CRITICAL)

Code MUST reflect intelligent algorithmic design.

| Scenario | Wrong Approach | Correct Approach | Complexity |
| --- | --- | --- | --- |
| Check if email exists | Loop through list | DB indexed query or `Set` lookup | O(1) |
| Find item by ID | Scan all items | Primary key lookup (B-Tree index) | O(log n) |
| Deduplicate tags | Nested loop | `Set` deduplication | O(n) |
| Batch-check permissions | N DB queries | Single `WHERE id IN (...)` | O(1) DB round-trip |
| Return sorted results | Sort in JS | `orderBy` in ORM | DB-native |
| Look up by key | Array.find() | `Map`/`Set` in TypeScript | O(1) |
| Filter large lists | Full table scan | Indexed column filter | O(log n) |
| Search by name/text | `LIKE '%term%'` | `pg_trgm` GIN index + `ILIKE` or `to_tsvector` full-text search | O(log n) |
| Multi-field search | Multiple `LIKE` queries | Composite GIN index with `tsvector` across fields | Single index scan |
| Autocomplete/typeahead | Query on every keystroke | Debounce (300ms) + server-side `LIMIT 10` + indexed prefix search | O(log n) + reduced API calls |

### Requirements

- Use `Map`/`Set` where lookup is O(1)
- Avoid nested loops O(n²) — justify if unavoidable
- Use indexed DB queries — never unindexed filters on large tables
- Pre-aggregate where necessary — store derived values transactionally
- Use cursor-based pagination — O(log n) via index, not O(n) skip
- Avoid memory-heavy operations — stream large datasets
- No unnecessary re-renders in React — `useMemo`/`useCallback` for expensive computations
- Memoization for expensive calculations
- Normalize before optimize — 3NF first, denormalize only with justification
- Use proper state machines for lifecycle transitions — explicit allowed transitions
- **Search MUST be fast** — use `pg_trgm` + GIN index for ILIKE searches, `to_tsvector` + GIN for full-text search; never unindexed `LIKE '%term%'`
- Debounce frontend search inputs (300ms minimum) — never fire a query on every keystroke
- Search endpoints MUST use `select` projection — return only fields needed for display, not full records
- Search results MUST be paginated — same cursor/offset rules as list endpoints

All logic MUST be deterministic and testable.

---

## 5. Coding Standards

### TypeScript

- `strict` mode enabled — no exceptions
- No `any` type — use proper interfaces and generics
- Explicit return types on all public functions
- Interface-driven contracts — define types before implementation
- Enums or union types for state modelling

### Naming Conventions

| Context | Convention | Example |
| --- | --- | --- |
| Variables/functions | `camelCase` | `createUser()`, `totalAmount` |
| Classes/Components | `PascalCase` | `UserService`, `VehicleCard` |
| DB tables (mapped) | `snake_case`, plural | `users`, `order_items` |
| DB columns (mapped) | `snake_case` | `created_at`, `user_id` |
| Prisma model fields | `camelCase` | `createdAt`, `userId` |
| React hooks | `camelCase`, `use` prefix | `useAuth`, `useSocket` |
| TypeScript types | `PascalCase` | `UserResponse`, `TripStatus` |
| Env variables | `UPPER_SNAKE_CASE` | `DATABASE_URL`, `JWT_SECRET` |
| Functions | Verb-first | `createUser`, `validateEmail` |

### Git

#### Branching Strategy
- **`main`** — Production branch. Always stable and deployable.
- **`develop`** — Development integration branch. All feature/fix branches merge here first.
- **Feature/fix branches** — Created from `develop`, merged back into `develop` via PR.
- Flow: `feature-branch` → `develop` (PR + review) → `main` (PR + review after validation)
- Branch naming: `<type>/<short-description>` (e.g., `feat/user-auth`, `fix/login-redirect`)
- Never push directly to `main` or `develop` — always use feature branches + PRs

#### Commits
- Conventional Commits — `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `security`, `wip`, `ux`
- Atomic commits — one logical change per commit
- No commented-out dead code — delete it, Git has history

### Formatting

- Prettier — consistent code formatting
- ESLint — strict config, no warnings ignored
- No unused imports or variables

---

## 6. Error Handling Standard

### Success Response

```json
{
  "success": true,
  "data": {},
  "message": "Resource created successfully"
}
```

### Paginated Response

```json
{
  "success": true,
  "data": [],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "totalCount": 150,
    "totalPages": 8,
    "hasNext": true,
    "hasPrev": false
  }
}
```

### Error Response

```json
{
  "success": false,
  "error_code": "VALIDATION_ERROR",
  "message": "Invalid request data",
  "details": [
    { "field": "email", "message": "Invalid email address" }
  ]
}
```

**Rule**: Never return raw errors. Every error MUST flow through the global `errorHandler` and return this structure.

### Common Error Codes

| Error Code | HTTP Status | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | 400/422 | Request validation failed |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password |
| `TOKEN_EXPIRED` | 401 | JWT has expired |
| `FORBIDDEN` | 403 | Authenticated but lacks permission |
| `NOT_FOUND` | 404 | Resource does not exist |
| `CONFLICT` | 409 | Duplicate resource or state conflict |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected server failure |

---

## 7. Testing Requirements

### Mandatory Test Types

| Type | Scope | Mandatory Coverage |
| --- | --- | --- |
| Unit | Business logic, validators, edge cases | 70% min / 85% target |
| Integration | API + DB interaction, auth flows, error responses | All CRUD endpoints |
| Security | JWT tampering, SQL injection, RBAC, mass assignment | Every write endpoint |
| Performance | Pagination, large datasets, response time < 200ms | All list endpoints |
| UX | Form validation, toast messages, navigation flow | All user-facing forms |
| Concurrency | Duplicate prevention, race condition handling | All state transitions |

### Hard Rules

- Minimum 70% overall coverage — 85% target
- Auth + validation logic MUST be 100% coverage
- Frontend validators MUST be 100% coverage
- No order-dependent tests — each test is fully isolated
- Never delete failing tests — fix the root cause
- Assert on `error_code` field in error responses — not just status codes
- Test both happy path AND error cases for every endpoint

---

## 8. Performance Requirements

| Metric | Target |
| --- | --- |
| API response time (baseline) | < 200ms |
| Paginated list endpoints | < 500ms with 1000+ records |
| Frontend Time to Interactive | < 3s on 3G |
| Bundle size (gzipped) | < 250KB initial load |
| Search endpoint response time | < 300ms with 10,000+ records |
| Autocomplete/typeahead latency | < 150ms perceived (debounced at 300ms) |

### Implementation

- Indexed filtering — every filter column has an index
- **Search indexing** — GIN indexes (`pg_trgm` or `to_tsvector`) on all searchable text columns; never rely on sequential `LIKE` scans
- **Search projection** — search endpoints return only display fields (`id`, `name`, matched highlight), not full records
- **Debounced search** — frontend debounces input at 300ms minimum; cancel in-flight requests on new input (`AbortController`)
- No `SELECT *` — always use ORM `select` to project specific columns
- Paginated list endpoints — max `take: 100`, default `take: 20`
- Lazy loaded frontend routes — `React.lazy` + `Suspense`
- Code splitting — vendor chunks separated from app code
- No unnecessary bundle bloat — tree-shake, no heavy unused dependencies

---

## 9. Scalability Requirements

Design MUST support 10x data growth:

| Component | Hackathon Scale | 10x Scale | Mitigation |
| --- | --- | --- | --- |
| Primary tables | ~500 rows | ~5,000 rows | BigInt PKs, cursor pagination, indexed queries |
| Concurrent connections | ~5 | ~50 | Connection pooling (PgBouncer), stateless JWT |
| Read:Write ratio | 80:20 | 90:10 | Read replicas, route reads via load balancer |
| API throughput | Single process | Clustered | PM2 cluster mode, NGINX reverse proxy |
| Frontend assets | Dev server | CDN | Vite build → CDN deployment (Vercel/Cloudflare) |
| File storage | N/A | Object storage | S3/MinIO — DB stores URLs only, never blobs |

### Architecture Decisions

- Stateless backend — no server-side sessions, JWT only
- Token-based auth — scales horizontally without shared session store
- Partition-ready large tables — audit logs, event tables designed for range partitioning
- Background jobs via cron — `node-cron` for scheduled tasks
- Event-driven extension possible — Socket.IO for real-time, webhook-ready

---

## 10. UI Consistency Requirements

### Design Token System

| Role | Token | Usage |
| --- | --- | --- |
| Primary | `indigo-600` | CTAs, active links, focus rings |
| Primary Hover | `indigo-700` | Hover state on primary elements |
| Primary Light | `indigo-50` | Selected backgrounds, badges |
| Success | `emerald-600` | Success states, confirmations |
| Error | `red-600` | Error text, destructive actions |
| Warning | `amber-600` | Warning banners, caution states |
| Headings | `slate-900` | Page titles, card headings |
| Body Text | `slate-600` | Paragraphs, labels |
| Muted Text | `slate-500` | Placeholders, captions |
| Border | `slate-200` | Cards, inputs, dividers |
| Background | `slate-50` | Page background |
| Surface | `white` | Cards, modals, inputs |

### Surface System

| Token | Usage |
| --- | --- |
| `rounded-lg` | Inputs, buttons |
| `rounded-xl` | Cards, containers |
| `shadow-sm` | Default card elevation |
| `shadow-md` | Hover elevation |

### Layout Discipline

- No ad-hoc colors — if it's not in the token table, don't use it
- Consistent shadow scale — `shadow-sm` → `shadow-md` → `shadow-lg`
- Consistent border radius — `rounded-lg` for controls, `rounded-xl` for containers
- Micro-interactions — 150ms–250ms with `cubic-bezier(0.4, 0, 0.2, 1)`
- Focus rings visible — `focus-visible:ring-2 focus-visible:ring-indigo-500`
- Accessible form labels — every input has a `<label>`
- No layout shift — skeleton loaders match content dimensions exactly
- Max width container — `max-w-6xl mx-auto` on every page
- Responsive grid system — `grid` or `flex` with 8px gap increments

---

## 11. Unsaid Practical Engineering Rules

> These are what judges silently evaluate. Violating ANY of these loses points.

| Rule | Why It Matters |
| --- | --- |
| No duplicated logic across layers | DRY principle — extract to shared utility |
| No silent failures | Every error MUST produce a visible response (toast, inline, or log) |
| No magic numbers | Use named constants: `const SALT_ROUNDS = 12`, not bare `12` |
| No `console.log` in production | Use proper logger (Morgan, Winston) — `console.log` is debug-only |
| No unused variables or imports | Linter should catch these — never commit unused code |
| No giant files | Max ~300 lines per file — split into modules |
| No inconsistent naming | One convention per codebase — enforce via linter |
| No mixed responsibilities | Single Responsibility Principle — one function, one job |
| No large controller files | Controllers delegate to services — max 10 lines per handler |
| No inline styles in React | Use Tailwind utilities — never `style={{}}` for static properties |
| No direct DB access in controllers | Controllers call services, services call ORM |
| No optimistic UI without rollback | Always capture previous state before optimistic mutation |
| No missing loading state | Every async operation shows loading → data/error/empty |
| No blocking main thread | Offload heavy computation — use `setTimeout`, `requestIdleCallback`, or Web Workers |
| No circular dependencies | Module A → B → A is a design flaw — restructure |
| No dead routes | Every route must be reachable and functional |
| No incomplete validation | Every field that enters the system MUST be validated |
| No `alert()` or `window.confirm()` | Use custom Modal/Toast components |
| No commented-out code | Delete it — Git preserves history |
| No `any` in TypeScript | Use proper types — `any` defeats the purpose of TypeScript |
| No hardcoded URLs or ports | Use env variables: `process.env.PORT`, `VITE_API_BASE_URL` |

---

## 12. Implementation Execution Order

For any new project, follow this sequence:

```
 1. Define Entities          → Identify all domain objects and their attributes
 2. Define Relationships     → Map cardinality (1:1, 1:N, M:N) and FK actions
 3. Define Roles             → RBAC role list with permission matrix
 4. Define State Machines    → Lifecycle transitions with allowed paths and side effects
 5. Define Business Rules    → Constraints, calculations, invariants
 6. Define Calculations      → Derived values, aggregations, formulas
 7. Generate DB Schema       → Prisma schema + CHECK constraints + indexes + triggers
 8. Generate Backend Modules → Routes → Controllers → Services → Validators per domain
 9. Generate API Endpoints   → RESTful design, proper HTTP verbs, structured responses
10. Generate Frontend Pages  → Route-level components composing atomic primitives
11. Implement Validation     → Multi-layer: Zod (request) → Service (business) → DB (constraints)
12. Implement Security       → JWT + bcrypt + rate limiting + CORS + Helmet
13. Implement Tests          → Unit + Integration + Security + Performance + UX
14. Implement Documentation  → README + API docs + Architecture docs + JSDoc
15. Provide Deployment       → Docker Compose + env config + build commands
```

Everything MUST follow this master specification at every step.

---

## 13. Final Directive

Build like this is:

| Perspective | Standard |
| --- | --- |
| **Production SaaS** | Code quality that ships to paying customers |
| **Senior engineer audit** | Every line survives a code review |
| **Security audit** | OWASP Top 10 addressed, no exposed secrets |
| **10x scale** | Architecture handles growth without rewrite |
| **Live demo under pressure** | App MUST NOT CRASH — every edge case handled |
| **Code quality review** | Clean, consistent, documented, tested |

**No shortcuts. No hacks. No temporary fixes.**

Everything MUST be extensible, modular, secure, and logically sound.

---

## Quick Reference — Agent Hierarchy (Agent Paperpal)

```
UNIVERSAL_AGENT.md                   ← YOU ARE HERE (read FIRST)
  ├── PROJECT_ARCHITECTURE.md        ← Agent Paperpal domain context (read SECOND)
  │     Python/FastAPI + CrewAI + GPT-4o-mini + React dark-theme UI
  │
  ├── Full-Stack Agents
  │   ├── api-agent.md               ← FastAPI/Python backend specialist
  │   ├── ui-ux-agent.md             ← Dark-theme React + TailwindCSS specialist
  │   ├── test-agent.md              ← Testing & QA specialist
  │   └── docs-agent.md              ← Documentation specialist
  │
  └── AI Agents
      ├── AI_AGENT.md                ← CrewAI agentic governance (read FIRST for any AI task)
      └── llm-agent.md               ← GPT-4o-mini prompt engineering + CrewAI patterns
```

Every agent MUST comply with this universal specification.
Project-specific architecture files add domain detail — they NEVER override the universal rules.
Where universal rules assume Node.js/TypeScript, `PROJECT_ARCHITECTURE.md` and `api-agent.md`
are the override authority for stack-specific Python/FastAPI patterns.
