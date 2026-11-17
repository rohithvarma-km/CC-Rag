# Agentic RAG Masterclass - PRD

## What We're Building

A RAG application with two interfaces:
1. **Chat** (default view) - Threaded conversations with retrieval-augmented responses
2. **Ingestion** - Upload files manually, track processing, manage documents

This is **not** an automated pipeline with connectors. Files are uploaded manually via drag-and-drop. Configuration is via environment variables, no admin UI.

## Target Users

Technically-minded people who want to build production RAG systems using AI coding tools (Claude Code, Cursor, etc.). They don't need to know Python or React - that's the AI's job.

**They need to understand:**
- RAG concepts deeply (chunking, embeddings, retrieval, reranking)
- Codebase structure (what sits where, how pieces connect)
- How to direct AI to build what they need
- How to direct AI to fix things when they break

## Scope

### In Scope
- ✅ Document ingestion and processing
- ✅ Vector search with pgvector
- ✅ Hybrid search (keyword + vector)
- ✅ Reranking
- ✅ Metadata extraction
- ✅ Record management (deduplication)
- ✅ Multi-format support (PDF, DOCX, HTML, Markdown)
- ✅ Text-to-SQL tool
- ✅ Web search fallback
- ✅ Sub-agents with isolated context
- ✅ Chat with threads and memory
- ✅ Streaming responses
- ✅ Auth with RLS

### Out of Scope
- ❌ Knowledge graphs / GraphRAG
- ❌ Code execution / sandboxing
- ❌ Image/audio/video processing
- ❌ Fine-tuning
- ❌ Multi-tenant admin features
- ❌ Billing/payments
- ❌ Data connectors (Google Drive, SFTP, APIs, webhooks)
- ❌ Scheduled/automated ingestion
- ❌ Admin UI (config via env vars) - except the admin-only model/parameter settings page planned for Module 3.5

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Backend | Python + FastAPI |
| Database | Supabase (Postgres + pgvector + Auth + Storage + Realtime) |
| LLM (Module 1) | OpenAI Responses API (managed threads + file_search) |
| LLM (Module 2+) | Any OpenAI-compatible endpoint (OpenRouter, Ollama, LM Studio, etc.) |
| Observability | LangSmith |

## Constraints

- No LLM frameworks - raw OpenAI SDK using the standard Chat Completions API (OpenAI-compatible), Pydantic for structured outputs
- Row-Level Security on all tables - users only see their own data
- Streaming chat via SSE
- Ingestion status via Supabase Realtime

---

## Module 1: The App Shell + Observability

**Build:** Auth, chat UI, OpenAI Responses API (manages threads + file_search), LangSmith tracing

**Learn:** What RAG is, why managed RAG exists, its limitations (OpenAI handles memory and retrieval - black box)

**Note:** The Responses API is OpenAI-specific. It provides managed threads and built-in file search, but locks you into OpenAI. Module 2 transitions to the standard Chat Completions API for provider flexibility.

---

## Architectural Decision: Module 1 → Module 2 Transition

At the end of Module 1, you have a working chat app using OpenAI's **Responses API**—a managed solution where OpenAI handles threads, memory, and file search. In Module 2, you switch to the standard **Chat Completions API** to support any OpenAI-compatible provider (OpenRouter, Ollama, LM Studio, etc.).

**The decision you need to make:** What do you do with the Responses API code? Here are two common approaches, but you're not limited to these—come up with your own if it makes sense for your use case.

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **A: Replace** | Remove Responses API code entirely, rebuild on Chat Completions | Clean codebase, single pattern, easier to maintain | Lose the ability to use OpenAI's managed RAG |
| **B: Dual Support** | Keep Responses API alongside Chat Completions, configurable per request | Flexibility to use either approach, compare them side-by-side | More complex codebase, two patterns to understand |

There is no right answer—this is a real architectural choice you'll face in building production systems.

**In the video, I chose Option A**—completely removing the Responses API code from the codebase and any related schema from the database. This keeps things simple and focused on the OpenAI-compatible Chat Completions pattern going forward.

**This is a lesson in steering Claude Code**: you need to clearly communicate your decision and guide the AI to implement it correctly. Be explicit about what you want removed, refactored, or kept.

---

## Module 2: BYO Retrieval + Memory

**Prerequisites:** Complete the architectural decision above.

