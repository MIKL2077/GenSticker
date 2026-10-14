# Multi-layout regression, 2026-10-14

These are private authoring tests, not production additions. The repository holds bounded briefs and reproducible commands, not downloaded meme images or validation portraits. Download the original files from the attributed pages into a private sample directory as `cat.jpg`, `doge.jpg`, and `farmer.jpg`. The script scales each to at most 750 pixels, then applies its corresponding reviewed brief.

## Cases and decisions

- [Cat Meme](https://commons.wikimedia.org/wiki/File:Cat_Meme.jpg), Jennifer Williams / credited derivative uploader, CC BY-SA 2.0. Two edge captions are editable. Closed eyes, petting hand, bench and imgflip watermark stay fixed. The first bottom caption box overlapped the watermark; it was shortened before accepting the brief. Glyph removal preserves the wood texture. The reconstructed font is approximate and requires visual review, even when the pixel gate passes.
- [Doge homemade meme](https://commons.wikimedia.org/wiki/File:Doge_homemade_meme.jpg), Euterpia, CC0. The bottom green phrase alone is editable. The dog expression and other scattered phrases are fixed. Removing a whole rectangle damaged the textured background; a colour-based glyph mask replaced it. Replacing the entire head would also destroy words crossing the head and the original reaction, so this test deliberately has no image slot.
- [Farmer meme with apostrophe](https://commons.wikimedia.org/wiki/File:Farmer_meme_with_apostrophe.jpg), Cakelot1 / Dianne Johnson (USDA), public domain as recorded on the source page. Only the face beneath the hat is replaceable. Hat, fixed slogans, overalls and field remain. An initial whole-head and rewritten-caption attempt exceeded the reconstruction gate; the final brief protects those elements and removes the original face offline. Cropping the validation photo matters: including its own hat can introduce a second brim. Subject extraction removes background, not semantic accessories.
- The user-provided “笑不出来” dog remains the product acceptance example. Version 3 prepares its old-head removal background before requests and offers extraction on/off. It does not require a frontal-face detector. Its source rights remain unverified, separate from the licensed test cases above.

## Reproduce

Run in the GenSticker environment with Pillow, NumPy, OpenCV, Pydantic and the project dependencies. Optional extraction needs the locally cached, checksum-verified U2NetP model and ONNX Runtime.

```sh
PYTHONPATH=backend/meme-generator python skills/meme-to-template/scripts/regression.py \
  --sample-dir /tmp/private-meme-samples \
  --validation-photo /tmp/cropped-portrait.png \
  --output-dir /tmp/private-meme-results
```

Repeat with `--extract-subject` to test the opt-in path. Existing transparent input reuses its alpha and avoids inference. Run `scripts/decompose.py` on a single brief with the same optional flag for targeted iteration. Keep source attribution and license obligations with any eventual distributed derivative; this test does not itself grant publication rights.

## Observed results and limits

The three final briefs rendered successfully. Default reconstruction mean absolute errors were 9.63 (cat), 2.57 (Doge) and 0.53 (farmer), on the helper's 128 × 128 comparison. Protected caption-background pixel error was zero. The farmer replacement changed pixels outside the editable union by approximately 0.05 mean intensity units after JPEG output. These gates check geometry and pixel preservation, not humour, font identity or realistic face blending. Outputs are labelled `rendered-for-visual-review`; the runner never publishes them.

Review source and output at actual size before publication. Reject residual original letters, double heads, lost props, watermark damage, block-shaped inpainting and misleading expressions. A successful tool run is insufficient. Record the rejected attempt, change a specific mask/slot/font rule, and rerender. Single-line captions use `max_lines: 1`: shrink to fit or reject overflow instead of silently splitting words. A public source with uncertain derivative permission stays pending regardless of quality.

Actual visual disposition: all three new examples remain pending publication. The cat output still has visible repaired patches in the bench texture; switching Telea to Navier–Stokes did not fix them. The farmer validation input includes an unwanted second hat brim and needs a tighter user-selected crop. Doge retains the original reaction and surrounding phrases, but its replacement typography is approximate. These failure cases are intentional regression coverage: do not interpret their low mean pixel errors as publication approval. The briefs record the reasons in `metadata.review`, and the runner includes that review alongside numerical results.
