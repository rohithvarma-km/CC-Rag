# Progress

Track your progress through the masterclass. Update this file as you complete modules - Claude Code reads this to understand where you are in the project.

## Convention
- `[ ]` = Not started
- `[-]` = In progress
- `[x]` = Completed

## Modules

### Module 1: App Shell + Observability  [x] Complete
- [x] Phase 1: backend/frontend scaffold, migration with RLS (`supabase/migrations/0001_threads_messages.sql`)
- [x] Phase 2: auth (Supabase email+password UI, backend JWT dependency) – pytest passes
- [x] Phase 3: chat via OpenAI Responses API + SSE, thread sidebar – pytest with mocked stream passes
- [x] Phase 4: LangSmith (`wrap_openai` + `@traceable` with user/thread metadata) – code in place
- [x] Live validation (API level, 2026-11-04):
  - Migration applied; RLS verified with two real users (cross-user select/insert/delete all blocked)
  - Streamed SSE chat, message persistence, and `previous_response_id` memory work
  - file_search grounded answer verified against the uploaded PDF, with the filename returned as a citation
  - LangSmith traces confirmed in project `agentic-rag` (chat_turn + LLM run with file_search, tokens, user/thread metadata)
  - Fixed during validation: `.env` was not exported to `os.environ`, so LangSmith tracing was silently off (`load_dotenv()` in `app/config.py`)
- [x] Browser walkthrough of the UI done manually by the user: sign up/in, session persistence, streamed grounded chat with citations, follow-up memory, history after reload, sign out, per-user isolation, thread delete all work
- [x] Alternate-flow browser tests with Playwright (2026-11-12): wrong password, duplicate sign-up, logged-out redirect to `/login`, failed chat turn (invalid model), deleting the active thread, second user sees empty sidebar - all pass
- [x] Fixed: orphan user message on failed OpenAI call (messages are now persisted only after a successful response; frontend rolls back optimistic bubbles and restores the input; test added)
- [x] Fixed: stale auth error persisted when toggling sign in / sign up
- [x] Cleanup: `rlstest-*` users deleted in Supabase (2026-11-12); verified `rlstest-a1` and `rlstest-b1` can no longer sign in

### Module 2: BYO Retrieval + Memory  [x] Released as 0.2 (2026-11-12); threshold tuning and test-user cleanup remain as follow-ups
Plan: `.agent/plans/2.byo-retrieval-memory.md`
- [x] Migration `supabase/migrations/0002_documents_chunks_retrieval.sql` written (documents, chunks vector(768) + HNSW, RLS, `match_chunks`, storage bucket + policies, Realtime) + `supabase/tests/0002_rls_check.sql` - **NOT yet applied**
- [x] Config/env: `LLM_*`, `EMBEDDING_*` + tunables (Ollama defaults); `OPENAI_*` removed
- [x] Backend: llm, chunking, embeddings, storage, ingestion (BackgroundTasks, state machine), retrieval (`search_documents` tool), agent (streaming tool loop), history; `/documents` router; chat rewritten on stateless Chat Completions with citations; Responses API removed
- [x] Frontend: AppLayout + Documents page (drag/drop, Realtime status, retry, delete), citation chips, "Searching documents..." indicator, rollback fix - `npm run build` clean
- [x] Tests: backend `pytest` 108 passed (fakes only, no network)
- [x] Migration 0002 applied (2026-11-12); RLS inventory: rls=true and 4 policies on documents, chunks, threads, messages
- [x] Local models live: `gemma4:e4b` chat + `embeddinggemma` (768 dims) via Ollama, with EmbeddingGemma query/doc prefixes; services restarted on Module 2 code
- [x] Live E2E validation with Playwright (2026-11-12): sign-up, identical sidebar + profile on both pages, .md upload pending->processing->completed via Realtime, .pdf rejected client-side (no request), non-UTF-8 .txt -> failed + Retry, chat with "Searching documents..." + citation chips (filename + similarity, expandable snippet) persisted across reload, follow-up memory, tool called only when needed
- [x] Two-user isolation: user B sees no documents/threads/chunks, cannot ingest/delete A's document (404), cannot download A's Storage object, and chat does not leak A's content; delete removes row, chunks and Storage object; no 500s in backend log
- [x] UI: Claude-style restyle (warm cream/terracotta theme, serif headings, dark mode via OS setting); one shared sidebar (wordmark, New chat, Chat/Documents nav, thread list, profile block with name + email + sign out) on both pages
- [x] Docs: README (env table, Ollama setup, migration order, privacy note) + ARCHITECTURE.md rewritten for Module 2; re-check after any further changes
- Known: cold-start latency ~11-12s (Ollama unloads models after 5 min idle; set `OLLAMA_KEEP_ALIVE`; warm turns ~2-6s, Supabase round trip ~0.1-0.2s); the assistant refuses general-knowledge questions by design (system prompt in `services/agent.py`); Documents page has no `<main>` landmark (a11y nit); composer text and an in-flight stream are lost when navigating Chat -> Documents -> Chat
- [ ] Still to do:
  - Delete test users `rlstest-a2@example.com` and `rlstest-b2@example.com` (Supabase -> Authentication -> Users)
  - Tune `RETRIEVAL_MIN_SIMILARITY` on more real documents (sample scores were 0.50-0.59 with a 0.25 cutoff)
  - Forced-failure rollback test (skipped as hard to trigger)
