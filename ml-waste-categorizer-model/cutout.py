import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OMPI_NUM_THREADS"] = "1"
import glob
from multiprocessing import Pool
import pandas as pd
from PIL import Image

session = None


def init():
    global session
    for d in glob.glob(".venv-rembg/Lib/site-packages/nvidia/*/bin/x86_64") + glob.glob(".venv-rembg/Lib/site-packages/nvidia/*/bin"):
        os.add_dll_directory(os.path.abspath(d))
        os.environ["PATH"] = os.path.abspath(d) + os.pathsep + os.environ["PATH"]
    from rembg import new_session
    session = new_session("u2net", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])


def target(split, cls, path):
    return f"data/cutout/{split}/{cls}/{os.path.basename(path)}"


def work(job):
    from rembg import remove
    split, cls, path = job
    out = target(split, cls, path)
    if os.path.exists(out):
        return 1
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cut = remove(Image.open(path).convert("RGB"), session=session)
        bg = Image.new("RGB", cut.size, (255, 255, 255))
        bg.paste(cut, mask=cut.split()[3])
        bg.save(out + ".tmp.jpg", quality=92)
        os.replace(out + ".tmp.jpg", out)
        return 1
    except Exception:
        return 0


if __name__ == "__main__":
    df = pd.read_csv("data/manifest.csv")
    df = df[df.split != "ext_test"]
    jobs = list(dict.fromkeys(zip(df.split, df.cls, df.path)))
    print("jobs", len(jobs), flush=True)
    with Pool(int(os.environ.get("DG_PROCS", 8)), initializer=init) as pool:
        ok = []
        for i, r in enumerate(pool.imap(work, jobs, chunksize=8)):
            ok.append(r)
            if i % 500 == 0:
                print(i, len(jobs), flush=True)
    df["path"] = [target(s, c, p) for s, c, p in zip(df.split, df.cls, df.path)]
    df = df[[os.path.exists(p) for p in df.path]]
    df.to_csv("data/manifest_cutout.csv", index=False)
    print("done", len(df), "failed", len(ok) - sum(ok), flush=True)
