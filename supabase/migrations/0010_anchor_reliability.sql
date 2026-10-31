-- Migration 0010: Anchor reliability
-- Anchoring used to be fire and forget: one transaction, a 45 second wait, and a "failed"
-- flag that was retried blindly. A dropped or stuck transaction could leave a version pending
-- forever. The reconciler (backend/src/passport_api/anchoring.py) now tracks every attempt, so
-- it can check receipts, replace a stuck transaction with the same nonce and a higher gas
-- price, back off after failures, and stop at an attempt cap for an admin to look at.
--
-- anchor_status gains two values:
--   retrying          a send failed or a transaction was replaced; the reconciler will retry.
--   failed_permanent  the attempt cap was reached, or the chain slot holds other content.
-- The old value "failed" stays allowed so a backend deployed before this migration keeps
-- working; the new backend reads it as "retrying", and the update below converts existing rows.
--
-- Apply before deploying the backend that reads or writes these columns. Safe to run twice.

alter table passport_versions
    add column if not exists anchor_nonce bigint,
    add column if not exists anchor_gas_price bigint,
    add column if not exists anchor_submitted_at timestamptz,
    add column if not exists anchor_attempts integer not null default 0,
    add column if not exists anchor_last_error text,
    add column if not exists anchor_next_attempt_at timestamptz,
    add column if not exists anchor_tx_hashes text[] not null default '{}';

comment on column passport_versions.anchor_nonce is
    'Nonce of the latest anchor transaction. A replacement reuses it.';
comment on column passport_versions.anchor_gas_price is
    'Gas price (wei) of the latest anchor transaction or replacement offer.';
comment on column passport_versions.anchor_submitted_at is
    'When the latest anchor transaction was broadcast. Drives the stuck and dropped timers.';
comment on column passport_versions.anchor_attempts is
    'Counted sends and failures. Reset by an admin retry. Capped by the reconciler.';
comment on column passport_versions.anchor_last_error is
    'Short code for the last problem (no URLs or keys). Cleared on confirmation.';
comment on column passport_versions.anchor_next_attempt_at is
    'Backoff: the reconciler leaves the version alone until this time.';
comment on column passport_versions.anchor_tx_hashes is
    'Every anchor transaction ever sent for this version, so a replaced one that mines anyway is found.';

alter table passport_versions drop constraint if exists passport_versions_anchor_status;
alter table passport_versions
    add constraint passport_versions_anchor_status check (
        anchor_status in ('pending', 'retrying', 'confirmed', 'failed', 'failed_permanent')
    );

alter table passport_versions drop constraint if exists passport_versions_anchor_attempts;
alter table passport_versions
    add constraint passport_versions_anchor_attempts check (anchor_attempts >= 0);

-- Existing rows: legacy "failed" becomes "retrying", and a known tx_hash becomes the first
-- entry of the history (a pending one starts its stuck timer now).
update passport_versions set anchor_status = 'retrying' where anchor_status = 'failed';

update passport_versions
set anchor_tx_hashes = array[tx_hash]
where tx_hash is not null
  and cardinality(anchor_tx_hashes) = 0;

update passport_versions
set anchor_submitted_at = now()
where tx_hash is not null
  and anchor_status <> 'confirmed'
  and anchor_submitted_at is null;

create index if not exists passport_versions_anchor_open
    on passport_versions (issued_at)
    where anchor_status <> 'confirmed';

-- One row that serialises reconciler runs, so two runs (sync cron, the reconcile endpoint, an
-- admin retry) never pick the same nonce at the same time. The backend takes it with one
-- conditional UPDATE and releases it when the run ends; an expired lock is free.
create table if not exists anchor_reconcile_lock (
    name text primary key,
    locked_until timestamptz not null default 'epoch'
);

insert into anchor_reconcile_lock (name) values ('reconciler') on conflict (name) do nothing;

alter table anchor_reconcile_lock enable row level security;
