# Sheet contract

BTU's Google Sheet is the only source of student and skill facts. The sync reads the first worksheet of the spreadsheet id in backend env.

## Header

Row 1 is the header. Names are matched case-insensitively after trim.

| Column | Required | Meaning |
| --- | --- | --- |
| `email` | Yes | Student identity. Must be a `btu.edu.ge` address. Compared trimmed and lowercased |
| `full_name` | Yes | Holder name used the next time a version is issued |
| `skill` | Yes | Official skill name, copied into the passport as written |
| `badge` | No | Badge or stamp. Empty means no badge text |
| `awarded_on` | No | `YYYY-MM-DD`, or empty. Any other value is stored as an unavailable date |

One row is one skill fact. The same email may appear on many rows and still produces one passport.

## Rows the sync ignores

- Blank `email` or blank `skill`.
- An email outside `@btu.edu.ge`.
- A repeated identical fact (`email`, `skill`, `badge`, raw `awarded_on`). It stays one skill entry.

## Identity rules

- Same email, same skill facts: no new version.
- Same email, skill facts changed: one new version for the latest set.
- Same email, only `full_name` changed: no new version. The issued holder name stays frozen.
- New email: new passport and a new permanent passport id.
- Email disappears from the sheet: existing passport is kept. The highest version remains current.

The service-account credentials for this sheet stay in the backend environment.
