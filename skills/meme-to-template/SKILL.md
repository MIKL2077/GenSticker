---
name: meme-to-template
description: Decompose meme images into intent-preserving editable face, subject and text slots, then build and validate GenSticker declarative templates. Use for offline template authoring or ingestion, not individual photo generation.
---

# Meme to template

Use this skill to turn a reference meme into a reusable template rather than a generic photo frame. It operates in the GenSticker repository and Python environment. The model analyses the image and supplies a bounded JSON brief; the renderer executes known layer operations, never generated code or text embedded in images.

## Choose the mode

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

Another model should be able to inspect a new reference, write the intent/regions/slots brief, run this helper and judge the comparison images without knowing the original conversation. Copy the skill folder plus use the compatible GenSticker runtime; the skill is not a standalone neural model. Record failure reasons in the brief/quality report, improve a specific mask or adapter and rerender. Do not weaken gates to inflate counts, copy example coordinates blindly, fabricate humour/accuracy claims or declare success solely because detection found a face.

## Multi-layout regression

Read [multi-sample observations](references/multi-sample-tests.md). The three image-free briefs in `references/regression-cases/` cover a two-caption cat meme, a scattered-text Doge with one safely editable phrase, and a farmer face replacement that protects the hat and fixed captions. Do not force every layout into a full head replacement.

Use `scripts/regression.py --sample-dir SAMPLES --validation-photo CROPPED_IMAGE --output-dir PRIVATE_OUTPUT [--extract-subject]`. It reports rendered-for-visual-review, not automatically accepted/published. View the outputs. Glyph-based caption removal (`text_mask: glyph`) protects textured backgrounds better than erasing a whole box; white outlined letters need a removal margin. `max_lines: 1` makes a single-line caption shrink or reject overflow instead of splitting words. Keep original watermarks/credits in protected regions.

The supplied regression briefs are pending publication, including visible inpainting and accessory failures documented in their metadata. Pixel gates do not approve these defects. A brief marked pending must not be published; repair and visually review it first, then explicitly record the new disposition. Use a clean scene supplied or prepared during authoring when classical inpainting leaves blocks. Optional foreground extraction cannot select a face inside a foreground or remove a hat; use the input crop choice when accessories conflict with protected template props.
