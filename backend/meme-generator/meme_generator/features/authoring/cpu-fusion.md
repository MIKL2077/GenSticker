# CPU character fusion (2026-10-27)

Use `Layer.fusion` only for individually reviewed face/character regions. A
small local MediaPipe geometry locator prepares each input once per GIF or
nine-result recommendation job. The renderer uses pre-authored eye/hair/mouth
anchors, affine triangles, finite-support Laplacian blending and exact final
occlusion masks. No generative model, hosted identity API or runtime download.

C is an offline generative-art direction, **not** evidence of CPU-rendered
quality. This implementation can retain template ears, head outline, fur,
clothes, action and props with recognizable uploaded features. It cannot invent
hair strands, recover absent teeth, synthesize a new expression or reconstruct
an unseen side of the uploaded face. Never label it expression transfer.

- Natural animal heads can include uploaded hair between protected ears. Match
  measured original eye positions, with a reviewed six-anchor hair cap.
- Human scenes normally retain source hair and use `include_hair: false`. Check
  original eyebrows, chin, glasses, bangs and every foreground hand.
- Black-and-white panda heads can use explicit `style: photocopy`. Review the
  actual supplied portrait: thresholding can destroy identity or leave old eyes.
- Caption-only templates, avatar props, whole-image effects and exaggerated
  cartoon faces should keep their existing adapter when that preserves intent.
- No detectable portrait, tiny faces and arbitrary objects use the authored
  `fallback_box` and alpha-aware paste. Do not require a frontal-face detector or
  silently force foreground extraction. The input's alpha remains authoritative.

Each fusion layer declares bounded `eyes`, optional six-point `hair`, optional
`mouth`/`chin`, `fallback_box`, `edge`, partial `color_match`, and 2..4
`pyramid_levels`. Its SHA mask is the only editable support; hands, text and ears
must remain outside it. Prepare template repairs offline. Zero RGB beneath
transparent repair pixels so public assets do not retain redundant scenes.

For GIFs author **every** source frame; source tracking is offline only. Preserve
complete normalized timing and the loop. Review every actual output frame,
especially raised paws, impact marks, turning heads and occluding fingers. Reject
side-face distortion, mismatched skin blocks, residual original features or any
modified fixed pixel. A detector finding a face is never visual approval.

Run `tools/qa/cpu_fusion.py` with isolated state and a private validation portrait.
Also check partial-alpha input, extraction on/off, arbitrary-object fallback,
changed captions, missing/empty/oversized input and CPU-host timings. Bind
`quality.spec_sha256`, `fusion_model_sha256`, `fusion_checked_frames` and
`fusion_fixed_pixel_max_error` to the approved recipe. `validate_elements` rejects
unbound evidence. Increment versions; preserve stable keys. Public source assets
and recipes may ship; user portraits and generated validation outputs may not.

The complete 958-key disposition is in
`docs/template-audit/20261027-compositing.json`: 44 fusion, 438 paste, 476 caption.
These are deployment decisions, not a claim that every input equals generative C.
