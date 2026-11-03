"""Real-terrain DEVELOPMENT run: Landsat D2 *val* split (20 tiles) and Sentinel-2 *dev* regions only. Resumable stores
p4dev_* on the external drive. Test/held-out splits are never read here."""
import sys, os
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
import numpy as np
from research.trs import paths, datasets as DS, experiments as E, runner, s2data
from research.trs.store import Store, Timer
def main():
    paths.check_drive(10)
    which = sys.argv[1]
    if which == "d2":
        names = list(E.p4_d2_methods("cpu").keys())
        for sub, metric in [("p4dev_d2", "metric_d2"), ("p4dev_d2_spectral", "metric_d2_sam")]:
            st = Store(paths.out_dir(sub) / "results.jsonl")
            print(sub, runner.run(DS.d2_samples("val"), "p4_d2_methods", metric, st, names, workers=2, log=print), flush=True)
    else:
        os.environ["OMP_NUM_THREADS"] = "3"
        st = Store(paths.out_dir("p4dev_s2") / "results.jsonl"); st2 = Store(paths.out_dir("p4dev_s2_spectral") / "results.jsonl")
        scenes = [s for s in s2data.list_scenes() if s["split"] == "dev"]; allsc = s2data.list_scenes()
        M = E.p4_s2_methods("cpu")
        for i, m in enumerate(scenes):
            if any(k.startswith(m["name"] + "_r") for k, _ in st.done):
                continue
            others = [x for x in allsc if x["region"] != m["region"] and x["split"] == "dev"]
            sc = s2data.load_scene(m["name"]); V = s2data.terrain_variants(sc, s2data.load_scene(others[i % len(others)]["name"])["dem"])
            n = 0
            for s in s2data.tiles(sc, V):
                for name, f in M.items():
                    try:
                        with Timer() as t:
                            out = np.clip(np.asarray(f(s), np.float32), 0, 1)
                        st.add(sample=s["name"], method=name, group=s["region"], status="ok", ms_per_mp=t.dt * 1e3 / (s["bands"].shape[0] * s["bands"].shape[1] / 1e6), **E.metric_s2(out, s))
                        st2.add(sample=s["name"], method=name, group=s["region"], status="ok", **E.metric_s2_sam(out, s))
                    except Exception as e:
                        st.add(sample=s["name"], method=name, group=s["region"], status=f"fail: {type(e).__name__}: {str(e)[:200]}")
                n += 1
            print("scene", m["name"], n, "tiles", flush=True)


if __name__ == "__main__":
    main()
