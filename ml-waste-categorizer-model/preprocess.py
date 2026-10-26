import os, sys, json, glob, random, hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from multiprocessing import Pool
import numpy as np, pandas as pd, torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset, DataLoader
from dataset import CLASSES, square_crop

D = "data"


def _size():
    return int(os.environ.get("DG_S", 256))


def _suffix(s):
    return "" if s == 256 else f"_{s}"


# ---------- crops: build data/manifest_all{SUF}.csv from the raw source datasets ----------

def _save_crop(job, out_dir, size):
    src, group, cls, path, box, exif = job
    name = hashlib.md5(f"{src}|{group}|{box}".encode()).hexdigest()[:16] + ".jpg"
    outp = f"{out_dir}/{src}/{cls}/{name}"
    if not os.path.exists(outp):
        try:
            im = Image.open(path)
            if exif:
                im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            if min(im.size) < 48:
                return None
            c = square_crop(im, box, size)
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            c.save(outp, quality=92)
        except Exception:
            return None
    return dict(path=outp, cls=cls, source=src, group=f"{src}:{group}")


def cmd_crops():
    random.seed(0)
    size = _size()
    out_dir = "data/crops" if size == 256 else f"data/crops{size}"
    suf = _suffix(size)

    jobs = []

    def folder_source(src, root, mapping, cap=None):
        for sub, cls in mapping.items():
            files = sorted(glob.glob(f"{root}/{sub}/*"))
            files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            random.shuffle(files)
            for f in files[:cap]:
                jobs.append((src, os.path.basename(f), cls, f, None, True))

    folder_source("trashnet", f"{D}/trashnet/dataset-resized", {
        "cardboard": "cardboard_paper", "paper": "cardboard_paper", "glass": "glass",
        "metal": "metal", "plastic": "rigid_plastic"}, cap=400)

    folder_source("garbage12", f"{D}/garbage12/garbage_classification", {
        "battery": "ewaste_hazard", "cardboard": "cardboard_paper", "paper": "cardboard_paper", "metal": "metal",
        "plastic": "rigid_plastic", "brown-glass": "glass", "green-glass": "glass", "white-glass": "glass",
        "clothes": "no_object", "shoes": "no_object"}, cap=700)

    giz = sorted(glob.glob(f"{D}/giz_ewaste/COCO with Pictures/images/*.jpg"))
    random.shuffle(giz)
    for f in giz[:500]:
        jobs.append(("giz", os.path.basename(f), "ewaste_hazard", f, None, True))

    TACO = {
        "rigid_plastic": [4, 5, 43, 44, 47],
        "soft_plastic_foam": [2, 3, 22, 36, 38, 39, 40, 41, 42, 46, 57],
        "cardboard_paper": [14, 15, 16, 17, 18, 19, 30, 33, 34],
        "metal": [0, 10, 12],
        "glass": [6, 26, 23],
        "ewaste_hazard": [1],
    }
    cat2cls = {c: k for k, v in TACO.items() for c in v}
    t = json.load(open(f"{D}/taco/annotations.json"))
    imgs = {i["id"]: i for i in t["images"]}
    for a in t["annotations"]:
        cls = cat2cls.get(a["category_id"])
        if not cls:
            continue
        x, y, w, h = a["bbox"]
        if w < 40 or h < 40:
            continue
        im = imgs[a["image_id"]]
        jobs.append(("taco", f"{a['image_id']}", cls, f"{D}/taco/{im['file_name']}", (x, y, w, h), True))

    for sub, cls in (("hazard", "ewaste_hazard"), ("background", "no_object"), ("paper", "cardboard_paper")):
        fs = sorted(glob.glob(f"{D}/openimages/img/{sub}/*.jpg"))
        for f in fs:
            jobs.append(("oi", os.path.basename(f), cls, f, None, False))

    TB = {
        "plastic/plastic bags": "soft_plastic_foam", "plastic/plastic bottles": "rigid_plastic", "plastic/plastic containers": "rigid_plastic", "plastic/plastic cups": "rigid_plastic",
        "e-waste/electrical cables": "ewaste_hazard", "e-waste/electronic chips": "ewaste_hazard", "e-waste/laptops": "ewaste_hazard", "e-waste/small appliances": "ewaste_hazard", "e-waste/smartphones": "ewaste_hazard",
        "paper/news paper": "cardboard_paper", "paper/paper": "cardboard_paper", "cardboard": "cardboard_paper",
        "glass": "glass", "metal/beverage cans": "metal", "metal/metal containers": "metal", "metal/spray cans": "metal",
    }
    if os.path.isdir("data/trashbox/train/TrashBox_train_dataset_subfolders"):
        folder_source("trashbox", "data/trashbox/train/TrashBox_train_dataset_subfolders", TB, cap=500)

    if os.path.exists("data/coco/selected.csv"):
        for r in pd.read_csv("data/coco/selected.csv").itertuples():
            if os.path.exists(r.file):
                jobs.append(("coco", f"{r.image_id}", r.cls, r.file, None if r.x < 0 else (r.x, r.y, r.w, r.h), False))

    for sub, cls in (("hazard", "ewaste_hazard"), ("background", "no_object"), ("paper", "cardboard_paper")):
        for f in sorted(glob.glob(f"data/openimages_train/img/{sub}/*.jpg")):
            jobs.append(("oitrain", os.path.basename(f), cls, f, None, False))

    realwaste_root = next(iter(glob.glob("data/realwaste/extract/*/RealWaste")), None)
    if realwaste_root:
        folder_source("realwaste", realwaste_root, {"Cardboard": "cardboard_paper", "Paper": "cardboard_paper", "Glass": "glass", "Metal": "metal"})

    for cls in CLASSES:
        for f in sorted(glob.glob(f"data/scraped/{cls}/*.jpg")):
            jobs.append(("scrape", os.path.basename(f), cls, f, None, False))

    if os.path.isdir("data/zerowaste/extract/splits_final_deblurred"):
        zw = "data/zerowaste/extract/splits_final_deblurred"
        ZW = {"cardboard": "cardboard_paper", "metal": "metal", "rigid_plastic": "rigid_plastic", "soft_plastic": "soft_plastic_foam"}
        ZCAP = {"train": {"rigid_plastic": 1100, "metal": 400, "soft_plastic_foam": 3000, "cardboard_paper": 1500},
                "val": {"rigid_plastic": 150, "metal": 60, "soft_plastic_foam": 150, "cardboard_paper": 100},
                "test": {"rigid_plastic": 315, "metal": 63, "soft_plastic_foam": 300, "cardboard_paper": 300}}
        for sp in ("train", "val", "test"):
            d = json.load(open(f"{zw}/{sp}/labels.json"))
            names = {c["id"]: c["name"] for c in d["categories"]}
            imgs = {i["id"]: i for i in d["images"]}
            per = {}
            for a in d["annotations"]:
                cls = ZW.get(names[a["category_id"]])
                x, y, w, h = a["bbox"]
                if cls and w >= 60 and h >= 60:
                    per.setdefault(cls, []).append(a)
            for cls, lst in per.items():
                random.shuffle(lst)
                for a in lst[:ZCAP[sp][cls]]:
                    im = imgs[a["image_id"]]
                    src = "zerowaste_test" if sp == "test" else "zerowaste"
                    jobs.append((src, f"{sp}{a['image_id']}", cls, f"{zw}/{sp}/data/{im['file_name']}", tuple(a["bbox"]), False))

    print("jobs", len(jobs), flush=True)
    with ThreadPoolExecutor(12) as ex:
        res = [r for r in ex.map(lambda j: _save_crop(j, out_dir, size), jobs) if r]
    df = pd.DataFrame(res)
    df.to_csv(f"data/manifest_all{suf}.csv", index=False)
    print(df.groupby(["source", "cls"]).size().unstack(fill_value=0).to_string())


