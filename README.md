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


