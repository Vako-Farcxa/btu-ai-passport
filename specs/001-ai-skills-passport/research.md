# Research: BTU AI Skills Digital Passport

Phase 0 resolves planning choices against [spec.md](./spec.md) and `AGENTS.md`. No technical-context items remain open.

## 1. Keep the existing two-app layout

- **Decision**: Extend `frontend/` and `backend/src/passport_api/`. Do not add a third package.
- **Rationale**: Both trees, FastAPI, CORS, and the health route already exist. AGENTS.md fixes this layout.
- **Alternatives considered**: A monorepo package for shared types. Rejected. The contract file is the shared source; a generated package would be a new workflow for two hand-mirrored models.

## 2. Sheet shape and idempotent sync

- **Decision**: One header row: `email`, `full_name`, `skill`, `badge`, `awarded_on`. One skill per row. Group rows by trimmed, lowercased email. See [contracts/sheet.md](./contracts/sheet.md).
- **Rationale**: The spec groups a student by email and treats skill, badge/stamp, and award date as the skill facts. A row-per-skill sheet matches that without a column for every skill.
- **Alternatives considered**: One cell with a delimited skill list. Rejected. It makes badge and date ambiguous and makes "the same record" harder to define.

- **Decision**: A source record key is the SHA-256 of the normalized email, skill, badge, and raw award cell. Two fingerprints are stored per version. `skill_fingerprint` is keccak256 of the ordered skill list only and is what the sync compares. `content_hash` is keccak256 of passport id, version number, issued holder name, and that same skill list, and it is the value anchored on Amoy. A new version is created only when the sheet's `skill_fingerprint` differs from the latest version. Identical keys and an equal skill fingerprint do nothing. Removing a skill changes the skill fingerprint, so it issues one new version. A name-only edit does not. The version number stays out of `skill_fingerprint` so an unchanged skill list cannot mint a new version.
- **Rationale**: "Never process the same record twice" and "one new version when skills change" are different rules. Record keys stop duplicate row application. The skill-list fingerprint catches removals and collapses several unseen edits into one version.
- **Alternatives considered**: New version on every sync. Rejected. It breaks the unchanged-sheet rule and would anchor duplicates.

- **Decision**: The only scheduler is a GitHub Actions workflow on cron `*/15 * * * *` (and `workflow_dispatch`). It calls `POST /internal/sync` with header `X-Sync-Token`. The API process does not poll. Overlapping runs: the second call exits as `skipped` when a run is already marked running. A failed sheet read commits nothing.
- **Rationale**: Meets the 15-minute outcome without a loop inside `main.py` and without a new scheduler library. The secret header keeps the route off the public app. Unique constraints on `(student_id, skill_fingerprint)` and `(student_id, version_number)` stop a retry from inserting a second version.
- **Alternatives considered**: An asyncio loop in the API process. Rejected. The schedule belongs in GitHub Actions. APScheduler. Rejected. It would be a new dependency.

## 3. Verification code and the two on-chain fingerprints

- **Decision**: Each version gets one code, `XXXX-XXXX-XXXX-XXXX`, from 16 Crockford Base32 characters (no I, L, O, U). Lookup trims surrounding spaces, removes nothing else, and compares case-insensitively. Stored normalized to uppercase. The code is shown only to the signed-in owner. It is not returned by public verify.
- **Rationale**: Employers can type it. Sixteen symbols from a 32-character alphabet are about 80 bits, so the public fingerprint is not reversible by trying short codes. Case-folding matches the spec.
- **Alternatives considered**: A short 8-character code. Rejected. The on-chain hash would be practical to guess. A UUID. Rejected. It is awkward to read aloud.

- **Decision**: `skill_fingerprint` and `content_hash` are keccak256 of UTF-8 canonical JSON. `verification_id_hash = keccak256(utf-8 uppercase code)`. Canonical JSON uses NFC strings, sorted keys, compact separators, and skills ordered by skill, then badge, then award date, with missing dates last. Dates are `YYYY-MM-DD` or `null`. Sync compares `skill_fingerprint` only. Amoy receives `content_hash` and `verification_id_hash`.
- **Rationale**: keccak256 matches the `bytes32` values the contract stores. The preimage stays in Postgres. Only the two hashes are sent to Amoy.
- **Alternatives considered**: SHA-256 on-chain as raw strings. Rejected. The contract would have to store variable text, which risks putting personal data in the transaction input.

## 4. Anchor contract

- **Decision**: [contracts/PassportAnchor.sol](./contracts/PassportAnchor.sol). The deployer is the BTU test issuer. `anchor(contentHash, verificationIdHash)` reverts unless `msg.sender` is that issuer, and reverts if that verification fingerprint is already stored. It emits `Anchored` and saves the pair. No strings, names, or skill text.
- **Rationale**: This is the smallest contract that makes a second publication of the same version fail on-chain, which matches the "retry does not create a second proof" rule.
- **Alternatives considered**: A bare transaction with no contract, putting the hashes in `data`. Rejected. It has no issuer allowlist and no duplicate guard. A third-party anchoring service. Rejected. AGENTS.md already specifies web3.py and a BTU issuer wallet.

