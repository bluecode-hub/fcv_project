"""E7 downstream utility: AID scene classification with FIXED weights.

Backbone: torchvision ResNet-50 (ImageNet weights, frozen). Head: multinomial logistic regression trained ONCE on
features of CLEAN AID images that are disjoint from the evaluation pool (manifest['head_train']).
The backbone and head are never changed; enhancement is applied to degraded test images only.
This is a fixed-model before/after comparison, not a training experiment on enhanced data.
"""
from __future__ import annotations

import json

import cv2
import numpy as np

from . import paths, datasets as DS, experiments as E
from .store import Store

_net = {}


def backbone():
    import torch, torchvision
    if "m" not in _net:
        w = torchvision.models.ResNet50_Weights.IMAGENET1K_V2
        m = torchvision.models.resnet50(weights=w)
        m.fc = torch.nn.Identity()
        _net["m"] = m.eval()
    return _net["m"]


def feats(bgr_list, bs=16):
    import torch
    m = backbone()
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    out = []
    for i in range(0, len(bgr_list), bs):
        x = []
        for b in bgr_list[i:i + bs]:
            r = cv2.resize(b[..., ::-1], (224, 224), interpolation=cv2.INTER_AREA)
            x.append(((r - mean) / std).transpose(2, 0, 1))
        with torch.no_grad():
            out.append(m(torch.from_numpy(np.stack(x)).float()).numpy())
    return np.concatenate(out)


def train_head(man, log):
    from sklearn.linear_model import LogisticRegression
    root = paths.ds("aid") / "images"
    X = feats([DS.read_bgr(root / k) for k in man["head_train"]])
    y = [k.split("/")[0] for k in man["head_train"]]
    clf = LogisticRegression(max_iter=2000, C=1.0).fit(X, y)
    log(f"  head trained on {len(y)} clean images, train acc {clf.score(X, y):.3f}")
    return clf


def run(cfg, log, device="cpu"):
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return dict(status="skipped: scikit-learn missing")
    man = json.load(open(paths.RESEARCH / "dataset_manifests/aid_subset.json"))
    store = Store(paths.out_dir("e_downstream") / "results.jsonl")
    clf = train_head(man, log)
    M = E.rgb_methods(device)
    root = paths.ds("aid") / "images"
    test = [k for k, s in sorted(man["split"].items()) if s == "test"]
    for deg in cfg["aid"]["degradations"]:
        for name, f in list(M.items()) + [("Clean-reference", None)]:
            key = f"{deg}|{name}"
            if store.has(key, name) and False:
                continue
            if store.has(key, "acc"):
                continue
            imgs, y = [], []
            for k in test:
                gt = DS.read_bgr(root / k)
                if max(gt.shape[:2]) > 600:
                    s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                if f is None:
                    imgs.append(gt)
                else:
                    x = DS.degrade(gt, deg, k)
                    imgs.append(np.clip(f(dict(bands=x)), 0, 1).astype(np.float32))
                y.append(k.split("/")[0])
            pred = clf.predict(feats(imgs))
            correct = (pred == np.array(y)).astype(float)
            store.add(sample=key, method="acc", variant=name, degradation=deg, status="ok", acc=float(correct.mean()),
                      per_image=json.dumps({k: int(c) for k, c in zip(test, correct)}), n=len(y))
            log(f"  {deg:10s} {name:22s} acc={correct.mean():.3f}")
    return dict(status="ok", n_test=len(test))
