# pil-utils compatibility fork

Vendored from the installed PyPI pil-utils 0.2.2 distribution (upstream: https://github.com/MeetWq/pil-utils), preserving its MIT license and source. Local version: `0.2.2+gensticker.1`.

The upstream package caps Pillow below 12. This fork permits the tested security release Pillow 12.3.x; compatibility changes, if required, are recorded below. Do not use `--no-deps` to bypass the old constraint. GenSticker tests and the full template smoke suite must pass before rollout.

Changes: packaging dependency bounds; use the same official OpenCV distribution as RapidOCR, avoiding two packages overwriting the cv2 namespace. No GUI API is used. See repository remediation report for regression evidence.
