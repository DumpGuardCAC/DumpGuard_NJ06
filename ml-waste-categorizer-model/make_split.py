import os, random
import numpy as np, pandas as pd, imagehash
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

random.seed(0)
np.random.seed(0)
SUF = "" if int(os.environ.get("DG_S", 256)) == 256 else "_" + os.environ["DG_S"]
clean = f"data/manifest_all_clean{SUF}.csv"
df = pd.read_csv(clean if os.path.exists(clean) else f"data/manifest_all{SUF}.csv")

CAP = {("oi", "ewaste_hazard"): 900, ("oi", "no_object"): 1500, ("garbage12", "no_object"): 500,
       ("trashnet", "*"): 400, ("oi", "cardboard_paper"): 1200,
       ("oitrain", "ewaste_hazard"): 1200, ("oitrain", "no_object"): 2500, ("oitrain", "cardboard_paper"): 3000,
       ("coco", "ewaste_hazard"): 900, ("coco", "no_object"): 2000, ("coco", "cardboard_paper"): 2500}
parts = []
for (src, cls), g in df.groupby(["source", "cls"]):
    cap = CAP.get((src, cls), CAP.get((src, "*"), None))
    if cap and src != "zerowaste_test" and len(g) > cap:
        g = g.sample(cap, random_state=0)
    parts.append(g)
df = pd.concat(parts, ignore_index=True)

groups = df.loc[~df.source.isin(["zerowaste_test", "scrape"]), "group"].unique().to_numpy(dtype=object)
rng = np.random.RandomState(0)
rng.shuffle(groups)
n = len(groups)
val_g = set(groups[: int(n * 0.075)])
te_g = set(groups[int(n * 0.075): int(n * 0.15)])


def split(r):
    if r.source == "zerowaste_test":
        return "ext_test"
    if r.source == "scrape":
        return "train"
    if r.group in val_g:
        return "val"
    if r.group in te_g:
        return "test_id"
    return "train"


df["split"] = df.apply(split, axis=1)


def ph(p):
    try:
        return imagehash.phash(Image.open(p), hash_size=8).hash.flatten()
    except Exception:
        return np.zeros(64, bool)


with ThreadPoolExecutor(12) as ex:
    H = np.array(list(ex.map(ph, df.path)))
tr = np.where(df.split == "train")[0]
ev = np.where(df.split != "train")[0]
drop = set()
Ht = H[tr].astype(np.uint8)
for i in ev:
    d = (Ht != H[i].astype(np.uint8)).sum(1)
    for j in np.where(d <= 4)[0]:
        drop.add(tr[j])
print("train near-duplicates of eval images dropped:", len(drop))
df = df.drop(index=list(drop)).reset_index(drop=True)
LIMIT = {"train": 4800, "val": 300, "test_id": 300}
SHARE = {"scrape": 0.3, "zerowaste": 0.4}
BOOST = {"taco": 1}


def fair(g, lim):
    sizes = g.source.value_counts()
    for src, share in SHARE.items():
        if src in sizes:
            others = sizes.sum() - sizes[src]
            sizes[src] = min(sizes[src], int(others * share / (1 - share)))
    lo, hi = 0, lim
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if np.minimum(sizes, mid).sum() <= lim:
            lo = mid
        else:
            hi = mid - 1
    take = np.minimum(sizes, lo)
    return pd.concat([g[g.source == src].sample(int(n), random_state=0) for src, n in take.items()])


web = df[(df.source == "web") & (df.split == "train")]
df = pd.concat([df, web, web], ignore_index=True)
kept = []
for (sp, cls), g in df.groupby(["split", "cls"]):
    lim = LIMIT.get(sp)
    kept.append(fair(g, lim) if lim else g)
df = pd.concat(kept, ignore_index=True)
extra = [df[(df.source == s) & (df.split == "train")] for s, k in BOOST.items() for _ in range(k)]
df = pd.concat([df] + extra, ignore_index=True)
df.to_csv(f"data/manifest{SUF}.csv", index=False)
print(df.groupby(["split", "cls"]).size().unstack(fill_value=0).to_string())
print(df[df.split == "train"].groupby(["cls", "source"]).size().unstack(fill_value=0).to_string())
