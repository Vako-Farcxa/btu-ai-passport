-- Migration 0011: Atomic sync
-- The sync used to write a student, then a passport version, then its skill entries as separate
-- API calls. A crash or a network error between them left a student with no version (every later
-- sync failed with student_conflict) or a version with no skills, whose anchored hash no longer
-- matched what the database stores.
--
-- sync_student_unit() writes one student's whole unit in ONE transaction: the student row (or
-- rename), the new passport version, its skill snapshot and the source records. A Postgres
-- function body is a single transaction, so any error rolls all of it back. The backend calls it
-- through Supabase RPC and computes the hashes from exactly the skills it sends; the function
-- returns the stored snapshot so the backend can check the hash against what was written.
--
--   * Idempotent: a retry that finds the same version already stored changes nothing.
--   * Safe against races: the student row is locked, and the unit must extend the stored
--     latest version number by exactly one.
--   * Anchoring is not part of the unit. It runs after commit (the reconciler).
--
-- Errors (SQLSTATE): PS001 the unit is stale (data changed since the sync read it),
-- PS002 the student is archived, PS003 the unit is malformed.
--
-- sync_inconsistencies() lists rows left half-written by the old sync, without changing them.
-- Run it in the SQL editor: select * from sync_inconsistencies();
--
-- Apply before deploying the backend that calls these. Safe to run twice.

create or replace function sync_student_unit(p_unit jsonb)
returns jsonb
language plpgsql
set search_path = public, pg_temp
as $$
declare
    v_email text := p_unit ->> 'email';
    v_passport_id text := p_unit ->> 'passport_id';
    v_full_name text := p_unit ->> 'full_name';
    v_rename boolean := coalesce((p_unit ->> 'rename')::boolean, false);
    v_expected integer := coalesce((p_unit ->> 'expected_latest')::integer, 0);
    v_version jsonb := p_unit -> 'version';
    v_student students%rowtype;
    v_latest passport_versions%rowtype;
    v_new passport_versions%rowtype;
    v_has_latest boolean;
    v_created_student boolean := false;
    v_created_version boolean := false;
    v_skill_count integer;
    v_inserted integer;
    v_target uuid;
begin
    if v_email is null or v_email = '' or v_passport_id is null or v_full_name is null then
        raise exception 'sync_unit_malformed: email, passport_id and full_name are required'
            using errcode = 'PS003';
    end if;
    if v_version is not null and jsonb_typeof(v_version) = 'null' then
        v_version := null;
    end if;

    select * into v_student from students where email = v_email for update;

    if not found then
        if v_version is null or v_expected <> 0 then
            raise exception 'sync_unit_stale: student % is gone', v_email using errcode = 'PS001';
        end if;
        insert into students (email, full_name, passport_id)
        values (v_email, v_full_name, v_passport_id)
        returning * into v_student;
        v_created_student := true;
    else
        if v_student.deleted_at is not null then
            raise exception 'sync_unit_archived: student % is archived', v_email
                using errcode = 'PS002';
        end if;
        if v_student.passport_id <> v_passport_id then
            -- The hash covers the passport id, so the unit must be built for the stored one.
            raise exception 'sync_unit_stale: passport id of % changed', v_email
                using errcode = 'PS001';
        end if;
        if v_rename and v_full_name <> v_student.full_name then
            update students set full_name = v_full_name, updated_at = now()
            where id = v_student.id
            returning * into v_student;
        end if;
    end if;

    select * into v_latest
    from passport_versions
    where student_id = v_student.id
    order by version_number desc
    limit 1;
    v_has_latest := found;
    v_target := case when v_has_latest then v_latest.id else null end;

    if v_version is not null then
        v_skill_count := coalesce(jsonb_array_length(v_version -> 'skills'), 0);
        if v_skill_count = 0 then
            raise exception 'sync_unit_malformed: a version needs at least one skill'
                using errcode = 'PS003';
        end if;

        if v_has_latest and v_latest.skill_fingerprint = v_version ->> 'skill_fingerprint' then
            -- A retry of a unit that already committed (for example the response was lost).
            if v_latest.version_number <> (v_version ->> 'version_number')::integer
               or v_latest.content_hash <> v_version ->> 'content_hash' then
                raise exception 'sync_unit_stale: latest version of % differs', v_email
                    using errcode = 'PS001';
            end if;
        else
            if (case when v_has_latest then v_latest.version_number else 0 end) <> v_expected then
                raise exception 'sync_unit_stale: latest version of % moved', v_email
                    using errcode = 'PS001';
            end if;
            if (v_version ->> 'version_number')::integer <> v_expected + 1 then
                raise exception 'sync_unit_malformed: version number must be % ', v_expected + 1
                    using errcode = 'PS003';
            end if;

            insert into passport_versions (
                student_id, version_number, holder_name, verification_code,
                verification_id_hash, skill_fingerprint, content_hash, anchor_status, issued_at
            )
            values (
                v_student.id,
                (v_version ->> 'version_number')::integer,
                v_version ->> 'holder_name',
                v_version ->> 'verification_code',
                v_version ->> 'verification_id_hash',
                v_version ->> 'skill_fingerprint',
                v_version ->> 'content_hash',
                'pending',
                coalesce((v_version ->> 'issued_at')::timestamptz, now())
            )
            returning * into v_new;

            insert into skill_entries (version_id, skill, badge, awarded_on, description, skill_id, position)
            select
                v_new.id,
                item ->> 'skill',
                coalesce(item ->> 'badge', ''),
                nullif(item ->> 'awarded_on', '')::date,
                coalesce(item ->> 'description', ''),
                nullif(item ->> 'skill_id', ''),
                ordinality
            from jsonb_array_elements(v_version -> 'skills') with ordinality as t (item, ordinality);
            get diagnostics v_inserted = row_count;
            if v_inserted <> v_skill_count then
                raise exception 'sync_unit_malformed: stored % of % skills', v_inserted, v_skill_count
                    using errcode = 'PS003';
            end if;

            v_created_version := true;
            v_latest := v_new;
            v_target := v_new.id;
        end if;
    end if;

    if p_unit -> 'source_keys' is not null and jsonb_typeof(p_unit -> 'source_keys') = 'array' then
        insert into source_records (record_key, email)
        select distinct key, v_email
        from jsonb_array_elements_text(p_unit -> 'source_keys') as k (key)
        on conflict (record_key) do nothing;
    end if;

    return jsonb_build_object(
        'student_id', v_student.id,
        'passport_id', v_student.passport_id,
        'created_student', v_created_student,
        'created_version', v_created_version,
        'version_number', case when v_has_latest or v_created_version then v_latest.version_number end,
        'holder_name', case when v_has_latest or v_created_version then v_latest.holder_name end,
        'skills', case
            when v_version is null or v_target is null then null
            else (
                select coalesce(jsonb_agg(
                    jsonb_build_object(
                        'skill', e.skill,
                        'badge', e.badge,
                        'awarded_on', e.awarded_on,
                        'description', e.description,
                        'skill_id', e.skill_id
                    ) order by e.position), '[]'::jsonb)
                from skill_entries e
                where e.version_id = v_target
            )
        end
    );
