import os, sys, json
os.environ["KERAS_BACKEND"] = "torch"
import pandas as pd, torch, keras
from dataset import CLASSES, C2I, make_loader
from model import build_model

SMOKE = "--smoke" in sys.argv
IMG = int(os.environ.get("DG_IMG", 224))
MAN = os.environ.get("DG_MANIFEST", "data/manifest.csv")
BS = int(os.environ.get("DG_BS", 64))
WORKERS = int(os.environ.get("DG_WORKERS", 8))
OUT = next((a for a in sys.argv[1:] if not a.startswith("--")), "out/run1")
os.makedirs(OUT, exist_ok=True)
torch.backends.cudnn.benchmark = True
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
keras.utils.set_random_seed(0)
keras.mixed_precision.set_global_policy("mixed_bfloat16")

df = pd.read_csv(MAN)
if SMOKE:
    df = df.groupby(["split", "cls"]).sample(frac=1, random_state=0).groupby(["split", "cls"]).head(20)


class Prog(keras.callbacks.Callback):
    def on_train_batch_end(self, batch, logs=None):
        if batch % 25 == 0:
            print("  batch", batch, {k: round(float(v), 3) for k, v in (logs or {}).items()}, flush=True)


def loader(split, aug, shuffle, cw=None):
    return make_loader(df, split, aug, shuffle, img=IMG, batch_size=BS, num_workers=WORKERS, smoke=SMOKE, cw=cw)


def main():
    counts = df[df.split == "train"].cls.value_counts()
    cw = {C2I[c]: float(len(df[df.split == "train"]) / (len(CLASSES) * counts[c])) for c in CLASSES}
    cw = {k: min(v, 3.0) for k, v in cw.items()}
    tr, va = loader("train", True, True, cw), loader("val", False, False)
    print("train", len(tr.dataset), "val", len(va.dataset), "class weights", {CLASSES[k]: round(v, 2) for k, v in cw.items()})

    model, base = build_model(IMG, weights="imagenet")
    loss = keras.losses.SparseCategoricalCrossentropy()

    E1, E2 = (1, 1) if SMOKE else (4, 14)
    base.trainable = False
    model.compile(optimizer=keras.optimizers.AdamW(1e-3, weight_decay=1e-4), loss=loss, metrics=["accuracy"])
    model.fit(tr, validation_data=va, epochs=E1, callbacks=[Prog()], verbose=2)

    base.trainable = True
    for l in base.layers[:100]:
        l.trainable = False
    for l in base.layers:
        if isinstance(l, keras.layers.BatchNormalization):
            l.trainable = False
    steps = E2 * len(tr)
    lr = keras.optimizers.schedules.CosineDecay(3e-4, steps, alpha=0.02)
    model.compile(optimizer=keras.optimizers.AdamW(lr, weight_decay=1e-4), loss=loss, metrics=["accuracy"])
    cbs = [keras.callbacks.ModelCheckpoint(f"{OUT}/best.weights.h5", save_weights_only=True, monitor="val_accuracy",
                                            mode="max", save_best_only=True),
           keras.callbacks.EarlyStopping(monitor="val_accuracy", mode="max", patience=4, restore_best_weights=True)]
    model.fit(tr, validation_data=va, epochs=E2, callbacks=cbs + [Prog()], verbose=2)
    model.save_weights(f"{OUT}/last.weights.h5")
    json.dump(CLASSES, open(f"{OUT}/labels.json", "w"))
    print("saved")


if __name__ == "__main__":
    main()
