"""Recursive character splitter with overlap. Pure function, no I/O."""

_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split(text: str, limit: int, seps: list[str]) -> list[str]:
    """Break text into atomic segments of at most `limit` chars, keeping separators attached."""
    if len(text) <= limit:
        return [text]
    if not seps:
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    sep, rest = seps[0], seps[1:]
    parts = text.split(sep)
    out: list[str] = []
    for i, part in enumerate(parts):
        piece = part + sep if i < len(parts) - 1 else part
        if not piece:
            continue
        out.extend(_split(piece, limit, rest) if len(piece) > limit else [piece])
    return out


def chunk_text(text: str, size: int = 1000, overlap: int = 200) -> list[str]:
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")
    if not text.strip():
        return []

    # Atomic segments are capped at size-overlap so (overlap tail + segment) always fits in a chunk.
    segments = _split(text, size - overlap, _SEPARATORS)

    chunks: list[str] = []
    current = ""
    fresh = False  # does `current` contain anything beyond the carried-over overlap?
    for seg in segments:
        if fresh and len(current) + len(seg) > size:
            chunks.append(current)
            current = current[-overlap:] if overlap else ""
            fresh = False
        current += seg
        fresh = True
    if fresh:
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]
