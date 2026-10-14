#!/bin/sh
set -eu
# API and worker each use their own environment; manual subject extraction needs CPU ONNX in API.
/opt/gensticker-venv/bin/python -m pip install 'onnxruntime>=1.23,<2' 'opencv-python-headless>=4.10,<5'
if [ ! -d /opt/gensticker-worker-venv ]; then
  cp -a /opt/gensticker-venv /opt/gensticker-worker-venv
fi
PYTHON=/opt/gensticker-worker-venv/bin/python
"$PYTHON" -m pip install 'onnxruntime>=1.23,<2' 'opencv-python-headless>=4.10,<5' pyclipper PyYaml shapely flatbuffers protobuf sympy coloredlogs humanfriendly
# RapidOCR declares GUI OpenCV, but headless supplies the same cv2 API on this server.
"$PYTHON" -m pip install --no-deps rapidocr-onnxruntime==1.4.4
"$PYTHON" -c 'import onnxruntime, cv2, rapidocr_onnxruntime, yaml; print("CPU feature runtime ready")'