- [x] Committed and tagged `0.2` (2026-11-12); `docs/ARCHITECTURE.md` updated (release note, frontend layout, known limitations)
- [x] LangSmith trace structure verified (`chat_turn` with nested `embed_query`/`retrieve`/LLM spans; separate `ingest_document`)
- [x] Fixed: `tests/test_embeddings.py` leaked `EMBEDDING_*_PREFIX` from the local `backend/.env` (Settings reads `.env` directly); the test fixture now pins the prefixes. pytest: 108 passed

### Module 3: Record Manager  [x] Built and live-validated (2026-11-17); not yet committed
Plan: `.agent/plans/3.record-manager.md`
- [x] Migration `supabase/migrations/0003_documents_content_hash.sql` (`documents.content_hash`, unique `(user_id, filename)`) + `supabase/tests/0003_record_manager_check.sql` - **NOT yet applied** (run the pre-flight duplicate-filename query in the file first)
- [x] Backend: `services/record_manager.py` (`decide`: created / unchanged / retry / updated / conflict), `POST /documents` now takes `content_hash` and returns `{action, document}` (200 for unchanged, 409 for changed content while processing, unique-violation race re-resolved), `run_ingestion` hashes the downloaded bytes, rejects a mismatch with the declared hash and stores the server hash
- [x] Modified files are fully re-chunked and re-embedded (existing delete-first order kept: a failed update leaves no stale vectors); per-chunk diffing was considered and rejected
- [x] Frontend: SHA-256 via Web Crypto before upload, unchanged files skip upload and embedding, storage upload uses upsert, a failed upload only deletes rows it created, Ingestion page shows "already ingested (unchanged)" / "content changed, re-processing"
- [x] Tests: backend `pytest` 131 passed, 1 failed (`test_config.py::test_every_setting_in_env_example`, caused by the uncommitted removal of variables from `backend/.env.example`, not by Module 3); `npm run build` clean
- [x] Migration 0003 applied; `0003_record_manager_check.sql` passed (unique index + RLS)
- [x] Live E2E with Playwright + LangSmith (2026-11-17): full results in `.agent/plans/3.1.record-manager-test-plan.md`. Unchanged re-upload creates no row, no chunk changes and no `ingest_document` run; edited files keep the row id and replace every chunk; two-user isolation holds; races, retries and the 409 guard behave
- [x] Bug found and fixed in testing: overwriting a storage object in place and re-ingesting within ~1 min read stale CDN bytes (the hash check failed the document safely). `storage.download` now takes `version=content_hash` (`?v=` + `Cache-Control: no-cache`); tests added; pytest 134 passed + the 1 known `.env.example` failure
- Known, not Module 3: deleting a never-uploaded document returns 502 (`storage.delete` only treats 404 as missing; Supabase returns 400); LangSmith marks failed ingestions as success; pytest traces to the real LangSmith project
- [ ] Delete test users `rlstest-a3@example.com` and `rlstest-b3@example.com` (Supabase -> Authentication -> Users); their data is already deleted
- Deviations from plan: no backend storage-upsert test (uploads go straight from the browser, so only the frontend sets `upsert: true`); added a `conflict` action (409) when changed content arrives while the same document is `processing`

## Current status / next steps (2026-11-12)
- Release **0.2** (Module 2) is committed and tagged. Built and live-validated end-to-end against Supabase + local Ollama.
- **Next:** delete `rlstest-a2`/`rlstest-b2` users (Supabase -> Authentication -> Users), tune `RETRIEVAL_MIN_SIMILARITY`, then commit Module 3.
