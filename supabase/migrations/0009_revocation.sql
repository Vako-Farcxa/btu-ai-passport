-- Migration 0009: Revocation
-- A single version of a passport can be revoked by an admin (wrong award, fraud, an error
-- found after issue). The verification page then shows "Revoked" for that version's code
-- instead of "Valid", and the student can no longer download its PDF. Nothing is deleted
-- and no hash or anchor changes; clearing revoked_at restores the version.
--
-- Archiving a whole student needs no new column: students.deleted_at (migration 0006)
-- already marks it, and the API now treats every version of an archived student as
-- revoked, from that date. Restoring the student clears deleted_at.
--
-- Apply before deploying the backend that reads or writes revoked_at. Safe to run twice.

alter table passport_versions
    add column if not exists revoked_at timestamptz default null;

comment on column passport_versions.revoked_at is
    'Set when an admin revokes this version. Null means the version is in good standing.';
