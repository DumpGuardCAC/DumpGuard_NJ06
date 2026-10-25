import os, sys, time, csv, hashlib, shutil, threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

UA = "DumpGuard-student-project/1.0"
HDR = {"User-Agent": UA}
O = "data/scraped"
REJ = "data/scraped_rejected"
META = O + "/meta.csv"
META_COLS = "file,cls,query,source,page,title,creator,license,license_version,landing,url\n"
MAX_PAGES = 12
N_THREADS = 10
TIMEOUT = 25
MIN_BYTES = 8000
MIN_SIDE = 200
BAD_EXT = (".gif", ".svg", ".tif", ".tiff", ".webp.gif")

TARGETS = {
    "rigid_plastic": 1800,
    "soft_plastic_foam": 1800,
    "cardboard_paper": 1800,
    "metal": 1800,
    "glass": 1800,
    "ewaste_hazard": 1800,
    "no_object": 1500,
}
if os.environ.get("DG_SCRAPE_SMOKE") == "1":
    TARGETS = {c: 5 for c in TARGETS}

OBJECTS = {
    "rigid_plastic": [
        "plastic water bottle", "milk jug", "detergent bottle", "yogurt tub",
        "takeout container", "plastic cup", "shampoo bottle", "pill bottle",
        "plastic soda bottle", "laundry detergent jug", "plastic food container",
        "empty plastic bottle", "plastic bottle recycling", "bleach bottle",
        "mouthwash bottle", "plastic peanut butter jar", "ketchup plastic bottle",
        "plastic produce container", "clamshell plastic container", "plastic lid",
        "rigid plastic packaging", "plastic soap dispenser", "hand sanitizer bottle",
        "plastic spice jar", "plastic juice bottle", "plastic water jug",
    ],
    "soft_plastic_foam": [
        "chip bag", "plastic grocery bag", "bubble wrap", "cling film",
        "styrofoam cup", "foam takeout box", "candy wrapper", "packing peanuts",
        "plastic shopping bag", "ziplock bag", "snack wrapper", "bread bag",
        "plastic film wrap", "styrofoam packaging", "foam egg carton",
        "crumpled plastic bag", "plastic produce bag", "food wrapper plastic",
        "shipping bubble mailer", "plastic trash bag", "foam meat tray",
        "styrofoam peanuts", "plastic net bag", "shrink wrap plastic",
        "soft plastic packaging", "plastic sleeve wrapping",
    ],
    "cardboard_paper": [
        "stack of books", "pile of textbooks", "hardcover book", "paperback books on a table",
        "spiral notebook", "magazine stack", "newspaper", "mail envelopes",
        "printer paper stack", "flattened cardboard box", "pizza box", "egg carton",
        "paper bag", "cereal box", "paper cup", "paper towel roll", "books on a desk",
        "notebook open on table", "paperback novel", "cardboard shipping box",
        "junk mail pile", "paper shopping bag", "corrugated cardboard",
        "tissue box", "cardboard egg carton", "loose paper sheets",
        "magazine on table", "books on a shelf", "paper napkin stack",
    ],
    "metal": [
        "soda can", "beer can", "soup can", "tuna can", "aluminum foil ball",
        "energy drink can", "crushed can", "tin can", "aluminum can recycling",
        "empty soda can", "cat food can", "metal food can", "crushed beer can",
        "aluminum can litter", "steel can", "beverage can", "foil food tray",
        "crumpled aluminum foil", "paint tin empty", "metal bottle cap",
        "soda cans in bin", "coffee can metal", "tomato can", "bean can",
        "aluminum drink can", "metal can on table",
    ],
    "glass": [
        "beer bottle", "wine bottle", "jam jar", "pickle jar", "sauce bottle",
        "drinking glass", "glass bottles recycling", "empty glass bottle",
        "mason jar", "olive oil bottle", "glass jar kitchen", "soda glass bottle",
        "brown glass bottle", "green glass bottle", "clear glass bottle",
        "glass jar with lid", "vinegar bottle glass", "perfume bottle glass",
        "broken glass bottle", "glass milk bottle", "syrup glass bottle",
        "glass bottles in bin", "empty wine bottle", "glass food jar",
        "beer bottles empty", "glass recycling bin bottles",
    ],
    "ewaste_hazard": [
        "old smartphone", "used batteries", "AA batteries", "old laptop",
        "phone charger", "power bank", "light bulb", "fluorescent tube",
        "remote control", "headphones", "game controller", "paint can",
        "aerosol can", "car battery", "broken cell phone", "USB cable tangle",
        "old computer keyboard", "computer mouse old", "button cell battery",
        "compact fluorescent bulb", "LED light bulb", "phone charging cable",
        "electronic waste pile", "old tablet computer", "spray paint can",
        "9 volt battery", "earphones tangled", "hard drive old",
    ],
    "no_object": [
        "empty kitchen counter", "empty desk", "living room interior", "bedroom",
        "hallway", "sidewalk", "grass lawn", "carpet floor", "hand open palm",
        "houseplant", "empty trash can", "shoes on floor", "clothes on bed",
        "wooden table empty", "bathroom counter empty", "office desk empty",
        "kitchen floor", "garage interior", "empty shelf", "sofa living room",
        "window view room", "backyard patio empty", "stairs hallway",
        "tile floor empty", "park bench empty", "empty dining table",
        "feet on carpet", "open palm hand close up",
    ],
}

