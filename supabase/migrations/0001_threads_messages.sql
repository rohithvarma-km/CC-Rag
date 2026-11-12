-- Module 1: threads + messages with RLS.
-- NOTE: threads.openai_last_response_id is Module 1 only (OpenAI managed threads); Module 2 removes it.
create table public.threads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  title text not null default 'New chat',
  openai_last_response_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.threads(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  role text not null check (role in ('user','assistant')),
  content text not null,
  openai_response_id text,
  created_at timestamptz not null default now()
);

create index messages_thread_idx on public.messages(thread_id, created_at);
create index threads_user_idx on public.threads(user_id, updated_at desc);

alter table public.threads enable row level security;
alter table public.messages enable row level security;

create policy "threads_select_own" on public.threads for select using (user_id = auth.uid());
create policy "threads_insert_own" on public.threads for insert with check (user_id = auth.uid());
create policy "threads_update_own" on public.threads for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "threads_delete_own" on public.threads for delete using (user_id = auth.uid());

create policy "messages_select_own" on public.messages for select using (user_id = auth.uid());
create policy "messages_insert_own" on public.messages for insert with check (
  user_id = auth.uid() and exists (select 1 from public.threads t where t.id = thread_id and t.user_id = auth.uid())
);
create policy "messages_update_own" on public.messages for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "messages_delete_own" on public.messages for delete using (user_id = auth.uid());
