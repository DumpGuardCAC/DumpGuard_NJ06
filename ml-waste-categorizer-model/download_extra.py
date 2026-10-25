import glob, json, os, random, subprocess, sys, zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

D = "data"
random.seed(0)
os.makedirs(D, exist_ok=True)
STEPS = sys.argv[1:] or ["coco", "oitrain", "realwaste"]
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


def coco():
    out = f"{D}/coco"
    fetch_file("http://images.cocodataset.org/annotations/annotations_trainval2017.zip", f"{out}/annotations.zip")
    member = "annotations/instances_train2017.json"
    if not os.path.exists(f"{out}/{member}"):
        zipfile.ZipFile(f"{out}/annotations.zip").extract(member, out)
    data = json.load(open(f"{out}/{member}"))
    names = {c["id"]: c["name"] for c in data["categories"]}
    imgs = {i["id"]: i for i in data["images"]}
    paper_names = {"book"}
    hazard_names = {"cell phone", "laptop", "remote", "keyboard"}
    scene_names = {"chair", "couch", "potted plant", "bed", "bench", "bicycle", "car", "truck", "bus", "traffic light", "fire hydrant", "stop sign", "tree", "dining table", "oven", "sink", "refrigerator", "toilet"}
    cats = {}
    boxes = []
    for a in data["annotations"]:
        n = names[a["category_id"]]
        cats.setdefault(a["image_id"], set()).add(n)
        x, y, w, h = a["bbox"]
        if w < 90 or h < 90 or a["iscrowd"]:
            continue
        if n in paper_names:
            boxes.append((a["image_id"], "cardboard_paper", a["bbox"]))
        elif n in hazard_names:
            boxes.append((a["image_id"], "ewaste_hazard", a["bbox"]))
    random.shuffle(boxes)
    caps = {"cardboard_paper": 3000, "ewaste_hazard": 2500}
    taken = {}
    rows = []
    for image_id, cls, box in boxes:
        if taken.get(cls, 0) >= caps[cls]:
            continue
        taken[cls] = taken.get(cls, 0) + 1
        rows.append(dict(image_id=image_id, cls=cls, x=box[0], y=box[1], w=box[2], h=box[3]))
    scenes = [i for i, c in cats.items() if c <= scene_names and c]
    random.shuffle(scenes)
    for image_id in scenes[:2500]:
        rows.append(dict(image_id=image_id, cls="no_object", x=-1, y=-1, w=-1, h=-1))
    df = pd.DataFrame(rows)
    df["file"] = df.image_id.map(lambda i: f"{out}/img/{i:012d}.jpg")
    df["url"] = df.image_id.map(lambda i: imgs[i]["coco_url"])
    df.to_csv(f"{out}/selected.csv", index=False)
    print(df.cls.value_counts().to_string(), flush=True)
    fetch_all(list(set(zip(df.url, df.file))))
    print("coco done", flush=True)


def oitrain():
    out = f"{D}/openimages_train"
    fetch_file("https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions.csv", f"{out}/oidv7-class-descriptions.csv")
    fetch_file("https://storage.googleapis.com/openimages/v7/oidv7-train-annotations-human-imagelabels.csv", f"{out}/labels.csv")
    class_ids = pd.read_csv(f"{out}/oidv7-class-descriptions.csv", header=None, names=["id", "name"]).set_index("name")["id"].to_dict()

    def ids(names):
        return {class_ids[n] for n in names if n in class_ids}

    hazard = ids({"Battery", "Light bulb", "Incandescent light bulb", "Fluorescent lamp", "Compact fluorescent lamp", "Mobile phone", "Laptop", "Motherboard", "Battery charger", "Remote control", "Computer keyboard", "Printer", "Headphones", "Calculator", "Television", "Camera"})
    paper = ids({"Book", "Envelope", "Paper towel", "Newspaper", "Notebook", "Stationery"})
    ok = ids({"Table", "Countertop", "Floor", "Wall", "Desk", "Human hand", "Human face", "Person", "Tree", "Building", "Sky", "Grass", "Road", "Plant", "Furniture", "Kitchen", "Room", "Street", "Footwear", "Clothing", "Dog", "Cat", "Car", "Window", "Door", "Chair", "Couch", "Carpet"})
    bad = ids({"Bottle", "Can", "Tin can", "Box", "Cup", "Plastic bag", "Packaged goods", "Drink", "Food", "Container", "Glass", "Waste container", "Jar", "Mug", "Coffee cup", "Wine glass", "Beer", "Packaging and labeling", "Paper", "Cardboard", "Mobile phone", "Laptop", "Computer", "Television", "Battery", "Light bulb", "Tableware", "Bowl", "Plate", "Wine", "Soft drink", "Water bottle", "Cocktail", "Juice", "Milk", "Fast food", "Snack", "Candy", "Book", "Envelope", "Notebook"})
    interesting = hazard | paper | ok
    found = {}
    for chunk in pd.read_csv(f"{out}/labels.csv", usecols=["ImageID", "LabelName", "Confidence"], chunksize=2_000_000):
        chunk = chunk[(chunk.Confidence == 1) & chunk.LabelName.isin(interesting | bad)]
        for image_id, label in zip(chunk.ImageID, chunk.LabelName):
            found.setdefault(image_id, set()).add(label)
    groups = {"hazard": [], "paper": [], "background": []}
    for image_id, labels in found.items():
        if labels & paper:
            if not labels & hazard and not labels & (bad - paper):
                groups["paper"].append(image_id)
        elif labels & hazard:
            groups["hazard"].append(image_id)
        elif labels & ok and not labels & bad:
            groups["background"].append(image_id)
    caps = {"hazard": 3000, "paper": 3500, "background": 3000}
    for sub, lst in groups.items():
        print(sub, "candidates", len(lst), flush=True)
        random.shuffle(lst)
        have = len(glob.glob(f"{out}/img/{sub}/*.jpg"))
        pos = 0
        while have < caps[sub] and pos < len(lst):
            batch = lst[pos:pos + 1000]
            pos += 1000
            fetch_all([(f"http://open-images-dataset.s3.amazonaws.com/train/{i}.jpg", f"{out}/img/{sub}/{i}.jpg") for i in batch])
            have = len(glob.glob(f"{out}/img/{sub}/*.jpg"))
            print(sub, have, "of", caps[sub], flush=True)
    print("openimages train done", flush=True)


def realwaste():
    out = f"{D}/realwaste"
    fetch_file("https://archive.ics.uci.edu/static/public/908/realwaste.zip", f"{out}/realwaste.zip")
    if not os.path.exists(f"{out}/extract"):
        zipfile.ZipFile(f"{out}/realwaste.zip").extractall(f"{out}/extract")
    print("realwaste done", flush=True)


for step in STEPS:
    print("==", step, flush=True)
    {"coco": coco, "oitrain": oitrain, "realwaste": realwaste}[step]()
