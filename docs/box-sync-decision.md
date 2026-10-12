# Decision: local sensitivity guardrails and future Box Sync transport

This implements the classification/guardrail foundation of [R02, issue #3](https://github.com/Andrew-Copilot/localscribe/issues/3)
only. No backup transport or backup UI is implemented.

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

Remote backups, local snapshots, Box Sync directory copying, Box APIs,
authentication/credential storage, retention, deletion, remote versioning, and
Box application registration are not part of this slice. Transcription behavior
is unchanged. Tests use synthetic records only.
