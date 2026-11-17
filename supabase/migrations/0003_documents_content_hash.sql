-- Module 3: Record Manager. Idempotent.
-- A document's identity is (user_id, filename); its version is the SHA-256 of the file bytes.
-- Existing rows keep content_hash = null: the next upload of the same filename is treated as a change
-- and reprocessed once.
--
-- PRE-FLIGHT: the unique index fails if a user already has two documents with the same filename. Check first:
--   select user_id, filename, count(*) from public.documents group by 1, 2 having count(*) > 1;
-- If that returns rows, delete the stale duplicates (Ingestion page) before applying this migration.

alter table public.documents add column if not exists content_hash text;

create unique index if not exists documents_user_filename_key
  on public.documents (user_id, filename);
