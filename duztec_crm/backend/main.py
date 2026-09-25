"""Duztec Sales CRM — app factory (port 8016). Routes live in routes_*.py."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, import_mis
from .config import LOGGER, SETTINGS
from . import (routes_customers, routes_dashboard, routes_documents, routes_enquiries, routes_operations,
               routes_products, routes_quotations, routes_targets)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=f"{SETTINGS.company_name} — Sales CRM", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PUBLIC_PATHS = ("/api/auth/request-otp", "/api/auth/verify", "/api/auth/me", "/api/auth/logout", "/api/health")


VIEWER_ALLOWED_WRITES = ("/api/auth/logout", "/api/auth/heartbeat")


@app.middleware("http")
async def _require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS:
        user = auth.current_user(request)
        if user is None:
            return JSONResponse(status_code=401, content={"detail": {"error_type": "unauthenticated",
                                                                     "detail": "Please log in."}})
        # View-only users: every non-GET call is refused centrally, whatever the endpoint.
        if user["role"] == "viewer" and request.method != "GET" and path not in VIEWER_ALLOWED_WRITES:
            return JSONResponse(status_code=403, content={"detail": {"error_type": "read_only",
                                                                     "detail": "Your account is view-only."}})
    return await call_next(request)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    LOGGER.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": {"error_type": "internal", "detail": str(exc)}})


@app.on_event("startup")
def _startup():
    db.init()
    auth.init()
    res = import_mis.run()
    LOGGER.info("Startup import: %s", res)
    db.backfill_states()
    db.seed_products()


for r in (routes_dashboard, routes_customers, routes_enquiries, routes_quotations, routes_operations, routes_documents,
          routes_products, routes_targets):
    app.include_router(r.router)
app.include_router(auth.router)

# ---------------------------------------------------------------- frontend
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html", headers=NO_CACHE)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(FRONTEND / "duztec-mark.png", media_type="image/png")


@app.get("/style.css", include_in_schema=False)
def css():
    return FileResponse(FRONTEND / "style.css", media_type="text/css", headers=NO_CACHE)


@app.get("/crm.js", include_in_schema=False)
def js():
    return FileResponse(FRONTEND / "crm.js", media_type="application/javascript", headers=NO_CACHE)


@app.get("/charts.js", include_in_schema=False)
def charts_js():
    # served here (not via /static) so browsers revalidate it like crm.js — a cached old copy breaks the dashboard
    return FileResponse(FRONTEND / "charts.js", media_type="application/javascript", headers=NO_CACHE)
