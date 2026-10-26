-- Official sheet column "Skill Description". Display only: not part of the
-- skill fingerprint or the anchored content hash, so it can be filled in for
-- already anchored versions without changing what the blockchain proves.
alter table skill_entries
    add column if not exists description text not null default '';
