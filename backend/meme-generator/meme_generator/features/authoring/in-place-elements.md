# Source elements and authored animation

## Learn from the bundled code

Inspect code and assets for the relevant native templates:

- `memes/petpet/__init__.py`: five different avatar boxes; the hand is pasted **above** the avatar. The hand, compression and timing carry the joke.
- `memes/kiss/__init__.py`: two independent input identities and thirteen poses. Multiple people need explicit roles and input slots.
- `memes/throw_gif/__init__.py`: different position, scale, visibility and instance count in each frame. An invisible head stays invisible.
- `memes/hold_grudge/__init__.py`: actual editable wording, fixed text and explicit overflow handling. Caption templates need not accept photos.

The pattern is fixed scene + prepared removal + replacement + foreground occluders + original timing. An extra photo panel beside an intact meme is a different product. Do not use `reaction_templates.make_story` or its old context-phrase fallback for source-element conversion.

## Inventory and prepare each source

Inspect actual pixels. Record every face, paragraph, gesture, prop, effect and credit as editable, fixed or unresolved. Name the selected person in a multi-person scene. Distinguish wrapped paragraphs, independent bubbles, source captions and labels on props. OCR proposes boxes and text; it does not approve a transcription.

Keep the original scene/canvas. A source without a usable face or original text does not become an editable meme by adding a caption strip. Remove all old eyes, brows, nose and mouth in a face slot. Only a face slot intentionally preserves hair/ears/head outline; whole-head removal also removes those. Tell users which kind of input to crop. The uploaded photo supplies expression; this runtime does not transfer expressions or require a face detector at generation time.

Use uniform fill for genuinely plain caption backgrounds, glyph removal for textured regions, or a prepared clean plate where inpainting leaves visible blocks. Hands, cups, hats, microphones, cage bars and tears need mask holes or an occluder above the replacement. A large ellipse leaving a second eye or cutting a finger fails review.

## Author every GIF frame

Decode every source frame, including its composited/disposal result and duration, before intentional resampling. Retain any output-to-source frame mapping. File extensions and three key frames cannot establish the complete animation.

For every output frame store its source index, mask, bounds, optional rotation, occlusion/visibility and duration. Tracking and color segmentation are offline proposals. Weak matches, cuts, hidden faces and cropped heads need inspection and corrected geometry. Confidence is not acceptance. A face on an empty frame, a floating head, remaining old eyes/mouth, or a missing prop fails review.

Replace captions on every frame where they appear, including low-confidence OCR frames. Preserve appearance/disappearance timing. Distinguish changing source wording from OCR spelling variants. Paragraphs, top/bottom messages and vertical wording need matching slots and complete removal of outlines and punctuation.

## Executable contract

`features/element_templates.py:compile_elements` takes source bytes, one list of face/text `Layer` objects per decoded frame, and source paragraph defaults. It prepares hashed source assets, clean patches, original-caption patches and bounded `TemplateSpec.frames`. Runtime performs no OCR, tracking, inpainting, remote fetch or generated-code execution.

A frame specifies `asset`, `asset_format`, `source_index`, `duration_ms` and ordered `layers`. Face layers specify pixel `box`, `erase_polygon`, optional local `protect_polygons`, `rotation` and `tone`. Text layers specify the entire paragraph, `slot`, pixel `box`, typography, `direction`, `max_lines` and `line_spacing`. Exact source-caption patches are used only for matching defaults; changed and empty input use the clean plate. Counts must match rendered slots; up to five independent image/text slots are supported.

Use `scripts/decompose_frames.py` for an explicit plan. Batch tools `tools/collect/scan_meme_elements.py` and `tools/collect/rebuild_elements.py` generate **drafts**, never approvals. The installed skill needs the compatible GenSticker runtime, not just the script folder.

From the repository root, run the helper with `PYTHONPATH=backend/meme-generator .venv/bin/python skills/meme-to-template/scripts/decompose_frames.py SOURCE.gif PLAN.json --validation-photo PRIVATE_FACE.png --output-json DRAFT.json --preview-dir PRIVATE_PREVIEWS`. A plan has `frames` (one array of face/text layers for every decoded frame) and `defaults`. All geometry is in source pixels. Keep the plan, source checksum and exact frame mapping together.

