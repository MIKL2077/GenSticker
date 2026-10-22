"""Offline, resumable per-frame OCR inventory. Proposals require visual review."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def scan(inventory, output):
    output.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                      det_limit_side_len=384, text_score=.6)
    human = cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    cat = cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalcatface_extended.xml')
    started = time.monotonic()
    for row in inventory:
        target = output/(row['key']+'.json')
        if target.exists():
            continue
        frames = []
        with Image.open(row['path']) as source:
            for index in range(getattr(source, 'n_frames', 1)):
                source.seek(index)
                frame = source.convert('RGB')
                # OCR at twice the source scale improves tiny source lettering.
                scale = max(1, min(3, 640/max(frame.size)))
                pixels = np.asarray(frame.resize((round(frame.width*scale), round(frame.height*scale))))
                result, _ = engine(pixels)
                captions = []
                for points, text, score in result or []:
                    captions.append({'polygon': [[round(x/scale), round(y/scale)] for x,y in points],
                                     'text': text, 'confidence': round(float(score), 4)})
                gray = cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2GRAY)
                faces = {}
                for kind, cascade in [('person', human), ('cat', cat)]:
                    boxes = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4,
                                                      minSize=(18,18))
                    faces[kind] = [[int(v) for v in box] for box in boxes]
                frames.append({'index':index, 'duration_ms':int(source.info.get('duration',100)),
                               'captions':captions, 'faces':faces})
        target.write_text(json.dumps({'key':row['key'], 'canvas':row['canvas'], 'frames':frames},
                                    ensure_ascii=False, indent=2))
        if row['index'] % 10 == 0:
            print(json.dumps({'scanned':row['index']+1, 'elapsed_s':round(time.monotonic()-started)}), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('inventory',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    scan(json.loads(args.inventory.read_text()), args.output)
