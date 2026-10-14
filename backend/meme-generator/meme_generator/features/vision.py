"""Local CPU processing; never sends users' photos to a hosted API."""

import os
from pathlib import Path
from PIL import Image, ImageOps
from .store import root

_session = None
_emotion = None
PROCESSOR_VERSION = "u2netp-largest-v1-ferplus-v1"


def warmup(*, include_emotion=True):
    global _session, _emotion
    home = Path(os.getenv("U2NET_HOME", str(root() / "models")))
    if not (home / "u2netp.onnx").is_file():
        return False
    os.environ["U2NET_HOME"] = str(home)
    os.environ["OMP_NUM_THREADS"] = "2"
    import hashlib
    import onnxruntime as ort

    expected = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
    if hashlib.sha256((home / "u2netp.onnx").read_bytes()).hexdigest() != expected:
        raise ValueError("segmentation model checksum mismatch")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    _session = ort.InferenceSession(
        str(home / "u2netp.onnx"),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    if include_emotion and (home / "emotion-ferplus-8.onnx").is_file():
        if (
            hashlib.sha256((home / "emotion-ferplus-8.onnx").read_bytes()).hexdigest()
            != "a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c"
        ):
            raise ValueError("expression model checksum mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        _emotion = ort.InferenceSession(
            str(home / "emotion-ferplus-8.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    return True


def extract(image):
    import numpy as np

    if _session is None:
        raise ValueError("segmentation unavailable")
    array = np.asarray(image.convert("RGB").resize((320, 320)), dtype="float32")
    array /= max(float(array.max()), 1.0)
    array = (array - np.array([0.485, 0.456, 0.406], dtype="float32")) / np.array(
        [0.229, 0.224, 0.225], dtype="float32"
    )
    inputs = array.transpose(2, 0, 1)[None].astype("float32")
    prediction = _session.run(None, {_session.get_inputs()[0].name: inputs})[0][0, 0]
    spread = float(prediction.max() - prediction.min())
    if not np.isfinite(prediction).all() or spread < 1e-6:
        raise ValueError("uncertain segmentation")
    mask = Image.fromarray(
        ((prediction - prediction.min()) / spread * 255).astype("uint8")
    ).resize(image.size, Image.Resampling.LANCZOS)
    from PIL import ImageChops

    output = image.convert("RGBA")
    output.putalpha(ImageChops.multiply(mask, output.getchannel("A")))
    return output


def process(path):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    analysis = {
        "processor_version": PROCESSOR_VERSION,
        "subject": "unknown",
        "expression": "general",
        "confidence": 0.0,
        "cutout": False,
        "method": "original-crop",
        "warnings": [],
    }
    if _session is not None:
        try:
            cutout = extract(image)
            import cv2
            import numpy as np

            alpha = cutout.getchannel("A")
            mask = (np.asarray(alpha) > 100).astype("uint8")
            number, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            box = None
            if number > 1:
                largest = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
                x, y, w, h = stats[largest, :4]
                box = (
                    max(0, int(x) - 4),
                    max(0, int(y) - 4),
                    min(image.width, int(x + w) + 4),
                    min(image.height, int(y + h) + 4),
                )
                keep = cv2.dilate(
                    (labels == largest).astype("uint8"), np.ones((9, 9), dtype="uint8")
                )
                clean = (np.asarray(alpha) * keep).astype("uint8")
                cutout.putalpha(Image.fromarray(clean))
            if box:
                coverage = sum(v > 100 for v in alpha.resize((64, 64)).getdata()) / 4096
                if 0.02 < coverage < 0.98:
                    image = cutout.crop(box)
                    analysis.update(cutout=True, method="u2netp")
                else:
                    analysis["warnings"].append("主体不明确，已保留原图")
        except Exception:
            analysis["warnings"].append("主体提取失败，已保留原图")
    else:
        analysis["warnings"].append("抠图模型未就绪，已保留原图")
    try:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        cv2.setNumThreads(2)
        detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = detector.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            analysis["subject"] = "person"
            if _emotion is not None:
                crop = (
                    cv2.resize(gray[y : y + h, x : x + w], (64, 64))
                    .astype("float32")
                    .reshape(1, 1, 64, 64)
                )
                scores = _emotion.run(None, {_emotion.get_inputs()[0].name: crop})[0][0]
                probabilities = np.exp(scores - scores.max())
                probabilities /= probabilities.sum()
                index = int(probabilities.argmax())
                confidence = float(probabilities[index])
                names = [
                    "general",
                    "happy",
                    "surprised",
                    "sad",
                    "angry",
                    "general",
                    "surprised",
                    "general",
                ]
                if confidence >= 0.55:
                    analysis.update(
                        expression=names[index],
                        confidence=round(confidence, 3),
                        expression_method="ferplus",
                    )
            smile = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_smile.xml"
            )
            if _emotion is None and len(
                smile.detectMultiScale(gray[y + h // 2 : y + h, x : x + w], 1.8, 20)
            ):
                analysis.update(
                    expression="happy",
                    confidence=0.35,
                    expression_method="smile-heuristic",
                )
        # Unknown/non-human subjects deliberately use general rather than face labels.
    except ImportError:
        pass
    analysis["aspect"] = round(image.width / max(1, image.height), 2)
    analysis["warnings"].append("表情标签仅描述视觉线索，不判断真实情绪")
    return image, analysis