SETTINGS = [
    "on a table", "on a kitchen counter", "in a recycling bin", "in a trash can",
    "on the floor", "on a desk", "on the sidewalk", "in a backyard",
    "in a garage", "litter on grass", "in a hand",
]

CLIP_CLASS_TEXTS = {
    "rigid_plastic": [
        "a photo of a plastic bottle",
        "a photo of a plastic jug or tub",
        "a photo of a hard plastic container",
    ],
    "soft_plastic_foam": [
        "a photo of a plastic bag",
        "a photo of a chip bag or wrapper",
        "a photo of styrofoam or bubble wrap",
    ],
    "cardboard_paper": [
        "a photo of a stack of books",
        "a photo of a cardboard box",
        "a photo of paper or a notebook",
    ],
    "metal": [
        "a photo of a metal can",
        "a photo of an aluminum soda can",
        "a photo of a tin can",
    ],
    "glass": [
        "a photo of a glass bottle",
        "a photo of a glass jar",
        "a photo of glass bottles",
    ],
    "ewaste_hazard": [
        "a photo of a smartphone or electronics",
        "a photo of batteries",
        "a photo of a light bulb or charger",
    ],
    "no_object": [
        "a photo of an empty room",
        "a photo of an empty table or floor",
        "a photo of a hand or ordinary scene with no trash",
    ],
}

CLASSES = list(TARGETS.keys())
_wm_lock = threading.Lock()
_wm_last = [0.0]
_ov_token = [None]
_ov_backoff = [60]


def build_queries(cls):
    terms = OBJECTS[cls]
    out = list(terms)
    half = terms[::2]
    for t in half:
        for s in SETTINGS:
            out.append(t + " " + s)
    return out


def class_counts():
    c = {k: 0 for k in TARGETS}
    for cls in TARGETS:
        d = os.path.join(O, cls)
        if os.path.isdir(d):
            c[cls] = sum(1 for f in os.listdir(d) if f.lower().endswith(".jpg"))
    return c


def load_done():
    done = set()
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done.add((r["cls"], r["query"], r["source"], str(r["page"])))
    else:
        os.makedirs(O, exist_ok=True)
        open(META, "w", encoding="utf-8").write(META_COLS)
    return done


def path_for(cls, url):
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:14]
    return os.path.join(O, cls, h + ".jpg")


def bad_url(url):
    u = url.lower().split("?")[0]
    return any(u.endswith(e) for e in BAD_EXT)


def save_jpeg(raw, dest):
    tmp = dest + ".part"
    try:
        open(tmp, "wb").write(raw)
        im = ImageOps.exif_transpose(Image.open(tmp)).convert("RGB")
        if min(im.size) < MIN_SIDE:
            os.remove(tmp)
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "JPEG", quality=92)
        if os.path.exists(tmp):
            os.remove(tmp)
        return True
    except Exception:
        for p in (tmp, dest):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        return False


def fetch_bytes(url):
    if bad_url(url):
        return None
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=HDR)
            if r.status_code == 200 and len(r.content) >= MIN_BYTES:
                return r.content
            last = r.status_code
        except Exception as e:
            last = e
        time.sleep(0.5 * (attempt + 1))
    return None