- **Decision**: Chain id 80002. Explorer link `https://amoy.polygonscan.com/tx/{tx_hash}`. RPC URL, contract address, and issuer key come from backend env. Compile once with solc 0.8.24 and commit `backend/assets/PassportAnchor.json`. The API loads that artifact. It does not compile at runtime.
- **Rationale**: Avoids a Solidity compiler dependency in the running service.
- **Alternatives considered**: Hardhat or Foundry as a second toolchain. Rejected for one contract.

- **Decision**: Verify returns `valid` or `outdated` only after the anchor status is `confirmed`. Until then, including a failed send, the outcome is `error`. The next sync polls an existing transaction, or sends one only when the contract slot is empty.
- **Rationale**: Matches FR-011 and the edge case for a PDF that exists before the proof.

## 5. PDFs in both languages

- **Decision**: Two supplied templates, `backend/assets/templates/passport-en.pdf` and `passport-ka.pdf`, plus `fields.json` mapping canonical fields (`holder_name`, `passport_id`, `version`, `issued_on`, `verification_code`, `skill_{n}_name`, `skill_{n}_badge`, `skill_{n}_date`) onto each template's AcroForm names. pypdf fills the form. When skills exceed the template's repeating slots, reportlab appends overflow pages on the same page size, using a Georgian-capable TTF from `backend/assets/fonts/` for `ka` and for any Georgian text in names or skills.
- **Rationale**: Uses both libraries already in the project. The map keeps BTU's design files free of code changes when field names differ. Official skill text is copied, not translated.
- **Alternatives considered**: HTML-to-PDF. Rejected. It would be a new renderer and would not fill the ready-made design. One bilingual PDF. Rejected. The spec now requires a complete PDF in each language.

## 6. Storage and database access

- **Decision**: Private Storage bucket `passports`, objects `{passport_id}/v{version}/en.pdf` and `ka.pdf`. Postgres holds the paths. The backend streams a download after it checks the Supabase JWT and ownership. RLS is enabled on every passport table with no policies for `anon` or `authenticated`. The backend uses the service role.
- **Rationale**: The anon key must stay in the browser for Supabase Auth. RLS makes that key useless for reading passports. A private bucket stops guessing PDF URLs.
- **Alternatives considered**: Public bucket URLs. Rejected. Anyone with a path could download a passport. Direct Postgres from the browser. Rejected. AGENTS.md says the frontend talks only to the API.

## 7. Sign-in limited to btu.edu.ge

- **Decision**: The browser starts Google sign-in with Supabase Auth and `hd=btu.edu.ge` as a hint. Every passport route still sends the Supabase access token as `Authorization: Bearer`. The API verifies the JWT signature and expiry against the project's JWKS, then rejects any email whose domain is not `btu.edu.ge` with `403 domain_not_allowed`. A matching account with no sheet row returns `200` and `"passport": null`.
- **Rationale**: The hosted-domain hint is not a security boundary. The API check is.
- **Alternatives considered**: Trusting the client, or checking the domain only in the Next.js page. Rejected. A copied token from another Google account would still be accepted.

## 8. English and Georgian without a new library

- **Decision**: Message maps in `frontend/src/i18n` for `en` and `ka`. A `passport_locale` cookie stores the choice. First visit: Georgian if the browser prefers `ka`, English if it prefers `en`, otherwise Georgian. `html lang` follows the cookie. Fonts are Noto Sans and Noto Sans Georgian through `next/font`. The API returns stable outcome codes (`valid`, `outdated`, `not_found`, `error`); the maps supply the sentences, including "outdated version".
- **Rationale**: Two languages do not need an i18n framework. `ka` is the language code for Georgian. Geist does not cover Georgian letters.
- **Alternatives considered**: `next-intl` and locale-prefixed routes. Rejected. New dependency and extra routes for a switcher the spec can satisfy with a cookie.

## 9. Motion

- **Decision**: GSAP runs only on the home and passport arrival: opacity and transform, about a short fade/rise, skipped when `prefers-reduced-motion: reduce`. The verify route does not import GSAP. The result is rendered as text plus an icon with an accessible name. Color is not the only signal.
- **Rationale**: AGENTS.md forbids animating the verify result and forbids layout animation.
- **Alternatives considered**: Page transitions on the outcome. Rejected.

## 10. Public verify contract

- **Decision**: `POST /verify` with `{ "code": "..." }`. One JSON object, `outcome` discriminator. Found outcomes include holder name, version, `is_latest`, skills, and `tx_url`. `not_found` and `error` include no passport fields. An empty code is rejected in the form and, if it still reaches the API, with `422 code_required`, never as `not_found`.
- **Rationale**: The four spec states stay distinct from validation. Withholding fields on failure avoids leaking that a similar code exists.
- **Alternatives considered**: HTTP 404 for not found. Rejected. A completed "not found" check is a successful answer, and the UI must not treat it as a transport error.

## 11. What stays off this plan

- **Decision**: No staff UI, no employer accounts, no revocation beyond a newer skill version, no network other than Amoy, no third language, no translation of sheet facts.
- **Rationale**: Those are explicit non-goals in the spec.
- **Alternatives considered**: Translating skill names when the UI language changes. Rejected. The official list would no longer match the PDF or the sheet.