# ---------- clean: CLIP-score data/manifest_all{SUF}.csv, relabel/drop, write data/manifest_all_clean{SUF}.csv ----------

TRUSTED = {"zerowaste", "zerowaste_test"}
CURATED = {"trashnet", "realwaste", "trashbox", "garbage12", "taco", "giz"}
RELABEL_CONF = 0.6
CURATED_RELABEL_CONF = 0.95
OBJECT_REJECT_CONF = 0.5
DROP_OWN = 0.08
CURATED_DROP_OWN = 0.03

CLIP_PROMPTS = {
    "rigid_plastic": ["a photo of a plastic water bottle", "a photo of a hard plastic container", "a photo of a plastic cup", "a photo of a plastic jug or tub", "a photo of a shampoo or detergent bottle"],
    "soft_plastic_foam": ["a photo of a plastic bag", "a photo of a crumpled plastic wrapper", "a photo of plastic film or bubble wrap", "a photo of styrofoam", "a photo of an empty chip bag"],
    "cardboard_paper": ["a photo of a cardboard box", "a photo of a stack of books", "a photo of a book", "a photo of crumpled paper", "a photo of a newspaper or magazine", "a photo of a paper bag", "a photo of an egg carton", "a photo of a notebook"],
    "metal": ["a photo of an aluminum soda can", "a photo of a tin can", "a photo of a crushed beer can", "a photo of aluminum foil", "a photo of a metal food can"],
    "glass": ["a photo of a glass bottle", "a photo of a glass jar", "a photo of a wine bottle", "a photo of broken glass", "a photo of a drinking glass"],
    "ewaste_hazard": ["a photo of a battery", "a photo of a smartphone", "a photo of a laptop", "a photo of a light bulb", "a photo of electronic circuit boards", "a photo of a charger and cables", "a photo of a remote control", "a photo of an aerosol spray can or paint can"],
    "no_object": ["a photo of an empty room", "a photo of an empty table", "a photo of a street or sidewalk", "a photo of grass or plants", "a photo of a person's hand with nothing in it", "a photo of a floor or wall", "a photo of clothing or shoes"],
}
CLIP_COUNTS = [len(CLIP_PROMPTS[c]) for c in CLASSES]
_DEV = "cuda" if torch.cuda.is_available() else "cpu"
_CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype="float32")
_CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype="float32")


