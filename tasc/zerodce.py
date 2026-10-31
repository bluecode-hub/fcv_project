"""Zero-DCE (Guo et al., CVPR 2020) inference in plain NumPy.

Loads the authors' pretrained ``Epoch99.pth`` (legacy PyTorch serialisation) without
PyTorch, then runs DCE-Net (7 conv layers, 32 channels) and the 8 iterations of the
light-enhancement curve LE(x) = x + r (x^2 - x).

Weights: https://github.com/Li-Chongyi/Zero-DCE  (Zero-DCE_code/snapshots/Epoch99.pth)
"""
from __future__ import annotations

import pickle
import struct
from collections import OrderedDict
from pathlib import Path

import numpy as np

_DTYPES = {"FloatStorage": np.float32, "DoubleStorage": np.float64, "HalfStorage": np.float16,
           "LongStorage": np.int64, "IntStorage": np.int32, "ByteStorage": np.uint8}


class _Storage:
    def __init__(self, dtype, numel):
        self.dtype, self.numel, self.data = dtype, numel, None


def _rebuild_tensor_v2(storage, offset, size, stride, *args):
    return ("tensor", storage, offset, tuple(size), tuple(stride))


class _StorageType:
    def __init__(self, name):
        self.name = name


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, storages):
        super().__init__(f)
        self.storages = storages

    def find_class(self, module, name):
        if module == "torch._utils" and name == "_rebuild_tensor_v2":
            return _rebuild_tensor_v2
        if module == "torch" and name.endswith("Storage"):
            return _StorageType(name)
        if module == "collections" and name == "OrderedDict":
            return OrderedDict
        raise pickle.UnpicklingError(f"blocked global {module}.{name}")   # never run arbitrary code

    def persistent_load(self, pid):
        _, stype, key, _location, numel = pid[:5]
        if key not in self.storages:
            self.storages[key] = _Storage(_DTYPES[stype.name], numel)
        return self.storages[key]


def load_legacy_state_dict(path: str | Path) -> dict:
    with open(path, "rb") as f:
        for _ in range(3):                      # magic number, protocol version, sys info
            pickle.load(f)
        storages: dict = {}
        obj = _Unpickler(f, storages).load()
        keys = pickle.load(f)
        for key in keys:
            st = storages[key]
            (n,) = struct.unpack("<q", f.read(8))
            st.data = np.frombuffer(f.read(n * np.dtype(st.dtype).itemsize), dtype=st.dtype)
    out = {}
    for name, (_, st, offset, size, stride) in obj.items():
        itemsize = np.dtype(st.dtype).itemsize
        arr = np.lib.stride_tricks.as_strided(st.data[offset:], shape=size,
                                              strides=tuple(s * itemsize for s in stride))
        out[name.replace("module.", "")] = np.array(arr, dtype=np.float32)
    return out


def _conv3x3(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """x: (C, H, W); w: (O, C, 3, 3) -> (O, H, W), zero padding 1."""
    C, H, W = x.shape
    xp = np.pad(x, ((0, 0), (1, 1), (1, 1)))
    cols = np.empty((C, 9, H, W), np.float32)
    for i in range(3):
        for j in range(3):
            cols[:, i * 3 + j] = xp[:, i:i + H, j:j + W]
    y = w.reshape(w.shape[0], C * 9) @ cols.reshape(C * 9, H * W)
    return (y + b[:, None]).reshape(-1, H, W)


class ZeroDCE:
    def __init__(self, weights: str | Path):
        self.p = load_legacy_state_dict(weights)

    def _layer(self, i, x):
        return _conv3x3(x, self.p[f"e_conv{i}.weight"], self.p[f"e_conv{i}.bias"])

    def enhance_rgb(self, rgb: np.ndarray, tile: int = 384, pad: int = 16) -> np.ndarray:
        """rgb: (H, W, 3) float in [0, 1] -> enhanced (H, W, 3).

        Large images run in overlapping tiles. DCE-Net's receptive field is 15 px, so a
        16 px overlap gives the same result as a single pass.
        """
        H, W, _ = rgb.shape
        if H <= tile + 2 * pad and W <= tile + 2 * pad:
            return self._enhance(rgb)
        out = np.empty_like(rgb, dtype=np.float32)
        for r in range(0, H, tile):
            for c in range(0, W, tile):
                r0, c0 = max(r - pad, 0), max(c - pad, 0)
                r1, c1 = min(r + tile + pad, H), min(c + tile + pad, W)
                o = self._enhance(rgb[r0:r1, c0:c1])
                out[r:min(r + tile, H), c:min(c + tile, W)] = o[r - r0:r - r0 + min(tile, H - r),
                                                              c - c0:c - c0 + min(tile, W - c)]
        return out

    def _enhance(self, rgb):
        x = np.moveaxis(rgb.astype(np.float32), -1, 0)
        relu = lambda t: np.maximum(t, 0)
        x1 = relu(self._layer(1, x))
        x2 = relu(self._layer(2, x1))
        x3 = relu(self._layer(3, x2))
        x4 = relu(self._layer(4, x3))
        x5 = relu(self._layer(5, np.concatenate([x3, x4], 0)))
        x6 = relu(self._layer(6, np.concatenate([x2, x5], 0)))
        r = np.tanh(self._layer(7, np.concatenate([x1, x6], 0)))
        y = x
        for k in range(8):
            rk = r[3 * k:3 * k + 3]
            y = y + rk * (y * y - y)
        return np.clip(np.moveaxis(y, 0, -1), 0, 1)
