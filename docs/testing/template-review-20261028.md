# Template review calibration — 2026-10-28

The S03 review contained 31 accepted, 13 adjustment and 53 direct-paste decisions;
3 of the original 100 templates were unlabelled. Other photos need no repeated
review per the user's instruction. The original 103 annotations, including six
annotations for other photos, were exported twice and preserved unchanged.

## Library changes

66 stable keys received one version increment. The 53 direct-paste decisions
disable expression recipes (and legacy fusion where applicable); existing native
layout, captions, image effects and animation remain in use. Twelve adjustment
templates received measured region/semantic-anchor corrections across 85 frames.
`look_this_icon` instead disables an unrelated background-character donor: the
uploaded avatar inside the sign is a prop. A/B math is byte-identical to the
previous commit, SHA-256
`217d629e9e74d59ee0253d9effbc61ebdc54278c3b8543791f84455478923713`.

The corrections update expression support, fallback support and clean patches
together. Examples include the complete white pig face instead of its right
half, both cat eyes, complete emoji faces, small cartoon geometry, source bangs,
per-frame phones and captions introduced after a GIF cut. Color-based mouth
proposals initially selected skin/collar pixels; the final plans use tighter
measured regions or explicit mouth bounds. This is source authoring evidence,
not a claim that extreme cartoon anatomy now looks natural for every portrait.

The 31 accepted keys retain their exact recipes, versions and outputs. Their
S03 output frame hashes also match the previous 100-template round.

## Actual evaluation

The new snapshot has 959 published templates: 483 image-capable and 476 caption
templates. All 483 were rendered with S03 using real native/declarative calls,
including the newly published image template and all fallback cases. This adds
383 templates to the previous review coverage. No failed case was filtered out.

- 236 outputs executed expression fusion; 247 used their existing adapter.
- 0 render failures; 0 dimension, frame-count/duration or loop mismatches.
- 221 animated outputs, 4,451 decoded output frames.
- All 53 direct-paste decisions avoid expression preparation.
- All 31 accepted outputs remain frame-identical.
- The 12 corrected declarative templates also pass a synthetic partial-alpha
  object fallback probe: 85 frames, maximum fixed-pixel change 0 before encoding.
- 175 feature regression tests pass, including versioned annotation persistence
  and rejection of cross-origin annotation writes.

Full sequential local evaluation peaked at 2,040.3 MiB RSS; this is a batch-wide
peak after visiting the whole native library, not a per-request bound. A deployed
Linux smoke run rendered all 13 correction cases plus an accepted reference and
a direct-paste native case as the service user, under CPUQuota=100% and
MemoryMax=1,536 MiB. All 15 matched expected execution, dimensions, durations and
loops, with 698.3 MiB peak RSS and fixed-pixel error 0. Temporary server test
portrait/state were removed after the report was retrieved.

The 66-key delta is deployed; API and worker are active and health reports 959
published templates. Non-target rows, including archived rows, were checked
unchanged. Rollback backup:
`/var/backups/gensticker-expression-ab-1793156807`.

## Review and authoring follow-up

The private gallery remains at `http://127.0.0.1:63514/index.html`. It provides
original/previous/current images, complete animation contacts, support overlays,
pagination, optional notes, and filters for the 13 corrections and 383 newly
tested templates. All original T001–T100 display identifiers are preserved.
Ratings bind template key, version and sample; old ratings stay in history.
Corrected versions remain pending human review. The 31 accepted and 53 explicit
direct-paste decisions carry forward, leaving 399 evaluations/rechecks pending.

The local server writes atomic annotation snapshots and an append-only history,
with a browser backup and JSON export. It binds only 127.0.0.1 and accepts writes
only from its own origin for known template versions. Portraits, generated
outputs, browser screenshots and full private annotation files are outside Git.
Sanitized measurements are in `evidence/2026-10-28-template-review/`.

The maintained, installed and backend authoring skill copies now include
`review-calibration.md`: distinguish support errors from geometry errors, name
donor/input roles, preserve accepted recipes, keep all frame occlusions and
captions, and preserve versioned user decisions. Both installed and maintained
skill validators pass. Subsequent visual feedback should refine specific source
plans without treating render success as aesthetic approval.
