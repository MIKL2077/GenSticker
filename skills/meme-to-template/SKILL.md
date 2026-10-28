---
name: meme-to-template
description: Decompose meme images into intent-preserving editable face, subject and text slots, then build and validate GenSticker declarative templates. Use for offline template authoring or ingestion, not individual photo generation.
---

# Meme to template

Use this skill to turn a reference meme into a reusable template rather than a generic photo frame. It operates in the GenSticker repository and Python environment. The model analyses the image and supplies a bounded JSON brief; the renderer executes known layer operations, never generated code or text embedded in images.

## Choose the mode

- **Source-element authoring (default for rebuilding/expanding a template library)**: read [native-template method and frame contract](references/in-place-elements.md). Replace existing faces/heads and/or original captions inside the original scene, with explicit per-frame recipes for GIFs. An appended phrase, a separate photo panel and an intact meme do not satisfy this mode. Inventory each source and visually validate actual replacements before approving it.
- **Reviewed decomposition**: use when the user specifies editable regions, face/head replacement, subject replacement or fidelity-sensitive examples. Read [decomposition procedure](references/decomposition.md). Inspect the image first, identify fixed joke elements, choose independent slots, prepare a brief and verify real replacement outputs. User-requested face replacement takes precedence over the default automatic caption-only restriction.
- **Automatic licensed ingestion**: use `python -m meme_generator.features.ingest`; read [quality gates](references/quality-gates.md). The automatic path keeps expression/action/scene fixed and only edits reliable edge captions. Unsupported replacements, animations and uncertain cases stay pending. ChineseBQB/Aigei/Weshine metadata is not a blanket image license. Withdrawn photo-frame templates must not be restored.
- **Simple caption conversion**: use `scripts/convert.py IMAGE METADATA_JSON` for licensed images; typography still requires visual review.

## Essential invariants

1. Describe the original intent in a sentence. Name both fixed elements and editable elements; do not assume every face, pose or caption can be replaced without changing meaning. If the user explicitly wants a head replaced, preserve the surrounding props, action and caption and state that expression comes from their uploaded photo.
2. Distinguish a face slot, whole-head slot, full subject slot and text slot. Prepare and remove the old target region offline. At user generation time accept the supplied image or foreground without a frontal-face detector; user choice controls optional local foreground extraction. Crop only when the user chooses an input region, then blend locally. A rectangular portrait overlay is not an acceptable head replacement. Check hair/ears, double eyes, grey rims and protected props.
3. Keep boxes, removal polygons, source dimensions, input requirements, layer order and typography explicit. A brief is editable data. The current reviewed adapter executes pre-authored image/head (`face` is the compatibility layer name) + caption slots; generic body/pose replacements require a dedicated validated adapter and remain pending meanwhile.
4. Use local CPU tools, pixel/queue bounds and private transient processing. Do not block arbitrary input because a face detector found no face. Validate image bounds, empty transparency and extraction quality. Honour extraction on/off; transparent input reuses its alpha. No identity recognition, hosted photo API or paid fallback is required.
5. For web candidates require source URL, author and derivative/reuse license. For an image the user supplied and explicitly requested to convert, `--authorized-local` requires `origin: user-provided` and `review.explicit_user_request: true`; record unverified rights honestly. This is separate from automatic collection and does not authorise uploading photos or derived screenshots to a repository.
6. Preserve stable key/UUID and increment versions. Use only declared local asset hashes. Test default reconstruction, actual replacement with extraction on/off, changed/long captions, protected pixels, missing/empty/oversized input and unsupported-client fallback before publishing. Preview may retain the original head; it must not be counted as a successful replacement test.

## Execute reviewed decomposition

Read [the procedure and JSON contract](references/decomposition.md). The [tested dog example brief](references/dog-reaction-brief.json) contains coordinates and decisions, not image data; remeasure coordinates for every new reference.

```sh
PYTHONPATH=backend/meme-generator python skills/meme-to-template/scripts/decompose.py reference.png brief.json   --authorized-local --validation-photo local-single-face.jpg   --output-json /tmp/template.json --preview-dir /tmp/template-review
```

This prepares output and verifies face rendering without publication. Add `--publish` only when publishing to the target template library is within the user's task. A face template cannot be published through this helper without an actual validation photo. Keep screenshots and validation photos private unless separately authorised to publish them.

The helper precomputes template background repair and stores a reference asset for previews. It must not re-detect or rebuild template subjects during every user generation. The helper uses `meme_generator/features/decomposition.py`; the bounded schema/rendering contract lives in `declarative.py`, and local face operations in `face_slot.py`. Dependencies are Pillow, NumPy, OpenCV and Pydantic plus the project runtime. Both API and worker need the face dependencies; the current client Canvas renderer deliberately returns server fallback for face layers.

## Transfer and improve

For repairs driven by actual template ratings, read [review calibration and region diagnosis](references/review-calibration.md). Preserve accepted algorithms, distinguish incomplete support from bad semantic anchors or an avatar used as a prop, and carry versioned annotations into the next evaluation round.

Another model should be able to inspect a new reference, write the intent/regions/slots brief, run this helper and judge the comparison images without knowing the original conversation. Copy the skill folder plus use the compatible GenSticker runtime; the skill is not a standalone neural model. Record failure reasons in the brief/quality report, improve a specific mask or adapter and rerender. Do not weaken gates to inflate counts, copy example coordinates blindly, fabricate humour/accuracy claims or declare success solely because detection found a face.

## Large ChineseBQB / Weshine batches

