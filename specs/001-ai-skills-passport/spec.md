# Feature Specification: BTU AI Skills Digital Passport

**Feature Branch**: `001-ai-skills-passport`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "BTU AI Skills Digital Passport. Every BTU student gets one unique Digital Passport with a permanent Passport ID. Student and skill data comes from a Google Sheet (BTU's test database of students, AI skills and badges/stamps); the system syncs it periodically, never processes the same record twice, and creates a new passport version when a student's skills change. For each version it automatically generates a complete multi-page PDF passport using BTU's ready-made design, with no manual work per student. Each version is anchored on a blockchain testnet (Polygon Amoy): only a hash and a hashed Verification ID go on-chain, never personal data, issued by a test BTU issuer wallet. Students sign in with Google (btu.edu.ge accounts only) to see their passport, its version history and download the PDF. Employers enter a Verification Code on a public verify page and see the official skill list with dates, the version, whether it is the latest, and a link to the blockchain transaction. Show clear states for valid, outdated version, not found and error. Keep the design minimal and BTU-like with subtle motion."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Issue a passport from the student sheet (Priority: P1)

BTU keeps students, AI skills, and badges/stamps in one sheet. On a regular schedule, the product reads that sheet and maintains exactly one Digital Passport per student. The passport keeps the same Passport ID for the life of that student. When a student's skills change, the product issues one new version, produces a complete multi-page PDF in English and one in Georgian from BTU's supplied designs, and publishes a public test-network proof for that version. Staff do not assemble, export, or anchor passports one student at a time. Reading the same unchanged facts again does not create another passport, version, PDF, or public proof.

**Why this priority**: Nothing else in the product is real until a student has one official passport that stays current without manual work. This is the smallest slice that delivers a finished passport.

**Independent Test**: Update the sheet for one student, wait for the next sync, and confirm that student has one new version, one complete PDF, and one public proof. Sync again without changes and confirm nothing new appears.

**Acceptance Scenarios**:

1. **Given** a student appears on the sheet for the first time with one or more skills, **When** the scheduled sync runs, **Then** the student has exactly one passport, a permanent Passport ID, a first version, a complete multi-page PDF in English, a complete multi-page PDF in Georgian, and one public proof for that version.
2. **Given** a student already has a passport and a skill is added, removed, or its badge/stamp or award date changes, **When** the scheduled sync runs, **Then** exactly one new version is created, a new PDF and a new public proof are created for that version, and the Passport ID stays the same.
3. **Given** the sheet is unchanged since the last successful sync, **When** the sync runs again, **Then** no new passport, version, PDF, or public proof is created.
4. **Given** the same skill change is still the latest fact on the sheet, **When** sync runs more than once, **Then** that change is reflected in only one version.
5. **Given** several students change between syncs, **When** one sync completes, **Then** each of those students receives one new version without a person preparing that student's PDF or public proof.
6. **Given** a new version is issued, **When** someone inspects its public proof, **Then** the proof was published by BTU's test issuer and contains only a fingerprint of the version and a fingerprint of that version's Verification ID, with no name, email, skill text, or badge text.
7. **Given** a student has a current version and an older version, **When** those versions are compared, **Then** each has its own Verification Code, and neither code changes if the sheet is read again.
8. **Given** two sheet rows share one student email, **When** sync runs, **Then** they belong to one passport. Identical skill facts appear once. The same skill with two award dates appears twice.
9. **Given** publication of a version fails, **When** publication is tried again, **Then** the same version gains one public proof and no second version is created. Until that proof exists, checking the version's code shows error.
10. **Given** a person tries to change a skill, name, or badge inside the product, **When** they look for a way to save that change, **Then** they cannot. The sheet remains the only place those facts are changed.
11. **Given** the sheet cannot be read, **When** the cycle ends, **Then** every passport already issued stays unchanged and the next cycle can try again.

---

### User Story 2 - Student opens and downloads their passport (Priority: P2)

A BTU student signs in with Google using a btu.edu.ge account, sees only their own passport, reviews every version, and downloads the PDF for any version. A Google account outside btu.edu.ge cannot enter. A BTU account that does not yet have a passport sees a clear empty state.

