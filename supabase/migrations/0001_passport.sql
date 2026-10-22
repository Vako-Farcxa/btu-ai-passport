-- Passport tables. RLS is on and there are no policies for anon or authenticated.
-- The API uses the service role, which bypasses RLS.

create extension if not exists pgcrypto;

create table students (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    full_name text not null,
    passport_id text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint students_email_btu check (
        email = lower(email) and email like '%@btu.edu.ge'
    ),
    constraint students_passport_id_format check (
        passport_id ~ '^BTU-[0-9A-HJ-KMNP-TV-Z]{10}$'
    )
);

create table passport_versions (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references students (id),
    version_number integer not null check (version_number >= 1),
    holder_name text not null,
    verification_code text not null unique,
    verification_id_hash text not null,
    skill_fingerprint text not null,
    content_hash text not null unique,
    issued_at timestamptz not null default now(),
    pdf_en_path text,
    pdf_ka_path text,
    anchor_status text not null default 'pending',
    tx_hash text,
    anchored_at timestamptz,
    constraint passport_versions_student_version unique (student_id, version_number),
    constraint passport_versions_student_skill unique (student_id, skill_fingerprint),
    constraint passport_versions_code_format check (
        verification_code ~ '^[0-9A-HJ-KMNP-TV-Z]{4}(-[0-9A-HJ-KMNP-TV-Z]{4}){3}$'
    ),
    constraint passport_versions_verification_hash check (
        verification_id_hash ~ '^0x[0-9a-f]{64}$'
    ),
    constraint passport_versions_skill_fingerprint check (
        skill_fingerprint ~ '^0x[0-9a-f]{64}$'
    ),
    constraint passport_versions_content_hash check (content_hash ~ '^0x[0-9a-f]{64}$'),
    constraint passport_versions_anchor_status check (
        anchor_status in ('pending', 'confirmed', 'failed')
    )
);

create table skill_entries (
    id uuid primary key default gen_random_uuid(),
    version_id uuid not null references passport_versions (id),
    skill text not null,
    badge text not null default '',
    awarded_on date,
    position integer not null check (position >= 1),
    constraint skill_entries_unique_fact unique (version_id, skill, badge, awarded_on)
);

create table source_records (
    id uuid primary key default gen_random_uuid(),
    record_key text not null unique,
    email text not null,
    first_seen_at timestamptz not null default now()
);

create table sync_runs (
    id uuid primary key default gen_random_uuid(),
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    rows_read integer not null default 0 check (rows_read >= 0),
    versions_created integer not null default 0 check (versions_created >= 0),
    error text,
    constraint sync_runs_status check (status in ('running', 'completed', 'skipped', 'failed'))
);

-- At most one running sync.
create unique index sync_runs_one_running on sync_runs ((1)) where status = 'running';

alter table students enable row level security;
alter table passport_versions enable row level security;
alter table skill_entries enable row level security;
alter table source_records enable row level security;
alter table sync_runs enable row level security;
