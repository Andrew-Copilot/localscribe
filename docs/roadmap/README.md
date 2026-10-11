# Local Scribe desktop roadmap

**Status:** proposed planning baseline  
**Scope:** desktop product only. Mobile work is intentionally out of scope because Local Scribe's primary workload—private, long-running local transcription of research recordings—is better served by desktop hardware, storage, and operating-system capabilities.

## Product north star

Local Scribe is an offline-first desktop workstation for researchers who need to transcribe, correct, validate, de-identify, archive, and export sensitive interview and media data while retaining custody of the data.

Product decisions must preserve these principles:

1. **Local processing by default.** Audio/video and transcripts remain on the researcher's computer unless the researcher explicitly exports or backs them up.
2. **Human validation.** AI transcription is a draft; the product must make review, correction, provenance, and sign-off efficient.
3. **No surprise network use.** Any network action must be visible, consented to, and compatible with Offline Lock.
4. **Institutional storage controls.** U of I Box is the planned backup destination. Source media containing PHI must only be backed up to an approved Box Health Data Folder (BHDF).
5. **Portable, auditable projects.** Projects must be recoverable, shareable through deliberate workflows, and traceable to model/settings/version information.

## Prioritized releases

| Release | Theme | Primary outcome |
|---|---|---|
| 1.02 | Safe storage and recovery | Researchers can back up and restore projects safely, with PHI-aware Box safeguards. |
| 1.03 | Fast human validation | Researchers can review uncertain transcript sections quickly and record validation status. |
| 1.04 | Portable research collaboration | Projects can be handed off, inspected, and re-imported without a cloud service. |
| 1.05 | Research-quality assistance | Vocabulary, de-identification review, multilingual validation, and cautious speaker assistance improve outcomes. |
| Ongoing | Accessibility, release trust, quality | The app is usable, supportable, testable, and trusted on supported desktops. |

## 1.02 — Safe storage and recovery

### Box backup integration

Build an **opt-in U of I Box backup** feature. It must use Box OAuth authorization for the signed-in researcher's account; do not embed a shared Box credential or automatically sync projects.

#### Backup destinations

- **Standard U of I Box folder:** may store projects that do not contain PHI, subject to applicable institutional data policy.
- **Approved Box Health Data Folder (BHDF):** required whenever source media contains PHI. The user must choose a folder to which their authorized Box account already has access.
- **No configured destination:** backup remains unavailable; Local Scribe must not silently select a generic Box folder.

#### PHI safety gate

At project creation and before the first backup, require the user to declare one of:

- `No PHI in source media`
- `Source media may contain PHI`
- `Unknown — treat as PHI`

If the last two values are selected:

- Disable backup to non-BHDF destinations.
- Require explicit selection and verification of an approved BHDF.
- Block backup if the destination cannot be verified; give a safe local-export alternative and explain that institutional approval is required.
- Never infer that a folder is a BHDF solely from its name. The verification mechanism and permitted metadata must be confirmed with U of I Box/HIPAA administrators before implementation.

#### Backup behavior

- Back up an immutable project snapshot, not the live working directory.
- Include a manifest with project format version, Local Scribe version, model/settings provenance, file list, sizes, SHA-256 checksums, PHI declaration, destination type, and backup timestamp.
- Support media-included and transcript-only backups. For PHI projects, both variants still require BHDF because transcripts and metadata may themselves be PHI.
- Use resumable uploads where supported; display progress, cancellation, retry, and a final verification result.
- Keep no Box access token in project archives or logs. Store refresh credentials only in the OS credential store/keychain, scoped to the least access possible.
- Do not download or synchronize remotely in the background. Restore/import requires an explicit user action.

#### Governance dependency

Before coding the Box connector, obtain written guidance from the U of I HIPAA Privacy Office and Box administrators on:

- how Local Scribe may reliably recognize a BHDF through the Box API or approved configuration;
- whether OAuth/Box app registration is permitted for BHDF access;
- required scopes, retention, collaboration, audit, encryption, and consent expectations;
- whether the app may upload directly to a BHDF, or must use another approved institutional workflow.

### Recovery, diagnostics, and safety

- Add local snapshot/restore UI in addition to Box backup.
- Add project integrity verification for local and imported archives.
- Add a sanitized diagnostics bundle: app/runtime version, OS, hardware detection, dependency health, and selected logs. Never include source media, transcript content, access tokens, or absolute user paths unless explicitly opted in.
- Improve first-run checks: supported runtime, free disk space, model download size, usable data directory, and model integrity.
- Confirm-before-delete and confirm-before-overwrite behavior for projects, imports, and backups.

## 1.03 — Fast human validation

### Review Mode

Create a keyboard-first review workflow based on the existing word timestamps, confidence markers, speaker labels, proofreader, and revision history.

