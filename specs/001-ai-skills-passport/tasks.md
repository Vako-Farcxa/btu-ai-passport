# Tasks: BTU AI Skills Digital Passport

**Input**: Design documents from `/specs/001-ai-skills-passport/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included. plan.md requires tests before the implementation they cover. Write each test task, confirm it fails, then implement.

**Organization**: Tasks are grouped by user story. Delivery order is the one requested for this list: seed data and the public verify flow first, sheet sync next, student sign-in after that, PDF generation after that, Polygon Amoy anchoring last. Sync is only `POST /internal/sync` from `.github/workflows/sync.yml`. Do not add a sync loop to `backend/src/passport_api/main.py`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/src/passport_api/`, `frontend/src/`
- Contracts: `specs/001-ai-skills-passport/contracts/`
- Data rules: `specs/001-ai-skills-passport/data-model.md`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Env examples and the API package the later routes import

- [X] T001 Add `backend/.env.example` with `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SYNC_TOKEN`, `CORS_ORIGINS`, `SHEET_ID`, and `GOOGLE_SERVICE_ACCOUNT_JSON`. Leave `AMOY_RPC_URL`, `ANCHOR_CONTRACT_ADDRESS`, and `BTU_ISSUER_PRIVATE_KEY` listed and commented as chain-phase values. No real secrets.
- [X] T002 [P] Add `frontend/.env.example` with `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL` only
- [X] T003 [P] Create `backend/src/passport_api/api/__init__.py` so route modules can be imported

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, settings, database client, and shared error bodies. No sheet read, PDF, or chain call yet.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `supabase/migrations/0001_passport.sql` with RLS enabled and no `anon` or `authenticated` policies. Tables and constraints, quoted from the data model: Student `email` unique, required, must end with `@btu.edu.ge`; `full_name` required; `passport_id` unique, required, format `BTU-` plus 10 Crockford characters, immutable. Source record `record_key` unique, SHA-256 hex of `email`, `skill`, `badge`, and the raw award cell, joined by U+001F. Passport version `version_number` required and unique with `student_id`; `holder_name` required and frozen at issue; `verification_code` unique, required, normalized `XXXX-XXXX-XXXX-XXXX`; `verification_id_hash` required, `0x` plus 64 hex chars; `skill_fingerprint` required, `0x` plus 64 hex chars, unique with `student_id`; `content_hash` required, `0x` plus 64 hex chars, unique; `anchor_status` one of `pending`, `confirmed`, `failed`, default `pending`; `pdf_en_path` and `pdf_ka_path` nullable. Skill entry `skill` required trimmed, `badge` trimmed and empty string when the cell is empty, `awarded_on` date or null, `position` integer starting at 1. Sync run `status` one of `running`, `completed`, `skipped`, `failed`, with at most one `running` row.
- [X] T005 [P] Load `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SYNC_TOKEN`, and `CORS_ORIGINS` in `backend/src/passport_api/settings.py` from the environment
- [X] T006 Implement the service-role client in `backend/src/passport_api/db.py` using the settings from T005. The frontend must never receive this client.
- [X] T007 [P] Add Pydantic models in `backend/src/passport_api/schemas.py` for `Health`, `ErrorBody` codes `unauthorized`, `domain_not_allowed`, `code_required`, `version_not_found`, `pdf_not_ready`, `sync_unauthorized`, and `Skill` (`skill` string, `badge` string, `awarded_on` string or null) matching `specs/001-ai-skills-passport/contracts/openapi.yaml`
- [X] T008 Return those error bodies from `backend/src/passport_api/main.py` and keep CORS on the existing allowlist. Do not add a lifespan hook, timer, or background task.

**Checkpoint**: Database and shared API types exist. Story work can start. Verify is next, before PDF and chain.

---

## Phase 3: User Story 3 - Employer verifies a code (Priority: P3) 🎯 Early end-to-end

**Goal**: Seed fixed passports, then let anyone submit a code on `/verify` and see one still outcome: valid, outdated version, not found, or error. English and Georgian labels. No PDF and no blockchain in this phase. Confirmed seed rows carry a stored explorer URL so the page can render a link.