class ClipImages(Dataset):
    def __init__(self, paths):
        self.paths = paths

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            im = Image.open(self.paths[i]).convert("RGB").resize((224, 224), Image.BILINEAR)
        except Exception:
            im = Image.new("RGB", (224, 224))
        x = (np.asarray(im, dtype="float32") / 255 - _CLIP_MEAN) / _CLIP_STD
        return torch.from_numpy(x).permute(2, 0, 1)


def _clip_text_features(model, proc):
    texts = [t for c in CLASSES for t in CLIP_PROMPTS[c]]
    with torch.no_grad():
        te = model.get_text_features(**proc(text=texts, return_tensors="pt", padding=True).to(_DEV))
        te = te if torch.is_tensor(te) else te.pooler_output
    return te / te.norm(dim=-1, keepdim=True)


def _clip_score(model, paths, te):
    out = []
    loader = DataLoader(ClipImages(paths), batch_size=96, num_workers=4)
    with torch.no_grad():
        for n, px in enumerate(loader):
            ie = model.get_image_features(pixel_values=px.to(_DEV))
            ie = ie if torch.is_tensor(ie) else ie.pooler_output
            ie = ie / ie.norm(dim=-1, keepdim=True)
            sims = 100 * ie @ te.T
            parts = torch.split(sims, CLIP_COUNTS, dim=1)
            per_class = torch.stack([p.mean(1) for p in parts], dim=1)
            out.append(per_class.softmax(-1).cpu().numpy())
            if n % 20 == 0:
                print(n * 96, len(paths), flush=True)
    return np.concatenate(out)


