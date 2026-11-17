# Project Context: Agentic RAG Masterclass App

A RAG web app built step by step (module by module) with Claude Code as a learning project. Users sign up, upload text documents, and chat with an AI that searches those documents. Config is via env vars only (no admin UI), until Module 3.5 adds an admin-only settings page for model and parameter settings.

## Status
- **Module 1** (app shell + observability): done. Used the OpenAI Responses API; since removed.
- **Module 2** (BYO retrieval + memory): done, tagged `0.2`. Live-tested end to end.
- **Module 3** (record manager): done, tagged `0.3` (commit `5bf669b`, local only). Live-tested with Playwright + LangSmith.
- **Next: Module 3.5** (admin-only model settings + roles; nothing built yet; plan goes in `.agent/plans/3.5.model-settings-roles.md`). Then Module 4. Open follow-ups: tune `RETRIEVAL_MIN_SIMILARITY` (0.25 now; real scores are about 0.50-0.59), delete leftover `rlstest-a2/b2/a3/b3` Supabase test users.
- **Planned**: M4 metadata extraction and filtering, M5 PDF/DOCX/HTML via docling, M6 hybrid search and reranking, M7 text-to-SQL and web search tools, M8 sub-agents.

## Stack
- **Frontend**: React 19, TypeScript, Vite, Tailwind 4, shadcn/ui, react-router. Warm cream/terracotta theme, dark mode follows the OS.
- **Backend**: Python, FastAPI, `venv`, raw `openai` SDK and Pydantic. No LangChain or LangGraph.
- **Database**: Supabase (Postgres, pgvector, Auth, Storage, Realtime).
- **Models**: any OpenAI-compatible endpoint. Defaults to local Ollama (`gemma4:e4b` chat, `embeddinggemma` at 768 dims).
- **Observability**: LangSmith (`chat_turn` and `ingest_document` traces).

## Hard rules (from CLAUDE.md)
- Raw SDK calls only, with Pydantic for structured outputs.
- RLS on every table, so users only see their own data. The backend never uses a service-role key. It builds a per-request Supabase client with the caller's JWT.
- Chat streams over SSE. Ingestion status uses Supabase Realtime.
- Stateless completions: we store and resend chat history ourselves.
- Ingestion is manual file upload only (no connectors).
- Workflow: plan (saved in `.agent/plans/N.name.md`), build, validate (Playwright), iterate. Update `PROGRESS.md` as tasks finish.

## How it works
- **Ingestion**: the browser uploads `.txt`/`.md` (max 5 MB) to a private Storage bucket (`{user_id}/{doc_id}`). The browser SHA-256 hashes the file and `POST /documents {filename, size_bytes, content_hash}` is the record manager: identity is `(user, filename)`, version is the hash. Outcomes: `created`; `unchanged` (skip, no upload or embedding); `retry` (same hash after a failure); `updated` (new hash, same row and storage object); 409 if new content arrives while the document is processing. `POST /documents/{id}/ingest` runs a background task: download (versioned URL `?v=hash`, no-cache, because overwritten objects can be served stale by the CDN), verify the bytes against the declared hash (mismatch fails the document), decode, recursive chunking (1000 chars, 200 overlap), batch embed, insert into `chunks`; a changed file is fully re-chunked and re-embedded with the old chunks deleted first (no per-chunk diffing). Status goes `pending -> processing -> completed | failed` and is pushed live via Realtime. Retry and delete are supported.
- **Retrieval**: the Postgres function `match_chunks` (security invoker, cosine similarity, HNSW index, min-similarity filter) searches only `completed` documents.
- **Chat** (`POST /threads/{id}/chat`): a tool-calling loop (max 3 iterations). The model gets a `search_documents` tool and decides when to call it. It loads a bounded history window (20 messages, 24k chars) and streams deltas via SSE. Events: `tool`, `delta`, `done` (with citations and title), `error`. The user and assistant messages are saved only after success. Citations (filename, chunk, snippet, similarity) are stored in `messages.citations`.
- **System prompt**: the assistant answers only from documents and refuses general-knowledge questions (in `services/agent.py`).

## Layout
```
backend/app/        main.py, auth.py (JWT), config.py (pydantic-settings), db.py, schemas.py
  routers/          chat.py, documents.py, threads.py
  services/         agent.py (tool loop), llm.py, embeddings.py, chunking.py,
                    ingestion.py, record_manager.py, retrieval.py, history.py, storage.py
backend/tests/      pytest with fakes, no network (134 passing; 1 unrelated failure, the `test_config.py` env-example check, caused by the trimmed `.env.example`)
frontend/src/       pages/ (Chat, Ingestion, Login), components/ (AppLayout, chat/Citations,
                    documents/*, ui/*), lib/ (api, supabase, documents, threads)
supabase/migrations 0001_threads_messages.sql, 0002_documents_chunks_retrieval.sql, 0003_documents_content_hash.sql (all applied)
supabase/tests/     0002_rls_check.sql, 0003_record_manager_check.sql (run manually in the SQL editor)
docs/ARCHITECTURE.md  detailed plain-English walkthrough
.agent/plans/       1.app-shell-observability.md, 2.byo-retrieval-memory.md, 3.record-manager.md,
                    3.1.record-manager-test-plan.md (test plan + results)
PRD.md, PROGRESS.md, CLAUDE.md, README.md, scripts/start-services.sh
```

## Running it
- Needs `backend/.env` and `frontend/.env` (see the `.env.example` files), Supabase migrations applied in order, and Ollama running with the two models pulled.
- Start or stop both services (backend :8000, frontend :5173): `scripts/start-services.sh` or `scripts/start-services.sh stop`.
- Tests: `cd backend && venv/bin/python -m pytest`. Frontend check: `cd frontend && npm run build`.

## Known limitations
- Only `.txt` and `.md`. The embedding dimension is locked to `vector(768)` (changing it needs a migration and re-ingest). Dedup is by filename + SHA-256 content hash (Module 3).
- Deleting a document whose file was never uploaded returns 502 and leaves the row (`storage.delete` only treats 404 as missing; Supabase returns 400). LangSmith shows failed ingestions as `success`, and `pytest` sends traces to the real LangSmith project.
- Ollama cold start takes about 11-12 s (set `OLLAMA_KEEP_ALIVE`).
- Composer text and an in-flight stream are lost when switching between the Chat and Documents pages.
- The Documents page has no `<main>` landmark (a11y nit).
- Privacy: local models still send documents and chunks to cloud Supabase. LangSmith traces include prompts and chunk text (`LANGSMITH_TRACING=false` disables them).

## Git state
Branch `master`. Latest commits: `0.3` Module 3 (`5bf669b`, tagged, not pushed), LangSmith trace verification docs, `0.2` Module 2, `0.1.1` fixes. `origin` is a GitHub repo; nothing from Module 3 is pushed yet. Uncommitted on purpose: `PRD.md` (Module 3 decisions and the new Module 3.5 section), `backend/.env.example` (trimmed, removing the tunables for embedding dimension, batch size, chunk size, retrieval and so on; this is why one test fails, and `docs/ARCHITECTURE.md` and the README still describe those variables, so check whether the trim was intentional), `context.md`, and the doc updates to `PROGRESS.md` and `docs/ARCHITECTURE.md`.

## Rollback
`git switch -c recover 0.3` returns to the Module 3 code without touching `master`. Git does not roll back the Supabase schema: migration 0003 stays applied (the 0.3 code works with it; the 0.2 code would not, because of the unique filename index). Keep Module 3.5 migrations additive.
