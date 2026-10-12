# Decision: local sensitivity guardrails and future Box Sync transport

This documents the classification/guardrail foundation of [R02, issue #3](https://github.com/Andrew-Copilot/localscribe/issues/3)
and the local snapshot foundation of [R03, issue #4](https://github.com/Andrew-Copilot/localscribe/issues/4).
No backup transport or backup UI is implemented.

## Decision and revised roadmap

- **R01 — Define local backup policy and guardrails (documentation/decision).**
  R01 documents this policy, not an institutional-approval blocker for R02.
  Local Scribe makes no HIPAA, IRB, U of I, Box Health, or institutional
  approval/compliance claims. Classification is user-declared and does not
  determine whether data is PHI or provide compliance advice.
- **R02 — Per-project sensitivity declaration.** Durable values are `no_phi`,
  `may_contain_phi`, and `unknown_treat_as_phi`. New projects default to unknown.
  Missing or unrecognized stored values normalize conservatively in memory;
  the next project write persists that value. Reading/listing at startup does
  not rewrite existing projects. Incoming invalid declarations are rejected.
- **R05 — Future Box Sync folder backup transport.** Use the researcher's
  existing U of I Box Sync desktop folder, preferred when configured and
  available. Do not build Box API verification, OAuth, or Box app registration.
  Authentication (including institutional Entra/SSO) belongs to the Box Sync
  client; Local Scribe must not handle credentials or tokens.

These revised entries supersede earlier roadmap wording requiring Box APIs,
OAuth/application registration, or institutional approval before implementing
local classification. The prior planning-branch backlog is not in this checkout.

## Destination policy

PHI/potential-PHI and unknown projects require an approved Box Health
destination. The initial local heuristic checks whether the selected **root
folder name** contains the literal, case-sensitive string `[Box Health - `.
Child-folder names and full paths are not root-name evidence. A matching name
can be renamed or spoofed: it is a heuristic, not Box API verification or proof
of approval. The helper does not check existence, synchronization, or availability.

After failed/inconclusive recognition, a researcher may override only by
explicitly confirming they independently verified that the selected destination
is an approved Box Health folder. This never permits ordinary Box storage for
PHI. The local helper records only the latest explicit override's timestamp,
selected destination root path, and confirmation in project metadata.
Do not supply source filenames, sensitive content, credentials, or tokens.
Generic metadata edits cannot create an override. The record is an audit
attestation, not permission for another destination or a later backup.
No override is needed or recorded for `no_phi`.

Source media, transcript text, preview audio, exports, metadata, and archives
are eligible for future backup through the approved destination. Classification
must not exclude these artifacts or imply that derived data is automatically safe.

## Out of scope

Remote backups, Box Sync directory copying, Box APIs,
authentication/credential storage, retention, deletion, remote versioning, and
Box application registration are not part of this slice. Transcription behavior
is unchanged. Tests use synthetic records only.

## R03 Phase 1: local snapshot format

The existing `.lsproj` ZIP container and `localscribe-manifest.json` name are
retained. New exports use `format: localscribe-project`, `format_version: 2`.
v1 archives remain importable without checksum assurance; the pure
`app.snapshots.validate_snapshot` function deliberately rejects v1 rather than
calling it verified. Future versions require an explicit reader/migration;
unknown versions are rejected.

### Manifest contract

Required fields:

- `format` and integer `format_version`: identifier and schema version.
- `app_version`: Local Scribe version at snapshot creation.
- `exported`: timezone-aware ISO-8601 creation timestamp.
- `slug` and `title`: project identity (the current store uses a slug, not a UUID).
- `data_sensitivity`: the project's normalized declaration; missing/invalid
  legacy values become `unknown_treat_as_phi` without rewriting the source.
- `includes_media`: boolean; full or transcript-only.
- `documents`: unique entries sorted by document ID, with ID, filename, status,
  and `provenance`. Provenance copies available document `engine`/`stats` and
  transcript schema, model, actual engine/settings, stats, language, timestamps,
  and human-edit/retimestamp state. Missing provenance stays empty; no current
  global settings are substituted for historical settings.
- `artifacts`: unique entries sorted by canonical archive path, each containing
  `path`, nonnegative integer `size_bytes`, and lowercase SHA-256 `sha256`.

JSON keys and inventories are sorted. Identical source data, app version, mode,
and creation timestamp produce identical manifests; separate real snapshots
have different creation times and unique filenames. ZIP timestamps/compression
and archive filenames are not a reproducible-byte contract. The manifest does
not checksum itself; every other archive member must be declared and checksummed.

### Artifact boundary and safety

Selection is an allowlist: `project.json`, document metadata and canonical
transcripts, revision JSON, and standard `outputs/transcript.*` files
(`txt`, `md`, `docx`, `vtt`, `srt`, `json`). Full mode additionally includes
only source media referenced by document metadata and `preview.m4a`.
Transcript-only mode excludes **both** source media and derived preview audio.
Waveform caches, orphan media, arbitrary extras, application logs, PID files,
Python environments, temporary files, and credential/secret files are outside
the selection. Unsafe/missing referenced media and selected symlinks fail closed;
transcript-only exports can still be made when source media is unavailable.
This is not content redaction: do not place credentials inside legitimate
project metadata, engine settings, or transcript text. No credential store is
implemented or read.

Validation reads only: it does not extract, mutate project state, log content,
or contact any service. It checks schema/version, canonical relative paths,
duplicates (including case collisions), special-file entries, declared files,
byte sizes, and SHA-256. v2 rejects all unexpected archive members, including
directory entries, instead of silently ignoring them. v1 may retain its directory
entries and extras but must also pass archive path safety checks.
v2 import validates the same open ZIP before replacement or extraction.

Creation streams artifacts and hashes the bytes actually written. Metadata is
read once for both archived bytes and provenance. In-process project writes are
locked during export; external edits are not a transactional filesystem snapshot.
A same-directory temporary ZIP is closed, flushed/fsynced, and validated before
atomic rename to a unique `.lsproj`; failures remove the temporary file and do
not replace earlier snapshots. Archive endpoint logs contain only generic
operation/count/size information, not titles, source filenames, or classifications.
This does not change logging in unrelated transcription operations.

Snapshots are unencrypted sensitive-data containers, including transcript-only
snapshots. Checksums provide corruption detection, not signatures, authenticity,
PHI detection, institutional approval, or compliance. Future copying by the
user's existing Box Sync client is a separate transport phase subject to the
destination policy above; Phase 1 does not select or copy to a Box destination,
implement Box APIs/OAuth/authentication, store credentials, or add backup UI.
