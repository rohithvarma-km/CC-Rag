"""Document ingestion: download -> decode -> chunk -> embed -> store. Runs as a background task."""
import logging
from datetime import datetime, timedelta, timezone

from langsmith import traceable

from app.config import get_settings
from app.services import storage
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingDimensionError, embed_texts, to_pgvector
from app.services.llm import ProviderUnavailableError

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)
INSERT_BATCH = 100


class IngestionError(Exception):
    """A user-presentable ingestion failure."""


def claimable_filter(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - STALE_AFTER).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"status.in.(pending,failed),and(status.eq.processing,updated_at.lt.{cutoff})"


def claim_document(db, doc_id: str) -> dict | None:
    """Atomically move a claimable document to processing. Returns the row, or None if not claimable."""
    res = (
        db.table("documents")
        .update({"status": "processing", "error": None})
        .eq("id", doc_id)
        .or_(claimable_filter())
        .execute()
    )
    return res.data[0] if res.data else None


def decode_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise IngestionError("File is not valid UTF-8 text") from e
    text = text.replace("\x00", "")
    if not text.strip():
        raise IngestionError("File is empty")
    return text


def _safe_error(e: Exception) -> str:
    if isinstance(e, (IngestionError, ProviderUnavailableError, EmbeddingDimensionError, storage.StorageNotFound)):
        msg = str(e) or type(e).__name__
        if isinstance(e, storage.StorageNotFound):
            msg = "Uploaded file not found in storage"
        return msg[:500]
    return f"Unexpected error ({type(e).__name__})"


@traceable(
    name="ingest_document",
    run_type="chain",
    process_inputs=lambda i: {"document_id": i["doc"]["id"], "user_id": i["doc"].get("user_id")},
)
async def run_ingestion(db, token: str, doc: dict) -> None:
    """Never raises. On failure the document is marked failed with a user-safe error."""
    doc_id = doc["id"]
    try:
        s = get_settings()
        raw = await storage.download(doc["storage_path"], token)
        if len(raw) > s.max_upload_bytes:
            raise IngestionError(f"File exceeds the {s.max_upload_bytes} byte limit")
        text = decode_text(raw)
        db.table("chunks").delete().eq("document_id", doc_id).execute()
        chunks = chunk_text(text, s.chunk_size, s.chunk_overlap)
        if not chunks:
            raise IngestionError("File is empty")
        vectors = await embed_texts(chunks)
        rows = [
            {
                "document_id": doc_id,
                "user_id": doc["user_id"],
                "chunk_index": i,
                "content": c,
                "embedding": to_pgvector(v),
            }
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ]
        for i in range(0, len(rows), INSERT_BATCH):
            db.table("chunks").insert(rows[i : i + INSERT_BATCH]).execute()
        db.table("documents").update(
            {"status": "completed", "error": None, "chunk_count": len(rows)}
        ).eq("id", doc_id).execute()
    except Exception as e:  # noqa: BLE001 - background task must never raise
        log.exception("Ingestion failed for document %s", doc_id)
        try:
            db.table("chunks").delete().eq("document_id", doc_id).execute()
        except Exception:  # noqa: BLE001
            log.warning("Chunk cleanup failed for document %s", doc_id)
        try:
            db.table("documents").update(
                {"status": "failed", "error": _safe_error(e), "chunk_count": 0}
            ).eq("id", doc_id).execute()
        except Exception:  # noqa: BLE001
            log.warning("Could not mark document %s failed", doc_id)