def download_one(item):
    cls, url = item["cls"], item["url"]
    dest = path_for(cls, url)
    if os.path.exists(dest):
        return dest, True
    raw = fetch_bytes(url)
    if raw is None:
        return dest, False
    ok = save_jpeg(raw, dest)
    return dest, ok


def openverse_token():
    if _ov_token[0] is not None:
        return _ov_token[0]
    cid = os.environ.get("OPENVERSE_CLIENT_ID")
    sec = os.environ.get("OPENVERSE_CLIENT_SECRET")
    if not cid or not sec:
        _ov_token[0] = ""
        return ""
    try:
        r = requests.post(
            "https://api.openverse.org/v1/auth_tokens/token/",
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec},
            headers={"Content-Type": "application/x-www-form-urlencoded", **HDR},
            timeout=30,
        )
        if r.status_code == 200:
            _ov_token[0] = r.json().get("access_token", "")
            print("openverse auth ok, page_size=100", flush=True)
            return _ov_token[0]
    except Exception as e:
        print("openverse auth fail", e, flush=True)
    _ov_token[0] = ""
    return ""


def openverse_page(q, page):
    tok = openverse_token()
    ps = 100 if tok else 20
    headers = dict(HDR)
    if tok:
        headers["Authorization"] = "Bearer " + tok
    backoff = _ov_backoff[0]
    while True:
        try:
            r = requests.get(
                "https://api.openverse.org/v1/images/",
                params=dict(q=q, page_size=ps, page=page, license_type="all-cc", mature="false"),
                headers=headers,
                timeout=30,
            )
        except Exception as e:
            print("openverse err", e, flush=True)
            time.sleep(5)
            return []
        if r.status_code == 429:
            print("openverse 429 sleep", backoff, flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)
            _ov_backoff[0] = backoff
            continue
        _ov_backoff[0] = 60
        if r.status_code != 200:
            print("openverse", r.status_code, q, page, flush=True)
            return []
        break
    out = []
    for x in r.json().get("results", []):
        url = x.get("url") or x.get("thumbnail")
        if not url:
            continue
        out.append({
            "url": url,
            "title": x.get("title") or "",
            "creator": x.get("creator") or "",
            "license": x.get("license") or "",
            "license_version": x.get("license_version") or "",
            "landing": x.get("foreign_landing_url") or "",
        })
    return out


def wm_throttle():
    with _wm_lock:
        now = time.time()
        wait = 0.21 - (now - _wm_last[0])
        if wait > 0:
            time.sleep(wait)
        _wm_last[0] = time.time()


def license_ok(text):
    t = (text or "").lower()
    keys = (
        "creative commons", "cc0", "cc-by", "cc by", "cc-sa", "cc sa",
        "public domain", "pdm", "pd-", "pd/", "wtfpl", "gpl",
    )
    return any(k in t for k in keys)


def wikimedia_page(q, page):
    wm_throttle()
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": q,
        "gsrnamespace": 6,
        "gsrlimit": 20,
        "gsroffset": (page - 1) * 20,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": 640,
        "format": "json",
    }
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=HDR, timeout=30)
    except Exception as e:
        print("wikimedia err", e, flush=True)
        return []
    if r.status_code == 429:
        print("wikimedia 429 sleep 60", flush=True)
        time.sleep(60)
        return wikimedia_page(q, page)
    if r.status_code != 200:
        print("wikimedia", r.status_code, q, page, flush=True)
        return []
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        infos = p.get("imageinfo") or []
        if not infos:
            continue
        ii = infos[0]
        mime = (ii.get("mime") or "").lower()
        if mime and not mime.startswith("image/"):
            continue
        if "gif" in mime or "svg" in mime or "tiff" in mime:
            continue
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("License", {}) or {}).get("value", "")
        lic_short = (meta.get("LicenseShortName", {}) or {}).get("value", "")
        if not license_ok(lic + " " + lic_short):
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            continue
        artist = (meta.get("Artist", {}) or {}).get("value", "")
        if "<" in artist:
            artist = artist.split(">")[-1].split("<")[0].strip() or artist
        out.append({
            "url": url,
            "title": p.get("title") or "",
            "creator": artist,
            "license": lic_short or lic,
            "license_version": "",
            "landing": ii.get("descriptionurl") or ("https://commons.wikimedia.org/wiki/" + quote(p.get("title") or "")),
        })
    return out


