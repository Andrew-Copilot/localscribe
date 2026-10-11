# Issue-ready roadmap backlog

Create GitHub issues from these entries after project stakeholders review and label them. Suggested labels: `roadmap`, `privacy`, `backup`, `box`, `phi`, `security`, `accessibility`, `research-workflow`.

> **Rule for PHI-related work:** no production Box Health Data Folder integration, test account, test artifact, or user-facing compliance claim may be created until U of I HIPAA Privacy Office and Box administrators approve the architecture.

## Milestone 1.02 — Safe storage and recovery

### R01 — Define the U of I Box and BHDF integration policy
**Labels:** `roadmap`, `privacy`, `box`, `phi`, `blocked`

**Goal:** Obtain institutional decisions required to design a compliant opt-in U of I Box backup feature.

**Acceptance criteria**
- Written guidance confirms whether a Local Scribe Box app may access BHDFs.
- An approved BHDF-identification method is documented; folder names alone are explicitly rejected.
- OAuth application type, scopes, token storage, retention, collaboration, and audit expectations are documented.
- Approved test process uses no PHI unless specifically authorized.
- Product copy is reviewed so Local Scribe does not overstate HIPAA/IRB compliance.

**Dependencies:** U of I HIPAA Privacy Office, Box administrators, institutional security review.

### R02 — Add per-project data sensitivity declaration
**Labels:** `roadmap`, `privacy`, `phi`, `backup`

**Acceptance criteria**
- Projects support `no_phi`, `may_contain_phi`, and `unknown_treat_as_phi` states.
- New-project and first-backup flows explain selection responsibility.
- PHI/unknown states prevent non-BHDF remote backup.
- State is present in project metadata and backup manifests.
- Existing projects migrate to conservative defaults.

**Dependencies:** R01 for final BHDF enforcement behavior.

### R03 — Build a stable, checksummed project snapshot format
**Labels:** `roadmap`, `backup`, `research-workflow`

**Acceptance criteria**
- Immutable snapshot excludes transient caches/logs by default.
- Manifest contains format/app version, project ID, transcription provenance, files, sizes, and SHA-256 checksums.
- Media-included and transcript-only modes are supported.
- Restore verifies checksums before import.
- Archive schema is versioned and migration-tested.

### R04 — Implement local backup, restore, and destructive-action safeguards
**Labels:** `roadmap`, `backup`, `privacy`

**Acceptance criteria**
- UI supports local snapshot creation and restore.
- Destructive actions and overwrite imports offer confirmation and snapshot option.
- Restore never silently overwrites; it offers rename/replace/abort.
- Outcomes appear in local activity history.

**Dependencies:** R03.

### R05 — Implement opt-in U of I Box backup connector
**Labels:** `roadmap`, `backup`, `box`, `privacy`, `phi`

**Acceptance criteria**
- OAuth sign-in/revocation, folder selection, upload, retry, cancellation, and post-upload verification work.
- Credentials use OS credential storage, never archives/logs.
- Remote work requires explicit user action and is blocked by Offline Lock.
- PHI/unknown projects target only a verified BHDF according to R01.
- No generic Box folder is selected automatically.
- Mocked API tests cover auth failure, partial upload, destination rejection, and token revocation.

**Dependencies:** R01, R02, R03.

### R06 — Add privacy center, activity history, and sanitized diagnostics
**Labels:** `roadmap`, `privacy`, `security`, `support`

**Acceptance criteria**
- Privacy Center shows Offline Lock, backup configuration, storage location, and last remote action.
- Activity history records network-affecting and recovery actions.
- Diagnostics exclude media, transcript content, tokens, and user paths by default.
- Users inspect diagnostics before saving.

### R07 — Add startup and storage health checks
**Labels:** `roadmap`, `reliability`, `support`

**Acceptance criteria**
- Checks report low storage, inaccessible data directory, corrupt/missing model data, and unsupported runtime.
- Model download flows show estimated disk requirements.
- Checks never transmit data.

## Milestone 1.03 — Fast human validation

### R08 — Create Review Mode and issue queue
**Labels:** `roadmap`, `research-workflow`, `editor`

**Acceptance criteria**
- Queue supports low-confidence segments, possible artifacts, unassigned speakers, flags, and changed-since-validation segments.
- Filters, counts, and completion progress are visible.
- Review actions advance efficiently to the next unresolved item.
- Queue state is portable with project data.

