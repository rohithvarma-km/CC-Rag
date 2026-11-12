# Module 1: What We Built (Plain English)

## 1. The idea in one paragraph
A chat website where you sign up, log in, and talk to an AI. The AI can look up facts in documents you put in an OpenAI "vector store" and answer using them (that is the "RAG" part: Retrieval-Augmented Generation). Every user has their own private chat threads. Every chat is traced in LangSmith so you can see what the AI did.

## 2. The pieces (architecture)

```
 Browser (React + Vite + Tailwind + shadcn/ui)
   |  1. login with email/password  --------------------> Supabase Auth
   |  2. gets a token (JWT) back  <------------------------+
   |  3. every request: "Authorization: Bearer <token>"
   v
 Backend (Python FastAPI)
   |  - checks the token with Supabase Auth
   |  - reads/writes threads + messages in Supabase Postgres AS THE USER
   |      (so Row-Level Security limits them to their own rows)
   |  - calls OpenAI Responses API (with file_search tool)
   |  - streams the answer back to the browser using SSE
   |  - sends a trace of the whole turn to LangSmith
   v
 OpenAI                      Supabase Postgres              LangSmith
 - the model (gpt-4.1-mini)  - threads table                - traces: inputs, output,
 - vector store (documents)  - messages table                 latency, tokens, tool calls
 - stored responses (memory) - RLS on both tables
```

Rules we followed: no LangChain/LangGraph (raw SDK calls only), RLS on every table, chat streamed over SSE, Python in a venv.

## 3. Step-by-step: what happens when you send a message

1. **Sign in.** The React app signs you in through Supabase Auth and keeps the session (token) in the browser. Refreshing the page keeps you logged in.
2. **You type a message** in a thread. The frontend POSTs to `/threads/{id}/chat` with your token.
3. **Backend checks who you are.** It asks Supabase "is this token valid?" and gets your user id.
4. **Backend loads your thread** using a Supabase client that carries *your* token. Postgres RLS means you can only ever see your own thread; someone else's thread id gives a 404.
5. **Your message is saved** to the `messages` table first.
6. **Backend calls OpenAI** (`responses.create`, streaming) with your message, the thread's `openai_last_response_id` (this is the memory), and the `file_search` tool pointing at your vector store.
7. **OpenAI retrieves and answers.** If the model decides it needs documents, it searches the vector store, reads the best passages, and writes an answer using them.
8. **Words stream back.** Each piece of text is forwarded to the browser as an SSE event, so the answer appears as it is generated.
9. **When finished,** the backend saves the assistant's full answer to `messages`, stores the new OpenAI response id on the thread, sets the title (first 60 characters of your first message), and sends a final event with the cited file names.
10. **LangSmith** records the whole turn (tagged with user_id and thread_id, no secrets).

## 4. Where is the data stored?

| Data | Where |
|---|---|
| Accounts, passwords, sessions | Supabase Auth |
| Threads and chat messages (what you see in the UI) | Supabase Postgres: `threads`, `messages` (RLS: only the owner can see/change rows) |
| Your documents, their chunks and embeddings | OpenAI vector store (managed by OpenAI, not in our database) |
| The conversation context the model actually uses | OpenAI stored responses, linked by id |
| Traces / monitoring | LangSmith |
| Secrets (API keys) | `.env` files, never committed |

Important: the vector store is ONE store, set by `OPENAI_VECTOR_STORE_ID`. Every signed-in user searches the same documents. Chat history is private per user; the documents are shared. Per-user documents come in Module 2.

## 5. How is it chunked?
We do NOT chunk anything ourselves in Module 1. When you upload files to the OpenAI vector store, OpenAI splits them into chunks and creates embeddings automatically. By default it uses chunks of about 800 tokens with about 400 tokens of overlap (so a sentence at a boundary isn't lost). You can change this only when attaching files to the store; our code doesn't touch it.

## 6. How is it retrieved?
Also handled by OpenAI. We only attach the `file_search` tool. When the model decides a question needs your documents, OpenAI turns the question into an embedding, finds the most similar chunks in the vector store, and gives them to the model. The answer carries annotations naming the source files, which we surface as citations. We do not control ranking, top-k or hybrid search here.

## 7. How does it remember each user's conversation?
Two separate things:
- **For display:** every message is saved in Supabase `messages`, tied to the thread and user. That is what you see when you reload.
- **For the AI's memory:** each OpenAI response has an id. We store the latest one in `threads.openai_last_response_id`. On the next message we send it as `previous_response_id`, and OpenAI supplies the earlier conversation to the model itself. We never resend the history.

Because the id is stored per thread and threads belong to one user, memory is per user and per thread. A new thread starts with no memory.
Caveat: this relies on OpenAI keeping responses (they are stored for a limited time, roughly 30 days by default). Very old threads may display fine but lose model memory. Module 2 fixes this by storing and sending history ourselves (stateless completions).

## 8. What Module 2 will change
`services/openai_responses.py` and the `openai_last_response_id` column get replaced: our own file upload, our own chunking, embeddings in pgvector, per-user documents, history sent by us, OpenRouter models, and Realtime ingestion status.

## 9. Current status
Code written, pytest passes with a mocked OpenAI stream. Supabase migration applied. Still to do: fill in `.env` files, run the app, two-user RLS test in the browser, confirm a LangSmith trace.