def pixabay_page(q, page):
    key = os.environ.get("PIXABAY_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params=dict(key=key, q=q, image_type="photo", safesearch="true", page=page, per_page=20),
            headers=HDR,
            timeout=30,
        )
    except Exception as e:
        print("pixabay err", e, flush=True)
        return []
    if r.status_code == 429:
        print("pixabay 429 sleep 60", flush=True)
        time.sleep(60)
        return pixabay_page(q, page)
    if r.status_code != 200:
        print("pixabay", r.status_code, q, page, flush=True)
        return []
    out = []
    for x in r.json().get("hits", []):
        url = x.get("webformatURL") or x.get("previewURL")
        if not url:
            continue
        out.append({
            "url": url,
            "title": x.get("tags") or "",
            "creator": x.get("user") or "",
            "license": "Pixabay Content License",
            "license_version": "",
            "landing": x.get("pageURL") or "",
        })
    return out


def pexels_page(q, page):
    key = os.environ.get("PEXELS_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params=dict(query=q, page=page, per_page=20),
            headers={**HDR, "Authorization": key},
            timeout=30,
        )
    except Exception as e:
        print("pexels err", e, flush=True)
        return []
    if r.status_code == 429:
        print("pexels 429 sleep 60", flush=True)
        time.sleep(60)
        return pexels_page(q, page)
    if r.status_code != 200:
        print("pexels", r.status_code, q, page, flush=True)
        return []
    out = []
    for x in r.json().get("photos", []):
        src = x.get("src") or {}
        url = src.get("large") or src.get("medium") or src.get("original")
        if not url:
            continue
        out.append({
            "url": url,
            "title": x.get("alt") or "",
            "creator": x.get("photographer") or "",
            "license": "Pexels License",
            "license_version": "",
            "landing": x.get("url") or "",
        })
    return out


SOURCES = [
    ("openverse", openverse_page),
    ("wikimedia", wikimedia_page),
    ("pixabay", pixabay_page),
    ("pexels", pexels_page),
]


def append_meta(rows):
    with open(META, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)
        f.flush()
        os.fsync(f.fileno())


def write_attribution():
    rows = list(csv.DictReader(open(META, encoding="utf-8")))
    by_src = defaultdict(Counter)
    for r in rows:
        by_src[r["source"]][r["license"] or "unknown"] += 1
    lines = [
        "# Attribution",
        "",
        "Scraped images for DumpGuard. Full per-image creator and landing page are in `meta.csv`.",
        "",
        "If you publish this dataset, CC-BY (and similar) images need credit to the creator and a link to the license/landing page.",
        "",
    ]
    for src in sorted(by_src):
        lines.append("## " + src)
        lines.append("")
        for lic, n in by_src[src].most_common():
            lines.append("- %s: %d" % (lic, n))
        lines.append("")
    lines.append("See `meta.csv` columns: creator, license, license_version, landing, url.")
    lines.append("")
    open(os.path.join(O, "ATTRIBUTION.md"), "w", encoding="utf-8").write("\n".join(lines))


def print_counts(counts, label="progress"):
    print("---", label, "---", flush=True)
    total = 0
    for c in CLASSES:
        n = counts.get(c, 0)
        total += n
        print("%-22s %5d / %5d" % (c, n, TARGETS[c]), flush=True)
    print("%-22s %5d" % ("TOTAL", total), flush=True)


def process_page(cls, q, src_name, src_fn, page, counts, done):
    key = (cls, q, src_name, str(page))
    if key in done:
        return 0
    items = src_fn(q, page)
    if items is None:
        return -1
    done.add(key)
    rows = []
    kept = 0
    if items:
        need = TARGETS[cls] - counts[cls]
        jobs = []
        for it in items:
            if len(jobs) >= need:
                break
            dest = path_for(cls, it["url"])
            if os.path.exists(dest):
                continue
            jobs.append({**it, "cls": cls, "query": q, "source": src_name, "page": page})
        if jobs:
            with ThreadPoolExecutor(N_THREADS) as ex:
                results = list(ex.map(download_one, jobs))
            for job, (dest, ok) in zip(jobs, results):
                if not ok:
                    continue
                kept += 1
                counts[cls] += 1
                rows.append([
                    dest.replace("\\", "/"), cls, job["query"], job["source"], job["page"],
                    job.get("title", ""), job.get("creator", ""), job.get("license", ""),
                    job.get("license_version", ""), job.get("landing", ""), job["url"],
                ])
                if counts[cls] >= TARGETS[cls]:
                    break
    if not rows:
        rows = [["", cls, q, src_name, page, "", "", "", "", "", ""]]
    append_meta(rows)
    print(cls, src_name, "p" + str(page), q[:50], "kept", kept, "now", counts[cls], "/", TARGETS[cls], flush=True)
    if src_name == "openverse":
        time.sleep(1.0)
    elif src_name in ("pixabay", "pexels"):
        time.sleep(0.4)
    return kept


