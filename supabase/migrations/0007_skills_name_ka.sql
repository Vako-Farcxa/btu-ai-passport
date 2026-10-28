-- Migration 0007: Add name_ka to skills catalog
-- Georgian name for the skills catalog, edited on the admin Skills page and in the
-- Skills tab of the sheet. name stays the English name. Apply before deploying the
-- backend that reads or writes name_ka.

alter table skills
    add column if not exists name_ka text not null default '';

