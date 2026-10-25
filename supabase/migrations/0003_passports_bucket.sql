-- Private storage bucket for issued passport PDFs.
insert into storage.buckets (id, name, public)
values ('passports', 'passports', false)
on conflict (id) do nothing;
