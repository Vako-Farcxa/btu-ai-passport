-- Migration 0012: Performance
-- Three things the backend can use to make the sync and the admin dashboard faster. All of them
-- are optional: a backend that cannot find a function falls back to the slower way it worked
-- before, so this can be applied before or after deploying the backend. Safe to run twice.
--
--   1. sync_student_units(jsonb): runs many sync units in one round trip. Each unit is still
--      its own all-or-nothing step (sync_student_unit from 0011) inside its own savepoint, and
--      a unit that fails is reported by name without stopping or rolling back the others.
--   2. admin_dashboard_stats(): every number on the admin dashboard in one query, instead of
--      loading 100 students with all their versions to count them in the browser.
--   3. admin_health_snapshot(): the rows the admin health banner needs in one query.
--
-- Indexes: sync_runs gets one row every sync (about 100 a day) and the dashboard and health
-- banner read its newest rows, so those reads should not scan the whole table.

-- 1. Batched sync units ------------------------------------------------------------------
create or replace function sync_student_units(p_units jsonb)
returns jsonb
language plpgsql
set search_path = public, pg_temp
as $$
declare
    v_unit jsonb;
    v_out jsonb := '[]'::jsonb;
begin
    if p_units is null or jsonb_typeof(p_units) <> 'array' then
        raise exception 'sync_unit_malformed: p_units must be an array' using errcode = 'PS003';
    end if;
    for v_unit in select value from jsonb_array_elements(p_units) loop
        begin
            -- The block is a savepoint: an error undoes this unit only.
            v_out := v_out || jsonb_build_array(
                jsonb_build_object('ok', true, 'result', sync_student_unit(v_unit))
            );
        exception when others then
            v_out := v_out || jsonb_build_array(
                jsonb_build_object('ok', false, 'code', sqlstate, 'message', sqlerrm)
            );
        end;
    end loop;
    return v_out;
end;
$$;

comment on function sync_student_units(jsonb) is
    'Runs sync_student_unit for each element of the array, each in its own savepoint. Returns one {ok, result | code, message} per unit, in order. Called by the backend with the service role only.';

-- 2. Admin dashboard numbers -------------------------------------------------------------
-- Anchor statuses follow the backend (normalize_anchor_status): pending, retrying and the
-- legacy "failed" are still being worked on; any other value that is not confirmed needs an
-- admin (failed_permanent).
create or replace function admin_dashboard_stats()
returns jsonb
language sql
stable
set search_path = public, pg_temp
as $$
    select jsonb_build_object(
        'total_students', (select count(*) from students where deleted_at is null),
        'admin_managed_students',
            (select count(*) from students where deleted_at is null and admin_managed),
        'pending_anchors', (select count(*) from passport_versions where anchor_status <> 'confirmed'),
        'failed_anchors', (
            select count(*) from passport_versions
            where anchor_status not in ('confirmed', 'pending', 'retrying', 'failed')
        ),
        'open_flags', (select count(*) from flags where status = 'open'),
        'recent_runs', (
            select coalesce(jsonb_agg(to_jsonb(r) order by r.started_at desc), '[]'::jsonb)
            from (
                select id, status, started_at, finished_at, rows_read, versions_created, error
                from sync_runs
                order by started_at desc
                limit 5
            ) r
        )
    );
$$;

comment on function admin_dashboard_stats() is
    'Counts and the five newest sync runs for the admin dashboard. Read only.';

-- 3. Admin health banner inputs ----------------------------------------------------------
-- plpgsql (not sql) so that a database without migration 0011 can still create it: the
-- consistency count is then null and the banner says the check could not run.
create or replace function admin_health_snapshot()
returns jsonb
language plpgsql
stable
set search_path = public, pg_temp
as $$
declare
    v_inconsistencies bigint;
begin
    begin
        select count(*) into v_inconsistencies from sync_inconsistencies();
    exception when others then
        v_inconsistencies := null;
    end;
    return jsonb_build_object(
        'last_finished_run', (
            select to_jsonb(r) from (
                select status, started_at, finished_at, error
                from sync_runs
                where status in ('completed', 'failed')
                order by started_at desc
                limit 1
            ) r
        ),
        'last_success_run', (
            select to_jsonb(r) from (
                select status, started_at, finished_at, error
                from sync_runs
                where status = 'completed'
                order by started_at desc
                limit 1
            ) r
        ),
        'open_versions', (
            select coalesce(jsonb_agg(to_jsonb(v)), '[]'::jsonb) from (
                select anchor_status, issued_at, anchor_submitted_at, anchor_last_error
                from passport_versions
                where anchor_status <> 'confirmed'
            ) v
        ),
        'inconsistencies', v_inconsistencies
    );
end;
$$;

comment on function admin_health_snapshot() is
    'The rows the admin health banner evaluates, in one call. Read only.';

-- Only the service role may call these. Supabase grants new functions to anon and
-- authenticated by default, so take that away explicitly.
do $$
declare
    fn text;
begin
    foreach fn in array array[
        'sync_student_units(jsonb)',
        'admin_dashboard_stats()',
        'admin_health_snapshot()'
    ] loop
        execute format('revoke all on function %s from public', fn);
        if exists (select 1 from pg_roles where rolname = 'anon') then
            execute format('revoke all on function %s from anon', fn);
        end if;
        if exists (select 1 from pg_roles where rolname = 'authenticated') then
            execute format('revoke all on function %s from authenticated', fn);
        end if;
        if exists (select 1 from pg_roles where rolname = 'service_role') then
            execute format('grant execute on function %s to service_role', fn);
        end if;
    end loop;
end
$$;

-- Indexes -------------------------------------------------------------------------------
create index if not exists sync_runs_started_at_idx on sync_runs (started_at desc);
create index if not exists sync_runs_status_started_idx on sync_runs (status, started_at desc);

-- Make PostgREST (Supabase's API layer) see the new functions right away.
notify pgrst, 'reload schema';