**Independent Test**: Run `backend/scripts/seed_demo.py`, open `/verify` signed out, and submit the three seeded codes plus an unknown code and an empty field. Each shows only its own outcome.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T009 [P] [US3] Write failing pytest in `backend/tests/test_verify.py` for `POST /verify`. A code for the latest confirmed version returns `outcome: valid`, `is_latest: true`, holder name, skills, version, and `tx_url`. An older confirmed version returns `outcome: outdated` and `is_latest: false`. An unknown code returns only `outcome: not_found`. A version whose `anchor_status` is not `confirmed` returns only `outcome: error`. A blank code returns `422` with `code: code_required` and is not `not_found`. Surrounding spaces are ignored and letter case does not change the match. Internal characters are kept. Found results omit email, passport id, and the code.
- [X] T010 [P] [US3] Write failing vitest in `frontend/src/lib/api/verify.test.ts`. An empty field does not call the API and is not treated as `not_found`. The four API codes map to distinct labels. `valid` and `outdated` keep the skill text returned by the API without translation.

### Implementation for User Story 3

- [X] T011 [P] [US3] Add `backend/scripts/seed_demo.py` inserting two students and no sheet call. `demo.student@btu.edu.ge` passport id `BTU-A1B2C3D4E5`: version 1 code `K9M2-N3P4-Q5R6-S7T8`, `anchor_status` `confirmed`, holder name frozen, one skill; version 2 code `A1B2-C3D4-E5F6-G7H8`, `anchor_status` `confirmed`, a different skill list, and this version is the maximum. `error.student@btu.edu.ge` passport id `BTU-V2W3X4Y5Z6`: version 1 code `V2W3-X4Y5-Z6A7-B8C9`, `anchor_status` `pending`. Each confirmed row stores `tx_hash` `0x` plus 64 hex chars and a `https://amoy.polygonscan.com/tx/...` URL. Re-running the script does not insert a second passport.
- [X] T012 [P] [US3] Add English and Georgian copy in `frontend/src/i18n/messages.ts` for sign-in, passport, and all four verification outcomes (`valid`, outdated version, not found, error). `ka` is the Georgian code. Cookie `passport_locale` is `en` or `ka`. First visit uses Georgian when the browser prefers `ka`, English when it prefers `en`, otherwise Georgian.
- [X] T013 [P] [US3] Implement lookup in `backend/src/passport_api/verify.py` using the outcome table in `specs/001-ai-skills-passport/data-model.md`: blank after trim is not a lookup; no row is `not_found`; `anchor_status` other than `confirmed` is `error`; confirmed maximum version is `valid`; confirmed older version is `outdated`.
- [X] T014 [US3] Expose `POST /verify` from `backend/src/passport_api/api/verify.py` and register it in `backend/src/passport_api/main.py`. Request and response match `VerifyRequest` and `VerifyResult` in `specs/001-ai-skills-passport/contracts/openapi.yaml`. No auth.
- [X] T015 [P] [US3] Add zod types and a fetch helper in `frontend/src/lib/api/types.ts` and `frontend/src/lib/api/client.ts` for `POST /verify`, matching the OpenAPI schemas field for field
- [X] T016 [US3] Add `frontend/src/components/locale-switcher.tsx` that sets `passport_locale` and updates `html lang` using the messages from T012
- [X] T017 [US3] Build `frontend/src/app/verify/page.tsx` with a code field, submit, loading, the four outcomes, and the locale switcher. Do not import GSAP. Show the result as still text plus an icon that has an accessible name. Do not rely on color alone. Empty submit asks for a code. A found result shows holder name, skills, award dates, version, whether it is latest, and the transaction link. `not_found` and `error` show none of those fields. Switching language changes labels only.
- [X] T018 [US3] Add `frontend/e2e/verify.spec.ts` that, against the seeded codes, checks valid, outdated, not found, empty prompt, error, keyboard submit, both languages, and that the result node does not animate

**Checkpoint**: Seed plus `/verify` works end to end. Stop here to demo verification before any PDF or chain work.

---

## Phase 4: User Story 1 - Issue versions from the sheet (Priority: P1)

**Goal**: `POST /internal/sync`, called by GitHub Actions every 15 minutes, creates and updates passport versions from the sheet. This phase does not generate PDFs or send transactions. New versions stay `anchor_status` `pending`, so their codes verify as `error` until Phase 7. Seeded confirmed rows stay valid.

**Independent Test**: Point sync at a fake sheet, run it twice with no edits, and expect `versions_created: 0`. Change a skill and expect exactly one new version. A second overlapping call returns `skipped`.

### Tests for User Story 1

