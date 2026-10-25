import glob, os, hashlib
import pandas as pd
from PIL import Image
from concurrent.futures import ProcessPoolExecutor
from common import square_crop

OUT = "data/crops/oiother/no_object"
CLEAN = "data/manifest_all_clean.csv"


def crop(path):
    outp = f"{OUT}/{hashlib.md5(path.encode()).hexdigest()[:16]}.jpg"
    if not os.path.exists(outp):
        try:
            im = Image.open(path).convert("RGB")
            if min(im.size) < 48:
                return None
            os.makedirs(OUT, exist_ok=True)
            square_crop(im, None, 256).save(outp, quality=92)
        except Exception:
            return None
    return dict(path=outp, cls="no_object", source="oiother", group=f"oiother:{os.path.basename(path)}")


if __name__ == "__main__":
    files = sorted(glob.glob("data/openimages_train/img/other/*.jpg"))
    with ProcessPoolExecutor(20) as ex:
        rows = [r for r in ex.map(crop, files, chunksize=32) if r]
    base = pd.read_csv(CLEAN)
    base = base[base.source != "oiother"]
    if not os.path.exists(CLEAN + ".bak"):
        base.to_csv(CLEAN + ".bak", index=False)
    out = pd.concat([base, pd.DataFrame(rows)], ignore_index=True)
    out.to_csv(CLEAN, index=False)
    print("added", len(rows), "total", len(out))
