# CLAUDE.md

RAG app with chat (default) and document ingestion interfaces. Config via env vars, no admin UI.

## Stack
- Frontend: React + Vite + Tailwind + shadcn/ui
- Backend: Python + FastAPI
- Database: Supabase (Postgres, pgvector, Auth, Storage, Realtime)
- LLM: OpenAI (Module 1), OpenRouter (Module 2+)
- Observability: LangSmith

## Rules
- Python backend must use a `venv` virtual environment
- No LangChain, no LangGraph - raw SDK calls only
- Use Pydantic for structured LLM outputs
- All tables need Row-Level Security - users only see their own data
- Stream chat responses via SSE
- Use Supabase Realtime for ingestion status updates
- Module 2+ uses stateless completions - store and send chat history yourself
- Ingestion is manual file upload only - no connectors or automated pipelines

## Planning
- Save all plans to `.agent/plans/` folder
- Naming convention: `{sequence}.{plan-name}.md` (e.g., `1.auth-setup.md`, `2.document-ingestion.md`)
- Plans should be detailed enough to execute without ambiguity
- Each task in the plan must include at least one validation test to verify it works
- Assess complexity and single-pass feasibility - can an agent realistically complete this in one go?
- Include a complexity indicator at the top of each plan:
  - ✅ **Simple** - Single-pass executable, low risk
  - ⚠️ **Medium** - May need iteration, some complexity
  - 🔴 **Complex** - Break into sub-plans before executing

## Development Flow
1. **Plan** - Create a detailed plan and save it to `.agent/plans/`
2. **Build** - Execute the plan to implement the feature
3. **Validate** - Test and verify the implementation works correctly. Use browser testing where applicable via an appropriate MCP
4. **Iterate** - Fix any issues found during validation

## Running the app
- Start both services: `scripts/start-services.sh` (backend :8000, frontend :5173, logs in `.logs/`). Stop: `scripts/start-services.sh stop`. It is safe to re-run (restarts both).
- Requires `backend/.env` and `frontend/.env` (see the `.env.example` files) and a Supabase project with `supabase/migrations/` applied.
- Backend tests: `cd backend && venv/bin/python -m pytest`. Frontend check: `cd frontend && npm run build`.
- Browser testing: use the Playwright MCP (`claude mcp add playwright -- npx @playwright/mcp@latest`). Email confirmation is disabled in Supabase, so test users can sign up directly; delete `rlstest-*`/test users afterwards.

## Progress
Check PROGRESS.md for current module status. Update it as you complete tasks.