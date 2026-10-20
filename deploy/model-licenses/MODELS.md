# Local CPU models

No model weights are committed. Deployment obtains weights from the upstream distributions and verifies hashes before using them. These models run locally in the bounded API preview process and the isolated queue worker. No uploaded photo is sent to their authors or a hosted AI service.

U2NetP: official rembg distribution, upstream U-2-Net project Apache-2.0. Source: https://github.com/xuebinqin/U-2-Net and https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx. MD5 from rembg's official session: 8e83ca70e441ab06c318d82300c84806. SHA256: 309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8.

Emotion FERPlus opset8: ONNX Model Zoo, documented MIT model license. Source/model card: https://github.com/onnx/models/tree/main/validated/vision/body_analysis/emotion_ferplus. Download: https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx. SHA256: a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c.

The model outputs visual expression probabilities on a detected face. It does not identify a person, establish their psychological state, or classify non-human emotions. Low-confidence or missing faces use general templates. Do not use it for consequential judgments about people.

OCR uses RapidOCR ONNX locally, Apache-2.0: https://github.com/RapidAI/RapidOCR. OCR is used for licensed ingestion and images explicitly submitted by the user for template authoring. Ordinary recommendation photos are not sent through the OCR pipeline; no text is sent to a hosted OCR service. Low-confidence user drafts require explicit review before publication checks.
