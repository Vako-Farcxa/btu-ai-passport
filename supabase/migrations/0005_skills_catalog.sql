-- Skills catalog. One row per skill from the sheet's "Skill ID" column (e.g. SKL-002).
-- RLS is on and there are no policies for anon or authenticated. The API uses the
-- service role, which bypasses RLS.
--
-- skill_entries keeps its copied text (skill, badge, description), which is what
-- passports show and what the fingerprint and anchored content hash are built from.
-- skill_id is only a link to the catalog and is not part of either hash, so existing
-- passports keep their versions and their anchored hashes stay valid.
-- Existing skill_entries rows keep skill_id null: the old sync never saved the sheet's
-- Skill ID, so there is nothing to backfill from.

create table skills (
    id text primary key,
    name text not null,
    category text not null default '',
    badge text not null default '',
    description text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint skills_id_format check (id = upper(id) and length(id) between 1 and 40)
);

alter table skill_entries
    add column if not exists skill_id text references skills (id);

create index if not exists skill_entries_skill_id_idx on skill_entries (skill_id);

alter table skills enable row level security;
