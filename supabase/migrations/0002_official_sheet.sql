-- Official BTU test sheet support.
-- 1. Test students use example.org emails, so the domain is enforced by the API
--    (ALLOWED_EMAIL_DOMAINS) instead of a fixed check here.
-- 2. Students can arrive with an existing Passport ID such as BTU-AI-000125.

alter table students drop constraint students_email_btu;
alter table students add constraint students_email_lower check (email = lower(email) and email like '%@%');

alter table students drop constraint students_passport_id_format;
alter table students add constraint students_passport_id_format check (
    passport_id ~ '^BTU-[0-9A-Z]+(-[0-9A-Z]+)*$' and length(passport_id) <= 40
);
