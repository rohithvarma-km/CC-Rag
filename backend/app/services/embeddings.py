import openai
from langsmith import traceable

from app.config import get_settings
from app.services.llm import get_embedding_client, provider_unavailable


class EmbeddingDimensionError(RuntimeError):
    pass


def to_pgvector(v: list[float]) -> str:
    """Text literal accepted by pgvector / PostgREST for a vector column."""
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


async def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    """Embed texts in batches, preserving order. Applies optional task prefixes."""
    if not texts:
        return []
    s = get_settings()
    prefix = s.embedding_query_prefix if is_query else s.embedding_doc_prefix
    client = get_embedding_client()
    out: list[list[float]] = []
    for i in range(0, len(texts), s.embedding_batch_size):
        batch = [prefix + t for t in texts[i : i + s.embedding_batch_size]]
        try:
            resp = await client.embeddings.create(model=s.embedding_model, input=batch)
        except openai.APIConnectionError as e:
            raise provider_unavailable(s.embedding_base_url) from e
        vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        if len(vectors) != len(batch):
            raise RuntimeError(f"Embedding provider returned {len(vectors)} vectors for {len(batch)} inputs")
        for v in vectors:
            if len(v) != s.embedding_dim:
                raise EmbeddingDimensionError(
                    f"Embedding model '{s.embedding_model}' returned {len(v)} dims, expected {s.embedding_dim}"
                )
        out.extend(vectors)
    return out


@traceable(name="embed_query", run_type="chain")
async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text], is_query=True))[0]
