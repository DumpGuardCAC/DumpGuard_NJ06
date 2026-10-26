import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision.transforms import v2 as T

CLASSES = ["rigid_plastic", "soft_plastic_foam", "cardboard_paper", "metal", "glass", "ewaste_hazard", "no_object"]
C2I = {c: i for i, c in enumerate(CLASSES)}


def square_crop(im, box=None, size=256, pad=1.2, min_side=96):
    W, H = im.size
    if box is None:
        side = min(W, H)
        cx, cy = W / 2, H / 2
    else:
        x, y, w, h = box
        side = min(max(max(w, h) * pad, min_side), min(W, H))
        cx, cy = x + w / 2, y + h / 2
    x0 = min(max(cx - side / 2, 0), W - side)
    y0 = min(max(cy - side / 2, 0), H - side)
    return im.crop((int(x0), int(y0), int(x0 + side), int(y0 + side))).resize((size, size), Image.BICUBIC)


def make_transforms(img):
    train_tf = T.Compose([
        T.RandomResizedCrop(img, scale=(0.45, 1.0), ratio=(0.75, 1.33), antialias=True),
        T.RandomHorizontalFlip(),
        T.RandomApply([T.RandomRotation(25)], p=0.5),
        T.ColorJitter(brightness=(0.25, 1.35), contrast=(0.6, 1.4), saturation=(0.5, 1.4), hue=0.04),
        T.RandomGrayscale(0.05),
        T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 2.0))], p=0.25),
    ])
    eval_tf = T.Compose([T.Resize((img, img), antialias=True)])
    return train_tf, eval_tf


class WasteDataset(Dataset):
    def __init__(self, d, aug, train_tf, eval_tf, cw=None):
        self.cw = cw
        self.p = d.path.tolist()
        self.y = [C2I[c] for c in d.cls]
        self.aug = aug
        self.train_tf = train_tf
        self.eval_tf = eval_tf

    def __len__(self):
        return len(self.p)

    def __getitem__(self, i):
        im = Image.open(self.p[i]).convert("RGB")
        x = torch.from_numpy(np.asarray(im)).permute(2, 0, 1)
        x = (self.train_tf if self.aug else self.eval_tf)(x)
        if self.aug and torch.rand(1) < 0.2:
            x = (x.float() + torch.randn(x.shape) * 8).clamp(0, 255).to(torch.uint8)
        w = self.cw[self.y[i]] if self.aug else 1.0
        return x.permute(1, 2, 0).contiguous(), self.y[i], torch.tensor(w, dtype=torch.float32)


def _winit(_):
    torch.set_num_threads(1)


def make_loader(df, split, aug, shuffle, img=224, batch_size=64, num_workers=8, smoke=False, cw=None):
    train_tf, eval_tf = make_transforms(img)
    d = df[df.split == split]
    ds = WasteDataset(d, aug, train_tf, eval_tf, cw)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, num_workers=0 if smoke else num_workers,
                       persistent_workers=not smoke, drop_last=aug, worker_init_fn=_winit,
                       prefetch_factor=None if smoke else 4)
