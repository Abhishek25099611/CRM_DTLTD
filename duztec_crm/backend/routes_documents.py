"""Documents: file uploads attached to customers, enquiries, quotations and orders.

Files live on disk under data/uploads/<entity_type>/<entity_id>/ and are served only to logged-in
users; the database row carries the metadata. The nightly backup must include the uploads folder.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from . import auth, db
from .config import LOGGER, SETTINGS
from .services import _is_admin, _scope

router = APIRouter()

ENTITY_TABLES = {"customer": "customers", "enquiry": "enquiries", "quotation": "quotations", "order": "orders"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _limits() -> tuple[int, set[str], list[str]]:
    u = SETTINGS.uploads
    max_bytes = int(float(u.get("max_mb", 25)) * 1024 * 1024)
    exts = {str(e).lower().lstrip(".") for e in (u.get("allowed_extensions") or ["pdf"])}
    return max_bytes, exts, [str(c) for c in (u.get("categories") or ["Other"])]


def _check_entity_access(request: Request, entity_type: str, entity_id: int, con) -> None:
    """Customers are shared; enquiry/quotation/order rows follow the RKZ scope of the caller."""
    table = ENTITY_TABLES.get(entity_type)
    if not table:
        raise HTTPException(422, {"error_type": "bad_entity", "detail": f"entity_type must be one of {', '.join(ENTITY_TABLES)}"})
    row = con.execute(f"SELECT * FROM {table} WHERE id=?", (entity_id,)).fetchone()
    if not row:
        raise HTTPException(404, {"error_type": "not_found", "detail": f"{entity_type} {entity_id}"})
    sc = _scope(request)
    if not sc or entity_type == "customer":
        return
    owner = (row["responsible"] if entity_type == "order" else row["salesperson"]) or ""
    if entity_type == "order" and not owner and row["quotation_id"]:
        q = con.execute("SELECT salesperson FROM quotations WHERE id=?", (row["quotation_id"],)).fetchone()
        owner = (q["salesperson"] if q else "") or ""
    if owner.strip().upper() != sc:
        raise HTTPException(403, {"error_type": "forbidden", "detail": f"This {entity_type} belongs to another RKZ code."})


@router.get("/api/documents")
def list_documents(request: Request, entity_type: str, entity_id: int):
    con = db.connect()
    _check_entity_access(request, entity_type, entity_id, con)
    out = db.rows(con.execute("""SELECT id, entity_type, entity_id, category, filename, size, mime, note, uploaded_by, uploaded_at
                                 FROM documents WHERE entity_type=? AND entity_id=? ORDER BY id DESC""",
                              (entity_type, entity_id)))
    con.close()
    return out


@router.get("/api/documents/categories")
def categories():
    max_bytes, exts, cats = _limits()
    return {"categories": cats, "allowed_extensions": sorted(exts), "max_mb": max_bytes // (1024 * 1024)}


@router.post("/api/documents")
async def upload_document(request: Request, entity_type: str = Form(...), entity_id: int = Form(...),
                          category: str = Form(""), note: str = Form(""), file: UploadFile = File(...)):
    max_bytes, exts, cats = _limits()
    original = Path(file.filename or "file").name
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in exts:
        raise HTTPException(422, {"error_type": "bad_type",
                                  "detail": f"File type .{ext or '?'} is not allowed. Allowed: {', '.join(sorted(exts))}"})
    category = category.strip() or cats[-1]
    con = db.connect()
    try:
        _check_entity_access(request, entity_type, entity_id, con)
        user = auth.current_user(request) or {}
        folder = SETTINGS.uploads_dir / entity_type / str(entity_id)
        folder.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex[:12]}_{_SAFE.sub('_', original)[:120]}"
        dest = folder / stored
        size = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    fh.close(); dest.unlink(missing_ok=True)
                    raise HTTPException(413, {"error_type": "too_large",
                                              "detail": f"File exceeds the {max_bytes // (1024 * 1024)} MB limit."})
                fh.write(chunk)
        cur = con.execute("""INSERT INTO documents(entity_type,entity_id,category,filename,stored_name,size,mime,note,uploaded_by,uploaded_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (entity_type, entity_id, category, original, stored, size, file.content_type or "",
                           note.strip(), user.get("email", ""), db.now()))
        db.log_activity(con, entity_type, entity_id, "document_uploaded", f"{original} ({category})")
        con.commit()
        return {"id": cur.lastrowid, "filename": original, "size": size}
    finally:
        con.close()


@router.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int, request: Request):
    con = db.connect()
    d = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"document {doc_id}"})
    _check_entity_access(request, d["entity_type"], d["entity_id"], con)
    con.close()
    path = SETTINGS.uploads_dir / d["entity_type"] / str(d["entity_id"]) / d["stored_name"]
    if not path.exists():
        raise HTTPException(410, {"error_type": "missing_file", "detail": "The file is missing on the server disk (restore from backup)."})
    return FileResponse(path, media_type=d["mime"] or "application/octet-stream", filename=d["filename"])


@router.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, request: Request):
    con = db.connect()
    d = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"document {doc_id}"})
    user = auth.current_user(request) or {}
    if not _is_admin(request) and user.get("email") != d["uploaded_by"]:
        con.close(); raise HTTPException(403, {"error_type": "forbidden", "detail": "Only an admin or the person who uploaded the file can delete it."})
    path = SETTINGS.uploads_dir / d["entity_type"] / str(d["entity_id"]) / d["stored_name"]
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        LOGGER.warning("Could not remove %s: %s", path, e)
    con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    db.log_activity(con, d["entity_type"], d["entity_id"], "document_deleted", d["filename"])
    con.commit(); con.close()
    return {"ok": True}