- [X] T019 [P] [US1] Write failing pytest in `backend/tests/test_fingerprint.py`. `skill_fingerprint` is keccak256 of the ordered skill array only. `content_hash` is keccak256 of the canonical document with `holder_name`, `passport_id`, `skills`, and `version`. A name-only change does not change `skill_fingerprint`. Missing dates sort last. Identical `(skill, badge, awarded_on)` triples collapse to one entry.
- [X] T020 [P] [US1] Write failing pytest in `backend/tests/test_sync.py` using a fake sheet. Rules from `specs/001-ai-skills-passport/contracts/sheet.md`: group by trimmed lowercased email; ignore blank email, blank skill, and non-`btu.edu.ge` email; same skill facts do not create a version; a skill, badge, or award-date change creates exactly one next version; several unseen edits still create one version; a removed skill creates one version; a name-only edit updates `Student.full_name` and does not create a version; a new email creates a new passport id; a disappeared email leaves the old passport in place. `anchor_status` starts at `pending`. `pdf_en_path` and `pdf_ka_path` stay null. A failed sheet read commits nothing. A second run while status is `running` is `skipped`. Wrong or missing `X-Sync-Token` returns `401` with `sync_unauthorized`. Assert `backend/src/passport_api/main.py` starts no background sync.

### Implementation for User Story 1

- [X] T021 [US1] Implement canonical hashes in `backend/src/passport_api/fingerprint.py` as specified in `specs/001-ai-skills-passport/data-model.md` (NFC, sorted keys, compact separators, skills ordered by skill, then badge, then award date)
- [X] T022 [US1] Implement `backend/src/passport_api/sync.py` with gspread and the rules tested in T020. Generate `passport_id` as `BTU-` plus 10 Crockford characters once per student. Generate `verification_code` as `XXXX-XXXX-XXXX-XXXX` from Crockford Base32 excluding I, L, O, and U, stored uppercase. Do not import `pdf.py` or `chain.py`.
- [X] T023 [US1] Expose `POST /internal/sync` from `backend/src/passport_api/api/sync.py`, compare `X-Sync-Token` with `secrets.compare_digest`, and register the router in `backend/src/passport_api/main.py`. Response matches `SyncResult` in the OpenAPI contract. Still no lifespan loop.
- [X] T024 [US1] Add `.github/workflows/sync.yml` with cron `*/15 * * * *` and `workflow_dispatch`. The job `POST`s `${{ secrets.SYNC_URL }}/internal/sync` with header `X-Sync-Token: ${{ secrets.SYNC_TOKEN }}` and fails on a non-success HTTP status. Do not commit the token. Do not add a scheduler inside `backend/src/passport_api/main.py`.

**Checkpoint**: Sheet sync issues versions. Verification of those new codes returns `error` until they are anchored. Seeded codes still verify.

---

## Phase 5: User Story 2 - Student opens their passport (Priority: P2)

**Goal**: A `btu.edu.ge` Google account sees only their passport, version history, and verification code. Other Google accounts are refused. PDF download is Phase 6.

**Independent Test**: Sign in as `demo.student@btu.edu.ge` and see two versions. A non-BTU Google account receives `domain_not_allowed`. A BTU account with no row sees an empty state and no other student's data.

### Tests for User Story 2

- [X] T025 [P] [US2] Write failing pytest in `backend/tests/test_me.py`. `GET /me/passport` with a valid `btu.edu.ge` token returns that email's passport only, newest version first, including `verification_code`. No row returns `200` and `"passport": null`. A token whose email does not end with `@btu.edu.ge` returns `403` `domain_not_allowed`. Missing or invalid bearer returns `401` `unauthorized`.
- [X] T026 [P] [US2] Write failing vitest in `frontend/src/lib/api/passport.test.ts` for the empty body, the `403` explanation, and rendering the caller's versions without another student's passport id

### Implementation for User Story 2

- [X] T027 [US2] Verify the Supabase JWT from the JWKS in `backend/src/passport_api/auth.py`, then reject any email that does not end with `@btu.edu.ge`
- [X] T028 [P] [US2] Add Supabase browser and server clients in `frontend/src/lib/supabase/client.ts` and `frontend/src/lib/supabase/server.ts`, starting Google sign-in with `hd=btu.edu.ge` as a hint only
- [X] T029 [US2] Implement `GET /me/passport` in `backend/src/passport_api/api/me.py` per the OpenAPI `PassportResponse` schema and register it in `backend/src/passport_api/main.py`
- [X] T030 [US2] Build `frontend/src/app/passport/page.tsx` with loading, empty, error, passport id, current version, history, and the owner's verification code. Include the locale switcher. Skill text stays as stored. No download button yet.
- [X] T031 [US2] Replace the starter content in `frontend/src/app/page.tsx` with BTU sign-in and a link to `/verify`. Show the domain refusal message when the API returns `domain_not_allowed`.
- [X] T032 [US2] Add `frontend/e2e/passport.spec.ts` for the empty state, a refused non-BTU session, and a signed-in student who cannot navigate to another passport

