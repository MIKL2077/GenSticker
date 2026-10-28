# Local CPU models

No model weights are committed. Deployment obtains weights from the upstream distributions and verifies hashes before using them. These models run locally in the bounded API preview process and the isolated queue worker. No uploaded photo is sent to their authors or a hosted AI service.

U2NetP: official rembg distribution, upstream U-2-Net project Apache-2.0. Source: https://github.com/xuebinqin/U-2-Net and https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx. MD5 from rembg's official session: 8e83ca70e441ab06c318d82300c84806. SHA256: 309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8.

Emotion FERPlus opset8: ONNX Model Zoo, documented MIT model license. Source/model card: https://github.com/onnx/models/tree/main/validated/vision/body_analysis/emotion_ferplus. Download: https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx. SHA256: a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c.

The model outputs visual expression probabilities on a detected face. It does not identify a person, establish their psychological state, or classify non-human emotions. Low-confidence or missing faces use general templates. Do not use it for consequential judgments about people.

OCR uses RapidOCR ONNX locally, Apache-2.0: https://github.com/RapidAI/RapidOCR. OCR is used for licensed ingestion and images explicitly submitted by the user for template authoring. Ordinary recommendation photos are not sent through the OCR pipeline; no text is sent to a hosted OCR service. Low-confidence user drafts require explicit review before publication checks.

## Reviewed GANimation expression driver

The 2026-10-29 selected templates use the EmotionNet generator from
[donydchen/ganimation_replicate](https://github.com/donydchen/ganimation_replicate),
8,467,584 parameters, 128×128 RGB, with its documented 17 normalized AU inputs.
Code license: MIT; see `GANIMATION-LICENSE.txt`. Upstream pretrained weights:
`https://drive.google.com/file/d/132yr2CtF8oD0hU9HbjusMigrvRdUages/view`.
Original `.pth` SHA256:
`4db83e1727128e2c5de27bc80d2929586535e04a709af45016a63e7cf7c46b0c`.
Separate commercial rights for the training data/weights have not been verified.

The locally exported, opset-17 ONNX file is installed as
`features/models/ganimation-emotionnet-v1.onnx`, 33,924,122 bytes, SHA256
`e4ceefd1c354a1e13a1d46e322108aeb5024d846ee7536468d19aca3f51b6f46`.
The renderer requires this exact file and uses only `CPUExecutionProvider`,
one intra-op/inter-op thread, sequential execution and disabled idle spinning.
It does not download models at request time or import PyTorch. A missing optional
model uses the normal image-slot fallback. The model edits uploaded features;
it does not recognize identities or understand a template's joke. AU curves,
geometry and occlusion masks are authored offline per template.

The selected deployment includes only 11 GAN templates and 2 geometry templates.
No CelebA or 3DDFA model is installed. Test photos and their derived media are
private and excluded from repository batches and model packages.

For a clean installation, `tools/qa/export_expression_driver.py` reproduces the
exact ONNX file from the above `.pth` and upstream `model/model_utils.py` in an
offline PyTorch 2.6.0 export environment. It checks both upstream hashes, ONNX
parity and the final hash. Production needs ONNX Runtime only; do not install
PyTorch in the API/worker environments.
