# Backups and restoring

Every night at 02:05 Tbilisi time, `.github/workflows/backup.yml` saves:

- **the database**: every table (`students`, `passport_versions`, `skill_entries`, `skills`, `source_records`, `sync_runs`, `admin_users`, `flags`) as one JSON Lines file each, and
- **the Google Sheet**: every tab as a CSV file (the values as displayed; formatting, formulas and validation rules are not saved),

packs them into one file, **encrypts it with AES-256**, and keeps it as a workflow artifact for **30 days**. The repository is public and anyone signed in to GitHub can download the artifacts of a public repository, so the file is only readable with the `BACKUP_PASSPHRASE` secret. Nothing readable is ever uploaded, and the job log shows only table names and row counts.

**Not in the backup** (and why it is fine):

- *Supabase Auth users*: they are created again the next time someone signs in with Google.
- *The `passports` Storage bucket (PDFs)*: the PDFs are generated from the database. See step 6.
- *The blockchain anchors*: they are public and permanent on Polygon Amoy.
- *The `anchor_reconcile_lock` table*: it only says "an anchoring run is in progress".

## One-time setup: the five repository secrets

On GitHub open the repository, then **Settings**, **Secrets and variables**, **Actions**, **New repository secret**. Add these five, one at a time (Name, then Secret, then **Add secret**):

| Name | Value |
| --- | --- |
| `SUPABASE_URL` | Same as on Render, like `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Same as on Render (Supabase: Project Settings, API, `service_role`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Same as on Render: the whole JSON of the service account key |
| `SHEET_ID` | Same as on Render: the long id in the Sheet's address |
| `BACKUP_PASSPHRASE` | A new, long, random passphrase (16 characters or more). **Save a copy in your password manager.** Without it the backups cannot be opened and nobody can recover it. |

`SYNC_URL` and `SYNC_TOKEN`, which the sync uses, are separate and stay as they are. Secrets are hidden in logs; the backup scripts never print them.

## Run a backup by hand and check it

1. On GitHub open the **Actions** tab, click **Nightly backup** on the left, then **Run workflow** (right side), then the green **Run workflow** button.
2. After about a minute open the new run. All steps should be green. In the **Export the database and the Sheet** step you see lines like `database students: 120 rows` and `Backup complete.`
3. At the bottom of the run, under **Artifacts**, there is `btu-backup-encrypted-N`. Click it to download a zip that holds `btu-backup-YYYY-MM-DD.tar.gz.enc`.
4. Check that it opens (the real test of a backup): follow "Restore" step 1 and 2 below on your PC. `restore_backup.py` without `--yes` prints the row counts and writes nothing. Do this once after the first run, then once a month.

A failed run (missing secret, Sheet no longer shared with the service account, Supabase key rotated) makes GitHub email you. GitHub also switches scheduled workflows off after 60 days without any repository activity, so glance at the Actions tab now and then.

To take a backup from your own PC (the files are NOT encrypted, they hold personal data, so delete them afterwards or encrypt them with `.github/scripts/encrypt-backup.sh`):

```bash
cd backend
uv run python scripts/backup.py --out ../backup-now
```

## Restore

You need this repository on your PC, [uv](https://docs.astral.sh/uv/), and `bash` with `openssl` (on Windows, **Git Bash** has both). Take a backup first (run the workflow by hand) so that you can go back if the restore is not what you wanted.

### 1. Download and decrypt

Download the artifact (see above), unzip it, and from the repository folder run:

```bash
bash .github/scripts/decrypt-backup.sh ~/Downloads/btu-backup-2026-11-01.tar.gz.enc ./restore-work
```

It asks for the passphrase (not shown while you type) and unpacks into `restore-work/`. "Wrong passphrase or not a backup file" means the passphrase is wrong. The same thing without the script:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in btu-backup-2026-11-01.tar.gz.enc | tar -xzf - -C restore-work
```

`restore-work/` now holds `manifest.json`, `database/*.jsonl` and `sheet/*.csv`. Keep it private and delete it when you are done.

### 2. Look inside (writes nothing)

```bash
cd backend
uv run python scripts/restore_backup.py ../restore-work
```

