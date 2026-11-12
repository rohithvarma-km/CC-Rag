-- Run in the Supabase SQL editor AFTER migration 0002. Everything is rolled back.
-- Simulates two authenticated users and checks isolation. Expect NOTICE lines "PASS ..." and no exceptions.
begin;

do $$
declare
  a uuid := gen_random_uuid();
  b uuid := gen_random_uuid();
  doc_a uuid := gen_random_uuid();
  n int;
  zero text := '[' || array_to_string(array_fill(0.01::float, array[768]), ',') || ']';
begin
  insert into auth.users (id, instance_id, aud, role, email) values
    (a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-a@example.com'),
    (b, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-b@example.com');

  -- As user A: create a completed document + chunk
  perform set_config('request.jwt.claim.sub', a::text, true);
  perform set_config('role', 'authenticated', true);
  insert into public.documents (id, user_id, filename, storage_path, status)
    values (doc_a, a, 'a.md', a || '/' || doc_a, 'completed');
  insert into public.chunks (document_id, user_id, chunk_index, content, embedding)
    values (doc_a, a, 0, 'secret of A', zero::extensions.vector);
  select count(*) into n from public.match_chunks(zero::extensions.vector, 5, 0);
  if n <> 1 then raise exception 'FAIL: A should match own chunk (got %)', n; end if;
  raise notice 'PASS A sees own chunk via match_chunks';

  -- As user B
  perform set_config('request.jwt.claim.sub', b::text, true);
  select count(*) into n from public.documents;
  if n <> 0 then raise exception 'FAIL: B sees % documents', n; end if;
  select count(*) into n from public.chunks;
  if n <> 0 then raise exception 'FAIL: B sees % chunks', n; end if;
  select count(*) into n from public.match_chunks(zero::extensions.vector, 5, 0);
  if n <> 0 then raise exception 'FAIL: B matched % of A chunks', n; end if;
  raise notice 'PASS B sees 0 documents/chunks and match_chunks returns 0';

  begin
    insert into public.chunks (document_id, user_id, chunk_index, content, embedding)
      values (doc_a, b, 1, 'injected', zero::extensions.vector);
    raise exception 'FAIL: B inserted a chunk into A''s document';
  exception when insufficient_privilege or check_violation then
    raise notice 'PASS B cannot insert chunk for A''s document';
  end;
end $$;

rollback;

-- Policy / RLS inventory (expect 4 policies each, rls = true)
select c.relname, c.relrowsecurity as rls, count(p.*) as policies
from pg_class c
left join pg_policies p on p.tablename = c.relname and p.schemaname = 'public'
where c.relnamespace = 'public'::regnamespace and c.relname in ('documents','chunks','threads','messages')
group by c.relname, c.relrowsecurity;
