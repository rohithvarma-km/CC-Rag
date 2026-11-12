# Module 2: How It Works (Plain English)

_Release 0.2. Covers BYO retrieval + memory: own ingestion pipeline, pgvector search, tool-calling chat over stateless completions._

## 1. The idea in one paragraph
A chat website where you sign up, log in, upload your own text documents, and talk to an AI that looks things up in them (RAG: Retrieval-Augmented Generation). We own the whole pipeline: file storage, chunking, embeddings, vector search, and the conversation memory. The model is reached through the standard OpenAI-compatible Chat Completions API (default: local Ollama), so you can swap providers with environment variables. Every user's documents and chats are private to them (Row-Level Security). Every turn is traced in LangSmith.

## 2. The pieces

```
 Browser (React + Vite + Tailwind + shadcn/ui)
   |  login ---------------------------------------------> Supabase Auth  (returns a JWT)
   |  upload file directly ------------------------------> Supabase Storage (private bucket)
   |  watch document status <----------------------------- Supabase Realtime
   |  every API call: "Authorization: Bearer <JWT>"
   v
 Backend (Python FastAPI)  -- acts AS THE USER (their JWT), so RLS applies everywhere
   |  /documents      create row, trigger ingestion, delete
   |  /threads        threads + messages (with citations)
   |  /threads/{id}/chat   tool-calling loop, streamed over SSE
   v
 Model provider (OpenAI-compatible)     Supabase Postgres + pgvector        LangSmith
 - chat model (tool calling)            - threads, messages                 - chat_turn, ingest_document
 - embedding model                      - documents, chunks (vector(768))     traces incl. prompts and
 default: Ollama on localhost:11434     - match_chunks() search function      retrieved chunk text
```

**Frontend layout:** `AppLayout` provides one shared sidebar (wordmark, New chat, Chat/Documents nav, thread list, profile block with name, email and sign out) around both pages. Chat shows citation chips (filename + similarity, expandable snippet) and a "Searching documents..." indicator; Documents has drag-and-drop upload, live status badges, Retry and Delete. The theme is warm cream/terracotta with serif headings and follows the OS dark mode setting.

Rules: no LangChain/LangGraph (raw SDK calls), RLS on every table, chat streamed over SSE, Python in a venv, ingestion is manual file upload only.

## 3. Ingestion: from file to searchable chunks

1. **Create.** The browser checks the file (`.txt` / `.md`, at most 5 MB) and calls `POST /documents {filename, size_bytes}`. The backend validates again and inserts a `documents` row with status `pending` and `storage_path = {user_id}/{document_id}`.
2. **Upload.** The browser uploads the file straight to the private `documents` bucket in Supabase Storage (storage policies only allow your own `{user_id}/` folder). If the upload fails the browser calls `DELETE /documents/{id}`.
3. **Ingest.** `POST /documents/{id}/ingest` atomically claims the document and returns 202. The work then runs as a FastAPI background task using the user's JWT (no service-role key).
4. **Process.** Download from Storage, decode as UTF-8 (BOM tolerated, NUL bytes stripped, empty file is an error), delete any old chunks, split into chunks, embed them in batches, insert into `chunks` in batches of 100.
5. **Finish.** Status becomes `completed` with `chunk_count`. Any error deletes that document's chunks and sets `failed` with a short, user-safe `error` message (for example "Cannot reach model provider at ...").

**State machine:** `pending -> processing -> completed | failed`. `failed -> processing` on Retry. A document stuck in `processing` for more than 10 minutes (for example the server restarted) can be claimed again. A fresh `processing` document cannot, so double clicks return 409.

**Chunking:** a hand-written recursive splitter (paragraph, line, sentence, word, then hard split) with overlap. Defaults: 1000 characters, 200 overlap. `CHUNK_SIZE` is capped at 1500 characters so a chunk always fits the embedding model's context.

**Embeddings:** `POST {EMBEDDING_BASE_URL}/embeddings` in batches of `EMBEDDING_BATCH_SIZE`, optional document/query prefixes, and a check that each vector has `EMBEDDING_DIM` (768) numbers.

**Realtime status:** `documents` is in the `supabase_realtime` publication (replica identity full). The Documents page subscribes to changes filtered by your user id and refetches on (re)subscribe, so badges flip live without a refresh.

## 4. Retrieval

`match_chunks(query_embedding vector(768), match_count, min_similarity)` is a Postgres SQL function declared `security invoker`, so RLS applies and you only ever search your own chunks. It uses cosine similarity (`1 - (embedding <=> query)`), only considers chunks of `completed` documents, drops anything below `min_similarity` (default 0.25), returns at most 10 rows, and is backed by an HNSW index (`vector_cosine_ops`).

## 5. Chat: a tool-calling loop over stateless completions

The model is not given the documents. It is given a `search_documents` tool (arguments `query`, `top_k`, defined by a Pydantic model) and decides when to use it. The provider keeps no memory; we send everything each turn.

