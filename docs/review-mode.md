# Review Mode

Each transcript editor includes a Review Mode queue for segments with low
word confidence, likely transcription artefacts, unassigned speakers, manual
flags, or edits made since their last review. Proofreading findings arrive as
the document's background spelling/artefact sweep checks segments; the queue's
artifact count can therefore grow while that sweep runs.

The category filters narrow the visible unresolved items without changing the
counts or completion progress. Use **Next unresolved** to jump to and play the
next item, or use a queue row to open a specific segment. Marking an item
reviewed advances to the next unresolved item. A manual flag is removed when
its queue action is cleared, and can also be toggled from a segment's flag
button. Resolving a review item records that segment as reviewed. Editing
segment text or speaker assignment clears prior resolutions and places the
segment in the changed-since-validation queue.

Flags and completion state are stored alongside each segment in
`transcript.json`. That file is included in Local Scribe project archives, so
review progress moves with project export, backup, and restore without a
separate sidecar file.

The standalone model checks are in `tests/test_review.py` and can be run with
`python -m tests.test_review`.
