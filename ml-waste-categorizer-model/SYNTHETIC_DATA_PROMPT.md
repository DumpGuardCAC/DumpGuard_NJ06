# Cursor prompt: synthetic training images for DumpGuard

Paste everything inside the box below into Cursor, with this folder (`ml-waste-categorizer-model/`) open.

The retraining order, after Cursor has written the script, is at the bottom.

---

```
You are working in ml-waste-categorizer-model/ of the DumpGuard repo. Write ONE new script, synth_images.py, that generates at least 10,000 synthetic photos of recyclable and non-recyclable household items in ordinary settings, on my local NVIDIA GPU. I will run the commands myself, so make the script robust and resumable, and tell me the exact commands at the end.

CONTEXT
- DumpGuard classifies a phone photo into 7 classes (names must match exactly, they are in common.py as CLASSES):
  rigid_plastic, soft_plastic_foam, cardboard_paper, metal, glass, ewaste_hazard, no_object
- The real model keeps calling a stack of books "ewaste_hazard". It has never seen books. cardboard_paper must cover books, notebooks, magazines, mail, loose paper, cardboard boxes, egg cartons, paper bags. no_object must cover ordinary scenes with nothing recyclable as the subject.
- The images will be center-cropped to a square and shrunk to 256 then 224 pixels, so the subject must sit near the center and fill roughly 30 to 80 percent of the frame.
- Code style for this repo: plain, simple, human-looking Python. NO comments, no docstrings, no emojis, ASCII punctuation only (no em dashes or curly quotes). Match the style of prep.py and web_photos.py (short functions, argparse not required, env vars for knobs like PAGES / DG_S).

WHAT TO BUILD
1. Model choice
   - Use the diffusers library. Detect VRAM with torch.cuda.
   - If VRAM >= 24 GB use black-forest-labs/FLUX.1-schnell (Apache-2.0, 4 steps, guidance 0).
   - Otherwise use stabilityai/sdxl-turbo (1 to 2 steps, guidance 0.0) at 512x512.
   - Allow override with env var DG_SYNTH_MODEL. Use bfloat16 / float16, enable xformers or sdpa attention, and model_cpu_offload only if VRAM is under 12 GB.
   - Generate at 512x512, batch as large as VRAM allows (start at 8, back off on OOM automatically).

2. Prompt matrix (build it in code, do not hardcode 10,000 strings)
   - Per class, a list of 25+ concrete objects. Examples:
     rigid_plastic: water bottle, milk jug, detergent bottle, yogurt tub, takeout container, plastic cup, shampoo bottle, pill bottle, plastic tray
     soft_plastic_foam: chip bag, grocery bag, bubble wrap, cling film, styrofoam cup, foam takeout box, candy wrapper, packing peanuts, plastic pouch
     cardboard_paper: stack of books, single hardcover book, paperback pile, spiral notebook, magazine stack, newspaper, mail envelopes, printer paper, flattened cardboard box, pizza box, egg carton, paper bag, cereal box, paper cup, paper towel roll, textbooks on a desk  (books and stacks of books must be at least 30 percent of this class)
     metal: soda can, beer can, soup can, tuna can, aluminum foil ball, energy drink can, pet food can, metal lid, aerosol-free paint-free empty tin
     glass: beer bottle, wine bottle, jam jar, pickle jar, sauce bottle, drinking glass, perfume bottle, olive oil bottle
     ewaste_hazard: phone, battery pile, AA batteries, laptop, charger, power bank, light bulb, fluorescent tube, remote control, headphones, keyboard, game controller, paint can, aerosol can, car battery, hard drive
     no_object: empty kitchen counter, empty desk, living room, bedroom, hallway, sidewalk, grass, carpet, hand with nothing in it, bookshelf seen from far away with no focus, plants, dishes, shoes, clothes, a person's feet, an empty trash can, a closed laptop-free table
   - Settings (30+): kitchen counter, wooden table, living room floor, office desk, garage shelf, recycling bin, trash can, sidewalk, park grass, car seat, bathroom counter, dorm room desk, school classroom desk, picnic table, curbside pile, backyard, kitchen sink edge, balcony, stairs, shopping bag on floor
   - Lighting: daylight window, overhead warm indoor, overcast outdoor, harsh flash, dim evening, fluorescent office
   - Camera: "snapshot taken on a smartphone", "slightly blurry phone photo", "casual amateur photo", "close-up, held at arm's length", "top-down phone photo", "low angle"
   - Variations: single item, two or three items, item partly in a hand, clutter around, dirty or crumpled or wet, different colors and brands (no readable brand logos or text)
   - Compose each prompt as: "{camera} of {object(s)} {on/in} {setting}, {lighting}, realistic, natural, unedited, not studio". NEVER use words like "illustration", "render", "3d", "cartoon", "studio", "product shot", "white background" except for a small 5 percent slice with a plain background.
   - Add a negative or avoid-list in the prompt text where the model supports it (SDXL-Turbo ignores negative prompts at guidance 0, so instead make the positive prompt specific).

3. Counts
   - Target per class: 1700 images for each of the six object classes and 1500 for no_object, so a little over 11,700 total. Make the totals a table at the top of the script that I can edit. The script must stop a class once it has its target.
   - Seed deterministically from (class, index) so reruns reproduce and resume exactly.

4. Output
   - Save JPEG quality 92 to data/synthetic/<class>/<class>_<index>.jpg (512x512 is fine, prep.py will crop and resize).
   - Append one row per image to data/synthetic/meta.csv with: file, cls, prompt, seed, model.
   - Skip anything that already exists so the script resumes after a crash or Ctrl+C. Flush the csv after every batch.
   - Print progress per class every batch.

5. Quality filter (second mode of the same script: python synth_images.py --filter)
   - Use openai/clip-vit-large-patch14 through transformers.
   - For each image, zero-shot score the real class prompt against all the other class prompts (use short texts like "a photo of a stack of books", "a photo of a metal can", and so on, derived from the object list), and drop (move to data/synthetic_rejected/<class>/) any image where CLIP gives its own class less than 45 percent or where a different class wins clearly.
   - Also drop near-duplicates with imagehash.phash (hamming distance <= 4) within the same class, and anything with blur variance (cv2.Laplacian) under 15, and anything that is almost a flat color.
   - Print how many were kept and rejected per class.

6. Safety and honesty rules
   - Write a data/synthetic/README.txt at the end of generation with the model name, its license, and the date.
   - Do not generate people's faces as the subject, readable text, or brand logos. Add "no text, no logos, no faces" to the positive prompt tail.

7. Do NOT modify prep.py, make_split.py or train.py. They already read data/synthetic/<class>/*.jpg as source "synth", train only, never val or test.

DELIVERABLE
- synth_images.py, plus a requirements-synth.txt listing exactly the packages needed with minimum versions (torch, diffusers, transformers, accelerate, safetensors, sentencepiece, protobuf, pillow, imagehash, opencv-python-headless).
- At the end, print the exact commands to: install, log in to Hugging Face if the model needs it, run a 40-image smoke test (env var DG_SYNTH_SMOKE=1 which makes each class stop at 4 images), run the full generation, then run the filter.
- Estimate the time per image on my GPU after the smoke test and print the projected total.
```

---

## After Cursor writes it: run order

Run these from `ml-waste-categorizer-model/` yourself.

```bash
python download_data.py
python web_photos.py
python synth_images.py
python synth_images.py --filter
python prep.py
python make_split.py
python train.py out/run2
python evaluate.py
python export.py
```

Notes:

- `download_data.py` now also pulls up to 1500 Open Images photos of books, envelopes, paper towels, newspapers and notebooks into `data/openimages/img/paper`. It also leaves out any hazard image that contains a book, so desks with a laptop and a book are no longer labeled as electronics.
- `prep.py` picks up the Open Images paper photos and everything in `data/synthetic/<class>/`.
- `make_split.py` puts every synthetic image in train only. Validation and test stay 100 percent real photos, so the accuracy numbers you see are honest. Open Images paper is capped at 1200.
- Synthetic images should stay under about 40 percent of the training set. If `evaluate.py` shows real-photo accuracy dropping while training accuracy rises, cut the synthetic counts at the top of `synth_images.py` and run again.
- Before shipping the model, take 10 to 20 real phone photos of books, notebooks, cans and phones, and check them in the app. Synthetic data fixes gaps, but only real photos show whether the gap is closed.
