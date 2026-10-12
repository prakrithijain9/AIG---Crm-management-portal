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
(`pydantic[email]`, used by `EmailStr`). `requirements.txt` specifies minimum versions only.

## Project layout

```
backend/
  requirements.txt          dependencies
  .env.example              safe template (copy to .env)
  pytest.ini
  alembic.ini               Alembic config (no DB URL in it)
  alembic/env.py            reads DB URL from app settings + Base.metadata; accepts a test connection
  alembic/versions/09d6732c3643_create_crm_tables.py   first migration
  app/main.py               FastAPI app, CORS from CORS_ORIGINS
  app/core/config.py        Settings (DB_* env vars, SecretStr password, TEST_DB_NAME)
  app/db/session.py         SQLAlchemy engine, SessionLocal, get_db dependency
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
  tests/conftest.py         test DB engine (runs migrations), rolled-back connection, db + API client fixtures
  tests/api_helpers.py      camelCase payload builders for API tests
  tests/test_health.py
  tests/test_migrations.py  single head, downgrade/upgrade round trip, models == schema
  tests/test_models.py      relationships, cascades, constraints
  tests/test_api_*.py       companies, contacts, deals, activities, common (pagination/errors/CORS)
  tests/test_seed.py        seed logic (on the rolled-back test DB) and seed safety guards
```

Frontend files involved in the API integration:

```
lib/api.ts                       typed fetch client for /api/*, ApiError (status + camelCase fieldErrors), listAll paging
lib/api.test.ts                  API client unit tests (Node's built-in test runner)
components/crm/crm-provider.tsx  loads from / writes to the API
components/crm/data-gate.tsx     loading spinner / error card with "Try again"; page stays rendered underneath
components/crm/use-dialog-form.ts dialog form state, saving flag, server + client errors, reset on open
components/crm/entity-dialog.tsx, confirm-dialog.tsx   saving state, error banner, stay open on failure
components/crm/form-fields.tsx   fields with per-field errors; select fields show option labels
components/crm/{company,contact,deal,activity}-dialog.tsx   use useDialogForm; show field errors
app/{companies,contacts,deals,activities}/page.tsx   await saves/deletes; close dialog only on success
components/layout/app-shell.tsx  wraps pages in DataGate
next.config.ts                   rewrites /api/:path* -> FastAPI (CRM_API_URL, default http://127.0.0.1:8000)
```

`lib/mock-data.ts` is kept as the source of the demo data but is no longer imported by the app.

`.gitignore` excludes `.env*` (except `.env.example`), `backend/.venv/`, `__pycache__/`, `*.py[cod]` and `.pytest_cache/`, so `backend/.env` is never committed.

## Setup

All commands from `backend/` in PowerShell.

```powershell
py -3.13 -m venv .venv                       # once
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env                  # then edit .env, set DB_PASSWORD
.venv\Scripts\python scripts\create_dev_db.py   # prompts for the PostgreSQL superuser password
.venv\Scripts\alembic upgrade head           # create the CRM tables in aig_crm_dev
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
# http://127.0.0.1:8000/docs        -> interactive API docs (lists every registered route)
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
npm run dev              # http://localhost:3000 ; /api/* is proxied to FastAPI
npm run test:frontend    # API client unit tests
npm run lint
npm run build
# Different backend address: set CRM_API_URL (server-side only) before dev/build, e.g.
# $env:CRM_API_URL = "http://127.0.0.1:8001"; npm run dev
```

## Testing

### Current results

| Check | Result |
|---|---|
| Backend `pytest` | 111 passed |
| `npm run test:frontend` | 9 passed |
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
- `test_health.py` checks the dev DB with a read-only `SELECT 1`, so it needs PostgreSQL running and `backend/.env` present.

### API test setup

- **Shared rolled-back transaction:** `client` overrides `get_db` so every request gets a **new** session on the test connection. Each `commit()` only releases a SAVEPOINT, and the outer transaction is rolled back after the test.
- **Fresh session per request:** a shared session would cache rows that the DB had already cascade-deleted.
- **Guard:** the `client` fixture asserts `current_database()` is the test DB before any request.
- **Timestamps:** `now()` is the transaction start time, so rows created inside one test share a `created_at`. The newest-first test sets distinct times explicitly. In production each request is its own transaction.

### What the tests cover

- **Migrations:** single head, downgrade/upgrade round trip, models match the migrated schema (no drift).
- **Models:** full object graph and defaults, optional activity contact, company delete cascades, contact delete
  sets `activities.contact_id` to NULL, and constraint checks that assert the exact constraint name
  (name/email uniqueness, not-blank, email `@`, status/stage/type values, value >= 0, foreign keys, NOT NULL).
- **API:** CRUD for all four resources, pagination, search (including wildcard escaping), error mapping and CORS.
- **Seed:** full insert with correct relationships, idempotent second run, user-edited records left unchanged,
  dry run writes nothing, guards refuse test DB names and a mismatched connected DB.
- **Frontend API client:** request building, error mapping (including non-JSON server errors and network failures), paging.

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

## Troubleshooting

- **`/health/db` returns `{"detail":"Not Found"}`:** the routes are `/health` and `/health/db` with no prefix, and
  paths are case-sensitive. `/health/DB`, `/api/health/db` and `/healthdb` all return this 404. Open `/docs` to see
  the routes the running server actually has, and restart Uvicorn from `backend/` if it is an old instance.
- **`/health/db` returns 503 `database unavailable (OperationalError)`:** PostgreSQL is not running, or
  `backend/.env` is missing or has wrong credentials.
- **Test setup fails with `Test database 'aig_crm_test' is not reachable`:** run `scripts/create_dev_db.py` to create it.

## Limitations and future work

- **No authentication or authorization.** Required before the API is exposed beyond localhost.
- **Not deployment-ready:** no HTTPS, secrets management, hosted database, rate limiting or production logging.
  Backend dependencies use minimum-version ranges (`>=`) without a lock file; pin them before deploying.
- **Data freshness:** data is loaded once per page load. Changes made elsewhere (another tab or user) appear only
  after a reload or "Try again". Consider refetch-on-focus or a data library if multi-user editing matters.
- **Client-side search and filtering:** the UI filters the loaded data. The API's server-side search and filters
  are unused for now and would matter for large data sets.
- **UI test coverage:** frontend automated tests cover the API client only; UI behaviour is verified manually.
- **The activity/contact company rule** is enforced in the API (with row locks), not as a DB constraint.
- **Scaling:** search is `ILIKE '%term%'`, fine for small data; add trigram indexes if it grows. List `limit` is
  capped at 500, so the frontend should page or filter for larger data sets.
- **`updated_at`** is set by the ORM on update. Raw SQL updates won't change it.