def cmd_clean():
    from transformers import CLIPModel, CLIPProcessor
    size = _size()
    suf = _suffix(size)
    src = f"data/manifest_all{suf}.csv"
    cache = f"data/audit_clip{suf}.csv"

    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(_DEV).eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    df = pd.read_csv(src)
    done = pd.read_csv(cache) if os.path.exists(cache) else pd.DataFrame(columns=["path"] + CLASSES)
    todo = df[~df.path.isin(set(done.path))]
    print("to score", len(todo), "cached", len(done), flush=True)
    if len(todo):
        probs = _clip_score(model, todo.path.tolist(), _clip_text_features(model, proc))
        new = pd.DataFrame(probs, columns=CLASSES)
        new.insert(0, "path", todo.path.tolist())
        done = pd.concat([done, new], ignore_index=True)
        done.to_csv(cache, index=False)
    a = df.merge(done, on="path", how="left")
    p = a[CLASSES].values.astype("float32")
    top = p.argmax(1)
    conf = p.max(1)
    y = a.cls.map({c: i for i, c in enumerate(CLASSES)}).values
    own = p[np.arange(len(a)), y]
    no_obj = CLASSES.index("no_object")
    action, new_cls = [], []
    for i, r in enumerate(a.itertuples()):
        t, l = top[i], y[i]
        if r.source in TRUSTED or t == l:
            action.append("keep")
            new_cls.append(r.cls)
        elif l == no_obj:
            drop = conf[i] >= OBJECT_REJECT_CONF
            action.append("drop" if drop else "keep")
            new_cls.append(r.cls)
        elif conf[i] >= (CURATED_RELABEL_CONF if r.source in CURATED else RELABEL_CONF) and t == no_obj:
            action.append("drop")
            new_cls.append(r.cls)
        elif conf[i] >= (CURATED_RELABEL_CONF if r.source in CURATED else RELABEL_CONF):
            action.append("relabel")
            new_cls.append(CLASSES[t])
        elif own[i] < (CURATED_DROP_OWN if r.source in CURATED else DROP_OWN):
            action.append("drop")
            new_cls.append(r.cls)
        else:
            action.append("keep")
            new_cls.append(r.cls)
    a["clip_top"] = [CLASSES[t] for t in top]
    a["clip_conf"] = conf.round(3)
    a["action"] = action
    a["new_cls"] = new_cls
    a.to_csv(f"data/audit{suf}.csv", index=False)
    print(a.groupby(["source", "action"]).size().unstack(fill_value=0).to_string())
    print(a[a.action == "relabel"].groupby(["source", "cls", "new_cls"]).size().to_string())
    clean = a[a.action != "drop"].copy()
    clean["cls"] = clean.new_cls
    clean[["path", "cls", "source", "group"]].to_csv(f"data/manifest_all_clean{suf}.csv", index=False)
    print(clean.groupby(["source", "cls"]).size().unstack(fill_value=0).to_string())


# ---------- clip_probs / best_box: CLIP + OwlViT scoring primitives used by web_photos.py ----------

_OWLVIT_CLIP_PROMPTS = {
    "rigid_plastic": ["a photo of a rigid plastic bottle", "a photo of a hard plastic container or cup", "a photo of a plastic jug or tub"],
    "soft_plastic_foam": ["a photo of a plastic bag or plastic wrapper", "a photo of crumpled plastic film", "a photo of styrofoam or foam packaging"],
    "cardboard_paper": ["a photo of a cardboard box", "a photo of crumpled paper or a paper bag", "a photo of cardboard or paper waste"],
    "metal": ["a photo of a metal soda can", "a photo of a tin can or aluminum can", "a photo of crumpled aluminum foil"],
    "glass": ["a photo of a glass bottle", "a photo of a glass jar", "a photo of broken glass"],
    "ewaste_hazard": ["a photo of a battery", "a photo of a smartphone or electronic device", "a photo of a light bulb or electronics waste"],
    "no_object": ["a photo of an empty table or floor", "a photo of a room with no trash", "a photo of a plain background"],
}
OWL_Q = {
    "rigid_plastic": ["a plastic bottle", "a plastic container", "a plastic cup"],
    "soft_plastic_foam": ["a plastic bag", "a plastic wrapper", "styrofoam", "bubble wrap"],
    "cardboard_paper": ["a cardboard box", "a piece of paper", "a paper bag", "an egg carton"],
    "metal": ["a metal can", "a tin can", "aluminum foil"],
    "glass": ["a glass bottle", "a glass jar", "broken glass"],
    "ewaste_hazard": ["a battery", "a smartphone", "a laptop", "a light bulb", "a paint can", "an aerosol can", "a charger", "a remote control"],
}
_owlvit_clip_state = None
_owlvit_detector = None


def _owlvit_clip():
    global _owlvit_clip_state
    if _owlvit_clip_state is None:
        from transformers import CLIPModel, CLIPProcessor
        m = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(_DEV).eval()
        p = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        texts = [t for c in CLASSES for t in _OWLVIT_CLIP_PROMPTS[c]]
        with torch.no_grad():
            te = m.get_text_features(**p(text=texts, return_tensors="pt", padding=True).to(_DEV))
            te = te if torch.is_tensor(te) else te.pooler_output
            te = te / te.norm(dim=-1, keepdim=True)
        _owlvit_clip_state = (m, p, te)
    return _owlvit_clip_state


