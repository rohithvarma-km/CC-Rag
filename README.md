# Cloud Code Agentic RAG Masterclass

Build an agentic RAG application from scratch by collaborating with Claude Code. Follow along with our video series using the docs in this repo.

[![Claude Code RAG Masterclass](./video-thumbnail.png)](https://www.youtube.com/watch?v=xgPWCuqLoek)

[Watch the full video on YouTube](https://www.youtube.com/watch?v=xgPWCuqLoek)

## What This Is

A hands-on course where you collaborate with Claude Code to build a full-featured RAG system. You're not the one writing code—Claude is. Your job is to guide it, understand what you're building, and course-correct when needed.

**You don't need to know how to code.** You do need to be technically minded and willing to learn about APIs, databases, and system architecture.

## What You'll Build

- **Chat interface** with threaded conversations, streaming, tool calls, and subagent reasoning
- **Document ingestion** with drag-and-drop upload and processing status
- **Full RAG pipeline**: chunking, embedding, hybrid search, reranking
- **Agentic patterns**: text-to-SQL, web search, subagents with isolated context

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React, TypeScript, Tailwind, shadcn/ui, Vite |
| Backend | Python, FastAPI |
| Database | Supabase (Postgres + pgvector + Auth + Storage) |
| Doc Processing | Docling |
| AI Models | Local (LM Studio) or Cloud (OpenAI, OpenRouter) |
| Observability | LangSmith |

## The 8 Modules

1. **App Shell** — Auth, chat UI, managed RAG (replaced by our own pipeline in Module 2)
2. **BYO Retrieval + Memory** — Ingestion, pgvector, switch to generic completions API
3. **Record Manager** — Content hashing, deduplication
4. **Metadata Extraction** — LLM-extracted metadata, filtered retrieval
5. **Multi-Format Support** — PDF, DOCX, HTML, Markdown via Docling
6. **Hybrid Search & Reranking** — Keyword + vector search, RRF, reranking
7. **Additional Tools** — Text-to-SQL, web search fallback
8. **Subagents** — Isolated context, document analysis delegation

## Getting Started

1. Clone this repo
2. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
3. Open in your IDE (Cursor, VS Code, etc.)
4. Run `claude` in the terminal
5. Use the `/onboard` command to get started

## Docs

- [PRD.md](./PRD.md) — What to build (the 8 modules in detail)
- [CLAUDE.md](./CLAUDE.md) — Context for Claude Code
- [PROGRESS.md](./PROGRESS.md) — Track your build progress

## Join the Community

If you want to connect with hundreds of builders creating production-grade AI and RAG systems, join us in [The AI Automators community](https://www.theaiautomators.com/). Share your progress, get help when you're stuck, and see what others are building.

## Run instructions (Module 2)

### 1. Models (default: local Ollama)

```
ollama pull embeddinggemma   # embeddings, 768 dimensions
ollama pull gemma4:e4b       # chat model (supports tool calling)
```

Ollama serves an OpenAI-compatible API at `http://localhost:11434/v1`, which is the default `LLM_BASE_URL`. Keep Ollama running while you use the app. If it is unreachable, ingestion marks the document `failed` and chat shows "Cannot reach model provider at <url>".

Tool-calling caveat: retrieval works by the model calling a `search_documents` tool, so the chat model must support tool calling. Small local models can be unreliable at it (they may skip the tool, or emit malformed arguments). If answers ignore your documents, switch `LLM_*` to a stronger tool-capable model (see below).

### 2. Supabase

1. Create a Supabase project and run `supabase/migrations/0001_threads_messages.sql`, then `supabase/migrations/0002_documents_chunks_retrieval.sql` in the SQL editor.
2. **Apply 0002 BEFORE restarting the backend.** It is destructive: it drops `threads.openai_last_response_id` and `messages.openai_response_id` (Module 1 memory). The old backend breaks once they are gone, and the new backend breaks without the new tables. Order: stop services, migrate, update `.env`, start.
3. 0002 creates `documents` and `chunks` (pgvector), the `match_chunks` function, a private `documents` Storage bucket, RLS policies on all of them, and enables Realtime on `documents`. It is idempotent.

### 3. Start

```
cd backend && cp .env.example .env     # fill in Supabase values
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cd ../frontend && cp .env.example .env && npm install
cd .. && scripts/start-services.sh     # backend :8000, frontend :5173, logs in .logs/
```

`scripts/start-services.sh` runs uvicorn **without `--reload`**, so re-run it (it restarts both services) after any backend change or `.env` edit. Stop with `scripts/start-services.sh stop`.

Tests: `cd backend && venv/bin/python -m pytest`. Frontend check: `cd frontend && npm run build`.

### 4. Use it

- **Documents page** (`/ingestion`): drag and drop `.txt` or `.md` files. Supported: UTF-8 text, up to 5 MB (`MAX_UPLOAD_BYTES`). Status updates live (pending, processing, completed, failed) via Supabase Realtime. Failed documents can be retried; documents can be deleted (removes the file, chunks and row).
- **Chat page** (`/`): ask questions. The model searches your documents when relevant, streams its answer, and shows citation chips (filename, snippet, similarity).

### Backend environment variables

All are read from `backend/.env` (see `backend/.env.example`). Every field of `Settings` in `backend/app/config.py` is listed.

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | (empty) | Supabase project URL. |
| `SUPABASE_ANON_KEY` | (empty) | Supabase anon key. The backend acts as the user with their JWT; no service-role key is used. |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed browser origins. |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible Chat Completions endpoint. |
| `LLM_API_KEY` | `ollama` | API key for that endpoint (any placeholder for Ollama). |
| `LLM_MODEL` | `gemma4:e4b` | Chat model name. Must support tool calling. |
| `EMBEDDING_BASE_URL` | (empty, falls back to `LLM_BASE_URL`) | Embeddings endpoint. |
| `EMBEDDING_API_KEY` | (empty, falls back to `LLM_API_KEY`) | Embeddings API key. |
| `EMBEDDING_MODEL` | `embeddinggemma` | Embedding model name. |
| `EMBEDDING_DIM` | `768` | Expected vector size. Must equal `vector(N)` in migration 0002. |
| `EMBEDDING_QUERY_PREFIX` | (empty) | Text prepended to search queries. EmbeddingGemma works best with `task: search result | query: `. |
| `EMBEDDING_DOC_PREFIX` | (empty) | Text prepended to chunks when embedding. EmbeddingGemma: `title: none | text: `. |
| `EMBEDDING_BATCH_SIZE` | `64` | Chunks per embeddings request. |
| `CHUNK_SIZE` | `1000` | Chunk size in characters. Must be 1 to 1500 (embedding context limit); checked at startup. |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks in characters. Must be >= 0 and < `CHUNK_SIZE`. |
| `MAX_UPLOAD_BYTES` | `5000000` | Maximum upload size. |
| `RETRIEVAL_TOP_K` | `5` | Default number of chunks per search (the tool clamps requests to 1 to 10). |
| `RETRIEVAL_MIN_SIMILARITY` | `0.25` | Minimum cosine similarity for a chunk to be returned. Tune on your own documents. |
| `MAX_TOOL_ITERATIONS` | `3` | Max model calls per turn; the last one is forced to answer without tools. |
| `HISTORY_MAX_MESSAGES` | `20` | Max stored messages resent to the model each turn. |
| `HISTORY_MAX_CHARS` | `24000` | Character budget for the resent history (oldest dropped first). |
| `LANGSMITH_TRACING` | `true` (in `.env.example`) | Set `false` to disable tracing. Read directly by the LangSmith SDK. |
| `LANGSMITH_API_KEY` | (none) | LangSmith key. Read by the SDK. |
| `LANGSMITH_PROJECT` | `agentic-rag` | LangSmith project name. Read by the SDK. |

Frontend (`frontend/.env`): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`.

### Using OpenRouter or OpenAI instead of Ollama

Any OpenAI-compatible endpoint works for chat; point the `LLM_*` variables at it:

```
# OpenRouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
LLM_MODEL=<a tool-capable model id>

# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini
```

Embeddings follow `LLM_*` unless you set `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` (use this when your chat provider has no embeddings endpoint, for example keep embeddings on Ollama while chatting via OpenRouter). Set `EMBEDDING_MODEL` accordingly.

### Embedding dimension is locked to 768

The `chunks.embedding` column and the `match_chunks` function are `vector(768)` to match `embeddinggemma`. The backend checks every returned vector against `EMBEDDING_DIM` and fails ingestion early on a mismatch. To use a model with a different dimension you must (1) write a new migration that changes the column and function to `vector(N)` (and rebuilds the HNSW index), (2) set `EMBEDDING_DIM=N` and `EMBEDDING_MODEL`, and (3) re-ingest all documents, since old vectors are not comparable across models. Changing only the model name, even at the same dimension, also requires re-ingesting.

### Privacy: local models do not mean local data

Ollama only runs inference. Your original files (private Storage bucket `documents`), chunk text, embeddings, threads and messages live in your cloud-hosted Supabase project. LangSmith tracing also uploads prompts, answers and retrieved chunk text. To keep content out of LangSmith set `LANGSMITH_TRACING=false`. A fully local setup would additionally need a self-hosted Supabase stack (only `SUPABASE_URL` and the keys change).

See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for how it all fits together.
