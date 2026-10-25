import glob, os, random
import pandas as pd
from download_extra_lib import fetch_all

D = "data/openimages_train"
random.seed(1)
class_ids = pd.read_csv(f"{D}/oidv7-class-descriptions.csv", header=None, names=["id", "name"]).set_index("name")["id"].to_dict()


def ids(names):
    return {class_ids[n] for n in names if n in class_ids}


other = ids({"Toy", "Doll", "Teddy bear", "Ball", "Tool", "Hammer", "Screwdriver", "Wrench", "Scissors", "Knife", "Spoon", "Fork", "Kitchen utensil",
             "Pillow", "Houseplant", "Flower", "Fruit", "Apple", "Banana", "Orange", "Vegetable", "Pen", "Pencil", "Key", "Watch", "Glasses", "Hat",
             "Shoe", "Bag", "Backpack", "Umbrella", "Clock", "Candle", "Vase", "Towel", "Brush", "Comb", "Soap", "Toothbrush", "Bicycle", "Musical instrument",
             "Guitar", "Hand", "Sports equipment", "Basketball", "Football", "Skateboard", "Helmet", "Jewelry", "Necklace", "Wallet", "Coin"})
avoid = ids({"Bottle", "Can", "Tin can", "Box", "Cup", "Plastic bag", "Packaged goods", "Drink", "Container", "Glass", "Waste container", "Jar", "Mug",
             "Coffee cup", "Wine glass", "Beer", "Packaging and labeling", "Paper", "Cardboard", "Mobile phone", "Laptop", "Computer", "Television", "Battery",
             "Light bulb", "Book", "Envelope", "Notebook", "Printer", "Camera", "Remote control", "Computer keyboard", "Headphones", "Calculator", "Motherboard",
             "Battery charger", "Fluorescent lamp", "Compact fluorescent lamp", "Incandescent light bulb", "Newspaper", "Paper towel", "Stationery", "Tableware",
             "Bowl", "Plate", "Food", "Fast food", "Snack", "Candy", "Wine", "Milk", "Juice", "Water bottle", "Soft drink", "Cocktail"})
found = {}
for chunk in pd.read_csv(f"{D}/labels.csv", usecols=["ImageID", "LabelName", "Confidence"], chunksize=2_000_000):
    chunk = chunk[(chunk.Confidence == 1) & chunk.LabelName.isin(other | avoid)]
    for image_id, label in zip(chunk.ImageID, chunk.LabelName):
        found.setdefault(image_id, set()).add(label)
pool = [i for i, labels in found.items() if labels & other and not labels & avoid]
print("candidates", len(pool), flush=True)
random.shuffle(pool)
cap = 4000
have = len(glob.glob(f"{D}/img/other/*.jpg"))
pos = 0
while have < cap and pos < len(pool):
    batch = pool[pos:pos + 1000]
    pos += 1000
    fetch_all([(f"http://open-images-dataset.s3.amazonaws.com/train/{i}.jpg", f"{D}/img/other/{i}.jpg") for i in batch])
    have = len(glob.glob(f"{D}/img/other/*.jpg"))
    print("other", have, "of", cap, flush=True)
print("done", flush=True)
