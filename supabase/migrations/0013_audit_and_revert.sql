-- Migration 0013: Admin audit log, and skill sets that can return to an earlier set
-- Safe to run twice. Apply before deploying the backend that writes the audit log. The
-- backend also works without it: a write to a missing audit table is logged and the admin
-- action still goes through.
--
-- 1. admin_audit: one row for each change an admin makes (who, what, to what, when). The
--    backend writes it with the service role after the change has been saved.
-- 2. The old rule "one version per (student, skill set)" made it impossible for a student
--    whose skills return to an earlier set (an award is corrected, then restored) to get a
--    new version: the insert broke the rule and the sync reported an error for that
--    student every 15 minutes. Versions are already unique by (student, version number)
--    and by content hash, which includes the version number, so the rule is not needed.
--    A new version after a return has the same skills as the older one and a new code.

-- 1. Audit log ------------------------------------------------------------------------------
create table if not exists admin_audit (
    id          uuid primary key default gen_random_uuid(),
    created_at  timestamptz not null default now(),
    actor       text not null,
    action      text not null check (char_length(action) between 1 and 64),
    target_type text not null default '' check (char_length(target_type) <= 32),
    target      text not null default '' check (char_length(target) <= 200),
    detail      jsonb not null default '{}'::jsonb
);

create index if not exists admin_audit_created_idx on admin_audit (created_at desc);
create index if not exists admin_audit_target_idx on admin_audit (target, created_at desc);

-- Only the API (service role) touches this table. No policies on purpose.
alter table admin_audit enable row level security;

comment on table admin_audit is
    'One row per admin change, written by the backend with the service role. The app only inserts and reads.';

-- 2. A skill set may come back ---------------------------------------------------------------
alter table passport_versions drop constraint if exists passport_versions_student_skill;
