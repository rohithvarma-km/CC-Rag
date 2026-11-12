import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.db import user_client
from app.schemas import DocumentCreate, DocumentOut
from app.services import ingestion, storage

router = APIRouter(prefix="/documents", tags=["documents"])

COLUMNS = "id,filename,status,error,chunk_count,size_bytes,storage_path,created_at,updated_at"
ALLOWED_EXT = (".txt", ".md")


@router.get("", response_model=list[DocumentOut])
def list_documents(user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    return db.table("documents").select(COLUMNS).order("created_at", desc=True).execute().data


@router.post("", response_model=DocumentOut, status_code=201)
def create_document(body: DocumentCreate, user: CurrentUser = Depends(get_current_user)):
    if not body.filename.lower().endswith(ALLOWED_EXT):
        raise HTTPException(422, "Only .txt and .md files are supported")
    if body.size_bytes <= 0:
        raise HTTPException(422, "File is empty")
    limit = get_settings().max_upload_bytes
    if body.size_bytes > limit:
        raise HTTPException(422, f"File exceeds the {limit} byte limit")
    doc_id = str(uuid.uuid4())
    row = {
        "id": doc_id,
        "user_id": user.id,
        "filename": body.filename,
        "size_bytes": body.size_bytes,
        "status": "pending",
        "storage_path": f"{user.id}/{doc_id}",
    }
    res = user_client(user).table("documents").insert(row).execute()
    return res.data[0] if res.data else row


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
