# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read first

- `AGENTS.md` warns this Next.js (16.4) has breaking changes vs. training data. Read the guide in `node_modules/next/dist/docs/` before writing Next code (run `npm install` first if `node_modules` is absent). `next.config.ts` enables `cacheComponents`, `partialPrefetching`, and `experimental.agentFeedback`; `agentFeedback` makes `next dev` rewrite the `AGENTS.md` blocks, so commit `AGENTS.md` with your work.
- **Branches differ a lot.** This branch (`Vishnu-merged`, from `feature/backend-api`) is the full stack: Next.js + FastAPI + PostgreSQL + admin auth. `origin/main` is still the old frontend-only version with in-browser mock data and has diverged from this branch (it has README commits this branch lacks). Check which branch you are on before assuming a backend exists.
- `NOTES.md` is the detailed backend reference (endpoint behaviour, auth design, seed safety rules, deployment). `README.md` and `NOTES.md` describe a planned Render + Neon + Vercel deployment; the real production host is a Hostinger VM (see Deployment below).

## Commands

Frontend (repo root; needs FastAPI on :8000 for data):

```bash
npm run dev             # http://localhost:3000; /api/* is proxied to CRM_API_URL (default http://127.0.0.1:8000)
npm run build
npm run lint            # eslint flat config
npm run test:frontend   # node --test on lib/api.test.ts, lib/auth.test.ts, lib/next-config.test.ts
npx tsc --noEmit        # typecheck
```

Backend (always run from `backend/`, so `app.main` imports and `backend/.env` is found; Windows venv paths shown):

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload     # http://127.0.0.1:8000, /docs in development only
.venv\Scripts\python -m pytest -v                          # all tests
.venv\Scripts\python -m pytest tests/test_api_deals.py::test_name -v   # single test
.venv\Scripts\alembic upgrade head
.venv\Scripts\alembic revision --autogenerate -m "..."     # always review the generated file
.venv\Scripts\python scripts\seed_demo_data.py [--apply]   # dry run by default
.venv\Scripts\python scripts\create_admin.py               # first admin (interactive)
```

First-time setup (venv, `.env` from `.env.example`, `create_dev_db.py`, `JWT_SECRET_KEY`) is in `NOTES.md` → Setup. Without `JWT_SECRET_KEY`, development starts but sign-in and every CRM request are refused.

Tests need a real PostgreSQL: they use a separate database (`TEST_DB_NAME`, default `aig_crm_test`), build the schema by running the real Alembic migrations, and roll back each test's transaction. Fixtures `client` (signed-in admin, test-only JWT secret) and `anon_client` are in `tests/conftest.py`.

## Architecture

```
Browser ──same-origin /api/*──▶ Next.js rewrite (next.config.ts) ──▶ FastAPI :8000 ──▶ PostgreSQL
```

**Frontend.** Next.js App Router, React 19, TypeScript strict, Tailwind 4 (via `@tailwindcss/turbopack` rule), shadcn `base-nova` on Base UI. Path alias `@/*` → repo root. `components/ui/` is generated shadcn code (add via the `shadcn` CLI, config in `components.json`).

- `app/layout.tsx` → `SessionProvider` (`components/auth/`). CRM pages live in the `app/(crm)/` route group, whose layout wraps them in `AppShell` → `CrmProvider`. `app/login/` is outside the group.
- `proxy.ts` (Next 16's renamed middleware) only redirects to `/login` when the session cookie is absent. Real enforcement is the backend's `require_admin` on every CRM route.
- `CrmProvider` (`components/crm/crm-provider.tsx`) loads all four lists from the API once signed in and exposes async add/update/delete via `useCrm()`. Mutations update local state only after the server confirms, and throw `ApiError` so dialogs can stay open and show field errors. Deletes **mirror the DB cascades locally by hand**: deleting a company removes its contacts, deals, and activities; deleting a contact sets `contactId: null` on its activities. Keep these in sync with the `ondelete` rules in `backend/app/models/`.
- `lib/api.ts` is the only HTTP client: normalises errors (422 → camelCase `fieldErrors`), holds the CSRF token in memory only, and sends it as `X-CSRF-Token` on writes. Lists are fetched with page size 500 (the API max).
- `DataGate` keeps page children mounted but hidden while loading. This is deliberate, so prerendering and instant navigation still see the page segment; don't replace it with an early return.
- **Page pattern (copy for new modules):** each list page owns local `search`/filter state, filters context data with `useMemo`, defines `Column<T>[]` for `DataTable`, and tracks dialog state as a discriminated union (`{open:false} | {open:true; mode:"create"} | {open:true; mode:"view"|"edit"; entity}`) plus `pendingDelete` for `ConfirmDialog`. Per-entity `*-dialog.tsx` files wrap the shared `EntityDialog` and `form-fields.tsx`. Pages do not read URL search params yet.

**Backend** (`backend/app/`). FastAPI + SQLAlchemy 2 + psycopg 3 + Alembic, Pydantic settings from `backend/.env`.

- `api/` holds one router per entity plus `auth.py`. `main.py` mounts the CRM routers behind `require_admin` (session JWT in an HttpOnly cookie, plus CSRF and Origin checks on writes). `api/common.py` provides the shared helpers: `paginated`, `contains_any` (search), `get_or_404`, `require_reference` (FK validation that returns 422 on the camelCase field), and `commit` (maps IntegrityError to 409/422).
- `schemas/` use a `to_camel` alias generator: the API speaks camelCase (`companyId`, `expectedCloseDate`), Python uses snake_case. Update schemas expose `.changes()` for PATCH.
- `models/`: UUID PKs and timestamps via mixins in `db/base.py`. DB constraints carry real rules: case-insensitive unique company name and contact email, `deal.value >= 0` as `Numeric(14,2)` (never float), and non-blank names. An activity's contact must belong to the same company; this is checked in `api/activities.py`, not the DB.
- **Enums must match in two places:** `backend/app/models/enums.py` (StrEnum, DB values) and the `as const` arrays in `lib/types.ts` (drive select options and badges). Changing one requires changing the other, plus a migration.

## Deployment (Hostinger VM)

Production is a Hostinger Ubuntu VM running Docker Compose from `/opt/aig-crm` (repo checkout in `/opt/aig-crm/src`). Containers: `caddy:2` proxy on :443, `frontend`, `backend`, and `postgres:18`. The compose and Caddy files live on the VM, not in this repo. The same VM also hosts an unrelated project (ProcureAI: host nginx on :80 and systemd services on 127.0.0.1:3000/8000), so don't touch host nginx or those ports when changing AIG CRM.