Preserve nested frame assets, caption patches and masks in seed import and garbage collection. Unsupported clients explicitly fall back to the server. Keep key/UUID, increment version, invalidate info/thumbnail caches and check input fields in the app.

## Review and release

Compare source, an actual avatar replacement and caption replacements. Render blank captions to expose leftover glyphs; test short wording, different values in each slot and explicit two-line input for multiline slots. Inspect the complete timeline, not just its first frame. Check empty/oversized input, non-frontal objects, transparency and clear overflow errors. Returning the source as a preview does not test avatar replacement.

Measure fixed pixels before lossy GIF quantization; separately check output palettes, frame count, duration and loops. Retain actual checks and unresolved defects. `element-replacement-v1` evidence binds recipe hash, source canvas, caption inventory, counts and analyzed frames, supplementing visual review. A success flag, source label or successful render cannot confer visual approval.

Remeasure every source even when reusing an adapter. Never bulk-write approvals to meet a quota. Unsupported originals remain preserved source candidates outside the published catalog, with specific reasons. Preserve source authorization and honestly unverified rights; do not publish test portraits or private validation screenshots.

## User-supplied discovery references

The user added `https://zh.moegirl.org.cn/猫Meme` and its related public pages on 2026-10-22 as a discovery reference. Follow publicly accessible article/file links with bounded requests, record the specific file page and upstream media attribution, then apply the same element and full-frame review. An encyclopedia article's text license does not establish the GIF's reuse rights. Keep unknown media rights labelled unverified.

On this run the article returned a JavaScript challenge and the public MediaWiki parse request returned `action-notallowed` / `Unauthorized API call`. Do not claim its GIFs were inspected or imported, bypass authentication, or turn a blocked page into invented source metadata. Preserve the URL in the discovery queue; existing verified source bytes can still be rebuilt independently.

## Fusion and expression-dependent reactions (2026-10-27)

The CPU renderer offers `face_blend` values `replace`, `color`, `seamless` and `expression`. Color matching and Poisson blending only improve local compositing. The experimental expression blend preserves more original gradients; it is not neural expression transfer and can leave double features or weaken identity. Never approve a template on this basis or promise that an uploaded neutral face will acquire the source expression.

Use an inner-face slot when ears, fur and head outline carry the joke. Inspect a fully uncropped photo as a negative case and a user-selected five-feature crop as the intended input. Do not silently crop or require a detector. For moving hands/paws, preserve the full gesture and impact marks on EVERY frame with measured protected regions or a foreground occluder. A large ellipse over the paws fails regardless of score. Compare all frames, including highest-raised hands, lowered hands and impact poses. Bind fixed-pixel and timing measurements to the new recipe hash, increment its version and invalidate previews.

For expression-dependent animals (squinting, puffed cheeks, crying, mouth shapes), explicitly decide whether replacing those features destroys the intent. If a deterministic replacement loses that intent, keep the candidate pending or publish a clearly described photo-expression variant only after explicit review; do not mislabel it as expression transfer. Review actual cropped-photo outputs for props/action preservation, not just the source preview.


For reviewed CPU character fusion, see [the bounded fusion contract](cpu-fusion.md). It preserves arbitrary-input paste fallback and requires actual-output/per-frame evidence; the older four blend controls remain experiments.

## Calibrate from actual template reviews

Read [review calibration](review-calibration.md) when repairing a reviewed library. Preserve accepted algorithms and actual output frames. For incomplete replacements, measure the entire intended face before changing fusion strength: a landmark rig may be correct while an inscribed ellipse still leaves an old eye or half a snout visible. Keep expression support, fallback support and the prepared clean patch consistent. An uploaded avatar inside a sign or screen is a prop; a detected background character must not automatically become its expression donor.

Tiny animal/cartoon rigs need semantic-anchor inspection. Check that both eyes, nose, mouth and jaw lie on the intended features; inspect source-color proposals because pink skin or a collar can be mistaken for a mouth. Preserve fixed hands, phones, other characters and captions independently on every frame, including scene cuts and later captions. Keep corrected recipes pending until the human reviews actual output. Save ratings by key/version/sample, retain prior decisions and expose the whole requested image-template library with failures included; a successful render does not approve it.
