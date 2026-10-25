# Sheet contract

BTU's Google Sheet is the only source of student and skill facts. The sync reads the first worksheet of the spreadsheet id in backend env and writes the sync result back to the same rows.

## Header

The header is the first row that contains an email column, so title and note rows above it are skipped. Names are matched case-insensitively after trim. Two layouts are accepted.

### Official BTU test sheet (header on row 3)

| Column | Used as |
| --- | --- |
| `Student ID` | Read, not stored yet |
| `First Name`, `Last Name` | Holder name (`First Last`) |
| `BTU Email (Test)` | Student identity. Trimmed and lowercased. Domain must be in `ALLOWED_EMAIL_DOMAINS` |
| `Program`, `Education Level`, `First Issued (Existing)`, `Student Status` | Read, not stored yet. Rows are not filtered by status |
| `Passport ID (Existing)` | Used as the permanent Passport ID when a new student is first issued. Written back for all the student's rows |
| `Record ID`, `Skill ID`, `Skill Description` | Read, not stored yet |
| `Skill Name` | Skill, copied as written |
| `Skill Category` | Used to compute the badge when `Badge/Stamp Code` is a formula or blank: AI Skill = `BDG-AI-001`, AI Applied Skill = `BDG-AI-002`, AI Advanced Skill = `BDG-AI-003` |
| `Badge/Stamp Code` | Badge |
| `Date Earned` | `YYYY-MM-DD` award date |
| `Passport Sync Status` | Written: `SYNCED` or `FAILED` |
| `Synced Passport Version` | Written: `V1`, `V2`, ... (current version of that student's passport) |
| `Synced At (UTC)` | Written: `YYYY-MM-DD HH:MM UTC` |
| `Sync Error / Notes` | Written: empty, or an error code |

### Old 5-column layout (header on row 1)

`email`, `full_name`, `skill`, `badge`, `awarded_on`. Same meaning as above. Nothing is written back because these columns have no output fields.

One row is one skill fact. The same email may appear on many rows and still produces one passport.

## Rows the sync ignores or fails

- Blank email and blank skill (empty lines, notes below the data): ignored, nothing written.
- Blank email, blank skill, or an email outside `ALLOWED_EMAIL_DOMAINS` (default `btu.edu.ge`): `FAILED` with `missing_email`, `missing_skill` or `email_domain_not_allowed`.
- New student with no name: `FAILED` / `missing_full_name`.
- New student whose existing Passport ID already belongs to another student: `FAILED` / `passport_id_taken`.
- A repeated identical fact (`email`, `skill`, `badge`, raw `awarded_on`). It stays one skill entry.

## Identity rules

- Same email, same skill facts: no new version.
- Same email, skill facts changed: one new version for the latest set.
- Same email, only the name changed: no new version. The issued holder name stays frozen.
- New email: new passport. Its id is `Passport ID (Existing)` when filled, otherwise a new `BTU-XXXXXXXXXX` id.
- Email disappears from the sheet: existing passport is kept. The highest version remains current.

## Write-back

Write-back uses the same service account with the `spreadsheets` scope, so share the sheet with it as **Editor**. A failed write-back is logged and does not undo the sync.

The service-account credentials for this sheet stay in the backend environment.