@torch.no_grad()
def clip_probs(images, bs=64):
    m, p, te = _owlvit_clip()
    out = []
    for i in range(0, len(images), bs):
        px = p(images=images[i:i + bs], return_tensors="pt").to(_DEV)
        ie = m.get_image_features(**px)
        ie = ie if torch.is_tensor(ie) else ie.pooler_output
        ie = ie / ie.norm(dim=-1, keepdim=True)
        s = (100 * ie @ te.T).view(len(ie), len(CLASSES), 3).mean(2)
        out.append(s.softmax(-1).cpu().numpy())
    return np.concatenate(out)


def _owlvit():
    global _owlvit_detector
    if _owlvit_detector is None:
        from transformers import OwlViTProcessor, OwlViTForObjectDetection
        _owlvit_detector = (OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32").to(_DEV).eval(),
                             OwlViTProcessor.from_pretrained("google/owlvit-base-patch32"))
    return _owlvit_detector


@torch.no_grad()
def best_box(im, cls, thr=0.12):
    m, p = _owlvit()
    qs = OWL_Q[cls]
    inp = p(text=[qs], images=im, return_tensors="pt").to(_DEV)
    o = m(**inp)
    W, H = im.size
    s = max(W, H)
    res = p.image_processor.post_process_object_detection(o, threshold=thr, target_sizes=torch.tensor([[s, s]]).to(_DEV))[0]
    if len(res["scores"]) == 0:
        return None
    k = int(res["scores"].argmax())
    x0, y0, x1, y1 = res["boxes"][k].tolist()
    x0, x1 = max(0, x0), min(W, x1)
    y0, y1 = max(0, y0), min(H, y1)
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None
    return x0, y0, x1 - x0, y1 - y0, float(res["scores"][k])


# ---------- add-other: fold data/openimages_train/img/other crops into the no_object class ----------

_ADD_OTHER_OUT = "data/crops/oiother/no_object"


def _crop_other(path):
    outp = f"{_ADD_OTHER_OUT}/{hashlib.md5(path.encode()).hexdigest()[:16]}.jpg"
    if not os.path.exists(outp):
        try:
            im = Image.open(path).convert("RGB")
            if min(im.size) < 48:
                return None
            os.makedirs(_ADD_OTHER_OUT, exist_ok=True)
            square_crop(im, None, 256).save(outp, quality=92)
        except Exception:
            return None
    return dict(path=outp, cls="no_object", source="oiother", group=f"oiother:{os.path.basename(path)}")


def cmd_add_other():
    clean_path = "data/manifest_all_clean.csv"
    files = sorted(glob.glob("data/openimages_train/img/other/*.jpg"))
    with ProcessPoolExecutor(20) as ex:
        rows = [r for r in ex.map(_crop_other, files, chunksize=32) if r]
    base = pd.read_csv(clean_path)
    base = base[base.source != "oiother"]
    if not os.path.exists(clean_path + ".bak"):
        base.to_csv(clean_path + ".bak", index=False)
    out = pd.concat([base, pd.DataFrame(rows)], ignore_index=True)
    out.to_csv(clean_path, index=False)
    print("added", len(rows), "total", len(out))


# ---------- split: dedup + balance data/manifest_all_clean{SUF}.csv into data/manifest{SUF}.csv ----------

SPLIT_CAP = {("oi", "ewaste_hazard"): 900, ("oi", "no_object"): 1500, ("garbage12", "no_object"): 500,
             ("trashnet", "*"): 400, ("oi", "cardboard_paper"): 1200,
             ("oitrain", "ewaste_hazard"): 1200, ("oitrain", "no_object"): 2500, ("oitrain", "cardboard_paper"): 3000,
             ("coco", "ewaste_hazard"): 900, ("coco", "no_object"): 2000, ("coco", "cardboard_paper"): 2500}
SPLIT_LIMIT = {"train": 4800, "val": 300, "test_id": 300}
SPLIT_SHARE = {"scrape": 0.3, "zerowaste": 0.4}
SPLIT_BOOST = {"taco": 1, "oiother": 1}


