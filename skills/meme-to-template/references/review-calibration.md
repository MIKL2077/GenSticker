# Calibrate source regions from actual user reviews

Read this when repairing a reviewed template library or preparing the next
evaluation round. Keep algorithm changes separate from source-region evidence.

## Diagnose the visible failure

- **Accepted result:** retain its recipe and algorithm. Compare actual output
  frame hashes with the accepted round before including unrelated authoring
  changes. A matching template name or first-frame thumbnail is insufficient.
- **Incomplete replacement:** inspect the original scene, full replacement and
  support overlay. A face detector may locate the intended face while the
  authored mask still clips an eye, snout or chin. Landmarks and a layer's box
  are not the replacement support. Measure the complete intended region and
  regenerate both the clean patch and fallback mask from the same support.
- **Wrong geometry:** tiny cartoons and animal faces can produce plausible but
  incorrect human landmarks (nose above eyes, off-center eyes, stretched jaw).
  Use measured semantic anchors and inspect their placement in the source.
  Do not compensate by increasing fusion strength or growing every mask.
- **Uploaded picture is a prop:** an avatar inside a sign, screen or image
  effect can need plain pasting. A detectable background face is not evidence
  that its expression should alter that avatar. Record the donor role and
  input role before enabling expression transfer. Respect explicit “no fusion”
  feedback even when a recipe can technically run. Native Python templates
  are not universally exempt: decide from roles and actual reviewed output.

## Correct the entire authored timeline

Author source-pixel support, visible feature regions, fixed subjects and
occluders independently. In a multi-character picture, name the selected
character; keep the other character outside the editable support. Protect
hands, phones, instruments, ears and action marks with per-frame exclusions.
Check phone/hand changes and scene cuts even when the old slot box is constant.

A feature locator's small oval can leave half an animal face intact. Conversely,
an oversized ellipse can cover a prop. Inspect both original eyes, mouth corners,
chin and the boundary after compositing. Retain hair or ears only when their
preservation is an explicit slot decision. Repairing the expression mask alone
while leaving an inaccurate fallback or stale clean patch creates inconsistent
results for inputs without detected faces.

Color segmentation is an offline proposal, not a measurement guarantee. In the
2026-10-28 review, pink skin was mistaken for a red cartoon mouth; a loose mouth
ROI selected collar colors. Inspect selected components and constrain their
source region. Use a measured mouth region when color cannot distinguish it.
Keep baked-in captions introduced after a GIF cut protected on those frames,
including white glyph outlines. Do not infer the complete timeline from frame 0.

Extreme cartoon anatomy can still stretch a human portrait under the preserved
A/B math. Correcting coverage does not establish aesthetic acceptance. Keep the
new recipe pending and expose the actual output for another human review.

## Make the next review usable

Snapshot the current published library and test all image-capable templates when
requested, including native layouts and fallback cases. Preserve failures in
the report. A representative portrait can be used when the human explicitly
says the remaining inputs behave similarly; this does not establish general
robustness for profiles, objects or arbitrary future photos.

Back up existing annotations before replacing a gallery. Identify a rating by
template key, recipe version and input sample; display ordinals are not stable
identities. Retain the previous rating alongside a corrected version and mark
that version for re-review. Keep accepted results and explicit direct-paste
decisions visible without asking the human to repeat them. Save annotations
durably, retain history and provide an export.

Show original artwork, previous actual output, current actual output and full
GIF frame comparisons. Report render failures, dimensions, frame count,
durations, loop settings and fixed-pixel checks separately from visual approval.
Keep test portraits and resulting media in private local storage. Public plans
may contain source coordinates, hashes and sanitized evidence, never private
portrait bytes or screenshots.

The repository helpers are `tools/qa/repair_expression_regions.py`,
`evaluate_template_review.py`, `build_template_review_gallery.py` and
`serve_template_review.py`. The measured 2026-10-28 plans are examples only:
remeasure each new source instead of copying their coordinates.

## Compare expression drivers before changing an accepted library

When the user requests natural movement of their own features, distinguish
source-texture geometry, learned expression editing and template-component
transplantation. Pasting a template's eyes or mouth can preserve an action yet
violate that request. Label borrowed pixels explicitly; do not carry a rejected
transplant strategy into the next candidate under a different name.

Retain the exact reviewed baseline, recipe version, model hash, full animation
and identical test photos. Keep candidate choices separate from prior ratings.
If new masks or compositing are used, state that comparison with the baseline
also includes those changes. Disclose hand-authored AU curves rather than
describing them as automatic expression analysis. Blink and brow movement do
not implement gaze direction. Record unsupported tongue, unseen teeth and
profile texture instead of counting them as solved.

Check mesh orientation before treating a geometry result as selectable. Folded
triangles can produce an encoded image while making the projection unusable.
Preserve such outputs as diagnosed failures and exclude them from choices.
Inspect glasses across blink/open-mouth states. Fixed-pixel checks before GIF
encoding do not prove exact colors after quantization or natural appearance.

Benchmark in an independent CPU process before API/worker integration. Separate
source preparation, cold load, warm inference, compositing and GIF encoding;
include full-template timing and repeated-action cache counts. Weight size
alone does not establish runtime memory. Use enforced CPU, memory, swap and
runtime limits appropriate to the host, single concurrency, and API/worker
health and restart counters before/after. Save each small report immediately:
a failed bulk media transfer must not destroy completed measurements. Resource
success does not approve picture quality or production integration.
