import os
os.environ.setdefault("KERAS_BACKEND", "torch")
import keras
from dataset import CLASSES


def build_model(img=224, weights="imagenet"):
    base = keras.applications.MobileNetV3Large(input_shape=(img, img, 3), include_top=False, weights=weights,
                                                 include_preprocessing=True, pooling="avg", minimalistic=False)
    x = keras.layers.Dropout(0.3)(base.output)
    out = keras.layers.Dense(len(CLASSES), activation="softmax", dtype="float32", name="probs")(x)
    return keras.Model(base.input, out), base