**Why this priority**: Students need a self-service way to hold and share the passport the sheet has already issued. The passport is still valuable to BTU without this screen, which is why this follows automatic issuance.

**Independent Test**: Sign in as a student who already has two versions and download each PDF. Separately, attempt sign-in with a non-BTU Google account and confirm the passport is not shown.

**Acceptance Scenarios**:

1. **Given** a student has a btu.edu.ge Google account that matches a student on the sheet, **When** they sign in, **Then** they see their passport, their permanent Passport ID, which version is current, and the history of earlier versions.
2. **Given** a signed-in student is viewing a version, **When** they choose download, **Then** they receive that version's complete PDF.
3. **Given** a person signs in with a Google account that is not a btu.edu.ge account, **When** sign-in is attempted, **Then** they are refused, they see a clear explanation, and no passport is shown.
4. **Given** a btu.edu.ge account matches no student on the sheet, **When** that person signs in, **Then** they see an empty state explaining that no passport is available yet, and they see no other student's data.
5. **Given** a student is signed in, **When** they look for another student's passport, **Then** they cannot open it.
6. **Given** a student prefers reduced motion, **When** they sign in and open their passport, **Then** they can read it and download a PDF with no decorative motion.
7. **Given** a student uses a keyboard only, **When** they sign in and move through the passport, **Then** they can reach the version history and download a PDF without a pointer.
8. **Given** a reviewer opens a student's passport, **When** they compare it with BTU's identity, **Then** the screen is sparse, uses that identity, and any motion only helps the student arrive at the content.
9. **Given** a student is using the passport in either English or Georgian, **When** they switch to the other language, **Then** the product's own labels, history, and actions appear in the selected language, the skill names and holder name stay exactly as recorded on the sheet, and they can download that version's PDF in the selected language.

---

### User Story 3 - Employer verifies a code (Priority: P3)

An employer opens a public page, enters a Verification Code, and immediately sees one clear outcome: valid, outdated version, not found, or error. A matching code shows the official skill list with award dates, the version, whether that version is the latest, the passport holder's name, and a link to that version's public transaction. No account is required.

**Why this priority**: Employers are the reason the passport must be checkable, but they can only check a passport after issuance. This journey stands alone once at least one version and its code exist.

**Independent Test**: Submit four codes against already issued versions: the current version, an older version, an unknown code, and a lookup that cannot be completed. Confirm each shows only its own outcome.

**Acceptance Scenarios**:

1. **Given** a Verification Code belongs to the latest version, **When** an employer submits it on the public page, **Then** the outcome is valid and the page shows the holder's name, that version's skill list with award dates, the version, a clear statement that it is the latest, and a link to that version's public transaction.
2. **Given** a Verification Code belongs to an older version, **When** an employer submits it, **Then** the outcome is outdated version and the page shows that older version's holder name, skill list, and award dates, the version, a clear statement that it is not the latest, and a link to that older version's public transaction.
3. **Given** a Verification Code matches no version, **When** an employer submits it, **Then** the outcome is not found and the page shows no holder name, skill list, or transaction link.
4. **Given** the product cannot complete a lookup, **When** an employer submits a code, **Then** the outcome is error and the page does not call the passport valid or outdated.
5. **Given** any of the four outcomes is shown, **When** the result appears, **Then** it is immediate and still, with no animation playing the result in or altering it.
6. **Given** an employer has no account, **When** they open the verification page, **Then** they can submit a code without signing in.
7. **Given** the verification field is empty, **When** the employer tries to submit, **Then** the page asks for a code and does not show not found.
8. **Given** a code is found, **When** the employer compares the page with that version's PDF, **Then** the holder name, skills, award dates, and version match, and the transaction link belongs to that same version.
9. **Given** an employer uses a keyboard only or cannot rely on color, **When** a result is shown, **Then** they can submit a code from the keyboard and tell valid, outdated version, not found, and error apart without color.
10. **Given** an employer prefers reduced motion, **When** any outcome is shown, **Then** the result appears still, with no decorative motion before or after it.
11. **Given** a code has surrounding spaces or different letter casing, **When** an employer submits it, **Then** it matches the same version as the cleaned code. A code that still matches nothing is not found.
12. **Given** a reviewer looks at the passport and the verification page, **When** they compare both with BTU's identity, **Then** both are sparse, use that identity, and keep motion limited to quiet orientation rather than decoration.
13. **Given** an employer has received an outcome, **When** they switch between English and Georgian, **Then** the labels and the outcome wording change to the selected language, and the outcome, holder name, skill list, dates, version, and transaction link stay the same.

