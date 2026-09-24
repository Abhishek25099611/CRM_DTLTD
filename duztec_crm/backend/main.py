"""Duztec Sales CRM — app factory (port 8016). Routes live in routes_*.py."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, import_mis
from .config import LOGGER, SETTINGS
from . import routes_customers, routes_dashboard, routes_enquiries, routes_operations, routes_quotations

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=f"{SETTINGS.company_name} — Sales CRM", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PUBLIC_PATHS = ("/api/auth/login", "/api/auth/request-otp", "/api/auth/set-password",
                "/api/auth/me", "/api/auth/logout", "/api/health")


@app.middleware("http")
async def _require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS:
        if auth.current_user(request) is None:
            return JSONResponse(status_code=401, content={"detail": {"error_type": "unauthenticated",
                                                                     "detail": "Please log in."}})
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


for r in (routes_dashboard, routes_customers, routes_enquiries, routes_quotations, routes_operations):
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
