import glob, json, os, random, subprocess, sys, zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

D = "data"
random.seed(0)
os.makedirs(D, exist_ok=True)
UA = {"User-Agent": "DumpGuard-student-project/1.0"}


def fetch_file(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.check_call(["curl", "-sS", "-L", "--retry", "3", "-o", path + ".part", url])
    os.replace(path + ".part", path)


def fetch_image(job):
    url, path = job
    if os.path.exists(path):
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for _ in range(3):
        try:
            r = requests.get(url, timeout=30, headers=UA)
            if r.status_code == 200 and len(r.content) > 4000:
                open(path, "wb").write(r.content)
                return True
        except Exception:
            pass
    return False


def fetch_all(jobs):
    with ThreadPoolExecutor(16) as ex:
        ok = list(ex.map(fetch_image, jobs))
    print("downloaded", sum(ok), "of", len(jobs), flush=True)


