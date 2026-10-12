# AIG CRM – Backend Notes

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
- **SQLAlchemy** builds the connection pool and sessions; **psycopg** (v3) is the driver that actually talks to PostgreSQL.
- **Alembic** versions schema changes as migration files (like Git for the database schema).
- **pytest + HTTPX** (via FastAPI's `TestClient`) call the endpoints in-process for tests.

## Requirements

- Python 3.13, PostgreSQL 18 on `localhost:5432`, Node.js (for the Next.js frontend)
- On Windows, `psql` may not be on PATH; use the full path, e.g. `"C:\Program Files\PostgreSQL\18\bin\psql.exe"`

## Files created

```
backend/
  requirements.txt          dependencies
  .env.example              safe template (copy to .env)
  pytest.ini
  alembic.ini               Alembic config (no DB URL in it)
  alembic/env.py            reads DB URL from app settings + Base.metadata; accepts a test connection
  alembic/versions/09d6732c3643_create_crm_tables.py   first migration
  app/main.py               FastAPI app, CORS for localhost:3000
  app/core/config.py        Settings (DB_* env vars, SecretStr password, TEST_DB_NAME)
  app/db/session.py         SQLAlchemy engine, SessionLocal, get_db dependency
  app/db/base.py            Base (constraint naming convention), UUID/timestamp mixins, str_enum helper
  app/models/               enums.py, company.py, contact.py, deal.py, activity.py
  app/schemas/              Pydantic request/response models (common.py + one per entity)
  app/api/health.py         GET /health and GET /health/db
  app/api/common.py         DB session dep, pagination, search, 404/422 helpers, IntegrityError -> 409/422
  app/api/companies.py, contacts.py, deals.py, activities.py   CRUD routers (mounted under /api)
  scripts/create_dev_db.py  create role + dev DB + test DB if missing (never drops)
  tests/conftest.py         test DB engine (runs migrations), rolled-back connection, db + API client fixtures
  tests/api_helpers.py      camelCase payload builders for API tests
  tests/test_health.py
  tests/test_migrations.py  single head, downgrade/upgrade round trip, models == schema
  tests/test_models.py      relationships, cascades, constraints
  tests/test_api_*.py       companies, contacts, deals, activities, common (pagination/errors/CORS)
  tests/test_seed.py        seed logic (on the rolled-back test DB) and seed safety guards
  app/seed/demo_data.json   one-time JSON export of lib/mock-data.ts (8 companies, 10 contacts, 8 deals, 8 activities)
  app/seed/demo.py          insert-only, idempotent seed logic + target/connection guards
  scripts/seed_demo_data.py CLI: dry run by default, --apply to insert into aig_crm_dev
```

Frontend files (integration with the API):

```
lib/api.ts                       typed fetch client for /api/*, ApiError (status + camelCase fieldErrors), listAll paging
lib/api.test.ts                  9 unit tests (Node's built-in test runner, no new dependency)
components/crm/crm-provider.tsx  now loads from / writes to the API (was in-memory mock data)
components/crm/data-gate.tsx     NEW: loading spinner / error card with "Try again" around page content
components/crm/use-dialog-form.ts NEW: dialog form state, saving flag, server + client errors, reset on open
components/crm/entity-dialog.tsx, confirm-dialog.tsx   saving state, error banner, stay open on failure
components/crm/form-fields.tsx   optional per-field error message (aria-invalid)
components/crm/{company,contact,deal,activity}-dialog.tsx   use useDialogForm; show field errors
app/{companies,contacts,deals,activities}/page.tsx   await saves/deletes; close dialog only on success
components/layout/app-shell.tsx  wraps pages in DataGate
next.config.ts                   rewrites /api/:path* -> FastAPI (CRM_API_URL, default http://127.0.0.1:8000)
lib/format.ts                    removed createId (mock id generator; the server now assigns UUIDs)
package.json                     added "test:frontend" script
tsconfig.json                    allowImportingTsExtensions (so Node can run lib/api.test.ts; noEmit already set)
```

`lib/mock-data.ts` is kept (source of the seed data) but no longer imported by the app.

Modified: `.gitignore` – added `!.env.example`, `backend/.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`. (`.env*` was already ignored, so `backend/.env` is never committed.)

## Dependencies installed (in `backend/.venv`)

fastapi 0.143.0 · uvicorn 0.54.0 · SQLAlchemy 2.1.4 · psycopg 3.3.6 (binary) · alembic 1.20.0 · pydantic 2.14.1 · pydantic-settings 2.15.0 · pytest 9.1.1 · httpx 0.28.1 · email-validator 2.3.0 (added for the CRUD API via `pydantic[email]`, used by `EmailStr`)

## Setup steps

All commands from `backend/` in PowerShell.

```powershell
py -3.13 -m venv .venv                       # once
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env                  # then edit .env, set DB_PASSWORD
.venv\Scripts\python scripts\create_dev_db.py   # prompts for postgres superuser password
```

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
.venv\Scripts\alembic upgrade head                        # apply migrations to aig_crm_dev
.venv\Scripts\alembic revision --autogenerate -m "..."    # after changing models; ALWAYS review the file
.venv\Scripts\python scripts\seed_demo_data.py            # demo data: dry run (read-only)
.venv\Scripts\python scripts\seed_demo_data.py --apply    # demo data: insert missing records into aig_crm_dev
```

Frontend (from the project root, with FastAPI running on port 8000):

```powershell
npm run dev              # http://localhost:3000 ; /api/* is proxied to FastAPI
npm run test:frontend    # API client unit tests
npm run lint
npm run build
# Different backend address: set CRM_API_URL (server-side only) before dev/build, e.g.
# $env:CRM_API_URL = "http://127.0.0.1:8001"; npm run dev
```

## Database role

The dev role/database are created with `scripts/create_dev_db.py`:
role `aig_crm` (LOGIN, not superuser) owning database `aig_crm_dev`.

## Test results

- 2026-10-12, before DB credentials: `/health` passed; `/health/db` 503 `database unavailable (OperationalError)` – expected, no `.env` yet.
- 2026-10-12 14:40, after DB setup:
  - `pytest -v`: **2 passed** (`test_health`, `test_health_db_connects_to_postgres`), 1 warning (see below)
  - Live server on 127.0.0.1:8000:
    - `GET /health` -> 200 `{"status":"ok"}`
    - `GET /health/db` -> 200 `{"status":"ok","database":"aig_crm_dev","server_version":"18.6"}`
    - `GET /health/db/` -> 307 redirect to `/health/db`
    - `GET /docs`, `/openapi.json` -> 200; OpenAPI lists `/health` and `/health/db`
    - `GET localhost:8000/health/db` -> 200
  - Connected identity: `current_user = aig_crm`, `current_database = aig_crm_dev`, DB owner `aig_crm`
  - `alembic current`: connects (PostgresqlImpl), no revision yet; `alembic heads`: none (no migrations)
  - Password is masked (`***`) in SQLAlchemy's URL repr; health errors expose only the exception type
- 2026-10-12 15:10, after adding models (before `aig_crm_test` exists):
  - `pytest`: **2 passed, 18 errors**. The health tests pass. All 18 model/migration tests stop at setup with
    `Test database 'aig_crm_test' is not reachable` (expected; the DB isn't created yet). The dev DB was not used.
- 2026-10-12, after `scripts/create_dev_db.py` (owner ran it; output: `aig_crm` and `aig_crm_dev` already
  existed, left unchanged; `aig_crm_test` created, owned by `aig_crm`):
  - `pytest -v`: **20 passed, 1 warning** (1.66s). Run again: 20 passed (1.73s).
    - test_health.py (2): `test_health`, `test_health_db_connects_to_postgres`
    - test_migrations.py (3): single head, downgrade/upgrade round trip, models match migrated schema (no drift)
    - test_models.py (15): full graph + defaults, optional activity contact, company delete cascades,
      contact delete sets activity.contact_id NULL, and 11 constraint checks (each asserts the exact
      constraint name: name/email uniqueness, not-blank, email `@`, status/stage/type values,
      value >= 0, FKs to companies/contacts, NOT NULL)
  - Warning: the known `StarletteDeprecationWarning` (httpx -> httpx2); no effect on results.
  - Isolation check after the runs:
    - `aig_crm_dev`: alembic `09d6732c3643`, 0 rows in all 4 tables (unchanged by tests)
    - `aig_crm_test`: alembic `09d6732c3643`, 0 rows in all 4 tables (every test rolled back)
- 2026-10-12, after adding the CRUD API:
  - `pytest`: **102 passed, 1 warning** (8.0s), on 2 separate clean runs. Per file: test_api_activities 14,
    test_api_common 25, test_api_companies 20, test_api_contacts 10, test_api_deals 13, test_health 2,
    test_migrations 3, test_models 15.
  - Mutation check (deliberately broken code, then restored byte-for-byte):
    - disabling the activity same-company check -> 3 tests failed
    - disabling LIKE wildcard escaping -> 1 test failed
    - So the tests do detect regressions in these rules.
  - After the runs: `aig_crm_dev` and `aig_crm_test` both have 0 rows in all 4 tables. API tests never wrote to the dev DB.
  - Live server on the dev DB (read-only GETs only): `/api/companies` 200 `[]` with `x-total-count: 0`;
    `/api/activities` 200 `[]`; `/api/deals?stage=Won` 200 `[]`; `/api/companies/<zero uuid>` 404
    `{"detail":"Company not found"}`; `/api/contacts?limit=0` 422.
- 2026-10-12, seed script + frontend integration:
  - Backend `pytest`: **111 passed, 1 warning** (9.2s) = 102 previous + 9 new in test_seed.py.
  - Frontend: `npm run test:frontend` **9/9 passed**; `tsc --noEmit` clean; `npm run lint` **0 problems**
    (baseline before this work: 4 errors, `react-hooks/set-state-in-effect` in the 4 dialogs, fixed by the
    dialog rewrite); `npm run build` **succeeded** (baseline also succeeded).
  - Seed dry run against `aig_crm_dev` (read-only): would create 8 companies, 10 contacts, 8 deals,
    8 activities; 0 skipped; 0 warnings. Dev DB still 0 rows afterwards. **`--apply` NOT run yet; awaiting approval.**
  - End-to-end through the Next.js proxy (`next start -p 3100` + FastAPI on dev DB; read-only GETs and one
    invalid POST that FastAPI rejects before touching the DB):
    `/` and `/companies` 200; `/api/companies|contacts|deals|activities` 200 `[]` with `x-total-count: 0`;
    `/api/companies/<zero uuid>` 404 `{"detail":"Company not found"}`; invalid POST -> 422 with field errors
    for `name`, `industry`, `email`.
  - Backend unreachable (`next dev -p 3101` with `CRM_API_URL=http://127.0.0.1:9`): `/api/companies` -> 500,
    plain-text "Internal Server Error". The client maps this to "The CRM server had a problem (HTTP 500).
    Check that the backend is running." (covered by a unit test).
  - Both temporary servers were stopped afterwards. Stopping the background shell left the Node child
    processes running, so they were ended by PID after checking their command lines.
  - After all runs: `aig_crm_dev` and `aig_crm_test` both 0 rows in all 4 tables.
  - Not done: clicking through the UI in a real browser (create/edit/delete via dialogs). Covered by the
    unit tests and API tests, but not exercised visually.

## Demo data seed (2026-10-12)

`scripts/seed_demo_data.py` loads the frontend's mock data into **aig_crm_dev only**.

Safety checks:
1. Refuses if the target is `TEST_DB_NAME` or ends in `_test` (`check_target`).
2. After connecting, verifies `current_database()` is the expected DB and the migration version equals the Alembic head (`check_connection`).
3. **Dry run by default**, in a `READ ONLY` transaction (PostgreSQL rejects any write). Writes need `--apply`.
4. **Insert-only.** Each record is matched by a natural key:
   - company: name (case-insensitive)
   - contact: email (case-insensitive)
   - deal: company + title
   - activity: company + subject + due date

   Existing records are skipped, never updated. Nothing is deleted.
5. Every record is validated with the API's own Pydantic schemas.
6. One transaction plus a PostgreSQL advisory lock: all-or-nothing, and two concurrent runs can't duplicate deals or activities.
7. If a demo contact's email already exists under another company, it is left alone and reported. An activity whose contact would belong to a different company is skipped with a warning.
8. Prints DB name, host and port only; never credentials.

Tests (`tests/test_seed.py`) call the seed *function* inside the rolled-back test-DB transaction:
- full insert with correct relationships
- second run creates nothing
- user-edited records are not modified
- dry run writes nothing
- the guards refuse test DB names and a mismatched connected DB

## Frontend integration (2026-10-12)

How it connects:

```
Browser --fetch /api/...--> Next.js (rewrites) --> FastAPI :8000 --> PostgreSQL aig_crm_dev
```

Next.js docs consulted (bundled in `node_modules/next/dist/docs`, as `AGENTS.md` requires):
- client-side data fetching guide
- environment variables (`NEXT_PUBLIC_` vars are inlined at build time, which is why a server-only rewrite was chosen)
- `rewrites` config reference (external destinations supported)

Decisions:
- **Same-origin proxy (Next.js rewrites)**, not direct browser -> :8000 calls.
  - No CORS issues, whether the app is opened on localhost or 127.0.0.1.
  - The backend URL is a server-only env var (`CRM_API_URL`). Rewrites are read when `next dev`/`next build` starts, so a change needs a restart or rebuild.
- **Plain `fetch` in the existing provider**, no data library. All pages already read from one context.
  - It loads all 4 lists in parallel on startup, following pagination via `X-Total-Count`.
  - After each write, local state is updated from the **server's response** (UUIDs, normalised values). Deletes mirror the DB's CASCADE and SET NULL locally.
  - The dashboard reads the same API-loaded state, so its metrics come from real data.
- **Loading / error:** `DataGate` shows a spinner while loading. On failure it shows the error and a "Try again" button that reloads. The sidebar and branding stay visible.
- **Empty states:** the existing table empty states ("No companies found …") are used for an empty DB. Contact, deal and activity dialogs show "Add a company first" instead of sending an empty `companyId`.
- **Errors in dialogs:**
  - Saves and deletes are awaited. The dialog closes only on success; on failure it stays open with the user's input.
  - 422 field errors appear under the matching field (camelCase names match the form fields directly).
  - 409, 404 and network errors appear as a banner.
  - Buttons show "Saving…" / "Deleting…" and are disabled to prevent double submits.
- **IDs:** opaque strings from the API (UUIDs). The frontend never generates ids now.
- **UI and branding:** layout, colours, labels and copy unchanged. The only visible additions are the loading/error card, error text and the saving labels.

## CRUD API (2026-10-12)

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
| GET / PATCH / DELETE | `/api/deals/{id}` | 200 / 200 / 204 | |
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
{"id": "6f1c…", "createdAt": "2026-10-12T15:40:00Z", "updatedAt": "2026-10-12T15:40:00Z",
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

### API test setup

- **Shared rolled-back transaction:** `client` overrides `get_db` so every request gets a **new** session on the test connection. Each `commit()` only releases a SAVEPOINT, and the outer transaction is rolled back after the test.
- **Fresh session per request:** a fresh session matters because a shared one would cache rows that the DB had already cascade-deleted.
- **Guard:** the `client` fixture asserts `current_database()` is the test DB before any request.
- **Timestamps:** `now()` is the transaction start time, so rows created inside one test share a `created_at`. The newest-first test sets distinct times explicitly. In production each request is its own transaction.

## CRM data model (2026-10-12)

Derived from the frontend's `lib/types.ts` and the delete rules in `components/crm/crm-provider.tsx`.
Before migrating, `aig_crm_dev` had no tables and no Alembic history.

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
- Frontend uses camelCase (`companyId`, `jobTitle`); DB uses snake_case. The API schemas will map between them.

Migration `09d6732c3643_create_crm_tables`: generated with `alembic revision --autogenerate`, then hand-edited.
Autogenerate emitted each enum CHECK constraint twice and left `create_constraint` on the column type.
I edited it so each enum column is `VARCHAR(20)` with one named CHECK, and reviewed the SQL with
`alembic upgrade head --sql` first. The upgrade only creates objects; it drops nothing.

Applied to `aig_crm_dev` 2026-10-12: `alembic upgrade head` -> `Running upgrade -> 09d6732c3643`.
`alembic current` = `09d6732c3643 (head)`. Inspected: 4 CRM tables (0 rows each), FKs and CHECKs as above.

### Test setup

- Tests that touch tables use a **separate database** `aig_crm_test` (`TEST_DB_NAME`). They never use `aig_crm_dev`.
- `conftest.py` refuses to run unless the test DB name differs from `DB_NAME` and ends in `_test`.
- At session start it rebuilds the test schema by running the real migrations (downgrade base -> upgrade head).
- Each test runs in a transaction that is rolled back afterwards, so tests leave no data.
- `aig_crm` cannot create databases, so `aig_crm_test` is created by `scripts/create_dev_db.py` (needs the postgres admin password, entered privately).
- `test_health.py` still checks the dev DB with a read-only `SELECT 1`.

## Debugging: `/health/db` returned 404

Reported: browser showed `{"detail":"Not Found"}` at `/health/db` while pytest passed.

Checked:
- Router: `app/api/health.py` defines `/health` and `/health/db` on an `APIRouter` with no prefix;
  `app/main.py` calls `app.include_router(health_router)`. Correct.
- Process on port 8000: the project venv running `python -m uvicorn app.main:app --reload`. Correct app.
- App code unchanged since 12:53; the current server was started at 14:36.

Result: could not reproduce – the running server returns 200. No code change was needed.
The 404 most likely came from an earlier server instance or a URL variant. These all return
exactly `{"detail":"Not Found"}`: `/health/DB` (paths are case-sensitive), `/api/health/db`,
`/healthdb`, or a trailing space. If it happens again: open `/docs` to see the routes the
running server actually has, and restart Uvicorn from `backend/`.

## Known issues / notes

- Warning: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2`. Harmless for now; revisit when upgrading test deps.
- `test_health_db_connects_to_postgres` needs PostgreSQL running and `backend/.env` present.

## Remaining work

- [x] Create `backend/.env` and run `scripts/create_dev_db.py`
- [x] Verify `/health/db` and full test suite against real DB
- [x] Verify `alembic current` connects
- [x] Define CRM models + first migration, applied to `aig_crm_dev`
- [x] Create `aig_crm_test` and run the full test suite (20 passed)
- [x] API: Pydantic schemas (camelCase <-> snake_case) and CRUD endpoints for all 4 entities
- [x] API: activity's contact must belong to the activity's company (enforced in the API with row locks; still not a DB constraint)
- [x] API: map unique/FK/CHECK violations to clear 409/422 errors
- [x] Seed script from `lib/mock-data.ts` (dry run verified; 9 tests)
- [ ] **Run `scripts/seed_demo_data.py --apply` on aig_crm_dev** (awaiting owner approval)
- [x] Wire frontend to the API (provider, loading/error states, 409/422 in dialogs, dashboard from API data)
- [ ] Click through create/edit/delete for each entity in a real browser once demo data is loaded
- [ ] Data is loaded once per page load. Changes made elsewhere (another tab or user) appear only after a reload or "Try again". Consider refetch-on-focus or a data library if multi-user editing matters.
- [ ] Search and filters run client-side on the loaded data (as before). The API's server-side search and filters are unused for now and would matter for large data sets.
- [ ] Decide on auth/authorization before exposing the API beyond localhost (none yet)
- [ ] Limitations to revisit:
  - Search is `ILIKE '%term%'`, fine for small data; add trigram indexes if it grows.
  - List `limit` is capped at 500, so the frontend should page or filter for larger data sets.
  - `updated_at` is set by the ORM on update. Raw SQL updates won't change it.
