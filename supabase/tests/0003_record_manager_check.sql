-- Module 3 check. Run manually in the Supabase SQL editor AFTER applying 0003. Rolls back; leaves no data.
-- Needs two existing auth.users rows (any two test users). Replace the placeholders below.
--   <USER_A>, <USER_B>: uuids from auth.users

begin;

-- 1. Same user + same filename must violate the unique index.
insert into public.documents (user_id, filename, storage_path, content_hash)
values ('<USER_A>', 'dup.txt', '<USER_A>/m3-a', repeat('a', 64));

do $$
begin
  begin
    insert into public.documents (user_id, filename, storage_path, content_hash)
    values ('<USER_A>', 'dup.txt', '<USER_A>/m3-b', repeat('b', 64));
    raise exception 'FAIL: duplicate (user_id, filename) was accepted';
  exception when unique_violation then
    raise notice 'PASS: duplicate (user_id, filename) rejected';
  end;
end $$;

-- 2. A different user may use the same filename.
insert into public.documents (user_id, filename, storage_path, content_hash)
values ('<USER_B>', 'dup.txt', '<USER_B>/m3-c', repeat('a', 64));
do $$ begin raise notice 'PASS: second user can reuse the filename'; end $$;

-- 3. RLS: user B must not see user A's row.
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"<USER_B>","role":"authenticated"}', true);
do $$
declare n int;
begin
  select count(*) into n from public.documents where user_id = '<USER_A>';
  if n <> 0 then raise exception 'FAIL: user B can see % of user A rows', n; end if;
  raise notice 'PASS: RLS hides other users documents';
end $$;

rollback;
