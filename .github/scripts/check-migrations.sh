#!/usr/bin/env bash
# Applies every file in supabase/migrations in order to an empty Postgres, applies the newest
# file a second time, and checks that the main objects exist afterwards. Needs DATABASE_URL and psql. Used by the
# "migrations" job in .github/workflows/ci.yml.
#
# Supabase provides some things before our migrations run (the API roles and the storage
# schema), so a plain Postgres gets small stand-ins for them, the same ones the backend
# tests (backend/tests/pg_support.py) use.
#
# Only the newest file is applied twice: 0001, 0002, 0005, 0006 and 0008 create tables without
# "if not exists", so they are written to run once on a fresh database, and they have already
# run on the live one. The newest file is the one most likely to be pasted into the Supabase
# SQL editor again, so it has to be safe to re-run.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must point at an empty Postgres}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
psql_run() { psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1 "$@"; }

echo "Stubbing what Supabase provides (roles anon, authenticated, service_role, storage schema)"
psql_run <<'SQL'
do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;
create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean);
SQL

shopt -s nullglob
files=("$root"/supabase/migrations/*.sql)
if [ "${#files[@]}" -eq 0 ]; then
  echo "No migration files found" >&2
  exit 1
fi

for file in "${files[@]}"; do
  echo "applying $(basename "$file")"
  psql_run -f "$file"
done

newest="${files[${#files[@]} - 1]}"
echo "re-applying $(basename "$newest") to prove it is safe to run twice"
psql_run -f "$newest"

echo "Checking the result"
missing=$(psql_run -A -t <<'SQL'
select string_agg(name, ', ') from (
  select t.name from (values
    ('students'), ('passport_versions'), ('skill_entries'), ('source_records'), ('skills'),
    ('admin_audit')
  ) as t(name)
  where to_regclass('public.' || t.name) is null
  union all
  select 'function ' || f.name
  from (values
    ('sync_student_unit'), ('sync_student_units'), ('admin_dashboard_stats'),
    ('admin_health_snapshot')
  ) as f(name)
  where not exists (select from pg_proc where proname = f.name)
) m
SQL
)
if [ -n "$missing" ]; then
  echo "Missing after migrating: $missing" >&2
  exit 1
fi
echo "OK: ${#files[@]} migrations applied in order, the newest twice, main tables and the sync and admin functions present"
