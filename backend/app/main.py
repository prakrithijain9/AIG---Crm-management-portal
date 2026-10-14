from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.activities import router as activities_router
from app.api.auth import require_admin
from app.api.auth import router as auth_router
from app.api.companies import router as companies_router
from app.api.contacts import router as contacts_router
from app.api.deals import router as deals_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.security import CSRF_HEADER_NAME

settings = get_settings()

# The interactive API docs describe every endpoint; only serve them outside production.
docs_enabled = not settings.is_production

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    # Exact, validated origins only (Settings refuses "*"), because credentials are allowed.
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", CSRF_HEADER_NAME],
    # Let browser JavaScript read the pagination total.
    expose_headers=["X-Total-Count"],
)

# Public: liveness/readiness checks and the sign-in endpoints themselves.
app.include_router(health_router)
app.include_router(auth_router, prefix="/api")

# Every CRM data route requires a signed-in admin (and CSRF checks on writes).
for router in (companies_router, contacts_router, deals_router, activities_router):
    app.include_router(router, prefix="/api", dependencies=[Depends(require_admin)])
