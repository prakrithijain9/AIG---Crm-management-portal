# AIG CRM – Backend & Integration Notes

> [!WARNING]
> **Authentication is not implemented.** All API endpoints are unauthenticated. Run the backend on
> localhost only; it is not ready for public deployment.

## How the pieces connect

```
Next.js frontend (:3000) ──HTTP──▶ FastAPI app (Uvicorn, :8000)
                                     │  settings from backend/.env (pydantic-settings)
                                     ▼
                                   SQLAlchemy engine ──psycopg──▶ PostgreSQL 18 (:5432) / aig_crm_dev
                                     ▲
                    Alembic migrations (same settings, same metadata)
```

- **FastAPI** defines the HTTP endpoints. **Uvicorn** is the server process that runs it.
- **pydantic-settings** reads `DB_*` values from environment variables or `backend/.env`.
- **SQLAlchemy** builds the connection pool and sessions; **psycopg** (v3) is the driver that talks to PostgreSQL.
- **Alembic** versions schema changes as migration files (like Git for the database schema).
- **pytest + HTTPX** (via FastAPI's `TestClient`) call the endpoints in-process for tests.

## Requirements

- Python 3.13, PostgreSQL 18 on `localhost:5432`, Node.js (for the Next.js frontend)
- On Windows, `psql` may not be on PATH; use the full path, e.g. `"C:\Program Files\PostgreSQL\18\bin\psql.exe"`

Tested with: fastapi 0.143.0 · uvicorn 0.54.0 · SQLAlchemy 2.1.4 · psycopg 3.3.6 (binary) · alembic 1.20.0 ·
pydantic 2.14.1 · pydantic-settings 2.15.0 · pytest 9.1.1 · httpx 0.28.1 · email-validator 2.3.0
(`pydantic[email]`, used by `EmailStr`). `requirements.txt` pins these exact versions, plus `starlette`,
`argon2-cffi` and `certifi` (see [Deployment](#deployment-render--neon--vercel)). `backend/.python-version` is `3.13.5`.

## Project layout

```
backend/
  requirements.txt          dependencies (exact, tested versions)
  .python-version           Python version for local tools and hosting (3.13.5)
  .env.example              safe template (copy to .env)
  pytest.ini
  alembic.ini               Alembic config (no DB URL in it)
  alembic/env.py            reads DB URL from app settings + Base.metadata; accepts a test connection
  alembic/versions/09d6732c3643_create_crm_tables.py   first migration
  alembic/versions/5b4a0b13a9f1_create_admin_users_table.py   admin_users table
  app/main.py               FastAPI app, CORS; CRM routers mounted behind require_admin
  app/core/config.py        Settings (DB_* incl. DB_SSLMODE, JWT_*, COOKIE_SECURE, TRUSTED_ORIGINS) + startup checks
  app/core/security.py      Argon2id hashing, session JWT create/verify, CSRF token comparison
  app/core/admins.py        create_admin() and reset_admin_password(): validation, verified hash, safe errors
  app/api/auth.py           /api/auth/login, /logout, /me; require_admin guard (session + CSRF/origin)
  app/schemas/auth.py       login request and session response
  app/models/admin_user.py  AdminUser model, username and hash-format rules, safe constraint messages
  app/db/session.py         SQLAlchemy engine (hide_parameters), SessionLocal, get_db dependency
  app/db/errors.py          describe DB errors without row values (no hashes in logs)
  app/db/base.py            Base (constraint naming convention), UUID/timestamp mixins, str_enum helper
  app/models/               enums.py, company.py, contact.py, deal.py, activity.py
  app/schemas/              Pydantic request/response models (common.py + one per entity)
  app/api/health.py         GET /health and GET /health/db
  app/api/common.py         DB session dep, pagination, search, 404/422 helpers, IntegrityError -> 409/422
  app/api/companies.py, contacts.py, deals.py, activities.py   CRUD routers (mounted under /api)
  app/seed/demo_data.json   demo data exported from lib/mock-data.ts (8 companies, 10 contacts, 8 deals, 8 activities)
  app/seed/demo.py          insert-only, idempotent seed logic + target/connection guards
  scripts/create_dev_db.py  create role + dev DB + test DB if missing (never drops)
  scripts/seed_demo_data.py CLI: dry run by default, --apply to insert into aig_crm_dev
  scripts/create_admin.py   CLI: create the first admin (interactive prompts, confirmation)
  scripts/reset_admin_password.py   CLI: reset one admin's password and sign out its sessions (recovery)
  tests/conftest.py         test DB engine (runs migrations), rolled-back connection, db, client (signed in), anon_client
  tests/test_auth.py        login, sessions, CSRF, logout, revocation, every CRM route needs a session
  tests/test_security.py, test_config.py, test_admin_user_rules.py   DB-free: hashing/JWT, settings, username/hash rules
  tests/test_admins.py      admin creation
  tests/test_reset_admin_password.py   password reset: script (fake terminal) and core logic
  tests/api_helpers.py      camelCase payload builders for API tests
  tests/test_health.py
  tests/test_migrations.py  single head, downgrade/upgrade round trip, models == schema
  tests/test_models.py      relationships, cascades, constraints
  tests/test_api_*.py       companies, contacts, deals, activities, common (pagination/errors/CORS)
  tests/test_seed.py        seed logic (on the rolled-back test DB) and seed safety guards
```

Frontend files involved in the API integration:

```
lib/api.ts                       typed fetch client for /api/*, ApiError, listAll paging, auth (login/me/logout), in-memory CSRF token
lib/api.test.ts                  API client unit tests (Node's built-in test runner)
lib/auth.ts, lib/auth.test.ts    session cookie name, safe ?next= redirects, login URL builder
proxy.ts                         redirects page requests without a session cookie to /login
components/auth/session-provider.tsx   session state (/auth/me), expiry, signIn/signOut
components/auth/login-form.tsx, app/login/page.tsx   login page
app/(crm)/layout.tsx             CRM pages require a session (AppShell)
components/crm/crm-provider.tsx  loads from / writes to the API
components/crm/data-gate.tsx     loading spinner / error card with "Try again"; page stays rendered underneath
components/crm/use-dialog-form.ts dialog form state, saving flag, server + client errors, reset on open
components/crm/entity-dialog.tsx, confirm-dialog.tsx   saving state, error banner, stay open on failure
components/crm/form-fields.tsx   fields with per-field errors; select fields show option labels
components/crm/{company,contact,deal,activity}-dialog.tsx   use useDialogForm; show field errors
app/(crm)/{companies,contacts,deals,activities}/page.tsx   await saves/deletes; close dialog only on success
components/layout/app-shell.tsx  session gate + redirect to /login; wraps pages in DataGate
components/layout/sidebar.tsx    navigation, signed-in username, Sign out
next.config.ts                   rewrites /api/:path* -> FastAPI (CRM_API_URL, default http://127.0.0.1:8000)
```

`lib/mock-data.ts` is kept as the source of the demo data but is no longer imported by the app.

`.gitignore` excludes `.env*` (except `.env.example`), `backend/.venv/`, `__pycache__/`, `*.py[cod]` and `.pytest_cache/`, so `backend/.env` is never committed.

## Setup

All commands from `backend/` in PowerShell.

```powershell
py -3.13 -m venv .venv                       # once
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env                  # then edit .env: DB_PASSWORD and JWT_SECRET_KEY (below)
.venv\Scripts\python scripts\create_dev_db.py   # prompts for the PostgreSQL superuser password
.venv\Scripts\alembic upgrade head           # create the CRM and admin_users tables in aig_crm_dev
.venv\Scripts\python scripts\create_admin.py    # create the first admin (prompts; see Authentication)
```

Generate the JWT signing secret and paste it into `backend/.env` as `JWT_SECRET_KEY=...`
(never commit it, and use a different value per environment):

```powershell
.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(64))"
```

`scripts/create_dev_db.py` creates the role `aig_crm` (LOGIN, not superuser) owning `aig_crm_dev`, plus
`aig_crm_test` for the test suite. It only creates what is missing and never drops anything.

## Run

Always start Uvicorn **from `backend/`** (so `app.main` can be imported and `.env` is found):

```powershell
cd backend                                  # from the repository root
.venv\Scripts\python -m uvicorn app.main:app --reload    # http://127.0.0.1:8000
# http://127.0.0.1:8000/health      -> API alive
# http://127.0.0.1:8000/health/db   -> real query against PostgreSQL
# http://127.0.0.1:8000/docs        -> interactive API docs (development/test only; off in production)
.venv\Scripts\python -m pytest -v                         # tests
.venv\Scripts\alembic current                             # migration state
.venv\Scripts\alembic upgrade head --sql                  # preview SQL without running it
.venv\Scripts\alembic revision --autogenerate -m "..."    # after changing models; ALWAYS review the file
.venv\Scripts\python scripts\seed_demo_data.py            # demo data: dry run (read-only)
.venv\Scripts\python scripts\seed_demo_data.py --apply    # demo data: insert missing records into aig_crm_dev
```

Frontend (from the repository root, with FastAPI running on port 8000):

```powershell
npm install
npm run dev              # http://localhost:3000 -> /login ; /api/* is proxied to FastAPI
npm run test:frontend    # API client and sign-in helper unit tests
npm run lint
npm run build
# Different backend address: set CRM_API_URL (server-side only) before dev/build, e.g.
# $env:CRM_API_URL = "http://127.0.0.1:8001"; npm run dev
```

## Testing

### Current results

| Check | Result |
|---|---|
| Backend `pytest` | 504 passed |
| `npm run test:frontend` | 26 passed |
| `tsc --noEmit` | passes |
| `npm run lint` | 0 problems |
| `npm run build` | succeeds |

Known warning: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2`.
It does not affect results; revisit when upgrading test dependencies.

### Test database isolation

- Tests that touch tables use a **separate database** `aig_crm_test` (`TEST_DB_NAME`). They never use `aig_crm_dev`.
- `conftest.py` refuses to run unless the test DB name differs from `DB_NAME` and ends in `_test`.
- At session start it rebuilds the test schema by running the real migrations (downgrade base -> upgrade head).
- Each test runs in a transaction that is rolled back afterwards, so tests leave no data.
- `aig_crm` cannot create databases, so `aig_crm_test` is created by `scripts/create_dev_db.py`.
- `test_health.py` checks `/health/db` through the test-database client and asserts the answer came from `aig_crm_test`.
- Auth tests use a test-only JWT secret and admin, never the values in `backend/.env`.

### API test setup

- **Shared rolled-back transaction:** `client` overrides `get_db` so every request gets a **new** session on the test connection. Each `commit()` only releases a SAVEPOINT, and the outer transaction is rolled back after the test.
- **Fresh session per request:** a shared session would cache rows that the DB had already cascade-deleted.
- **Guard:** the `api_app` fixture asserts `current_database()` is the test DB before any request.
- **Signed in by default:** `client` carries a real session for a test admin (cookie + `X-CSRF-Token`), so
  CRUD tests go through the real auth and CSRF checks. `anon_client` has no session.
- **Timestamps:** `now()` is the transaction start time, so rows created inside one test share a `created_at`. The newest-first test sets distinct times explicitly. In production each request is its own transaction.

### What the tests cover

- **Migrations:** single head, downgrade/upgrade round trip, models match the migrated schema (no drift).
- **Models:** full object graph and defaults, optional activity contact, company delete cascades, contact delete
  sets `activities.contact_id` to NULL, and constraint checks that assert the exact constraint name
  (name/email uniqueness, not-blank, email `@`, status/stage/type values, value >= 0, foreign keys, NOT NULL).
- **API:** CRUD for all four resources, pagination, search (including wildcard escaping), error mapping and CORS.
- **Seed:** full insert with correct relationships, idempotent second run, user-edited records left unchanged,
  dry run writes nothing, guards refuse test DB names and a mismatched connected DB.
- **Authentication:** login (cookie attributes, identical failures, inactive admin, cross-site rejection,
  missing secret, hash upgrade), `/me`, expired/tampered/foreign tokens, revocation via `token_version`, CSRF
  on every write, logout, a 401 for every CRM route without a session, public health checks, no
  registration endpoint, password hashing and token validation, admin creation, admin table constraints,
  and password reset (success, session sign-out, policy, unknown/inactive admin, mismatch, cancel,
  rollback on database errors, nothing sensitive in output or logs, refuses the test database).
- **Database TLS settings:** no SSL parameters locally by default, `verify-full` with the certifi bundle in
  production, weaker or unknown modes refused, custom/`system` CA, parameters accepted by libpq, and the
  bundle containing Neon's root CA.
- **Frontend API client:** request building, error mapping (including non-JSON server errors and network failures), paging,
  login, session loading, CSRF header on writes only, expired-session handling, logout; safe `?next=` redirects.
- **Frontend config:** the security headers in `next.config.ts` and the same-origin `/api` rewrite.

The tests were checked against deliberately broken code: disabling the activity same-company check failed
3 tests, and disabling LIKE wildcard escaping failed 1 test.

## CRM data model

Derived from the frontend's `lib/types.ts` and the delete rules in `components/crm/crm-provider.tsx`.

```
companies 1───* contacts        (contacts.company_id   -> companies.id, ON DELETE CASCADE)
companies 1───* deals           (deals.company_id      -> companies.id, ON DELETE CASCADE)
companies 1───* activities      (activities.company_id -> companies.id, ON DELETE CASCADE)
contacts  1───* activities      (activities.contact_id -> contacts.id,  ON DELETE SET NULL, optional)
```

All tables: `id` UUID primary key (`gen_random_uuid()`), `created_at` / `updated_at` (timestamptz, default `now()`).

| Table | Columns (all NOT NULL unless noted) | Constraints / indexes |
|---|---|---|
| companies | name, industry, email, phone, location, status (default Prospect) | name not blank; email contains `@`; status in Active/Prospect/Inactive; unique `lower(name)` |
| contacts | name, company_id, email, phone, job_title | name not blank; email contains `@`; unique `lower(email)`; index company_id |
| deals | title, company_id, value NUMERIC(14,2), stage (default Lead), expected_close_date DATE | title not blank; value >= 0; stage in Lead…Lost; index company_id, stage |
| activities | type, subject, company_id, contact_id (nullable), due_date DATE, status (default Pending) | subject not blank; type in Call/Meeting/Email/Task/Follow-up; status in Pending/Completed; index company_id, contact_id, due_date |

Design choices:
- Allowed values are stored as `VARCHAR(20)` + CHECK, not native PostgreSQL enums. Adding a value later is a simple constraint change.
- Money is `NUMERIC(14,2)` (exact), not float.
- Constraint names follow a naming convention (`ck_<table>_<name>`, `fk_<table>_<col>_<ref>`, `ix_…`), so future migrations can refer to them.
- ORM relationships use `passive_deletes=True`, so PostgreSQL performs the cascades and SET NULLs itself.
- The frontend uses camelCase (`companyId`, `jobTitle`); the DB uses snake_case. The API schemas map between them.

Migration `09d6732c3643_create_crm_tables` was generated with `alembic revision --autogenerate` and then
hand-edited: autogenerate emitted each enum CHECK constraint twice and left `create_constraint` on the column
type, so each enum column was changed to `VARCHAR(20)` with one named CHECK. The SQL was reviewed with
`alembic upgrade head --sql`. The upgrade only creates objects; it drops nothing.

## CRUD API

Interactive docs: http://127.0.0.1:8000/docs (start Uvicorn from `backend/`).

### Endpoints

| Method | Path | Success | Notes |
|---|---|---|---|
| GET | `/api/companies` | 200 list | `search`, `status`, `limit`, `offset`; newest first |
| POST | `/api/companies` | 201 | 409 duplicate name (case-insensitive) |
| GET | `/api/companies/{id}` | 200 | 404 if missing |
| PATCH | `/api/companies/{id}` | 200 | partial update; 409 duplicate name |
| DELETE | `/api/companies/{id}` | 204 | also deletes its contacts, deals, activities |
| GET | `/api/contacts` | 200 list | `search` (incl. company name), `companyId`, `limit`, `offset` |
| POST | `/api/contacts` | 201 | 422 unknown companyId; 409 duplicate email |
| GET / PATCH / DELETE | `/api/contacts/{id}` | 200 / 200 / 204 | PATCH `companyId` -> 409 if the contact has activities; DELETE sets those activities' `contactId` to null |
| GET | `/api/deals` | 200 list | `search` (title, stage, company name), `stage`, `companyId` |
| POST | `/api/deals` | 201 | 422 unknown companyId |
| GET / PATCH / DELETE | `/api/deals/{id}` | 200 / 200 / 204 | deleting a deal affects no other table |
| GET | `/api/activities` | 200 list | `search` (subject, type, company, contact), `status`, `type`, `companyId`, `contactId`; soonest due first |
| POST | `/api/activities` | 201 | 422 if contact missing or belongs to another company |
| GET / PATCH / DELETE | `/api/activities/{id}` | 200 / 200 / 204 | PATCH re-checks the final company/contact pair; `"contactId": null` unlinks |

Every endpoint above requires a signed-in admin (401 otherwise), and POST/PATCH/DELETE also need the
CSRF token (403 otherwise); see Authentication.

Lists return a plain JSON array (as the frontend's state expects). The total before paging is in the
`X-Total-Count` header, which CORS exposes to the browser. `limit` defaults to 100 and is capped at 500.

### Request / response examples

```http
POST /api/companies
{"name": "Northwind Logistics", "industry": "Transportation", "email": "partnerships@northwind.example",
 "phone": "+1 (415) 555-0142", "location": "San Francisco, CA", "status": "Active"}

201 Created
{"id": "6f1c…", "createdAt": "2026-01-15T09:30:00Z", "updatedAt": "2026-01-15T09:30:00Z",
 "name": "Northwind Logistics", "industry": "Transportation", "email": "partnerships@northwind.example",
 "phone": "+1 (415) 555-0142", "location": "San Francisco, CA", "status": "Active"}
```

```http
POST /api/deals
{"title": "Fleet expansion", "companyId": "6f1c…", "value": 186000, "stage": "Proposal", "expectedCloseDate": "2026-10-22"}
-> 201 {"id": "…", "title": "Fleet expansion", "companyId": "6f1c…", "value": 186000.0, "stage": "Proposal", "expectedCloseDate": "2026-10-22", …}

PATCH /api/activities/{id}
{"status": "Completed", "contactId": null}
-> 200 {… "status": "Completed", "contactId": null …}
```

### Errors

| Status | When | Body |
|---|---|---|
| 404 | id in the URL doesn't exist | `{"detail": "Company not found"}` |
| 409 | duplicate company name / contact email; moving a contact that has activities | `{"detail": "A company with this name already exists."}` |
| 422 | invalid/missing/unknown fields, bad enum/date/number, null for a required field, malformed UUID, bad `limit`/`offset`, referenced company/contact missing, contact from another company | `{"detail": [{"loc": ["body", "contactId"], "msg": "Contact belongs to a different company than the activity.", "type": "value_error"}]}` |

The app's own 422s use the same list shape as FastAPI's built-in validation errors, so the frontend can handle both one way.

### Key decisions

- **camelCase at the edge, snake_case inside:** Schemas declare snake_case fields with a camelCase alias generator.
  - Request bodies accept camelCase only and reject unknown keys (`extra="forbid"`), so typos fail loudly.
  - Responses are always camelCase.
- **PATCH for updates:** Only fields actually sent are changed (`exclude_unset`). An explicit `null` is rejected except for `contactId`.
- **Money:** `Decimal` in Python and the DB (max 2 decimal places, >= 0), sent as a JSON number because the frontend type is `number`.
- **Two layers of validation:**
  - Pydantic and explicit lookups give friendly 422s.
  - DB constraints are the final guarantee. `commit()` turns `IntegrityError` into 409/422 by SQLSTATE and constraint name, logs only the constraint name, and rolls back.
  - Uniqueness is checked only by the DB, which avoids a check-then-insert race.
- **Activity's contact must belong to its company:**
  - Checked on create and on any PATCH that touches `companyId` or `contactId`, using the combined final values.
  - The contact row is read `FOR SHARE`. A contact PATCH locks its row `FOR UPDATE` and refuses to change company if activities reference it. Together these stop a concurrent request from slipping a mismatch in.
- **Transactions:** one session per request (`get_db`); each write ends in a single commit. On error nothing is half-saved.
- **Search:** case-insensitive `ILIKE` across the same fields the frontend searches. `%` and `_` are escaped so they match literally.
- **Secrets:** the DB password is a `SecretStr` (masked as `***` in reprs and SQLAlchemy URLs); `/health/db` errors expose only the exception type.

## Demo data seed

`scripts/seed_demo_data.py` loads the frontend's demo data (34 fictional records) into **aig_crm_dev only**.
Demo email addresses use the reserved `.example` domain.

Safety checks:
1. Refuses if the target is `TEST_DB_NAME` or ends in `_test` (`check_target`).
2. After connecting, verifies `current_database()` is the expected DB and the migration version equals the Alembic head (`check_connection`).
3. **Dry run by default**, in a `READ ONLY` transaction (PostgreSQL rejects any write). Writes need `--apply`.
4. **Insert-only.** Each record is matched by a natural key:
   - company: name (case-insensitive)
   - contact: email (case-insensitive)
   - deal: company + title
   - activity: company + subject + due date

   Existing records are skipped, never updated. Nothing is deleted, so re-running it is safe.
5. Every record is validated with the API's own Pydantic schemas.
6. One transaction plus a PostgreSQL advisory lock: all-or-nothing, and two concurrent runs can't duplicate deals or activities.
7. If a demo contact's email already exists under another company, it is left alone and reported. An activity whose contact would belong to a different company is skipped with a warning.
8. Prints DB name, host and port only; never credentials.

## Frontend integration

How it connects:

```
Browser --fetch /api/...--> Next.js (rewrites) --> FastAPI :8000 --> PostgreSQL aig_crm_dev
```

Decisions:
- **Same-origin proxy (Next.js rewrites)**, not direct browser -> :8000 calls.
  - No CORS issues, whether the app is opened on localhost or 127.0.0.1.
  - The backend URL is a server-only env var (`CRM_API_URL`); `NEXT_PUBLIC_` vars would be inlined into the browser bundle at build time. Rewrites are read when `next dev`/`next build` starts, so a change needs a restart or rebuild.
- **Plain `fetch` in the existing provider**, no data library. All pages already read from one context.
  - It loads all 4 lists in parallel on startup, following pagination via `X-Total-Count`.
  - After each write, local state is updated from the **server's response** (UUIDs, normalised values). Deletes mirror the DB's CASCADE and SET NULL locally.
  - The dashboard reads the same API-loaded state, so its metrics come from real data.
- **Loading / error:** `DataGate` shows a spinner while loading. On failure it shows the error and a "Try again" button that reloads. The sidebar and branding stay visible.
  - The page itself is always rendered and only hidden (`hidden` attribute) until the data is ready. Data loads in an effect, so the server render is always in the loading state; replacing the page with the spinner would drop the page segment from every prerender, and Next.js (with `cacheComponents`) could not validate it for instant navigation.
- **Select fields:** `SelectField` passes its options to Base UI's `items` prop, so the trigger shows the option label rather than the raw value (e.g. a company name, not its UUID). Fields use `min-w-0` and truncate long labels so they stay inside their grid column.
- **Empty states:** the table empty states ("No companies found …") are used for an empty DB. Contact, deal and activity dialogs show "Add a company first" instead of sending an empty `companyId`.
- **Errors in dialogs:**
  - Saves and deletes are awaited. The dialog closes only on success; on failure it stays open with the user's input.
  - 422 field errors appear under the matching field (camelCase names match the form fields directly).
  - 409, 404 and network errors appear as a banner.
  - Buttons show "Saving…" / "Deleting…" and are disabled to prevent double submits.
- **Deal actions:** View / Edit / Delete are available from the Table tab's row menu and from each Pipeline card. On cards the menu sits beside the card button, not inside it, so there are no nested buttons and both stay keyboard-reachable.
- **IDs:** opaque strings from the API (UUIDs). The frontend never generates ids.
- **Backend unreachable:** the proxy returns a plain-text 500; the client maps it to "The CRM server had a problem (HTTP 500). Check that the backend is running."

## Authentication

One kind of user: an **admin**. There is no public registration; admins are created from the command line.

### Creating the first admin

After `alembic upgrade head` on the development database:

```powershell
.venv\Scripts\python scripts\create_admin.py
```

- Prompts for the username and the password (typed twice, never shown). Nothing is taken from arguments or
  environment variables, so the password never reaches shell history or process lists.
- Usernames: 1-150 characters, ASCII letters, digits and `. _ @ -` (unique regardless of case).
- Passwords: 12-256 characters, no leading/trailing spaces, not equal to the username.
- Stores only an Argon2id hash (pwdlib), verified before saving. Prints the username, never the password or hash.
- Refuses the test database, checks migrations are at head, refuses if an admin already exists, and asks
  for confirmation before writing.

### Resetting an admin password (recovery)

There is no "Forgot password" page or email recovery. A forgotten or compromised password is
reset by an **authorised administrator on the server**, in a terminal with access to the
backend code and `backend/.env` (the database credentials). Anyone with that access can
change any admin's password, so treat it like database access.

Prerequisites: PostgreSQL running, migrations at head, and the admin account exists and is active.
From `backend/` in PowerShell:

```powershell
.venv\Scripts\python scripts\reset_admin_password.py
```

1. Enter the admin's username (case-insensitive).
2. Enter the new password twice (not shown). Same policy as new accounts: 12-256 characters,
   no leading/trailing spaces, not the username; it must also differ from the current password.
3. Type `yes` to confirm.

On success the account gets a new Argon2id hash (verified before saving) and its `token_version`
is incremented in the same update, so **every existing session for that account is signed out**
(other admins are unaffected). Then sign in again at `/login` with the new password.

- No command-line options: the username and password are never put in arguments, shell history or
  process listings. Nothing sensitive (password, hash, secrets, raw database errors) is printed.
- It only changes one existing, active account; it never creates an account or resets several.
  An unknown or inactive username, mismatched passwords, a policy failure, a "no" at the
  confirmation, Ctrl+C, or a database error all roll back and exit with status 1 (2 if refused).
- It refuses the test database and checks the connected database and migration head first.
- An inactive account must be reactivated in the database before its password can be reset.

### How a session works

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` | `{"username", "password"}` -> sets the session cookie; returns `{username, csrfToken, expiresAt}` |
| `GET /api/auth/me` | the current admin and the session's CSRF token (401 if not signed in) |
| `POST /api/auth/logout` | revokes **all** the admin's sessions (bumps `token_version`) and clears the cookie |

- **Token:** an HS256 JWT signed with `JWT_SECRET_KEY`; claims `sub`, `iss`, `aud`, `iat`, `nbf`, `exp`, `jti`,
  `ver` (token version) and `csrf`. Every request re-checks the signature, algorithm, expiry, issuer, audience,
  that the admin exists and is active, and that `ver` matches the stored `token_version`.
- **Cookie:** `aig_crm_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age` = `JWT_EXPIRE_MINUTES`
  (default 8 hours), `Secure` outside development/test. JavaScript never sees the JWT; nothing is stored in
  localStorage or sessionStorage.
- **CSRF:** writes (POST/PATCH/DELETE) must send `X-CSRF-Token` equal to the token from login or `/me`, which
  the frontend keeps in memory. Login, logout and all writes also reject a foreign `Origin`/`Referer` (checked
  against `TRUSTED_ORIGINS`) and `Sec-Fetch-Site` other than `same-origin`/`none`.
- **Errors:** fixed messages only. Every failed login is `401 Invalid username or password.` (unknown users
  are checked against a dummy hash, so timing is the same). Missing/invalid sessions are
  `401 Not authenticated.`; CSRF/origin failures are 403; a missing `JWT_SECRET_KEY` is 503.
- **Revoking access:** set `is_active = false` or increment `token_version` for the admin; existing sessions
  stop working on their next request. A password reset (above) also increments `token_version`.
- **Public routes:** only `/health`, `/health/db` and the three auth endpoints. `/docs` and `/openapi.json`
  are served only in development/test.

### Frontend

- `proxy.ts` (Next.js 16's renamed middleware) redirects page requests without the session cookie to
  `/login?next=...`. It only checks that the cookie exists; FastAPI does the real verification on every call.
- `SessionProvider` (root layout) asks `/api/auth/me` on load. The CRM pages live in the `app/(crm)` route
  group, whose layout shows "Checking your session…" until then, loads CRM data only when signed in, and
  redirects to `/login` otherwise.
- Any 401 from a CRM request (expired or revoked session) sends the user to `/login?reason=expired`, and they
  return to the page they were on after signing in. A timer also signs out locally when the cookie expires.
- `?next=` only accepts same-site paths, so the login page cannot be used to redirect elsewhere.
- `next.config.ts` sends security headers on every response: `Content-Security-Policy: frame-ancestors 'none'`
  and `X-Frame-Options: DENY` (no framing), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin` and a `Permissions-Policy` disabling camera, microphone
  and geolocation. The CSP sets only `frame-ancestors`, so scripts, styles and API calls are unaffected.
- The sidebar shows the signed-in username and a Sign out button.

### Production configuration

In the production environment (not `backend/.env.example`):

- `ENVIRONMENT=production`. Any value other than `development`/`test` is treated as production, and a
  missing `ENVIRONMENT` logs a warning and falls back to development.
- `JWT_SECRET_KEY`: a unique random value of at least 32 characters (the API refuses to start without one).
- Serve the site over **HTTPS**: cookies are `Secure` in production and `COOKIE_SECURE=false` is rejected.
- `TRUSTED_ORIGINS` (or `CORS_ORIGINS`) = the exact public origin(s) of the frontend, e.g.
  `https://crm.example.com`: scheme and host, no path, and no default port (`:443`), since browsers omit it.
  Both settings are validated at startup: `*`, `null`, paths, credentials or malformed origins stop the API
  from starting (credentials are allowed, so a wildcard would let any site call the API).
- Database TLS: `DB_SSLMODE` defaults to `verify-full` in production (encrypted, with the server's certificate
  and hostname checked against the certifi CA bundle), and any weaker value stops the API from starting.
  `DB_SSLROOTCERT` can point to another CA file, or `system` for the OS store.
- The browser only ever talks to the Next.js site; it forwards `/api/*` to FastAPI. FastAPI itself may still be
  publicly reachable (as on Render), so every CRM route requires a session and cross-site writes are refused.

## Deployment (Render + Neon + Vercel)

PostgreSQL on **Neon**, FastAPI on **Render**, Next.js on **Vercel** (production tracks `main`). The browser
calls the Vercel site; Vercel forwards `/api/*` to Render, so the session cookie belongs to the Vercel domain.

**1. Neon (database)**

- Create a project (region close to the Render service), a database (e.g. `aig_crm`) and a role that owns it.
  Use new credentials, never the local ones.
- Use the **direct** connection host (not the `-pooler` one). Split Neon's connection string into the
  `DB_*` values below; the app does not read a single `DATABASE_URL`.

**2. Render (backend web service)**

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |

Environment variables (secrets marked; never commit them):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_NAME` | from Neon (`DB_PORT` is `5432`) |
| `DB_PASSWORD` | from Neon (**secret**) |
| `JWT_SECRET_KEY` | a new random value, 32+ characters (**secret**; generate as in Setup) |
| `CORS_ORIGINS` | the Vercel production origin(s), e.g. `https://<project>.vercel.app`; comma-separated |
| `PYTHON_VERSION` | `3.13.5` |

- Leave `DB_SSLMODE` unset (production uses `verify-full`) and `COOKIE_SECURE` unset (HTTPS-only in production).
  `TRUSTED_ORIGINS` defaults to `CORS_ORIGINS`. Never set `TEST_DB_NAME` or run the tests against Neon.
- `PYTHON_VERSION` takes precedence over `.python-version`. Render's docs describe the file at the repository
  root, while this one is in `backend/`, so set the variable (new Render services otherwise default to 3.14).

**3. Migrations and the first admin (once, before first use)**

Run from `backend/` in a terminal that can reach Neon: Render Shell (paid plans), or locally with **all** of
`ENVIRONMENT`, `JWT_SECRET_KEY` and the `DB_*` variables set to the production values in that terminal session
(they override `backend/.env`; anything left unset would fall back to the local `aig_crm_dev` settings).

```powershell
.venv\Scripts\alembic upgrade head
.venv\Scripts\python scripts\create_admin.py     # prompts for username and password
```

On paid Render plans, `alembic upgrade head` can instead be the service's **Pre-Deploy Command**.

**4. Check the backend** at `https://<service>.onrender.com`: `/health` returns `{"status":"ok"}`, `/health/db`
names the Neon database (proving the `verify-full` connection works), `/api/companies` returns 401, `/docs` is 404.

**5. Vercel (frontend)**

- Set `CRM_API_URL` = `https://<service>.onrender.com` (no trailing slash, no `/api`) for **Production only**.
  It is read at build time, so set it **before** the production build (merging into `main`), or redeploy after.
  Preview deployments then have no backend, which keeps them away from production data.
- After the production deploy: `/` redirects to `/login`, sign-in works and data loads, `/api/companies`
  without a session is 401, and responses carry the security headers.

**Notes:** Render's free plan sleeps after ~15 minutes idle and the first request can take a minute (Vercel's
proxy may time out meanwhile); a paid instance avoids this. Neon also suspends idle compute; pooled
connections are re-checked before use. Add a custom domain to `CORS_ORIGINS` when you add it in Vercel.

## Troubleshooting

- **Login page says "Sign-in is not configured on the server."** `JWT_SECRET_KEY` is missing from
  `backend/.env`; add one (see Setup) and restart Uvicorn.
- **"Invalid username or password." for every attempt:** check an admin exists (`scripts/create_admin.py`
  refuses to create a second one) and that `alembic upgrade head` was run on `aig_crm_dev`.
- **Signed out right after signing in, over plain http:** `COOKIE_SECURE=true` or a non-development
  `ENVIRONMENT` makes the cookie HTTPS-only; locally use `ENVIRONMENT=development`.

- **`/health/db` returns `{"detail":"Not Found"}`:** the routes are `/health` and `/health/db` with no prefix, and
  paths are case-sensitive. `/health/DB`, `/api/health/db` and `/healthdb` all return this 404. Open `/docs` to see
  the routes the running server actually has, and restart Uvicorn from `backend/` if it is an old instance.
- **`/health/db` returns 503 `database unavailable (OperationalError)`:** PostgreSQL is not running, or
  `backend/.env` is missing or has wrong credentials.
- **Test setup fails with `Test database 'aig_crm_test' is not reachable`:** run `scripts/create_dev_db.py` to create it.
- **API won't start: `DB_SSLMODE must be verify-full ...`:** production refuses weaker TLS modes; unset
  `DB_SSLMODE`. **`DB_SSLROOTCERT must be ...`:** the CA file path does not exist; unset it to use certifi.
- **Production `/health/db` returns 503 `OperationalError`:** check the `DB_*` values against Neon (direct host,
  database name, role), that the Neon project is not suspended or deleted, and the Render logs for TLS errors.

## Limitations and future work

- **Authentication is admin-only:** no roles, a single initial admin from the CLI, and password recovery only
  through the server-side reset script (no self-service password change in the UI).
- **No login rate limiting:** Argon2id slows each guess, but repeated attempts are not throttled or locked out.
  Add rate limiting (e.g. at a reverse proxy) before exposing the app publicly.
- **Deployment:** documented above but not yet carried out. Production logging and monitoring are not set up.
  `requirements.txt` pins direct dependencies (and Starlette and argon2-cffi), but other transitive packages
  are resolved at install time; use a lock file if fully reproducible builds are needed.
- **Data freshness:** data is loaded once per page load. Changes made elsewhere (another tab or user) appear only
  after a reload or "Try again". Consider refetch-on-focus or a data library if multi-user editing matters.
- **Client-side search and filtering:** the UI filters the loaded data. The API's server-side search and filters
  are unused for now and would matter for large data sets.
- **UI test coverage:** frontend automated tests cover the API client only; UI behaviour is verified manually.
- **The activity/contact company rule** is enforced in the API (with row locks), not as a DB constraint.
- **Scaling:** search is `ILIKE '%term%'`, fine for small data; add trigram indexes if it grows. List `limit` is
  capped at 500, so the frontend should page or filter for larger data sets.
- **`updated_at`** is set by the ORM on update. Raw SQL updates won't change it.
