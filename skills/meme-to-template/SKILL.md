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
2. Distinguish a face slot, whole-head slot, full subject slot and text slot. Crop/align human faces, remove the old target region, discard input background and blend locally. A rectangular portrait overlay is not an acceptable head replacement. Check hair/ears, double eyes, grey rims and protected props.
3. Keep boxes, removal polygons, source dimensions, input requirements, layer order and typography explicit. A brief is editable data. The current reviewed adapter executes face + caption slots; generic body/pose replacements require a dedicated validated adapter and remain pending meanwhile.
4. Use local CPU tools, pixel/queue bounds and private transient processing. Reject unclear/multiple faces rather than silently inserting the wrong person. No identity recognition, hosted photo API or paid fallback is required.
5. For web candidates require source URL, author and derivative/reuse license. For an image the user supplied and explicitly requested to convert, `--authorized-local` requires `origin: user-provided` and `review.explicit_user_request: true`; record unverified rights honestly. This is separate from automatic collection and does not authorise uploading photos or derived screenshots to a repository.
6. Preserve stable key/UUID and increment versions. Use only declared local asset hashes. Test default reconstruction, actual replacement, changed/long captions, protected pixels, missing/no/multiple-face input and unsupported-client fallback before publishing. Preview may retain the original head; it must not be counted as a successful replacement test.

## Execute reviewed decomposition

Read [the procedure and JSON contract](references/decomposition.md). The [tested dog example brief](references/dog-reaction-brief.json) contains coordinates and decisions, not image data; remeasure coordinates for every new reference.

```sh
PYTHONPATH=backend/meme-generator python skills/meme-to-template/scripts/decompose.py reference.png brief.json   --authorized-local --validation-photo local-single-face.jpg   --output-json /tmp/template.json --preview-dir /tmp/template-review
```

This prepares output and verifies face rendering without publication. Add `--publish` only when publishing to the target template library is within the user's task. A face template cannot be published through this helper without an actual validation photo. Keep screenshots and validation photos private unless separately authorised to publish them.

The helper uses `meme_generator/features/decomposition.py`; the bounded schema/rendering contract lives in `declarative.py`, and local face operations in `face_slot.py`. Dependencies are Pillow, NumPy, OpenCV and Pydantic plus the project runtime. Both API and worker need the face dependencies; the current client Canvas renderer deliberately returns server fallback for face layers.

## Transfer and improve

Another model should be able to inspect a new reference, write the intent/regions/slots brief, run this helper and judge the comparison images without knowing the original conversation. Copy the skill folder plus use the compatible GenSticker runtime; the skill is not a standalone neural model. Record failure reasons in the brief/quality report, improve a specific mask or adapter and rerender. Do not weaken gates to inflate counts, copy example coordinates blindly, fabricate humour/accuracy claims or declare success solely because detection found a face.