**Checkpoint**: Student sign-in and history work beside the already finished verify page.

---

## Phase 6: PDF passports (User Story 1 and User Story 2)

**Goal**: Each new version gets a complete English PDF and a complete Georgian PDF from BTU's templates. The student downloads the one that matches the selected language.

**Independent Test**: Sync a student with more skills than the template's repeating slots. Both PDFs contain every skill. Download `en` and `ka` as that student. Another student receives `404`. A missing file returns `409` `pdf_not_ready`.

### Tests

- [ ] T033 [P] [US1] Write failing pytest in `backend/tests/test_pdf.py`. Filling uses canonical fields `holder_name`, `passport_id`, `version`, `issued_on`, `verification_code`, `skill_{n}_name`, `skill_{n}_badge`, and `skill_{n}_date`. Overflow skills are appended, not dropped. Georgian text is drawn with the TTF from `backend/assets/fonts/`. Skill wording is copied, not translated. Re-running fill for the same version overwrites the same storage paths `{passport_id}/v{version_number}/en.pdf` and `ka.pdf`.

### Implementation

- [ ] T034 [US1] Implement `backend/src/passport_api/pdf.py` with pypdf for AcroForm fill and reportlab for overflow pages. Read the field map from `backend/assets/templates/fields.json` for `passport-en.pdf` and `passport-ka.pdf`. Upload to the private `passports` bucket and set `pdf_en_path` and `pdf_ka_path`.
- [ ] T035 [US1] After a version insert, and when those paths are null on a later sync, call the PDF step from `backend/src/passport_api/sync.py`. Still do not call the chain.
- [ ] T036 [US2] Add `GET /me/passport/versions/{version}/pdf?lang=en|ka` to `backend/src/passport_api/api/me.py`. Owner and `btu.edu.ge` checks apply. Missing version is `404` `version_not_found`. Null path is `409` `pdf_not_ready`. Stream `application/pdf`.
- [ ] T037 [US2] Add a download control to `frontend/src/app/passport/page.tsx` that requests the PDF for the selected locale and surfaces `pdf_not_ready` without treating it as an empty passport

**Checkpoint**: Versions now have both PDFs. Anchoring is still pending, so sheet-issued codes still verify as `error`.

---

## Phase 7: Polygon Amoy anchor (User Story 1)

**Goal**: Publish each version once from the BTU test issuer. The transaction contains only `content_hash` and `verification_id_hash`. After confirmation, verify returns `valid` or `outdated` and the real explorer link.

**Independent Test**: Anchor a pending seeded or synced version. The contract stores the two hashes and rejects a second anchor for that verification hash. Public verify for that code flips from `error` to `valid` or `outdated`. A failed send stays `failed` and can be retried only while the contract slot is empty.

### Tests

- [ ] T038 [P] [US1] Write failing pytest in `backend/tests/test_chain.py`. The payload is two `bytes32` values and no name, email, or skill string. A second anchor of the same `verification_id_hash` is not sent when the contract slot is filled. `anchor_status` moves `pending` → `confirmed` on a successful receipt, `pending` → `failed` on a failed send, and `failed` → `confirmed` only after a later success. `tx_url` is `https://amoy.polygonscan.com/tx/{tx_hash}`.

### Implementation

- [ ] T039 [US1] Add chain settings `AMOY_RPC_URL`, `ANCHOR_CONTRACT_ADDRESS`, and `BTU_ISSUER_PRIVATE_KEY` to `backend/src/passport_api/settings.py`. Keep them out of `frontend/.env.example`.
- [ ] T040 [US1] Implement `backend/src/passport_api/chain.py` with web3.py against chain id 80002, loading the ABI from `backend/assets/PassportAnchor.json`. Sender must be the issuer. Persist `tx_hash`, `anchor_status`, and `anchored_at` on the version.
- [ ] T041 [US1] Add `backend/scripts/deploy_anchor.py` that deploys `specs/001-ai-skills-passport/contracts/PassportAnchor.sol` from the issuer wallet (issuer is `msg.sender`) and writes `backend/assets/PassportAnchor.json` (ABI and bytecode). The running API does not compile Solidity.
- [ ] T042 [US1] From `backend/src/passport_api/sync.py`, after the version row exists, poll a known `tx_hash` or send one anchor when the contract slot is empty. Do not create a second version for the same `skill_fingerprint`. Confirmed versions then satisfy `valid` / `outdated` in `backend/src/passport_api/verify.py`.

