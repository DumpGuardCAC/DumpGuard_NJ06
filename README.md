# DumpGuard

**An AI-assisted full waste management & recycling contamination solution.** Built for the Congressional App Challenge 2026, District NJ-06 (Rep. Frank Pallone Jr.).

[Live Web App](https://dumpguard.vercel.app/) | [Devpost Submission](https://devpost.com) | [Demo Video](https://youtu.be)

## The Idea

Single-stream recycling programs face severe contamination rates due to "wish-cycling" (sorting non-recyclables like Styrofoam or grocery bags into blue bins), which damages public sorting machinery at facilities like the Middlesex County Improvement Authority (MCIA) and the Monmouth County Reclamation Center. 

DumpGuard solves this issue by acting as an AI-assisted ecosystem spanning a responsive Web Dashboard and a native Android application. It executes real-time, privacy-first computer vision material classification directly on-device, provides smart calendars tailored strictly to local NJ-06 zip codes, offers a client-side fuzzy-search directory fallback for multi-material sorting rules, and features a mockup API for scheduling municipal bulk pickups.

## How it works

1. **Sense.** A live device camera feed captures household items, streaming frames directly to an on-device vision subsystem.
2. **Classify.** A quantized TensorFlow Lite/JS model processes frames locally using hardware acceleration to accurately categorize materials into 6 core disposal streams.
3. **Fallback.** If camera confidence falls below a 65% threshold, a client-side fuzzy-search engine steps in, parsing a local 200+ multi-material lookup dictionary that safely handles typos.
4. **Schedule & Request.** The app pulls localized municipal collection data based on regional zip codes and allows residents to dispatch bulk pickup requests directly to a mock backend API gateway.

At the curb or in basements with weak cellular reception, custom Service Worker caching strategies on the web and local SQLite databases on Android guarantee full offline access to static shell interfaces, structural assets, and saved calendars.

## Website Features

Live at **https://dumpguard.vercel.app/**. It shows an item database lookup (via search or photo upload), localized municipal pickup days tracking, public illegal dumping reporting interfaces, and an interactive tracking map. It also houses a secure Government portal complete with a dashboard for public works administrative logging, report triaging (New, Noticed, In progress, Resolved), and analytics. Street map tiles load dynamically with fallback points for missing connections, and photo uploads automatically scrub location metadata for public privacy.

The item database is loaded into a client-side layout shell allowing immediate searches before external database synchronization completes. Materials without structural definitions or rules defaults display n/a.

## Software Architecture (Tech Stack)

| Layer / Directory | Technology / Tool | Job |
|---|---|---|
| **`website/`** | React / Next.js & Tailwind CSS | Renders responsive, cross-device layouts optimized for mobile and desktop viewports, hosted on Vercel. |
| **`android/`** | Kotlin / Java Android Studio | Powers the native mobile installation layer, offering fluid UI components, camera hardware bindings, and deep background lifecycle operations. |
| **`ml-waste-categorizer-model/`** | TensorFlow / Keras | Holds the raw pipeline notebooks, dataset scripts (TACO + TrashNet + ZeroWaste), and final quantized export files (`.tflite` / `.json`). |
| **`.github/workflows/`** | GitHub Actions CI/CD | Automates web deployment checkouts to Vercel and runs linting/compilation verification checks for the Android application bundle. |

## Core API Routing Specifications

### 1. Municipal Schedule Retrieval
Retrieves local municipal sorting rules based on the user's zip code.

* **Method / Route:** `GET /api/v1/schedule/:zip_code`
* **Sample Payload Response (`200 OK` for Edison `08817`):**
```json
{
  "status": "success",
  "zip_code": "08817",
  "municipality": "Edison Township",
  "county": "Middlesex",
  "schedules": {
    "trash_days": ["Tuesday", "Friday"],
    "recycling_days": ["Wednesday (Alternate)"],
    "next_recycling_date": "2026-10-07",
    "yard_waste": "Monday (Seasonal)"
  },
  "facility_alerts": [
    "Plastic bags are strictly prohibited in MCIA single-stream recycling."
  ]
}
```

### 2. Bulk Pickup Scheduling Request
Dispatches a request to schedule heavy item curbside collections. Contains safety rule compliance checks.

* **Method / Route:** `POST /api/v1/bulk-request`
* **Sample Request Payload:**
```json
{
  "zip_code": "08817",
  "street_address": "456 Oak Tree Road",
  "contact_email": "resident@example.com",
  "item_category": "Appliance",
  "item_description": "Refrigerator (Freon Unit)",
  "requested_pickup_date": "2026-10-12",
  "guidelines_accepted": true
}
```
* **Sample Payload Response (`201 Created`):**
```json
{
  "status": "confirmed",
  "confirmation_number": "DG-08817-9824",
  "scheduled_date": "2026-10-12",
  "instructions": "Place items at the curb by 6:00 AM. Ensure doors are removed or securely strapped shut."
}
```

## Running the Application

### Website Setup

Navigate to the `website` directory to install dependencies and boot your local server environment:

```bash
cd website
npm install
npm run test             # Executes deployment logic tests
npm run dev              # Launches local server on http://localhost:3000
```

### Android Native Build

To inspect or assemble the Android wrapper system:
1. Open the `/android` directory inside **Android Studio**.
2. Sync the project with Gradle files.
3. Place a compatible quantized `model.tflite` into the app assets directory.
4. Click **Run** to execute on an attached physical target device or local emulator.

### Model Training Pipeline

To view dataset handling configurations or compile weight changes:

```bash
cd ml-waste-categorizer-model
pip install -r requirements.txt
python train.py          # Builds execution pipeline and benchmarks matrix losses
```

## Repo Layout

* `.github/workflows/` - CI/CD pipeline automation suites.
* `android/` - Native Android source files, layouts, and gradle setups.
* `ml-waste-categorizer-model/` - Training history, optimization parameters, datasets, and quantized matrix nodes.
* `website/` - Source configurations for your live Vercel dashboard and structural pages.
* `.gitignore` - Centralized file protection mappings.

