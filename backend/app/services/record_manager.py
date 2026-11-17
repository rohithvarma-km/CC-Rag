"""Record manager: decide what an incoming upload means given what we already have. Pure function, no I/O.

A document's identity is (user, filename); its version is the SHA-256 of its bytes.
"""
from typing import Literal

Action = Literal["created", "unchanged", "retry", "updated", "conflict"]


def decide(existing: dict | None, incoming_hash: str) -> Action:
    if existing is None:
        return "created"
    status = existing.get("status")
    if existing.get("content_hash") == incoming_hash:
        # Same bytes. Skip if it is done or in flight; otherwise re-run it.
        return "unchanged" if status in ("completed", "processing") else "retry"
    # New bytes under a known filename. Do not swap content under a running ingestion.
    return "conflict" if status == "processing" else "updated"