**Build:** Ingestion UI, file storage, chunking → embedding → pgvector, retrieval tool, Chat Completions API integration (OpenRouter/Ollama/LM Studio), chat history storage (stateless API - you manage memory now), realtime ingestion status

**Learn:** Chunking, embeddings, vector search, tool calling, relevance thresholds, managing conversation history, **steering AI agents through architectural refactoring**

---

## Module 3: Record Manager

**Status:** Released as `0.3` (2026-11-17).

**Build:** Content hashing, detect changes, only process what's new/modified

**Learn:** Why naive ingestion duplicates, incremental updates

**Decisions made:**
- **Identity and version:** a document is identified by `(user, filename)`; its version is the SHA-256 of the file bytes.
- **Outcomes of an upload:** new filename → created; same hash → skipped with an "already ingested (unchanged)" notice (no upload, no embedding calls); same hash after a failure → retried on the same row; new hash → the same row is updated in place; new hash while the document is processing → rejected with 409.
- **Re-processing granularity:** a changed file is fully re-chunked and re-embedded, with the old chunks deleted first, so a failed update never leaves a half-old document. Per-chunk hashing and partial re-embedding were considered and rejected: the added complexity (atomic SQL swap, index collisions, embedding-config invalidation) outweighed the savings.
- **Trust:** the browser hashes the file, but the server re-hashes the stored bytes and fails the document on a mismatch.
- **Storage caching:** overwriting a stored file in place can serve stale bytes from the storage CDN for about a minute, so ingestion downloads a versioned URL.

---

## Module 3.5: Model Settings + Roles

**Status:** Not started. Sits between Module 3 and Module 4. It will be planned in `.agent/plans/3.5.model-settings-roles.md`.

**Build:** A settings page reachable from the user menu at the bottom of the sidebar, plus a minimal roles system.
- **Admins** can change the chat LLM (local or online provider), the embedding model, and the chunking/embedding parameters.
- **Regular users** get a read-only view; they cannot change anything.
- **Locking:** the embedding model, dimension and prefixes cannot be changed once chunks exist.

**Learn:** Roles with Row-Level Security, runtime configuration versus env vars, what changing an embedding model means for already-indexed data.

**Scope exception:** this deliberately supersedes the "no admin UI / config via env vars" rule for model and parameter settings only. Everything else stays env-configured.

**Open decisions for the plan:**
- API keys for online providers stay in env vars (the backend has no service-role key, so non-admin chats could not read keys stored in the database).
- The first admin is set once via SQL.
- How settings are stored and read per request (and how chat and ingestion pick them up).
- What happens to existing documents when chunking parameters change (mark stale and offer re-ingest, or only apply to new uploads).

**Safety:** keep the migrations additive (new tables and columns only) so the code can be rolled back to `0.3` without breaking the database. Tag the result `0.3.5`.

---

## Module 4: Metadata Extraction

**Build:** LLM extracts structured metadata, filter retrieval by metadata

**Learn:** Structured extraction, schema design, metadata-enhanced retrieval

---

## Module 5: Multi-Format Support

**Build:** PDF/DOCX/HTML/Markdown via docling, cascade deletes

**Learn:** Document parsing challenges, format considerations

---

## Module 6: Hybrid Search & Reranking

**Build:** Keyword + vector search, RRF combination, reranking

**Learn:** Why vector alone isn't enough, hybrid strategies, reranking

---

## Module 7: Additional Tools

**Build:** Text-to-SQL tool (query structured data), web search fallback (when docs don't have the answer)

**Learn:** Multi-tool agents, routing between structured/unstructured data, graceful fallbacks, attribution for trust

---

## Module 8: Sub-Agents

**Build:** Detect full-document scenarios, spawn isolated sub-agent with its own tools, nested tool call display in UI, show reasoning from both main agent and sub-agents

**Learn:** Context management, agent delegation, hierarchical agent display, when to isolate

---

## Success Criteria

By the end, students should have:
- ✅ A working RAG application they built with AI assistance
- ✅ Deep understanding of RAG concepts (chunking, embedding, retrieval, reranking)
- ✅ Understanding of codebase structure - what lives where, how pieces connect
- ✅ Ability to direct AI coding tools to build new features
- ✅ Ability to direct AI coding tools to debug and fix issues
- ✅ Experience with agentic patterns (multi-tool, sub-agents)
- ✅ Observability set up from day one
