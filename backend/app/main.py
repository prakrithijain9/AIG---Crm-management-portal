from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.activities import router as activities_router
from app.api.companies import router as companies_router
from app.api.contacts import router as contacts_router
from app.api.deals import router as deals_router
from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Let browser JavaScript read the pagination total.
    expose_headers=["X-Total-Count"],
)

app.include_router(health_router)
for router in (companies_router, contacts_router, deals_router, activities_router):
    app.include_router(router, prefix="/api")