---

### Edge Cases

- The sheet is read twice, including overlapping reads. Unchanged students gain nothing new. A student whose skills changed gains one version for the latest facts, not one version per read.
- Several skill changes for the same student happen before the next sync. One new version captures the sheet's latest skill list, not a version for every intermediate unseen edit.
- A skill row is removed. The next version's official list no longer includes it. Older versions remain checkable and show as outdated.
- A student has many skills. The PDF still includes every skill on that version across as many pages as BTU's design needs. Nothing is dropped to fit a single page.
- A skill has no award date. The skill still appears, and the date is shown as unavailable rather than filled in.
- The same skill and badge appear twice with the same award date. The official list shows that skill once. The same skill with two different award dates shows as two entries.
- The holder's name changes on the sheet but the skills do not. No new version is issued. The issued version keeps the name it had when it was issued.
- A student's email on the sheet changes. The new email is treated as a different student. The passport for the old email remains as last issued.
- A student disappears from the sheet. Existing versions are kept. The last issued version remains the latest. Removal is not treated as revocation.
- A signed-in student has a passport with only one version. History shows that single current version, and its PDF can be downloaded.
- The verification field is submitted empty. The page asks for a code and does not show not found.
- The code has extra spaces or different letter casing. Surrounding spaces are ignored and letter case does not change the match. An otherwise unknown code is not found.
- A version's PDF was created but its public proof is not available yet. Verification of that version's code shows error, not valid or outdated. Retrying publication does not create a second version or a second proof for the same content.
- The sheet cannot be read during a cycle. Passports already issued stay as they are. The next cycle tries again. No partial duplicate versions are created.
- A public proof cannot be opened by the visitor's network. The valid or outdated outcome still stands, and the transaction link remains available to try again.
- The person prefers reduced motion. Sign-in, the passport, and verification remain fully usable with no decorative motion. The verification result is still in every case.
- The person switches language before or after sign-in, and on the public verification page. The selected language applies to the product's own words. Holder names, skill names, and badge text stay as written on the sheet. The verification outcome does not change.
- Two students are present and one student is signed in. That student never sees the other student's passport, PDF, or verification code.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each student on the sheet MUST have at most one Digital Passport, and that passport MUST keep the same Passport ID across every version.
- **FR-002**: Student identity, AI skills, and badges/stamps MUST come only from BTU's student-and-skills sheet. People MUST NOT edit those facts in the product.
- **FR-003**: The product MUST read the sheet on a regular schedule for every student on it, without a person starting the work per student.
- **FR-004**: Students MUST be grouped into one passport by the email address on the sheet.
- **FR-005**: A repeated read of unchanged skill facts MUST NOT create another passport, version, PDF, or public proof.
- **FR-006**: When a student's skills change (a skill or badge/stamp is added or removed, or an award date changes), the product MUST create exactly one new version that reflects the sheet's latest skill list for that student. Several unseen edits between reads MUST still produce only one new version.
- **FR-007**: Every new version MUST receive a complete multi-page PDF in English and a complete multi-page PDF in Georgian. Each MUST use BTU's supplied design for that language, include every skill on that version, and require no manual preparation for that student.
- **FR-008**: Every issued version MUST be published once to the Polygon Amoy test network by BTU's designated test issuer.
- **FR-009**: The public proof for a version MUST contain only a fingerprint of that version and a fingerprint of that version's Verification ID. It MUST NOT contain the student's name, email, Passport ID, skill names, badge or stamp text, dates, or any other personal data.
- **FR-010**: Each version MUST have one Verification Code that does not change after issuance. The current version and each older version MUST have different codes.
- **FR-011**: A failed or repeated publication MUST NOT create a duplicate version or a second public proof for the same version content. Until the public proof exists, a check of that version MUST show error rather than valid or outdated.
- **FR-012**: A student MUST be able to sign in with Google only when the account email is a btu.edu.ge address. Any other Google account MUST be refused with a clear explanation and MUST NOT see a passport.
- **FR-013**: A signed-in student MUST see only the passport whose sheet email matches their btu.edu.ge account, including the Passport ID, which version is current, and the full version history.
- **FR-014**: A signed-in student MUST be able to download the PDF for every version of their own passport, including older versions, in the language they have selected.
- **FR-015**: A signed-in btu.edu.ge student with no matching sheet record MUST see a clear empty state and no other student's information.
- **FR-016**: Any person MUST be able to open the verification page and submit a Verification Code without an account.
- **FR-017**: A verification attempt MUST end in exactly one of these outcomes: valid, outdated version, not found, or error.
- **FR-018**: A code for the latest version whose public proof exists MUST show valid, the holder's name as issued on that version, the official skill list with award dates, the version, a clear statement that it is the latest, and a link to that version's public transaction.
- **FR-019**: A code for an older version whose public proof exists MUST show outdated version, that version's holder name, official skill list with award dates, version, a clear statement that it is not the latest, and a link to that older version's public transaction. It MUST NOT be presented as current.
- **FR-020**: A code that matches no version MUST show not found and MUST NOT reveal a holder name, skill list, Passport ID, or transaction link. An empty submission MUST ask for a code and MUST NOT use the not-found outcome.
- **FR-021**: When the check cannot be completed, including when the matching version has no public proof yet, the page MUST show error and MUST NOT present the passport as valid or outdated.
- **FR-022**: The skill list, holder name, and version shown for a found code MUST match that version's PDF. The transaction link MUST open the public proof for that same version.
- **FR-023**: The verification outcome MUST appear immediately and remain still. Motion MUST NOT introduce, replace, or decorate the result.
- **FR-024**: The passport and verification experience MUST look minimal and consistent with BTU's identity. Motion elsewhere MUST be subtle, MUST support orientation only, and MUST be absent when the person prefers reduced motion.
- **FR-025**: Sign-in and verification MUST be completable by keyboard alone. The four verification outcomes MUST be distinguishable without relying on color alone.
- **FR-026**: Codes MUST match after surrounding spaces are removed, regardless of letter case.
- **FR-027**: An official skill list MUST include every distinct skill fact on that version. A missing award date MUST be shown as unavailable, not replaced with a guessed date. Identical repeated facts MUST appear once. The same skill with different award dates MUST appear once per date.
- **FR-028**: Sign-in, the passport, and public verification MUST be available in English and Georgian. A person MUST be able to switch language on each of those screens, including before sign-in and without an account. Every product-written label and each of the four verification outcomes MUST exist in both languages.
- **FR-029**: Switching language MUST NOT change a verification outcome, the version shown, or the official facts. Holder names, skill names, and badge text MUST remain as recorded on the sheet and MUST NOT be translated by the product.
- **FR-030**: Each issued version MUST have a complete PDF in English and a complete PDF in Georgian, both using BTU's supplied design for that language. The student MUST be able to download the PDF that matches the language they have selected.

