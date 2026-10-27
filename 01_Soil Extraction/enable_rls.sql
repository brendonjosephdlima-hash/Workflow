-- Row-level security for the soil tables. Run in the Supabase SQL Editor once,
-- and again after every upload_soil.py / upload_attributes.py (they drop and recreate the tables).
--
-- Result: the publishable key (used by the Grasshopper soil component) can only READ the soil tables.
-- Inserts, updates and deletes are refused for anon and authenticated users.
-- Uploads still work because they connect with SUPABASE_DB_URL (the postgres role), which bypasses RLS.

alter table public.global_soils    enable row level security;
alter table public.soil_attributes enable row level security;

-- read-only access for everyone
drop policy if exists "soil polygons are readable" on public.global_soils;
create policy "soil polygons are readable" on public.global_soils
  for select to anon, authenticated using (true);

drop policy if exists "soil attributes are readable" on public.soil_attributes;
create policy "soil attributes are readable" on public.soil_attributes
  for select to anon, authenticated using (true);

-- belt and braces: remove write privileges as well
revoke insert, update, delete, truncate on public.global_soils    from anon, authenticated;
revoke insert, update, delete, truncate on public.soil_attributes from anon, authenticated;

-- check: both rows should show rowsecurity = true
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename in ('global_soils', 'soil_attributes');