- Queue low-confidence segments, possible artifacts, unassigned speakers, manual flags, and segments edited since validation.
- Provide replay, slower playback, configurable pre-roll/post-roll, loop/replay selection, accept/edit/split/merge, and speaker assignment shortcuts.
- Advance to the next outstanding review item after an action.
- Show review progress, remaining issue counts, and filters.
- Preserve a revision when a user marks a transcript as validated.

### Document state and sign-off

Add explicit states:

`Draft → Transcribed → In review → Validated → Exported`

- Track reviewer identity/initials, validation time, notes, and review completion state locally in the project.
- Mark exports with draft/validated status and provenance.
- Let users reopen a validated document deliberately; record the resulting change in provenance.

### Editing ergonomics

- Improve waveform zoom/cursor behavior and timestamp navigation.
- Add playback speed and robust keyboard navigation.
- Add find/replace preview before applying multi-segment edits.
- Ensure confidence, review, and speaker states do not rely on color alone.

## 1.04 — Portable research collaboration

### Versioned project format

Formalize and document the `.lsproj` format:

- format version and migrations;
- manifest and checksums;
- Local Scribe/model/settings provenance;
- source-media checksum and availability state;
- validation/sign-off and export history;
- safe behavior when importing transcript-only projects without source media.

### Deliberate offline handoff

- Create review/handoff packages containing selected transcript, optional media, comments, instructions, and provenance.
- Add timestamped segment annotations and unresolved questions.
- Detect import conflicts and preserve both revisions rather than overwrite work.
- Do not add real-time multi-user editing until file-based handoff, conflict handling, and institutional privacy requirements have been validated.

## 1.05 — Research-quality assistance

### Vocabulary and study presets

- Reusable study/project vocabulary profiles.
- CSV/TXT terminology import.
- Pre-transcription vocabulary review wired to current prompt/hotword settings.
- Recurring uncertain-term report.
- Shareable configuration presets that omit sensitive project data.

### De-identification review assistance

Implement as a review aid, never as a compliance guarantee or silent redaction:

- Flag likely names, emails, telephone numbers, addresses, dates, IDs, and user-defined patterns.
- Support consistent researcher-approved replacements such as `[PARTICIPANT_01]`.
- Keep replacement mappings local and separate from a shareable derivative transcript.
- Produce a review report with flagged, accepted, skipped, and unresolved findings.
- Preserve original text and make every replacement reversible through revision history.

### Multilingual and speaker assistance

- Do not claim language support until the full workflow—transcription, proofreading, exports, and tests—is validated for that language.
- Add language selection/auto-detection only with documented supported-language coverage.
- Improve manual speaker workflow first.
- Consider experimental offline diarization only when assignments are reversible, confidence is visible, and human confirmation is required.

## Ongoing quality and release trust

### Accessibility

- Full keyboard operation and visible focus handling.
- Screen-reader semantics and modal focus management.
- High-contrast and scalable-text support.
- Avoid color-only meaning.
- Add accessibility checks and keyboard-only workflow testing to release criteria.

### Quality engineering

- End-to-end fixtures: import media → transcribe fixture → edit/review → export → archive/import.
- Golden-file tests for SRT, VTT, DOCX, JSON, and `.lsproj` archives.
- Upgrade/migration tests for per-user data directories.
- Box connector tests using mocked Box APIs only; never use PHI fixtures.
- A consented, non-sensitive benchmark corpus for regression tracking.

### Signing and distribution

Implement a signing feasibility spike before committing to a distribution channel:

- **Windows:** evaluate free Microsoft Store distribution of an MSIX package, where Microsoft signs the Store package, versus a non-Store signed installer. Confirm that the app's filesystem, bundled runtime, and local-model workflow work acceptably under MSIX packaging before adopting it.
- **macOS:** direct distribution needs Developer ID signing and notarization. Request an Apple Developer Program fee waiver if the UIC/U of I organization qualifies as an accredited educational institution; otherwise budget for the annual program membership.
- **Open-source option:** investigate SignPath Foundation eligibility for release signing. Treat acceptance as uncertain and do not make the release process depend on it.
- Keep unsigned builds available only as a documented fallback during the transition. Do not rely on self-signed certificates for public distribution.
- Protect signing secrets in the CI platform's encrypted secrets; use short-lived credentials or managed signing where possible; verify signatures/notarization in CI.

## Explicit non-goals

- Accounts, centralized cloud projects, telemetry, or automatic remote synchronization.
- Cloud transcription or default generative rewriting/summarization of research content.
- Full mobile transcription. This is not planned in this roadmap because it conflicts with Local Scribe's desktop-centered local compute, storage, and validation workflow—not because of a prior user question.

## Planning references

- `docs/roadmap/issue-backlog.md` contains issue-ready work items and dependencies.
- Policy and implementation choices concerning PHI/BHDF must be reviewed by the responsible U of I offices before implementation.