def run_download():
    t0 = time.time()
    done = load_done()
    counts = class_counts()
    print_counts(counts, "start")
    queries = {c: build_queries(c) for c in CLASSES}
    work = {c: [] for c in CLASSES}
    for c in CLASSES:
        qs = queries[c]
        for page in range(1, MAX_PAGES + 1):
            for src_name, src_fn in SOURCES:
                for q in qs:
                    work[c].append((q, src_name, src_fn, page))

    active = [c for c in CLASSES if counts[c] < TARGETS[c]]
    ptr = {c: 0 for c in CLASSES}
    idle_rounds = 0
    while active:
        progressed = False
        for cls in list(active):
            if counts[cls] >= TARGETS[cls]:
                active.remove(cls)
                continue
            jobs = work[cls]
            advanced = False
            while ptr[cls] < len(jobs):
                q, src_name, src_fn, page = jobs[ptr[cls]]
                ptr[cls] += 1
                key = (cls, q, src_name, str(page))
                if key in done:
                    continue
                n = process_page(cls, q, src_name, src_fn, page, counts, done)
                if n < 0:
                    continue
                advanced = True
                progressed = True
                break
            if counts[cls] >= TARGETS[cls]:
                if cls in active:
                    active.remove(cls)
            elif not advanced and ptr[cls] >= len(jobs):
                print(cls, "queries exhausted at", counts[cls], flush=True)
                if cls in active:
                    active.remove(cls)
        if not progressed:
            idle_rounds += 1
            if idle_rounds >= 2:
                print("no progress on remaining classes, stopping", flush=True)
                break
        else:
            idle_rounds = 0

    write_attribution()
    counts = class_counts()
    print_counts(counts, "final")
    elapsed = time.time() - t0
    total = sum(counts.values())
    smoke = os.environ.get("DG_SCRAPE_SMOKE") == "1"
    full_goal = 1800 * 6 + 1500
    print("", flush=True)
    print("elapsed_sec", round(elapsed, 1), "images", total, flush=True)
    if smoke and total > 0 and elapsed > 0:
        est = elapsed / total * full_goal
        print("smoke estimate for full ~%d images: %.1f hours (%.0f min)" % (full_goal, est / 3600, est / 60), flush=True)
    elif total > 0 and elapsed > 0 and total < full_goal:
        est = elapsed / max(total, 1) * (full_goal - total)
        print("estimate remaining to ~%d: %.1f hours" % (full_goal, est / 3600), flush=True)
    print_run_help(elapsed, total, smoke)


def print_run_help(elapsed=None, total=None, smoke=False):
    print("", flush=True)
    print("Commands (from ml-waste-categorizer-model/):", flush=True)
    print("  pip install -r requirements-scrape.txt", flush=True)
    print("  $env:DG_SCRAPE_SMOKE=1; python scrape_images.py", flush=True)
    print("  python scrape_images.py", flush=True)
    print("  python scrape_images.py --filter", flush=True)
    print("Optional env: OPENVERSE_CLIENT_ID, OPENVERSE_CLIENT_SECRET, PIXABAY_KEY, PEXELS_KEY", flush=True)
    if smoke and elapsed and total:
        full_goal = 1800 * 6 + 1500
        est = elapsed / max(total, 1) * full_goal
        print("Based on this smoke run, full download ~%.1f hours." % (est / 3600), flush=True)


