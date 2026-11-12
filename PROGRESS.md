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
- [ ] Cleanup (manual, needs Supabase dashboard): delete the `rlstest-*` users (Authentication -> Users), including `rlstest-a1@example.com` and `rlstest-b1@example.com` created during browser tests

## Current status / next steps (2026-11-12)
- Module 1 is complete and validated, including alternate flows. Services run via `scripts/start-services.sh` (see CLAUDE.md "Running the app").
- **Next:** delete the `rlstest-*` users in Supabase, then plan Module 2 (Chat Completions + OpenRouter, own retrieval, ingestion).
