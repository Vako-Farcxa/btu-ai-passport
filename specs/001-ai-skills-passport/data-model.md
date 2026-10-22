# Data Model: BTU AI Skills Digital Passport

Postgres tables below are created in `supabase/migrations`. RLS is enabled on each table. There are no `anon` or `authenticated` policies. The API uses the service role. Field names match [contracts/openapi.yaml](./contracts/openapi.yaml).

Strings are stored as NFC. Emails are stored trimmed and lowercased.

## Student

One row per sheet email. The passport id is created with the row and never changes.

| Field | Rules |
| --- | --- |
| `id` | UUID, primary key |
| `email` | Unique, required, must end with `@btu.edu.ge` |
| `full_name` | Required. Latest name seen on the sheet. Not copied onto older versions |
| `passport_id` | Unique, required. Format `BTU-` plus 10 Crockford characters. Immutable |
| `created_at`, `updated_at` | Timestamps |

A sheet email that changes is a different student and a new passport. The old row stays.

## Source record

One row per distinct sheet skill fact the sync has already accepted. Used to prove a repeated read did not create work. Version creation itself depends on `Passport version.skill_fingerprint`, so a deletion (no new key) can still issue a version.

| Field | Rules |
| --- | --- |
| `id` | UUID, primary key |
| `record_key` | Unique. SHA-256 hex of `email`, `skill`, `badge`, and the raw award cell, joined by U+001F |
| `email` | Required |
| `first_seen_at` | Timestamp |

## Passport version

A frozen snapshot. Version numbers start at 1 and increase by 1 for that student.

| Field | Rules |
| --- | --- |
| `id` | UUID, primary key |
| `student_id` | Required, foreign key to Student |
| `version_number` | Required, unique with `student_id` |
| `holder_name` | Required. Name at the moment of issue. Later sheet edits do not change it |
| `verification_code` | Unique, required. Normalized `XXXX-XXXX-XXXX-XXXX` |
| `verification_id_hash` | Required. `0x` plus 64 hex chars. keccak256 of the uppercase code |
| `skill_fingerprint` | Required. `0x` plus 64 hex chars. Unique with `student_id`. Skill list only. This is the sync comparison |
| `content_hash` | Required. `0x` plus 64 hex chars. Unique. Anchored on Amoy. Includes passport id, version, issued name, and skills |
| `issued_at` | Timestamp |
| `pdf_en_path`, `pdf_ka_path` | Storage paths. Null until that file is uploaded |
| `anchor_status` | `pending`, `confirmed`, or `failed`. Starts `pending` |
| `tx_hash` | Null until a transaction is sent |
| `anchored_at` | Null until `confirmed` |

Unique `(student_id, skill_fingerprint)` makes a retry of the same skill list insert no second version.

### Fingerprints

Both are keccak256 over UTF-8 JSON with sorted keys and compact separators. Skills are ordered by `skill`, then `badge`, then `awarded_on`, missing dates last.

`skill_fingerprint` is the skill array only:

```json
[{ "awarded_on": "YYYY-MM-DD or null", "badge": "string", "skill": "string" }]
```

`content_hash` is the anchored version document. The version number is included here so two versions never share an on-chain fingerprint. It is not used to decide whether skills changed:

```json
{
  "holder_name": "string",
  "passport_id": "string",
  "skills": [{ "awarded_on": "YYYY-MM-DD or null", "badge": "string", "skill": "string" }],
  "version": 1
}
```

The verification code is not part of either document. Its fingerprint is `verification_id_hash`.

### Issue rules

- No student row: create Student, passport id, and version 1.
- Latest `skill_fingerprint` equals the sheet's current skill list: do not create a version. If PDFs or the anchor are unfinished, resume those steps.
- Skill fingerprint differs (skill or badge added or removed, or award date changed): insert exactly one next version inside the uniqueness rules, then generate both PDFs and anchor.
- Name-only sheet change: update `Student.full_name` only.
- Sheet read failure: commit no version, skill, or anchor change.
- Student missing from the sheet: leave existing rows as they are. The highest version stays current.

## Skill entry

Belongs to one version. Official list for that version. Text is the sheet text, not a translation.

| Field | Rules |
| --- | --- |
| `id` | UUID, primary key |
| `version_id` | Required, foreign key, cascade delete not used after issue |
| `skill` | Required, trimmed |
| `badge` | Trimmed, empty string if the cell is empty |
| `awarded_on` | Date or null when the cell is empty or not `YYYY-MM-DD` |
| `position` | Integer display order, starting at 1 |

Identical `(skill, badge, awarded_on)` triples are inserted once. The same skill with two dates is two rows.

## Sync run

Operational only. Not shown to students or employers.

| Field | Rules |
| --- | --- |
| `id` | UUID, primary key |
| `status` | `running`, `completed`, `skipped`, or `failed` |
| `started_at`, `finished_at` | Timestamps |
| `rows_read`, `versions_created` | Integers |
| `error` | Null, or a short code such as `sheet_unavailable` |

At most one `running` row. A second trigger records `skipped` and does not read the sheet.

## File objects

Bucket `passports`, private.

- `{passport_id}/v{version_number}/en.pdf`
- `{passport_id}/v{version_number}/ka.pdf`

The database stores those paths on the version. There is no public URL.

## Relationships

- Student 1 — * Passport version
- Passport version 1 — * Skill entry
- Passport version 1 — 1 on-chain anchor (the hash columns and `tx_hash` on the version; the chain copy is only `content_hash` and `verification_id_hash`). `skill_fingerprint` stays in Postgres.

## State transitions

### Anchor

`pending` → `confirmed` when the Amoy receipt succeeds and the contract stores this version's pair.

`pending` → `failed` when the send or receipt fails. The next sync may try again only if this verification fingerprint is still empty on the contract. A second confirmed pair is not allowed.

`failed` → `confirmed` on a later successful receipt. `confirmed` does not change.

### Verification outcome

Derived, not stored:

| Condition | Outcome |
| --- | --- |
| Code missing or blank after trim | Not an outcome. `422 code_required` |
| No version with that normalized code | `not_found` |
| Version found, `anchor_status` is not `confirmed` | `error` |
| Confirmed, and `version_number` is the student's maximum | `valid`, `is_latest: true` |
| Confirmed, and a higher version exists | `outdated`, `is_latest: false` |
| Database or unexpected failure while checking | `error` |

`valid` and `outdated` include the frozen holder name, that version's skill entries, the version number, and the Amoy transaction URL. They do not include email, passport id, or the code.

## Validation summary

- Passport id and verification code are generated by the server. Clients cannot set them.
- A student JWT can read only the student whose email equals the token email.
- Public verify accepts a code and returns one outcome object. It cannot list students.
- On-chain writes accept only the two `bytes32` values, from the issuer wallet.