def move_to(src, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.abspath(src) == os.path.abspath(dest):
        return dest
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(src, dest)
    return dest


def laplacian_var(path):
    import cv2
    import numpy as np
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return 0.0
    return float(cv2.Laplacian(im, cv2.CV_64F).var())


def is_flat(path):
    import numpy as np
    im = Image.open(path).convert("RGB").resize((64, 64))
    arr = np.asarray(im, dtype=np.float32)
    return float(arr.std()) < 8.0


def run_filter():
    import numpy as np
    import torch
    import imagehash
    from transformers import CLIPModel, CLIPProcessor
    from tqdm import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("filter device", device, flush=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(device).eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")

    class_prompts = []
    class_owners = []
    for c in CLASSES:
        for t in CLIP_CLASS_TEXTS[c]:
            class_prompts.append(t)
            class_owners.append(c)
    extra = [
        "a screenshot of text",
        "a diagram",
        "a portrait of a person",
        "a photo of a hand",
        "a photo of feet",
    ]
    all_texts = class_prompts + extra
    with torch.no_grad():
        te = model.get_text_features(**proc(text=all_texts, return_tensors="pt", padding=True).to(device))
        te = te / te.norm(dim=-1, keepdim=True)

    n_class_txt = len(class_prompts)
    idx_shot, idx_diag, idx_port, idx_hand, idx_feet = range(n_class_txt, n_class_txt + 5)

    files = []
    for cls in CLASSES:
        d = os.path.join(O, cls)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".jpg"):
                files.append((cls, os.path.join(d, f)))

    kept = Counter()
    rejected = Counter()
    hashes = []

    @torch.no_grad()
    def score_image(path):
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        px = proc(images=im, return_tensors="pt").to(device)
        ie = model.get_image_features(**px)
        ie = ie / ie.norm(dim=-1, keepdim=True)
        logits = (100.0 * ie @ te.T)[0].cpu().numpy()
        return logits

    for cls, path in tqdm(files, desc="filter"):
        try:
            logits = score_image(path)
        except Exception:
            move_to(path, os.path.join(REJ, cls))
            rejected[cls] += 1
            continue

        class_logits = []
        for c in CLASSES:
            idxs = [i for i, o in enumerate(class_owners) if o == c]
            class_logits.append(float(max(logits[i] for i in idxs)))
        class_logits = np.asarray(class_logits, dtype=np.float64)
        class_logits = class_logits - class_logits.max()
        probs = np.exp(class_logits)
        probs = probs / probs.sum()
        own = float(probs[CLASSES.index(cls)])
        best_i = int(probs.argmax())
        if CLASSES[best_i] != cls or own < 0.40:
            move_to(path, os.path.join(REJ, cls))
            rejected[cls] += 1
            continue

        own_logit = float(max(logits[i] for i, o in enumerate(class_owners) if o == cls))
        shot, diag, port = float(logits[idx_shot]), float(logits[idx_diag]), float(logits[idx_port])
        hand, feet = float(logits[idx_hand]), float(logits[idx_feet])
        if max(shot, diag) >= own_logit and max(shot, diag) >= port:
            move_to(path, os.path.join(REJ, cls))
            rejected[cls] += 1
            continue
        if port >= own_logit and port >= max(shot, diag):
            if cls == "no_object" and max(hand, feet) >= port:
                pass
            else:
                move_to(path, os.path.join(REJ, cls))
                rejected[cls] += 1
                continue

        try:
            if laplacian_var(path) < 15:
                move_to(path, os.path.join(REJ, cls))
                rejected[cls] += 1
                continue
            if is_flat(path):
                move_to(path, os.path.join(REJ, cls))
                rejected[cls] += 1
                continue
        except Exception:
            move_to(path, os.path.join(REJ, cls))
            rejected[cls] += 1
            continue

        try:
            ph = imagehash.phash(Image.open(path))
        except Exception:
            move_to(path, os.path.join(REJ, cls))
            rejected[cls] += 1
            continue

        dup = False
        for prev_cls, prev_path, prev_h in hashes:
            if ph - prev_h <= 4:
                move_to(path, os.path.join(REJ, "dupes"))
                rejected["dupes"] += 1
                dup = True
                break
        if dup:
            continue
        hashes.append((cls, path, ph))
        kept[cls] += 1

    print("--- filter kept ---", flush=True)
    for c in CLASSES:
        print("%-22s kept %5d  rejected %5d" % (c, kept[c], rejected[c]), flush=True)
    print("%-22s rejected %5d" % ("dupes", rejected["dupes"]), flush=True)
    print("%-22s %5d" % ("KEPT TOTAL", sum(kept.values())), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--filter":
        run_filter()
    else:
        run_download()
