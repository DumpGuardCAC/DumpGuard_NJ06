# Cursor prompt: download 10k+ real web photos for DumpGuard

Paste everything inside the box into Cursor, with this folder (`ml-waste-categorizer-model/`) open.

The run order after Cursor writes the script is at the bottom.

---

```
You are working in ml-waste-categorizer-model/ of the DumpGuard repo. Write ONE new script, scrape_images.py, that downloads at least 10,000 REAL photos from legitimate, licensed web sources of recyclable and non-recyclable household items in normal everyday settings. I will run the commands myself, so make it robust, polite to the servers, and resumable.

CONTEXT
- DumpGuard classifies a phone photo into 7 classes (exact names, also in common.py as CLASSES):
  rigid_plastic, soft_plastic_foam, cardboard_paper, metal, glass, ewaste_hazard, no_object
- The current model calls a stack of books "ewaste_hazard" because it never saw books. cardboard_paper must include books, notebooks, magazines, mail, loose paper, cardboard boxes, egg cartons and paper bags. no_object is ordinary scenes with no recyclable as the subject.
- Images are later center-cropped to a square, so the subject should be near the middle.
- Code style for this repo: plain, simple, human-looking Python. NO comments, no docstrings, no emojis, ASCII punctuation only. Look at web_photos.py in this folder first: it already pulls from the Openverse API with a query list. Reuse its approach (requests, ThreadPoolExecutor, resumable meta.csv, polite User-Agent "DumpGuard-student-project/1.0") instead of inventing a new style.

SOURCES (only these, do NOT scrape Google Images, Bing, Pinterest, Instagram or anything that forbids scraping in its terms)
1. Openverse API (https://api.openverse.org/v1/images/), no key needed. Use license_type=all-cc, mature=false, page_size=20, and page through up to 12 pages per query. Respect HTTP 429 with a 60 second sleep and exponential backoff. If I set OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET in the environment, get a token and use page_size=100 instead.
2. Wikimedia Commons API (https://commons.wikimedia.org/w/api.php), using generator=search with srnamespace=6, prop=imageinfo with iiprop=url|size|extmetadata and iiurlwidth=640. Keep only files whose extmetadata License is a Creative Commons or public domain license. Keep the Artist and LicenseShortName fields. Send the User-Agent above and no more than 5 requests per second.
3. Open Images V7 (already used by download_data.py): add nothing here, skip it.
4. Optional, only if the matching env var is set: Pixabay (PIXABAY_KEY) and Pexels (PEXELS_KEY) APIs, using their documented search endpoints and their image URLs only. Never hardcode a key. If the variable is not set, silently skip that source.

QUERY MATRIX (build it in code)
- Per class, 25+ object terms, for example:
  cardboard_paper: stack of books, pile of textbooks, hardcover book, paperback books on a table, spiral notebook, magazine stack, newspaper, mail envelopes, printer paper stack, flattened cardboard box, pizza box, egg carton, paper bag, cereal box, paper cup, paper towel roll, books on a desk
  rigid_plastic: plastic water bottle, milk jug, detergent bottle, yogurt tub, takeout container, plastic cup, shampoo bottle, pill bottle
  soft_plastic_foam: chip bag, plastic grocery bag, bubble wrap, cling film, styrofoam cup, foam takeout box, candy wrapper, packing peanuts
  metal: soda can, beer can, soup can, tuna can, aluminum foil ball, energy drink can, crushed can
  glass: beer bottle, wine bottle, jam jar, pickle jar, sauce bottle, drinking glass, glass bottles recycling
  ewaste_hazard: old smartphone, used batteries, AA batteries, old laptop, phone charger, power bank, light bulb, fluorescent tube, remote control, headphones, game controller, paint can, aerosol can, car battery
  no_object: empty kitchen counter, empty desk, living room interior, bedroom, hallway, sidewalk, grass lawn, carpet floor, hand open palm, houseplant, empty trash can, shoes on floor, clothes on bed
- Settings to append to roughly half of the object queries: on a table, on a kitchen counter, in a recycling bin, in a trash can, on the floor, on a desk, on the sidewalk, in a backyard, in a garage, litter on grass, in a hand.
- Also run every plain object term with no setting.
- Do not add words like studio, isolated, white background or product shot. I want normal-setting photos.

TARGETS
- Per class: aim for 1800 kept images for each of the six object classes and 1500 for no_object (about 12,300 total). Put these in a table at the top of the script. Stop a class when it reaches its target and rotate through the queries evenly so one query does not dominate.
- Print per-class progress and a final count table.

DOWNLOAD RULES
- Download the 640 px or smaller version when the API offers one (thumbnail or iiurlwidth), not the full-size original.
- Skip files under 8 KB, images where the shorter side is under 200 px, and animated or non-photo formats (gif, svg, tiff).
- Open each file with PIL, apply ImageOps.exif_transpose, convert to RGB, and save as JPEG quality 92 to data/scraped/<class>/<md5 of url first 14 chars>.jpg. Delete anything that fails to open.
- Use 10 download threads. Timeout 25 s. Retry twice.
- Resumable: keep data/scraped/meta.csv with columns file,cls,query,source,page,title,creator,license,license_version,landing,url. Skip any (cls, query, source, page) already recorded and any file that already exists. Flush the csv after every page.

QUALITY FILTER (second mode: python scrape_images.py --filter)
- Load openai/clip-vit-large-patch14 with transformers on the GPU.
- For each image, compute CLIP zero-shot scores of its own class text versus the other six classes (use short texts like "a photo of a stack of books", "a photo of a metal can", "a photo of an empty room", built from the object list). Move images where the own class is not the top scorer, or its score is under 0.40, to data/scraped_rejected/<class>/ instead of deleting them.
- Remove near-duplicates inside and across classes with imagehash.phash (hamming distance <= 4): keep one copy, move the others to data/scraped_rejected/dupes/.
- Move to rejected: images with Laplacian blur variance under 15, nearly flat-color images, and images that are mostly text (CLIP text "a screenshot of text" or "a diagram" scoring highest).
- Also move any image where CLIP thinks the main subject is a person's face ("a portrait of a person" is top) unless the class is no_object and the person is a hand or feet.
- Print kept and rejected counts per class.

ATTRIBUTION
- At the end of a download run, write data/scraped/ATTRIBUTION.md listing each source, its license mix (count per license), and a pointer to meta.csv which holds the creator and landing page for every image. Remind me that CC-BY images need credit if I publish the dataset.

DO NOT modify prep.py, make_split.py or train.py. They already read data/scraped/<class>/*.jpg as source "scrape", training set only, never validation or test.

DELIVERABLE
- scrape_images.py and requirements-scrape.txt (requests, pillow, imagehash, opencv-python-headless, torch, transformers, tqdm with minimum versions).
- A smoke-test mode: DG_SCRAPE_SMOKE=1 makes every class stop at 5 images.
- At the end print the exact commands to install, smoke test, run the full download, then run --filter, and an estimate of how long the full run will take based on the smoke test.
```

---

## After Cursor writes it: run order

Run these from `ml-waste-categorizer-model/` yourself.

```bash
python download_data.py
python web_photos.py
python scrape_images.py
python scrape_images.py --filter
python prep.py
python make_split.py
python train.py out/run2
python evaluate.py
python export.py
```

Notes:

- `download_data.py` now also pulls up to 1500 Open Images photos of books, envelopes, paper towels, newspapers and notebooks into the `cardboard_paper` class, and it leaves out electronics images that also contain a book.
- `prep.py` picks up everything in `data/scraped/<class>/`, and `make_split.py` puts all of it in the training set only. Web labels are noisy, so validation and test stay on the clean datasets and the accuracy you see is still honest.
- Keep scraped images under about 40 percent of the training set. If `evaluate.py` shows real-photo accuracy falling while training accuracy rises, lower the targets at the top of `scrape_images.py` and run again.
- Before shipping, take 10 to 20 real phone photos of books, notebooks, cans and phones and check them in the app.
