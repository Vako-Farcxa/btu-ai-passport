-- Migration 0005: Admin panel support
-- Adds the admin_users allow-list and extends the students table with
-- admin_managed + deleted_at columns required by the admin panel.

-- Admin allow-list -------------------------------------------------------
-- Only the service-role key can access this table (no anon/authenticated
-- policies). The API's require_admin() helper queries it to authorise staff.
create table admin_users (
    id         uuid primary key default gen_random_uuid(),
    email      text unique not null check (email like '%@btu.edu.ge'),
    created_at timestamptz not null default now()
);

alter table admin_users enable row level security;
-- Intentionally no policies: service role bypasses RLS.

-- Extend students ---------------------------------------------------------
-- admin_managed = true  → sheet sync skips this student entirely;
--                         the admin panel is the sole source of truth.
-- deleted_at  is not null → student is soft-deleted:
--                         cannot sign in, hidden from the panel by default,
--                         sheet sync skips them too.
alter table students
    add column if not exists admin_managed boolean not null default false,
    add column if not exists deleted_at    timestamptz     default null;
