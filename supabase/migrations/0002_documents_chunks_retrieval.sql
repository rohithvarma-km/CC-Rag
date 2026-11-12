-- Module 2: own ingestion + pgvector retrieval + stateless chat history. Idempotent.
-- DESTRUCTIVE: drops the Module 1 OpenAI Responses columns.
-- Embedding dimension (768) is tied to the embeddinggemma model; changing it needs a new migration + re-ingest.

create extension if not exists vector with schema extensions;

alter table public.threads  drop column if exists openai_last_response_id;
alter table public.messages drop column if exists openai_response_id;
alter table public.messages add column if not exists citations jsonb not null default '[]'::jsonb;

-- updated_at trigger helper
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  filename text not null,
  storage_path text not null,
  size_bytes bigint not null default 0,
  status text not null default 'pending' check (status in ('pending','processing','completed','failed')),
  error text,
  chunk_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists documents_set_updated_at on public.documents;
create trigger documents_set_updated_at before update on public.documents
  for each row execute function public.set_updated_at();

create table if not exists public.chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  chunk_index integer not null,
  content text not null,
  embedding extensions.vector(768) not null,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

create index if not exists documents_user_idx on public.documents(user_id, created_at desc);
create index if not exists chunks_document_idx on public.chunks(document_id);
create index if not exists chunks_user_idx on public.chunks(user_id);
create index if not exists chunks_embedding_hnsw on public.chunks
  using hnsw (embedding extensions.vector_cosine_ops);

alter table public.documents enable row level security;
alter table public.chunks enable row level security;

drop policy if exists "documents_select_own" on public.documents;
drop policy if exists "documents_insert_own" on public.documents;
drop policy if exists "documents_update_own" on public.documents;
drop policy if exists "documents_delete_own" on public.documents;
create policy "documents_select_own" on public.documents for select using (user_id = auth.uid());
create policy "documents_insert_own" on public.documents for insert with check (user_id = auth.uid());
create policy "documents_update_own" on public.documents for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "documents_delete_own" on public.documents for delete using (user_id = auth.uid());

drop policy if exists "chunks_select_own" on public.chunks;
drop policy if exists "chunks_insert_own" on public.chunks;
drop policy if exists "chunks_update_own" on public.chunks;
drop policy if exists "chunks_delete_own" on public.chunks;
create policy "chunks_select_own" on public.chunks for select using (user_id = auth.uid());
create policy "chunks_insert_own" on public.chunks for insert with check (
  user_id = auth.uid()
  and exists (select 1 from public.documents d where d.id = document_id and d.user_id = auth.uid())
);
create policy "chunks_update_own" on public.chunks for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "chunks_delete_own" on public.chunks for delete using (user_id = auth.uid());

-- Retrieval: security invoker so RLS applies; only chunks of completed documents.
create or replace function public.match_chunks(
  query_embedding extensions.vector(768),
  match_count int default 5,
  min_similarity float default 0.25
)
returns table (
  chunk_id uuid,
  document_id uuid,
  filename text,
  chunk_index int,
  content text,
  similarity float
)
language sql stable security invoker
set search_path = public, extensions
as $$
  select c.id, c.document_id, d.filename, c.chunk_index, c.content,
         (1 - (c.embedding <=> query_embedding))::float as similarity
  from public.chunks c
  join public.documents d on d.id = c.document_id
  where d.status = 'completed'
    and (1 - (c.embedding <=> query_embedding)) >= min_similarity
  order by c.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 10)
$$;

-- Private storage bucket; objects live at {user_id}/{document_id}.
insert into storage.buckets (id, name, public) values ('documents', 'documents', false)
on conflict (id) do nothing;

drop policy if exists "documents_objects_select_own" on storage.objects;
drop policy if exists "documents_objects_insert_own" on storage.objects;
drop policy if exists "documents_objects_update_own" on storage.objects;
drop policy if exists "documents_objects_delete_own" on storage.objects;
create policy "documents_objects_select_own" on storage.objects for select
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_objects_insert_own" on storage.objects for insert
  with check (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_objects_update_own" on storage.objects for update
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_objects_delete_own" on storage.objects for delete
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);

-- Realtime ingestion status
alter table public.documents replica identity full;
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'documents'
  ) then
    alter publication supabase_realtime add table public.documents;
  end if;
end $$;
