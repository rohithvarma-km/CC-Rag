import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import user_client
from app.schemas import DocumentCreate, DocumentCreateOut, DocumentOut
from app.services import ingestion, storage
from app.services.record_manager import decide

router = APIRouter(prefix="/documents", tags=["documents"])

COLUMNS = "id,filename,status,error,chunk_count,size_bytes,storage_path,content_hash,created_at,updated_at"
ALLOWED_EXT = (".txt", ".md")


@router.get("", response_model=list[DocumentOut])
def list_documents(user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    return db.table("documents").select(COLUMNS).order("created_at", desc=True).execute().data


def _find_by_filename(db, filename: str) -> dict | None:
    rows = db.table("documents").select(COLUMNS).eq("filename", filename).limit(1).execute().data
    return rows[0] if rows else None


def _is_unique_violation(e: Exception) -> bool:
    return getattr(e, "code", None) == "23505" or "23505" in str(e)


@router.post("", response_model=DocumentCreateOut, status_code=201)
def create_document(body: DocumentCreate, response: Response, user: CurrentUser = Depends(get_current_user)):
    """Record manager: decide whether this upload is new, unchanged, a retry or an update."""
    if not body.filename.lower().endswith(ALLOWED_EXT):
        raise HTTPException(422, "Only .txt and .md files are supported")
    if body.size_bytes <= 0:
        raise HTTPException(422, "File is empty")
    limit = get_settings().max_upload_bytes
    if body.size_bytes > limit:
        raise HTTPException(422, f"File exceeds the {limit} byte limit")

    db = user_client(user)
    content_hash = body.content_hash.lower()
    existing = _find_by_filename(db, body.filename)
    action = decide(existing, content_hash)

    if action == "created":
        doc_id = str(uuid.uuid4())
        row = {
            "id": doc_id,
            "user_id": user.id,
            "filename": body.filename,
            "size_bytes": body.size_bytes,
            "content_hash": content_hash,
            "status": "pending",
            "storage_path": f"{user.id}/{doc_id}",
        }
        try:
            res = db.table("documents").insert(row).execute()
            return {"action": "created", "document": res.data[0] if res.data else row}
        except Exception as e:  # noqa: BLE001
            if not _is_unique_violation(e):
                raise
            # Lost a race with a concurrent upload of the same filename: decide again against the winner.
            existing = _find_by_filename(db, body.filename)
            if existing is None:
                raise
            action = decide(existing, content_hash)

    if action == "conflict":
        raise HTTPException(409, "This document is being processed; try again in a moment")
    if action == "unchanged":
        response.status_code = 200
        return {"action": "unchanged", "document": existing}

    # retry (same bytes, previous attempt failed or never started) or updated (new bytes): keep id and storage_path.
    changes = {"status": "pending", "error": None}
    if action == "updated":
        changes.update({"content_hash": content_hash, "size_bytes": body.size_bytes})
    res = db.table("documents").update(changes).eq("id", existing["id"]).execute()
    return {"action": action, "document": res.data[0] if res.data else {**existing, **changes}}


@router.post("/{doc_id}/ingest", status_code=202)
def ingest_document(doc_id: str, background: BackgroundTasks, user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    doc = ingestion.claim_document(db, doc_id)
    if doc is None:
        visible = db.table("documents").select("id").eq("id", doc_id).execute().data
        if not visible:
            raise HTTPException(404, "Document not found")
        raise HTTPException(409, "Document is already being processed or completed")
    background.add_task(ingestion.run_ingestion, db, user.token, doc)
    return {"id": doc_id, "status": "processing"}


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    rows = db.table("documents").select("id,storage_path").eq("id", doc_id).execute().data
    if not rows:
        raise HTTPException(404, "Document not found")
    try:
        await storage.delete(rows[0]["storage_path"], user.token)
    except httpx.HTTPError:
        raise HTTPException(502, "Could not delete the stored file; try again")
    db.table("documents").delete().eq("id", doc_id).execute()
    return Response(status_code=204)
