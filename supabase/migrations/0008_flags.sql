-- Migration 0008: Student flags
-- A student can flag a version of their passport ("something looks wrong"). Admins
-- review the flag on /admin/flags, resolve or dismiss it with a note, and the student
-- sees the reply on their passport page. Flags never change a passport or any hash.
--
-- Apply before deploying the backend that serves /flags, /me/flags and /admin/flags.

create table flags (
    id                uuid primary key default gen_random_uuid(),
    passport_id       text not null references students (passport_id) on delete cascade,
    version           integer not null check (version >= 1),
    verification_code text not null,
    student_email     text not null,
    comment           text not null check (char_length(comment) between 10 and 500),
    status            text not null default 'open'
                      check (status in ('open', 'resolved', 'dismissed')),
    admin_note        text not null default '' check (char_length(admin_note) <= 500),
    resolved_by       text,
    created_at        timestamptz not null default now(),
    resolved_at       timestamptz,
    -- Set when the student opened their flags after the admin replied. Cleared again
    -- whenever an admin changes the reply, so "unseen reply" is status <> 'open' and
    -- student_seen_at is null.
    student_seen_at   timestamptz
);

-- One open flag per version. Resolved and dismissed flags do not block a new one.
create unique index flags_one_open_per_version
    on flags (passport_id, version) where status = 'open';

create index flags_status_created_idx on flags (status, created_at desc);
create index flags_student_idx on flags (student_email, created_at desc);

-- Only the API (service role) touches this table. No policies on purpose.
alter table flags enable row level security;
