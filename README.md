# DumpGuard NJ

https://dumpguard.vercel.app/

A recycling and illegal-dumping app for New Jersey residents. Built by Saanvika Govindaraj, Vedant Daga and Nethra Ramkumar for the Congressional App Challenge 2026, District NJ-06.

DumpGuard answers three questions: can I recycle this, when is my pickup, and how do I report dumping.

## Features

- **Identify.** Point the camera at an item and a live tracking box locks onto it as you move, cropping tight before the model ever sees a frame. Search by name works too. The app gives a yes or no recyclable verdict and your town's rule: trash, recycling, or special drop-off. When the model is unsure it says so and offers the closest matches.
- **Pickup days.** Enter an address and see the next trash, recycling, bulk and yard waste dates for your zone. 25 towns resolve an address to a zone from street lists or traced zone maps. The rest use a zone picker, and towns whose zone data is not yet published say so in the app.
- **Report dumping.** Photograph the site, mark the location and submit. You get a tracking code to check status. Photo metadata is stripped, and the public map only shows clusters of three or more reports.
- **Local resources.** Drop-off locations in one place, in English and Spanish.

## How it works

- Identification runs on the device. A fine-tuned MobileNetV3 model (7 classes: rigid plastic, soft plastic/foam, cardboard/paper, metal, glass, e-waste/hazard, no object) is served as a TensorFlow.js graph model of about 5.9 MB. Camera frames never leave the phone.
- A service worker caches the app and the model, so Identify works offline after the first visit.
- Town rules, schedules, facilities and reports live in Postgres. The API runs as Vercel serverless functions.
- The Android app is the same web app bundled with Capacitor.

## Model

- 39,110 images: TrashNet, TACO, Garbage12, RealWaste, ZeroWaste, TrashBox, Open Images and a curated e-waste set, topped up with our own openly-licensed scrapes (Openverse, Wikimedia Commons, Pixabay, Pexels) for the classes public datasets covered thinly.
- CLIP and OwlViT auto-label and clean the raw pull -- relabeling, cropping to the right object, dropping bad examples -- before a human ever looks at it. Perceptual-hash dedup keeps near-duplicates from leaking between train and the held-out splits.
- Held-out accuracy: 85.9% validation, 82.6% in-distribution test, 64.3% on the harder external set.
- Phase 1 trains a new head with the base frozen; phase 2 fine-tunes the upper layers with BatchNorm frozen.

## Repo layout

| Path | What it holds |
|---|---|
| `website/` | The web app (plain JavaScript, HTML, CSS), service worker, TF.js model in `lib/`, API in `api/`, town data in `data/` |
| `website/data/towns.json` | Town schedules, facilities, ZIP codes, and each town's street lists or zone polygons (used to turn an address into a pickup zone) |
| `android/` | Capacitor Android project |
| `ml-waste-categorizer-model/` | `preprocess.py` (dataset prep and cleaning), `dataset.py` (classes, crops, loaders), `model.py` (network definition), `train.py`, `evaluate.py`, `export.py` (TF.js export) |
| `.github/workflows/` | Builds and publishes the Android APK |

## Running it

Web app: serve `website/` with any static server. The API needs a Postgres database.

```bash
cd website
npm install
export DATABASE_URL=postgres://...
npm run migrate    # create the schema
npm run seed       # load towns, items, schedules and facilities
```

Android: from `android/`, run `npm install && npm run sync`, then open the project in Android Studio. The GitHub Actions workflow does the same and publishes a signed APK as a release.

Model:

```bash
cd ml-waste-categorizer-model
python train.py
python export.py
```

## Data

- **Town rules and schedules** come from each town's official calendars and pages, read and entered by hand, town by town, over several research passes. Always confirm with your town; the app says so wherever a zone is approximate.
- **Pickup zones** for towns without an official address lookup were traced by hand from township zone maps into street lists and polygons, then checked against real addresses. Towns we couldn't trace confidently fall back to a plain zone picker instead of guessing.
- **Training images** are a mix of public waste-sorting datasets and our own scrapes of openly-licensed (Creative Commons / Pixabay / Pexels) photos, pulled to fill in classes the public data covered thinly, then auto-cleaned (see Model above) rather than hand-sorted one by one.