**Checkpoint**: Sheet-issued versions verify with a real Amoy link. Personal data remains off-chain.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Motion, reduced motion, and the quickstart commands

- [ ] T043 [P] Add `frontend/src/components/entrance.tsx` and use it only from `frontend/src/app/page.tsx` and `frontend/src/app/passport/page.tsx`. GSAP may animate `opacity` and `transform` only. Skip it when `prefers-reduced-motion: reduce`. `frontend/src/app/verify/page.tsx` must not import it.
- [ ] T044 [P] Add `frontend/e2e/motion.spec.ts` to tab through sign-in and verify without a pointer, and to confirm the entrance does not run under reduced motion
- [ ] T045 Run the backend and frontend commands in `specs/001-ai-skills-passport/quickstart.md` and fix any failure in the files those commands report

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup. Blocks every story
- **Verify (Phase 3, US3)**: Depends only on Foundational. This is the early end-to-end slice
- **Sheet sync (Phase 4, US1)**: Depends on Foundational. Does not require the verify page, but delivery order places it after Phase 3
- **Student (Phase 5, US2)**: Depends on Foundational. Uses versions from the seed or from Phase 4
- **PDF (Phase 6)**: Depends on Phase 4 version rows and Phase 5 ownership checks
- **Anchor (Phase 7)**: Depends on Phase 4 version rows. PDF upload is not required for anchoring
- **Polish (Phase 8)**: Depends on the stories you intend to demo

### User Story Dependencies

- **User Story 3 (P3)**: First story to finish. Independent via `backend/scripts/seed_demo.py`
- **User Story 1 (P1)**: Split on purpose. Versions in Phase 4, PDFs in Phase 6, anchoring in Phase 7
- **User Story 2 (P2)**: Sign-in and history in Phase 5. Download in Phase 6 after the files exist

### Within Each User Story

- Tests fail before implementation
- Schema and hashes before services
- Services before routes
- Routes before pages that call them
- Seed before the verify end-to-end test

### Parallel Opportunities

- T002 and T003 with T001
- T005 and T007 with T004
- T009 and T010 together; then T011, T012, T013, and T015 together
- T019 and T020 together
- T025 and T026 together; T027 and T028 together
- T033 before PDF implementation; T038 before chain implementation
- T043 and T044 together

---

## Parallel Example: User Story 3

```bash
# Failing tests together:
Task: "Write failing pytest in backend/tests/test_verify.py"
Task: "Write failing vitest in frontend/src/lib/api/verify.test.ts"

# After those fail, independent files together:
Task: "Add backend/scripts/seed_demo.py"
Task: "Add frontend/src/i18n/messages.ts"
Task: "Implement backend/src/passport_api/verify.py"
Task: "Add frontend/src/lib/api/types.ts and client.ts"
```

---

## Implementation Strategy

### MVP First (verify from seed)

1. Complete Phase 1 and Phase 2
2. Complete Phase 3 (seed, `POST /verify`, `/verify`)
3. **STOP and VALIDATE**: four outcomes, both languages, no animation on the result
4. Demo verification before PDF or chain work

### Incremental Delivery

1. Foundation → verify demo
2. Sheet sync on the GitHub Actions schedule → new versions, still `error` until anchored
3. Student sign-in and history
4. English and Georgian PDFs and download
5. Amoy anchor → those versions become `valid` or `outdated`
6. Polish motion and run the quickstart commands

### Parallel Team Strategy

After Phase 2:

- One person finishes Phase 3 before anyone needs the verify page
- Sheet sync (Phase 4) and the verify page do not share feature code beyond the database
- PDF (Phase 6) and the anchor (Phase 7) should not edit `backend/src/passport_api/sync.py` at the same time

---

## Notes

- [P] tasks use different files and do not depend on unfinished tasks
- [US1], [US2], and [US3] map to spec.md stories. US1 is split across Phases 4, 6, and 7 so PDF and chain stay after verify
- The only scheduler is `.github/workflows/sync.yml`. `backend/src/passport_api/main.py` does not poll
- Commit after each task or logical group
- Stop at the Phase 3 checkpoint to validate verification on its own