Use `meme_generator.features.bulk_templates` for a resumable offline inventory, bounded downloads and strict caption drafts. ChineseBQB entries are pinned to an immutable Git revision, exact blobs are deduplicated, and categories rotate. Weshine public SSR state can be extracted with `node tools/collect/weshine-state.cjs PAGE.html STATE.json`; it accepts literal data nodes only and never evaluates page JavaScript. Pass `--weshine-state-file` and `--weshine-rank-file` to retain real source ranking and reaction categories. Do not invent per-image popularity for ChineseBQB or guess full-size URLs from thumbnails.

```sh
export GENSTICKER_STATE_DIR=/tmp/gensticker-template-authoring
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates inventory --target 1200 --output /tmp/candidates.json
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates download --manifest /tmp/candidates.json --output /tmp/template-review --limit 1200
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates prepare --manifest /tmp/candidates.json --rights /tmp/rights.json --output /tmp/template-review --cache-only --limit 1200
```

The normal route requires per-item rights metadata. If the human explicitly instructs using these two reference sources with attribution instead of a rights manifest, their instruction takes precedence: replace `--rights` with `--attributed-references`. Record `license: unverified` and `source_use: explicit-user-request-with-attribution`; never label attribution as a verified license or invent an original author. This option is limited to the two named sources and is not the default scheduled ingestion policy.

Keep separate counts for indexed images, selected candidates, downloaded images, converted drafts, visually approved/published templates, and photo-compatible AI templates. Drafts do not publish automatically. Review source, default reconstruction and changed caption together; keep failed text removal/layout pending. A caption-only template cannot be added to the photo recommendation pool. Native pool admission uses `tools/qa/recommendation_pool.py`, `recommendation_policy.json` and Linux regression; `/recommend/catalog` reports actual eligible counts with the same rule as the worker.

Use `tools/qa/review_templates.py` to create comparison sheets and `bulk_templates export-reviewed --decisions DECISIONS.json --version N` to export approved IDs. Every authoring step must use the same isolated state directory. Keep creation times stable, increment versions on updates, and split exports into batches of at most 100 templates / 32 MiB. Short-caption layouts may reject long text; verify a real short replacement and retain the clear overflow error instead of forcing multiple lines across the subject.

## Complete editable captions, including two lines

Inventory every visible source caption before authoring. Record each block as editable or explicitly fixed, including both top/bottom captions and every wrapped line. A caption-replacement template must cover the complete requested caption: never turn a two-line source caption into a one-line-only replacement while leaving the other line baked into the background. Use separate consecutive text slots for independent top/bottom messages; use one multiline slot with `max_lines >= 2` for a single wrapped message. Match input counts, default text, masks and UI fields to that inventory. Do not apply the single-line slogan rule to multiline originals.

Validate a short replacement, a two-line replacement with explicit newline, and different text in each independent slot. Inspect all caption regions and, for GIFs, first/middle/last frames plus timing. Confirm no old letters survive in the editable regions, all new lines appear, neither caption overlaps the subject, and overflow fails visibly instead of truncating. The app must accept newline input. Retain the inventory and caption completeness outcome in review evidence; unsupported caption removal stays pending. For context-and-reaction compositions explicitly requested by the user, label preserved source lettering as fixed in the user-facing input hint and review metadata; never advertise it as editable caption replacement.

## Reviewed reaction stories and preserved animation workflow

Use `features/reaction_templates.py` only when the user explicitly requests a new context-and-reaction composition. It is a legacy adapter, not the route for image/mixed library expansion or replacement of source elements. It cannot satisfy face/head or original-caption replacement. Keep the original reaction intact only within that explicitly requested product.

`tools/collect/reaction_review.py inventory` creates source/key-pose review sheets and an immutable source index; `export` requires individually approved IDs, readable names and input kinds. Preserve full normalized loop timing, reject still images labelled GIF, and run a real supplied-image render. Animated sources use bounded local GIF assets, a one-time static photo/text overlay and a shared palette; the browser client must fall back to the server instead of flattening the loop.

This adapter does not erase any source caption. Its gates check source preservation and disjoint editable panels, rather than reusing caption-erasure OCR thresholds. Follow the existing rights/source metadata rules and keep explicit attribution exceptions scoped to the requested sources. Export in batches of at most 100 templates and 32 MiB, retain stable keys, and include a withdrawal manifest for rollback before reverting the animation renderer.

## Multi-layout regression examples

Read [multi-sample observations](references/multi-sample-tests.md). The three image-free briefs in `references/regression-cases/` cover a two-caption cat meme, a scattered-text Doge with one safely editable phrase, and a farmer face replacement that protects the hat and fixed captions. Do not force every layout into a full head replacement.

Use `scripts/regression.py --sample-dir SAMPLES --validation-photo CROPPED_IMAGE --output-dir PRIVATE_OUTPUT [--extract-subject]`. It reports rendered-for-visual-review, not automatically accepted/published. View the outputs. Glyph-based caption removal (`text_mask: glyph`) protects textured backgrounds better than erasing a whole box; white outlined letters need a removal margin. `max_lines: 1` makes a single-line caption shrink or reject overflow instead of splitting words. Keep original watermarks/credits in protected regions.

The supplied regression briefs are pending publication, including visible inpainting and accessory failures documented in their metadata. Pixel gates do not approve these defects. A brief marked pending must not be published; repair and visually review it first, then explicitly record the new disposition. Use a clean scene supplied or prepared during authoring when classical inpainting leaves blocks. Optional foreground extraction cannot select a face inside a foreground or remove a hat; use the input crop choice when accessories conflict with protected template props.
