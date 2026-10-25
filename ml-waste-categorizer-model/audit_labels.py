import os
import numpy as np, pandas as pd, torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from transformers import CLIPModel, CLIPProcessor
from common import CLASSES

TRUSTED = {"zerowaste", "zerowaste_test"}
CURATED = {"trashnet", "realwaste", "trashbox", "garbage12", "taco", "giz"}
SUF = "" if int(os.environ.get("DG_S", 256)) == 256 else "_" + os.environ["DG_S"]
SRC = f"data/manifest_all{SUF}.csv"
CACHE = f"data/audit_clip{SUF}.csv"
RELABEL_CONF = 0.6
CURATED_RELABEL_CONF = 0.95
OBJECT_REJECT_CONF = 0.5
DROP_OWN = 0.08
CURATED_DROP_OWN = 0.03

PROMPTS = {
    "rigid_plastic": ["a photo of a plastic water bottle", "a photo of a hard plastic container", "a photo of a plastic cup", "a photo of a plastic jug or tub", "a photo of a shampoo or detergent bottle"],
    "soft_plastic_foam": ["a photo of a plastic bag", "a photo of a crumpled plastic wrapper", "a photo of plastic film or bubble wrap", "a photo of styrofoam", "a photo of an empty chip bag"],
    "cardboard_paper": ["a photo of a cardboard box", "a photo of a stack of books", "a photo of a book", "a photo of crumpled paper", "a photo of a newspaper or magazine", "a photo of a paper bag", "a photo of an egg carton", "a photo of a notebook"],
    "metal": ["a photo of an aluminum soda can", "a photo of a tin can", "a photo of a crushed beer can", "a photo of aluminum foil", "a photo of a metal food can"],
    "glass": ["a photo of a glass bottle", "a photo of a glass jar", "a photo of a wine bottle", "a photo of broken glass", "a photo of a drinking glass"],
    "ewaste_hazard": ["a photo of a battery", "a photo of a smartphone", "a photo of a laptop", "a photo of a light bulb", "a photo of electronic circuit boards", "a photo of a charger and cables", "a photo of a remote control", "a photo of an aerosol spray can or paint can"],
    "no_object": ["a photo of an empty room", "a photo of an empty table", "a photo of a street or sidewalk", "a photo of grass or plants", "a photo of a person's hand with nothing in it", "a photo of a floor or wall", "a photo of clothing or shoes"],
}
COUNTS = [len(PROMPTS[c]) for c in CLASSES]
dev = "cuda" if torch.cuda.is_available() else "cpu"
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype="float32")
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype="float32")
model = None
proc = None


def text_features():
    texts = [t for c in CLASSES for t in PROMPTS[c]]
    with torch.no_grad():
        te = model.get_text_features(**proc(text=texts, return_tensors="pt", padding=True).to(dev))
        te = te if torch.is_tensor(te) else te.pooler_output
    return te / te.norm(dim=-1, keepdim=True)


class Images(Dataset):
    def __init__(self, paths):
        self.paths = paths

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            im = Image.open(self.paths[i]).convert("RGB").resize((224, 224), Image.BILINEAR)
        except Exception:
            im = Image.new("RGB", (224, 224))
        x = (np.asarray(im, dtype="float32") / 255 - MEAN) / STD
        return torch.from_numpy(x).permute(2, 0, 1)


def score(paths, te):
    out = []
    loader = DataLoader(Images(paths), batch_size=96, num_workers=4)
    with torch.no_grad():
        for n, px in enumerate(loader):
            ie = model.get_image_features(pixel_values=px.to(dev))
            ie = ie if torch.is_tensor(ie) else ie.pooler_output
            ie = ie / ie.norm(dim=-1, keepdim=True)
            sims = 100 * ie @ te.T
            parts = torch.split(sims, COUNTS, dim=1)
            per_class = torch.stack([p.mean(1) for p in parts], dim=1)
            out.append(per_class.softmax(-1).cpu().numpy())
            if n % 20 == 0:
                print(n * 96, len(paths), flush=True)
    return np.concatenate(out)


def main():
    global model, proc
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    df = pd.read_csv(SRC)
    done = pd.read_csv(CACHE) if os.path.exists(CACHE) else pd.DataFrame(columns=["path"] + CLASSES)
    todo = df[~df.path.isin(set(done.path))]
    print("to score", len(todo), "cached", len(done), flush=True)
    if len(todo):
        probs = score(todo.path.tolist(), text_features())
        new = pd.DataFrame(probs, columns=CLASSES)
        new.insert(0, "path", todo.path.tolist())
        done = pd.concat([done, new], ignore_index=True)
        done.to_csv(CACHE, index=False)
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
    a.to_csv(f"data/audit{SUF}.csv", index=False)
    print(a.groupby(["source", "action"]).size().unstack(fill_value=0).to_string())
    print(a[a.action == "relabel"].groupby(["source", "cls", "new_cls"]).size().to_string())
    clean = a[a.action != "drop"].copy()
    clean["cls"] = clean.new_cls
    clean[["path", "cls", "source", "group"]].to_csv(f"data/manifest_all_clean{SUF}.csv", index=False)
    print(clean.groupby(["source", "cls"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
