# Street/zone data status

Files live in `website/data/streets/<town>.json`. A missing file means the town has no address-to-zone data and the app shows the zone picker instead. Validate with `node scripts/validate-streets.mjs`.

## Available (18)

| Town | Type | Notes |
|---|---|---|
| atlantic-highlands, carteret, hazlet, highlands, little-silver, matawan, neptune-township, south-amboy, union-beach, west-long-branch, woodbridge | streets | Street lists from town sources |
| old-bridge | streets | Wards. Exception areas (Central Park, The Arbors) not modeled |
| piscataway | polygons | 3 zones |
| edison | polygons (approx) | Recycling sections rs-1..rs-10 traced from the township map. Garbage districts have no published map, so garbage stays unresolved |
| red-bank, monmouth-beach, neptune-city, middletown | polygons (approx) | Split along the road/rail boundary from OpenStreetMap lines |

Polygon files marked approx show a "near a boundary" note in the app and snap to the nearest zone within `snap` meters.

## Not available

- Pending: metuchen, highland-park, south-plainfield, keansburg (map-image or line-split work)
- Being collected separately: keyport, new-brunswick, asbury-park, bradley-beach, oceanport
- Ambiguous boundary, left unresolved: perth-amboy, rumson, long-branch
- Neighborhood names only, no street list: aberdeen, sayreville
- Not yet researched: allenhurst, deal, fair-haven, interlaken, loch-arbour, sea-bright