def _phash(path):
    import imagehash
    try:
        return imagehash.phash(Image.open(path), hash_size=8).hash.flatten()
    except Exception:
        return np.zeros(64, bool)


def _fair(g, lim):
    sizes = g.source.value_counts()
    for src, share in SPLIT_SHARE.items():
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


def cmd_split():
    random.seed(0)
    np.random.seed(0)
    size = _size()
    suf = _suffix(size)
    clean_path = f"data/manifest_all_clean{suf}.csv"
    df = pd.read_csv(clean_path if os.path.exists(clean_path) else f"data/manifest_all{suf}.csv")

    parts = []
    for (src, cls), g in df.groupby(["source", "cls"]):
        cap = SPLIT_CAP.get((src, cls), SPLIT_CAP.get((src, "*"), None))
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

    with ThreadPoolExecutor(12) as ex:
        H = np.array(list(ex.map(_phash, df.path)))
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

    web = df[(df.source == "web") & (df.split == "train")]
    df = pd.concat([df, web, web], ignore_index=True)
    kept = []
    for (sp, cls), g in df.groupby(["split", "cls"]):
        lim = SPLIT_LIMIT.get(sp)
        kept.append(_fair(g, lim) if lim else g)
    df = pd.concat(kept, ignore_index=True)
    extra = [df[(df.source == s) & (df.split == "train")] for s, k in SPLIT_BOOST.items() for _ in range(k)]
    df = pd.concat([df] + extra, ignore_index=True)
    df.to_csv(f"data/manifest{suf}.csv", index=False)
    print(df.groupby(["split", "cls"]).size().unstack(fill_value=0).to_string())
    print(df[df.split == "train"].groupby(["cls", "source"]).size().unstack(fill_value=0).to_string())


# ---------- cutout: rembg background removal over data/manifest.csv -> data/manifest_cutout.csv ----------

_cutout_session = None


def _cutout_init():
    global _cutout_session
    for d in glob.glob(".venv-rembg/Lib/site-packages/nvidia/*/bin/x86_64") + glob.glob(".venv-rembg/Lib/site-packages/nvidia/*/bin"):
        os.add_dll_directory(os.path.abspath(d))
        os.environ["PATH"] = os.path.abspath(d) + os.pathsep + os.environ["PATH"]
    from rembg import new_session
    _cutout_session = new_session("u2net", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])


def _cutout_target(split, cls, path):
    return f"data/cutout/{split}/{cls}/{os.path.basename(path)}"


def _cutout_work(job):
    from rembg import remove
    split, cls, path = job
    out = _cutout_target(split, cls, path)
    if os.path.exists(out):
        return 1
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cut = remove(Image.open(path).convert("RGB"), session=_cutout_session)
        bg = Image.new("RGB", cut.size, (255, 255, 255))
        bg.paste(cut, mask=cut.split()[3])
        bg.save(out + ".tmp.jpg", quality=92)
        os.replace(out + ".tmp.jpg", out)
        return 1
    except Exception:
        return 0


def cmd_cutout():
    df = pd.read_csv("data/manifest.csv")
    df = df[df.split != "ext_test"]
    jobs = list(dict.fromkeys(zip(df.split, df.cls, df.path)))
    print("jobs", len(jobs), flush=True)
    with Pool(int(os.environ.get("DG_PROCS", 8)), initializer=_cutout_init) as pool:
        ok = []
        for i, r in enumerate(pool.imap(_cutout_work, jobs, chunksize=8)):
            ok.append(r)
            if i % 500 == 0:
                print(i, len(jobs), flush=True)
    df["path"] = [_cutout_target(s, c, p) for s, c, p in zip(df.split, df.cls, df.path)]
    df = df[[os.path.exists(p) for p in df.path]]
    df.to_csv("data/manifest_cutout.csv", index=False)
    print("done", len(df), "failed", len(ok) - sum(ok), flush=True)


COMMANDS = {
    "crops": cmd_crops,
    "clean": cmd_clean,
    "add-other": cmd_add_other,
    "split": cmd_split,
    "cutout": cmd_cutout,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: python preprocess.py <{'|'.join(COMMANDS)}>")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
