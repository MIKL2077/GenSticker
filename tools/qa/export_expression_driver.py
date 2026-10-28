#!/usr/bin/env python3
"""Offline export of the pinned upstream EmotionNet generator; never a server dependency."""
import argparse
import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

SOURCE_SHA = 'fcfb606848a3b4bce6f02acfd73d5793fc50c95d8d19fad68b89f8ed45477a5b'
WEIGHTS_SHA = '4db83e1727128e2c5de27bc80d2929586535e04a709af45016a63e7cf7c46b0c'
MODEL_SHA = 'e4ceefd1c354a1e13a1d46e322108aeb5024d846ee7536468d19aca3f51b6f46'


class Generator(torch.nn.Module):
    def __init__(self, network):
        super().__init__()
        self.network = network

    def forward(self, image, aus):
        color, attention, _ = self.network(image, aus)
        return attention * image + (1 - attention) * color


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream-model-utils', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if torch.__version__.split('+')[0] != '2.6.0':
        raise ValueError('use the verified offline PyTorch 2.6.0 environment')
    for path, expected in [(args.upstream_model_utils, SOURCE_SHA), (args.weights, WEIGHTS_SHA)]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('upstream file checksum mismatch: ' + path.name)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(20261028)
    spec = importlib.util.spec_from_file_location('ganimation_network', args.upstream_model_utils)
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    net = upstream.SplitGenerator(3, 17, 64, norm_layer=upstream.get_norm_layer('instance'))
    net.load_state_dict(torch.load(args.weights, map_location='cpu', weights_only=True), strict=True)
    net = Generator(net).eval()
    inputs = (torch.rand(1, 3, 128, 128) * 2 - 1, torch.rand(1, 17))
    with torch.inference_mode():
        expected = net(*inputs).numpy()
        torch.onnx.export(net, inputs, str(args.output), input_names=['image', 'aus'],
                          output_names=['output'], opset_version=17, dynamo=False)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.output), options, providers=['CPUExecutionProvider'])
    actual = session.run(None, {name: tensor.numpy() for name, tensor in zip(['image', 'aus'], inputs)})[0]
    if not np.allclose(expected, actual, atol=2e-4, rtol=2e-4):
        raise ValueError('export parity failed')
    if hashlib.sha256(args.output.read_bytes()).hexdigest() != MODEL_SHA:
        raise ValueError('export differs from the reviewed model; do not install it')
    print('PINNED_EXPORT_OK', args.output.stat().st_size, float(np.max(np.abs(expected - actual))))