For each `POST /threads/{id}/chat`:

1. **Auth and ownership.** Validate the JWT, load the thread as the user (someone else's thread id is a 404).
2. **History window.** Load the last `HISTORY_MAX_MESSAGES` (20) stored messages, drop the oldest until under `HISTORY_MAX_CHARS` (24000), and make sure the window starts on a user turn. This is read BEFORE the new turn is saved. Tool messages are not stored, so a later turn may simply search again.
3. **Build the request:** system prompt + history + your new message.
4. **Loop** (up to `MAX_TOOL_ITERATIONS`, default 3): call Chat Completions with streaming. Text deltas are forwarded to the browser immediately. Tool-call fragments are reassembled (tolerating missing indexes and arguments split across chunks). If the model asked for `search_documents`, we embed the query, call `match_chunks`, append a `tool` message with the passages, and loop. On the last iteration `tool_choice="none"` forces a plain answer. Bad tool arguments or unknown tools are returned to the model as an error message instead of crashing the turn.
5. **Citations.** Every chunk returned by the turn's searches is kept (deduplicated by document and chunk) as `{document_id, filename, chunk_index, snippet (240 chars), similarity}`.
6. **Persist after success.** Only when the model finished without error are the user message and the assistant message (with `citations`, stored in `messages.citations`) written, and the thread title set (first 60 characters of the first message). A failed call leaves no orphan user message.

**SSE events** (`data: {json}` lines):

| Event | Meaning |
|---|---|
| `{"type":"tool","name":"search_documents"}` | The model is searching; UI shows "Searching documents..." |
| `{"type":"delta","text":"..."}` | A piece of the answer |
| `{"type":"done","citations":[...],"title":"..."}` | Finished and saved |
| `{"type":"error","message":"..."}` | Something failed; nothing was saved |

`GET /threads/{id}/messages` returns stored messages including their citations, so chips survive a reload. Deleting a document removes the Storage object first (a 502 keeps the row if Storage fails), then the row, which cascades to its chunks.

## 6. Where is the data stored?

| Data | Where |
|---|---|
| Accounts, passwords, sessions | Supabase Auth |
| Original files | Supabase Storage, private bucket `documents`, path `{user_id}/{document_id}` |
| Chunk text and 768-dim embeddings | Supabase Postgres: `chunks` (pgvector) |
| Document metadata and ingestion status | Supabase Postgres: `documents` |
| Threads, messages, citations (also the model's memory) | Supabase Postgres: `threads`, `messages` |
| Traces / monitoring | LangSmith |
| Secrets (API keys) | `.env` files, never committed |

Local models do not mean local data: Ollama only runs inference. Documents and chunks sit in your cloud Supabase project, and LangSmith traces contain prompts and retrieved chunk text (set `LANGSMITH_TRACING=false` to turn tracing off).

## 7. Row-Level Security

All tables (`threads`, `messages`, `documents`, `chunks`) have RLS with `<table>_<cmd>_own` policies: you can only see and change rows where `user_id = auth.uid()`. Chunk inserts must also point at a document you own. `match_chunks` is `security invoker`, so search is filtered the same way. Storage policies on `storage.objects` limit the `documents` bucket to the folder named after your user id. The backend never uses a service-role key; it builds a Supabase client per request carrying the caller's JWT.

## 8. Memory
Memory is entirely ours. Every message is stored in `messages`; each turn we resend a bounded window (see section 5). Nothing depends on the model provider retaining state, so old threads keep working and you can switch models freely. A new thread starts empty. Per user and per thread, enforced by RLS.

## 9. Observability
LangSmith records one `chat_turn` trace per message with nested `embed_query`, `retrieve`, `execute_tool` and the LLM calls (tool calls visible), tagged with `user_id` and `thread_id`. Ingestion is a separate `ingest_document` trace. Metadata holds ids only, but the LLM and retrieval spans contain prompt and chunk text.

## 10. Limits and what comes next
**Known limitations in 0.2:**
- Cold start: Ollama unloads models after 5 minutes idle, so the first turn takes about 11-12 s (set `OLLAMA_KEEP_ALIVE`); warm turns take about 2-6 s.
- The assistant refuses general-knowledge questions by design (system prompt in `services/agent.py`).
- `RETRIEVAL_MIN_SIMILARITY` (0.25) is not yet tuned; sample scores on real documents were 0.50-0.59.
- Composer text and an in-flight stream are lost when navigating Chat -> Documents -> Chat.
- The Documents page has no `<main>` landmark (a11y nit).
- The LangSmith trace structure described in section 9 has not yet been checked in the LangSmith UI.

**Scope:** Only `.txt` and `.md`, at most 5 MB. The embedding dimension is locked to `vector(768)` (changing it needs a migration and re-ingest). No deduplication (Module 3), metadata filtering (4), PDF/DOCX/HTML (5), hybrid search or reranking (6).
