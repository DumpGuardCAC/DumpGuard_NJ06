#!/usr/bin/env node
/**
 * Validates website/data/streets/<town>.json against towns.json area_keys.
 * Usage: node website/scripts/validate-streets.mjs
 */
import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const streetsDir = join(root, 'website', 'data', 'streets');
const townsPath = join(root, 'website', 'data', 'towns.json');

const towns = JSON.parse(readFileSync(townsPath, 'utf8'));
const regionKeys = new Map();
for (const s of towns.schedules) {
  if (!regionKeys.has(s.region)) regionKeys.set(s.region, new Set());
  if (s.area_key) regionKeys.get(s.region).add(s.area_key);
}

const groupOf = (key) => (key.includes(':') ? key.split(':')[0] : 'area');

const files = readdirSync(streetsDir)
  .filter((f) => f.endsWith('.json') && !f.startsWith('_'));

const expected = [...regionKeys.keys()].sort();
const present = new Set(files.map((f) => f.replace(/\.json$/, '')));
const missing = expected.filter((id) => !present.has(id));
const extra = [...present].filter((id) => !regionKeys.has(id));

const errors = [];
const warnings = [];
const report = [];

if (missing.length) warnings.push(`Missing street files for towns: ${missing.join(', ')}`);
if (extra.length) warnings.push(`Extra street files (not in schedules): ${extra.join(', ')}`);

const TYPES = new Set(['streets', 'polygons', 'single', 'unavailable']);

for (const file of files.sort()) {
  const id = file.replace(/\.json$/, '');
  const path = join(streetsDir, file);
  let data;
  try {
    data = JSON.parse(readFileSync(path, 'utf8'));
  } catch (e) {
    errors.push(`${file}: invalid JSON (${e.message})`);
    continue;
  }

  const row = { town: id, type: data.type, source: data.source || '', ok: true, issues: [] };
  if (data.town !== id) {
    row.issues.push(`town field "${data.town}" != filename`);
    row.ok = false;
  }
  if (!TYPES.has(data.type)) {
    row.issues.push(`invalid type "${data.type}"`);
    row.ok = false;
  }
  if (!data.zones || typeof data.zones !== 'object' || Array.isArray(data.zones)) {
    row.issues.push('zones must be an object');
    row.ok = false;
    report.push(row);
    continue;
  }

  const allowed = regionKeys.get(id) || new Set();
  const zoneKeys = Object.keys(data.zones);

  if (data.type === 'single' || data.type === 'unavailable') {
    if (zoneKeys.length) {
      row.issues.push(`${data.type} files should have empty zones`);
      row.ok = false;
    }
    if (data.type === 'single' && allowed.size > 0) {
      warnings.push(`${id}: type single but towns.json has ${allowed.size} area_keys (may be intentional if keys are non-geographic)`);
    }
  }

  for (const key of zoneKeys) {
    if (allowed.size && !allowed.has(key)) {
      row.issues.push(`unknown area_key "${key}"`);
      row.ok = false;
    }
    const z = data.zones[key];
    if (!z || typeof z !== 'object') {
      row.issues.push(`zone ${key}: value must be object`);
      row.ok = false;
      continue;
    }
    if (data.type === 'polygons') {
      if (!z.geojson) {
        row.issues.push(`zone ${key}: polygons type needs geojson`);
        row.ok = false;
      }
    } else if (data.type === 'streets') {
      if (!Array.isArray(z.streets)) {
        row.issues.push(`zone ${key}: streets must be an array`);
        row.ok = false;
      }
    }
  }

  // Duplicate street within same group (e.g. two trash: keys)
  if (data.type === 'streets') {
    const byGroup = new Map();
    for (const [key, z] of Object.entries(data.zones)) {
      const g = groupOf(key);
      if (!byGroup.has(g)) byGroup.set(g, new Map());
      const seen = byGroup.get(g);
      for (const raw of z.streets || []) {
        const norm = String(raw).toLowerCase().trim();
        if (seen.has(norm) && seen.get(norm) !== key) {
          row.issues.push(`street "${raw}" in both ${seen.get(norm)} and ${key} (group ${g})`);
          row.ok = false;
        } else {
          seen.set(norm, key);
        }
      }
    }
  }

  if (!row.ok) errors.push(`${file}: ${row.issues.join('; ')}`);
  report.push(row);
}

const summary = {
  townsExpected: expected.length,
  files: files.length,
  missing,
  extra,
  errors: errors.length,
  warnings: warnings.length,
};

console.log(JSON.stringify({ summary, errors, warnings, towns: report }, null, 2));
if (errors.length) {
  console.error(`\nFAILED: ${errors.length} error(s)`);
  process.exitCode = 1;
} else {
  console.error(`\nOK: ${files.length} files validated` + (warnings.length ? ` (${warnings.length} warning(s))` : ''));
}
