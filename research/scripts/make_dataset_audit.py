"""Write dataset checksums/manifests (hashes of archives, counts, sizes) from what is actually on the drive."""
import hashlib, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research.trs import paths  # noqa: E402


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def size_gb(d):
    return sum(f.stat().st_size for f in Path(d).rglob("*") if f.is_file()) / 1e9


def main():
    paths.check_drive(1, create=False)
    out = {}
    arch = {}
    for name, rel in [("darkrs", "datasets/darkrs/raw_archive/darkrs.rar"), ("isaid_dark", "datasets/isaid_dark/raw_archive/isaid_dark.bin"),
                      ("exdark", "datasets/exdark/raw_archive/exdark.bin"), ("dffn_weights", "checkpoints/dffn/weight/model_best_isaid.pt"),
                      ("alexnet", "checkpoints/torch/hub/checkpoints/alexnet-owt-7be5be79.pth")]:
        p = paths.ROOT / rel
        if p.exists():
            arch[rel] = sha(p)
    json.dump(arch, open(paths.RESEARCH / "dataset_manifests/archives_checksums.json", "w"), indent=1)
    for d in ["landsat_original", "isaid_dark", "darkrs", "aid", "sentinel2", "copernicus_dem", "exdark", "synthetic"]:
        p = paths.ds(d)
        n = sum(1 for f in p.rglob("*") if f.is_file()) if p.exists() else 0
        out[d] = dict(files=n, size_gb=round(size_gb(p), 3) if p.exists() else 0)
    json.dump(out, open(paths.RESEARCH / "dataset_manifests/dataset_sizes.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