end;
$$;

comment on function sync_student_unit(jsonb) is
    'One student sync unit (student, new version, skill snapshot, source records) in a single transaction. Called by the backend with the service role only.';

-- Only the service role may call it. Supabase grants new functions to anon and authenticated by
-- default, so take that away explicitly.
revoke all on function sync_student_unit(jsonb) from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        execute 'revoke all on function sync_student_unit(jsonb) from anon';
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'revoke all on function sync_student_unit(jsonb) from authenticated';
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant execute on function sync_student_unit(jsonb) to service_role';
    end if;
end
$$;

-- Report only. Never changes data.
create or replace function sync_inconsistencies()
returns table (kind text, passport_id text, version_number integer, detail text)
language sql
stable
set search_path = public, pg_temp
as $$
    select 'student_without_version'::text, s.passport_id, null::integer,
           'Active student with no passport version. The next sync creates version 1.'::text
    from students s
    where s.deleted_at is null
      and not exists (select 1 from passport_versions v where v.student_id = s.id)
    union all
    select 'version_without_skills', s.passport_id, v.version_number,
           'Version has no skill entries, so its anchored hash cannot match its stored content.'
    from passport_versions v
    join students s on s.id = v.student_id
    where not exists (select 1 from skill_entries e where e.version_id = v.id)
    union all
    select 'version_number_gap', s.passport_id, null,
           'Version numbers are not 1..n without gaps (' || count(*) || ' versions, highest '
           || max(v.version_number) || ').'
    from passport_versions v
    join students s on s.id = v.student_id
    group by s.id, s.passport_id
    having max(v.version_number) <> count(*)
    union all
    select 'skill_position_gap', s.passport_id, v.version_number,
           'Skill positions are not 1..n without gaps.'
    from passport_versions v
    join students s on s.id = v.student_id
    join skill_entries e on e.version_id = v.id
    group by s.passport_id, v.id, v.version_number
    having max(e.position) <> count(*) or min(e.position) <> 1
    order by 2, 3 nulls first, 1;
$$;

comment on function sync_inconsistencies() is
    'Lists students and versions left half-written by the old non-atomic sync. Read only.';

revoke all on function sync_inconsistencies() from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        execute 'revoke all on function sync_inconsistencies() from anon';
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'revoke all on function sync_inconsistencies() from authenticated';
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant execute on function sync_inconsistencies() to service_role';
    end if;
end
$$;

-- Make PostgREST (Supabase's API layer) see the new functions right away.
notify pgrst, 'reload schema';
