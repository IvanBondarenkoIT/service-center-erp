from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.deps import AccountantOnlyCash, NotAuthenticated
from app.routers import auth, cash, dictionaries, orders, reports
from app.services.seed import seed_defaults
from app.services.db_migrate import ensure_schema

BASE_DIR = Path(__file__).resolve().parent.parent
settings = get_settings()

app = FastAPI(title=settings.app_name)


class NoStoreHtmlMiddleware(BaseHTTPMiddleware):
    """Prevent browsers from caching HTML (avoids stale PWA shells on shared ports)."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(NoStoreHtmlMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(dictionaries.router)
app.include_router(reports.router)
app.include_router(cash.router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(AccountantOnlyCash)
async def accountant_only_cash_handler(request: Request, exc: AccountantOnlyCash):
    return RedirectResponse("/cash", status_code=303)
