# Current Handoff

## Status

Assignment 2 Part 1 is implemented on `main`. The committed baseline before
this documentation update is `7e710028496807f29b22061a68b689756e7658ae`
(`Complete nearby hotel map experience`). This documentation update is
currently uncommitted. No application behavior was changed in this task.

The Vue frontend keeps the existing hotel-name search and adds a ZIP-driven
nearby-hotel panel. The FastAPI route
`GET /api/hotels/nearby?zip_code=<zip>` resolves the ZIP through
`LocationController`, passes the coordinates to `NearbyHotelController`, and
returns the requested ZIP, search center, and sanitized Geoapify hotel fields.
The Places request uses a 5 km (`5000` metre) circle. Geoapify access and the
environment key remain backend-only. No shortlist behavior was added.

## Evidence

Observation date: **2026-09-29**.

- The project-local backend imported FastAPI and pytest; Uvicorn was
  available.
- SQLite startup seeding remained idempotent for 8 hotels, 12 trips, 6 users,
  and 6 starter bookings. Existing booking CRUD verification remained as
  recorded in the prior handoff.
- Mocked ZIP and nearby-hotel coverage passed: **23 backend tests passed**.
  The suite covers valid ZIPs, leading-zero handling, invalid input,
  unresolved ZIP, missing configuration, provider failure, nearby success,
  no results, incomplete provider fields, and safe route mappings. TestClient
  emitted two third-party deprecation warnings.
- `npm run lint` passed and `npm run build` passed after the Vue map update.
- A live `GET http://127.0.0.1:8000/api/hotels/nearby?zip_code=16802`
  returned HTTP 200 with a resolved center and 20 sanitized provider hotel
  results. The API key was not returned or logged.
- Browser verification used [http://127.0.0.1:5174/](http://127.0.0.1:5174/):
  `16802` and `10001` returned successful results; `00501` preserved its
  leading zero and showed the unresolved state. Invalid empty, four-digit,
  six-digit, and non-digit inputs showed distinct validation messages.
- The successful `10001` result showed 20 cards and 20 markers with visible
  OpenStreetMap attribution. Selecting the observed `Faena hotel` list item
  selected/opened its matching marker; selecting the observed `The Holland
  Hotel` marker highlighted the matching list item. A new search cleared old
  results, markers, and selection.

## Design and sources

The design note records MVC responsibilities, the sanitized response shape,
the 5 km rule, state handling, interaction decisions, and limitations in
[`docs/design.md`](../docs/design.md). The development brief and verification
record are in [`prompts/assignment-2-part1.md`](../prompts/assignment-2-part1.md).

Source links used by the design:

- [Geoapify Forward Geocoding API](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/)
- [Geoapify Places API](https://apidocs.geoapify.com/docs/places/)
- [Leaflet reference](https://leafletjs.com/reference.html)
- [OpenStreetMap attribution](https://www.openstreetmap.org/copyright)

The useful observed interaction was the local running location-search UI's
labeled input, explicit submit action, loading feedback, and separate result
or error area. A separate early mockup URL is **Not verified** because none
is recorded in the repository or prior handoff evidence.

## Limitations

Geoapify results are provider observations only; they do not prove price,
room availability, rating, or booking eligibility. The Leaflet map depends
on network-loaded OpenStreetMap tiles. A live no-nearby-hotels ZIP and a live
provider/network outage were not reproduced without changing or stopping
services; mocked coverage verifies those branches. The backend is a local
development process on port 8000 and the frontend is served on port 5174.

## Next task

Proceed to **Assignment 2 Part 2: shortlist** only after reviewing this
handoff. Keep shortlist and booking controls out of the current Part 1
nearby-hotel panel until that work is explicitly started.