### Key Entities *(include if feature involves data)*

- **Student**: A person on BTU's sheet, recognized by their email address. The student has a name and may have skills. The student does not gain a second identity because a sync runs again.
- **Skill entry**: One AI skill on a version, including any badge or stamp from the sheet and the award date when the sheet has one. The official skill list is the set of skill entries on a single version.
- **Digital Passport**: The one credential for a student. It has a permanent Passport ID, a holder name captured when each version is issued, and one or more versions.
- **Passport version**: A frozen official snapshot created when the student's skill list changes. It has a stable version label, an issue time, a Verification Code, an English PDF, a Georgian PDF, and at most one public proof. Older versions stay available after a newer version exists.
- **Verification Code**: The value an employer types to check one specific version. It is the human form of that version's Verification ID. Only a fingerprint of the Verification ID is published.
- **Public proof**: The Polygon Amoy record for one version, published by BTU's test issuer. It stores a fingerprint of the version and a fingerprint of the Verification ID, plus a transaction a person can open from the verification page. It does not store personal data or skill text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a skill change is saved on the sheet, that student has exactly one new version and a complete PDF in both English and Georgian within 15 minutes, with no staff member preparing that passport.
- **SC-002**: In a sync of a 100-student sheet, every changed student receives one new version and every unchanged student receives none. A second sync with no sheet edits creates zero new versions, PDFs, or public proofs.
- **SC-003**: In a review of every public proof, 100% are from BTU's test issuer and 0% contain a student name, email, Passport ID, skill name, badge text, or award date.
- **SC-004**: A student with a btu.edu.ge account can open their passport and download a version's PDF on the first attempt in under 2 minutes. In a trial of non-BTU Google accounts, 100% are refused before any passport is shown.
- **SC-005**: An employer reaches exactly one of the four outcomes within 15 seconds of submitting a code. In a set of outdated codes, 100% are labeled as not the latest. In a set of unknown codes, 0% reveal a skill list or holder name.
- **SC-006**: For every found version in a sample of current and older codes, the name, skills, dates, and version on the page match that version's PDF, and the transaction link opens that version's own public proof.
- **SC-007**: A person who prefers reduced motion can sign in, read the passport, and verify a code with no decorative motion, and the verification result never animates for any person.
- **SC-008**: A keyboard-only user can complete sign-in and submit a verification code without a pointer. Each of the four outcomes remains clear when color is removed.
- **SC-009**: A person can switch the passport and the verification page between English and Georgian in one action. In both languages, 100% of the product's own labels and all four outcomes are present, and the holder name and skill text still match the sheet word for word.