### R09 — Add playback and keyboard-first review controls
**Labels:** `roadmap`, `editor`, `accessibility`

**Acceptance criteria**
- Playback speed, pre-roll/post-roll, loop/replay, waveform cursor, and zoom are available.
- Core actions have documented keyboard shortcuts.
- Controls have accessible labels and focus.
- Tests cover timestamp seeking and range-media behavior.

### R10 — Add validation states, sign-off, and export provenance
**Labels:** `roadmap`, `research-workflow`, `provenance`

**Acceptance criteria**
- State model is Draft → Transcribed → In review → Validated → Exported.
- Reviewer, time, and notes are stored locally.
- Reopening validation is deliberate and recorded.
- Export status/provenance is included where format permits.

## Milestone 1.04 — Portable research collaboration

### R11 — Specify and version the `.lsproj` interchange format
**Labels:** `roadmap`, `research-workflow`, `architecture`

**Acceptance criteria**
- Public specification covers manifest, checksums, version, provenance, and migrations.
- Transcript-only imports clearly identify missing media.
- Integrity results are visible.
- Golden archives protect backward compatibility.

### R12 — Build offline handoff, annotations, and conflict handling
**Labels:** `roadmap`, `research-workflow`, `collaboration`

**Acceptance criteria**
- Review package supports selected transcript, optional media, instructions, and annotations.
- Timestamped comments/questions persist.
- Conflict import preserves both versions and guides resolution.
- No real-time synchronization is added.

**Dependencies:** R11.

## Milestone 1.05 — Research-quality assistance

### R13 — Add vocabulary profiles and study presets
**Labels:** `roadmap`, `transcription`, `research-workflow`

**Acceptance criteria**
- Profiles support reuse, CSV/TXT import, and project assignment.
- They integrate transparently with prompt/hotword settings.
- Provenance records profile/settings without exporting sensitive vocabulary by default.
- An uncertain-term report is available.

### R14 — Add reversible de-identification review assistance
**Labels:** `roadmap`, `privacy`, `research-workflow`, `high-risk`

**Acceptance criteria**
- Configurable assistive flags cover common identifiers and custom patterns.
- Replacements are explicit, reversible, and revision-tracked.
- Replacement map is local and excluded from shareable exports by default.
- Review report lists flagged/resolved/skipped items.
- UI/docs say it is not a compliance guarantee.

### R15 — Validate multilingual support and improve speaker workflow
**Labels:** `roadmap`, `transcription`, `speakers`

**Acceptance criteria**
- Supported languages have tested transcription, proofreading, exports, and UI behavior.
- Detection/selection only claims supported coverage.
- Manual speaker workflow improves before automation.
- Experimental diarization is opt-in, confidence-marked, reversible, and human-confirmed.

## Ongoing milestones

### R16 — Accessibility release baseline
**Labels:** `accessibility`, `roadmap`

**Acceptance criteria**
- Keyboard-only operation covers main workflows and modals.
- Screen-reader labels, focus behavior, scalable text, high contrast, and non-color cues are tested.
- Accessibility checks are part of PR/release review.

### R17 — End-to-end quality and regression suite
**Labels:** `quality`, `testing`, `roadmap`

**Acceptance criteria**
- Non-sensitive fixtures cover import → processing fixture → edit/review → export → archive/import.
- Golden outputs cover SRT, VTT, DOCX, JSON, and archive manifests.
- Migration/package upgrade tests cover supported desktops.
- Box tests are mocked and never use PHI.

### R18 — Code-signing and distribution feasibility spike
**Labels:** `security`, `distribution`, `roadmap`

**Acceptance criteria**
- Windows MSIX/Microsoft Store compatibility is evaluated with local data, bundled Python, model downloads, and updates.
- macOS Developer ID/notarization and possible U of I fee-waiver path are documented.
- SignPath Foundation eligibility is investigated as non-guaranteed.
- CI secret management and signature/notarization verification plans are documented.
- Decision record compares cost, user friction, work, and supportability.

## Suggested sequencing

1. R01 → R02 → R03 → R04.
2. R05/R06/R07 after R01–R03.
3. R08 → R09 → R10.
4. R11 → R12.
5. R13/R14/R15, with privacy review before R14 release.
6. R16/R17/R18 proceed continuously; begin R18 early enough to affect the next installer release.