It prints when the backup was taken and how many rows each table and tab has. If it says the backup was incomplete, the manifest lists which half failed.

For the next steps the script needs your keys. If `backend/.env` is filled in (the same values as on Render) it reads them from there. Otherwise set them in the terminal first:

```bash
# Git Bash / Linux / macOS
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="..."
export SHEET_ID="..."
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
```

```powershell
# Windows PowerShell
$env:SUPABASE_URL = "https://xxxx.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "..."
```

### 3. Restore the database

Pick the case that fits.

**A. Some rows were deleted or changed** (the project is still there). The restore puts every saved row back, in the right order (skills, students, versions, skill entries, and so on). A row with the same id is overwritten by the saved copy, rows created after the backup are left alone.

```bash
cd backend
uv run python scripts/restore_backup.py ../restore-work --database            # dry run
uv run python scripts/restore_backup.py ../restore-work --database --yes      # for real
```

**B. Go back exactly to the backup** (for example a bad SQL command or wrong data everywhere). Rows created after the backup would stay with case A, so empty the tables first. This deletes data: make sure you have a fresh backup and the right one decrypted. In the Supabase **SQL Editor** run:

```sql
truncate table flags, skill_entries, passport_versions, source_records,
               students, skills, sync_runs, admin_users cascade;
```

then run the two commands of case A.

**C. A brand-new Supabase project.** Create the project, then in the SQL Editor run every file in `supabase/migrations/` in order (`0001` to the newest). Update `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and the keys for the frontend on Render and Vercel, and update the two repository secrets. Then run the two commands of case A. Turn on Google sign-in in the new project's Auth settings.

If a table fails, the script stops and names it with an HTTP status (for example `table students: HTTP 409`). A 409 means a unique value clashes with a row that is already there but has a different id, which only happens when restoring over different data: use case B.

### 4. Check the result

In the SQL Editor:

```sql
select * from sync_inconsistencies();   -- should return no rows
select count(*) from students;          -- compare with the manifest
```

Then open the admin dashboard: the health banner should be gone. The passports' blockchain anchors come back with the rows (the transaction hashes are in the backup). The next anchor reconcile run re-checks any version that was not confirmed yet.

### 5. Restore the Google Sheet

First try Google's own history: open the Sheet, **File**, **Version history**, **See version history**, pick a version from before the damage and **Restore this version**. That keeps formatting and formulas, which the backup does not.

If that is not enough, restore from the backup. The service account must be an **Editor** of the Sheet (the normal setup):

```bash
cd backend
uv run python scripts/restore_backup.py ../restore-work --sheet            # dry run
uv run python scripts/restore_backup.py ../restore-work --sheet --yes      # for real
```

Each saved tab is cleared and written back (a missing tab is created), with values entered as if typed, so dates stay dates. Formatting, formulas, column widths and validation rules are not restored.

By hand instead: in Google Sheets use **File**, **Import**, **Upload** and choose a file from `restore-work/sheet/` (`manifest.json` says which number is which tab), with **Replace current sheet**.

To restore into a **new Sheet**: create it, share it with the service account's email as Editor, run the command above with the new `SHEET_ID`, and change `SHEET_ID` on Render and in the repository secrets.

### 6. PDFs after a new project

If the Storage bucket is new (case C) the PDFs are gone, but the rows still point at them. In the SQL Editor run

```sql
update passport_versions set pdf_en_path = null, pdf_ka_path = null;
```

and then trigger a sync from the admin dashboard. The sync generates the missing PDFs again.

### 7. Finish

1. Trigger a sync on the admin dashboard and check the banner.
2. Open `https://<your-api>/health/ready`: the database should say `ok`.
3. Delete `restore-work/` from your PC.

## What the backup files look like

- `manifest.json`: when it was taken, the row count per table and tab, and any error.
- `database/<table>.jsonl`: one JSON object per line, exactly as the database returns it.
- `sheet/NN.csv`: one tab each, in the order of the Sheet.

The encryption is OpenSSL `aes-256-cbc` with a random salt and PBKDF2 (600000 rounds). The workflow decrypts its own output again before uploading it, so a file that cannot be opened fails the run instead of waiting for the day it is needed.