## Assumptions

- The sheet is BTU's test database. It includes the student's name, a btu.edu.ge email, AI skills, badges or stamps, and award dates. Email is the stable student key.
- "The same record" means the same student email with the same skill facts (skill, badge or stamp, and award date). Identical facts are never applied twice. A real change to those facts is applied once, as one new version.
- A new version is created only when skill facts change. A name-only edit does not issue a new version; the current PDF keeps the name from the time it was issued.
- Removing a student from the sheet does not delete or revoke an issued passport. Revocation, beyond issuing a newer version when skills change, is out of scope.
- The Verification Code is the value employers type. The Verification ID is that same credential, and the public proof stores only a fingerprint of it so the code cannot be read back from the public record.
- Each version's code is unique to that version so an older shared code is recognized as outdated instead of showing the student's newest skills.
- The verification page shows the holder's name so an employer can match the applicant. It does not show the student's email or Passport ID.
- Polygon Amoy is the public test network BTU specified. Publication uses one designated BTU test issuer. This feature does not use a production network and does not present the passport as a national or legal identity document.
- BTU supplies the ready-made passport design in English and in Georgian. Each PDF follows that design for its language, including page structure. The product does not offer a third design.
- The web experience supports English and Georgian. On a first visit the product uses Georgian when the person's language preference is Georgian, English when it is English, and Georgian otherwise. The person can switch language at any time, and the latest choice is kept for the next visit.
- Sync runs at least every 15 minutes while the product is operating. Students and employers do not trigger it.
- There is no staff console in this feature. Failed reads are retried on a later cycle and leave issued passports unchanged.
- Employers do not need accounts. Students cannot browse other passports. The public page cannot be used to list students or codes.
- Empty verification submissions are a prompt to enter a code, separate from not found. Codes are compared without surrounding spaces and without regard to letter case.
- A missing award date is shown as unavailable. Duplicate identical skill rows are shown once. The same skill awarded on different dates is shown once per date.
- If publication fails, the version is not treated as checkable until one proof exists. Retries attach that one proof rather than issuing another version.
- If a visitor cannot open the transaction link, the valid or outdated outcome remains, because the failure is outside the check itself.
- Subtle motion may ease arrival on ordinary screens. It is not used on the verification result, and it is turned off when the person prefers reduced motion.
- Sign-in and verification must work by keyboard, and the four outcomes must not depend on color alone, because the page is public and the result must be unambiguous.
- The product does not translate official passport facts. Names, skills, and badges appear in the language in which they were recorded on the sheet, even when the surrounding screen is in the other language.
- Out of scope: editing skills in the product, employer accounts, a staff dashboard, deletion or formal revocation, email notifications, native mobile apps, languages other than English and Georgian, and anchoring on any network other than Polygon Amoy.
