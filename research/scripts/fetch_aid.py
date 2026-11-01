"""Download AID (blanchon/AID on Hugging Face) to the external drive.

Files are fetched in a deterministic round-robin over the 30 classes (seeded shuffle inside each class),
so ANY completed prefix is class-balanced. The experiment subset is frozen from a prefix by
``make_manifest`` and recorded in dataset_manifests/aid_subset.json. Resumable; verifies git-blob sizes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.trs import paths  # noqa: E402

API = "https://huggingface.co/api/datasets/blanchon/AID/tree/main"
RAW = "https://huggingface.co/datasets/blanchon/AID/resolve/main"
S = requests.Session()


def get(url, **kw):
    for i in range(6):
        try:
            r = S.get(url, timeout=60, **kw)
            r.raise_for_status()
            return r
        except Exception:
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"failed: {url}")


def listing(cache: Path):
    if cache.exists():
        return json.load(open(cache))
    classes = [x["path"] for x in get(f"{API}/data").json() if x["type"] == "directory"]
    files = {}
    for c in sorted(classes):
        r = get(f"{API}/{c}").json()
        files[c.split("/")[-1]] = sorted([(x["path"], x["size"], x.get("lfs", {}).get("oid")) for x in r if x["type"] == "file"])
    json.dump(files, open(cache, "w"))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=100000, help="stop after this many files (total)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20261101)
    a = ap.parse_args()
    paths.check_drive(10)
    dst = paths.ds("aid")
    files = listing(dst / "listing.json")
    rng = random.Random(a.seed)
    order = {c: rng.sample(v, len(v)) for c, v in files.items()}
    rounds = max(len(v) for v in order.values())
    total = sum(len(v) for v in files.values())
    print(f"AID listing: {len(files)} classes, {total} files, {sum(t[1] for v in files.values() for t in v)/1e9:.2f} GB")
    tasks = []
    for i in range(rounds):
        for c in sorted(order):
            if i < len(order[c]):
                tasks.append(order[c][i])
    tasks = tasks[:a.max]
    from concurrent.futures import ThreadPoolExecutor

    def one(t):
        p, size, sha = t
        out = dst / "images" / p.split("/")[1] / Path(p).name
        if out.exists() and out.stat().st_size == size:
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        r = get(f"{RAW}/{p}")
        if len(r.content) != size or (sha and hashlib.sha256(r.content).hexdigest() != sha):
            print("size/sha256 mismatch", p, flush=True)
            return 0
        tmp = out.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.rename(out)
        return 1

    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for ok in ex.map(one, tasks):
            n += ok
            if n % 100 == 0:
                print(f"{n}/{len(tasks)}", flush=True)
    print("done", n)


if __name__ == "__main__":
    main()
