# Current Handoff

## Status

Part 2 is implemented on `assignment-1-part2-sqlite-crud` from Part 1 commit `f42f1548715981a1b06a6ac2e4cab3a90f882842`. SQLite search and booking CRUD work through FastAPI. The Vue interface now contains search, booking creation, history, cancellation, test-booking deletion, and success/error messaging.

The backend now follows MVC boundaries: `backend/models/` defines the supplied
Hotel, Trip, User, and Booking entities and their relationships;
`backend/controllers/` owns database and business workflows; FastAPI routes
adapt controller contracts to the established JSON API; and `frontend/`
remains the View. The MVC rules and API contracts are recorded in `AGENTS.md`.

An uncommitted backend-only ZIP demonstration is available at
`GET /api/demo/zip-location?zip_code=<zip>`. The route delegates to
`LocationController`; Geoapify access and the environment key remain in the
backend controller/configuration layer. Nearby hotel retrieval is available at
`GET /api/demo/nearby-hotels?zip_code=<zip>` through a separate
`NearbyHotelController`, using the resolved ZIP coordinates and a 5 km Places
circle. The thin production-facing route
`GET /api/hotels/nearby?zip_code=<zip>` now resolves the ZIP through
`LocationController`, passes its coordinates to that controller, and returns
the requested ZIP, search center, and sanitized provider place IDs/results.
No shortlist or booking behavior was added to this flow.

## Verification evidence

- Project-local Python imports FastAPI and pytest; Uvicorn is available.
- SQLite startup seeding is idempotent: 8 hotels, 12 trips, 6 users, and 6 starter bookings are not duplicated.
- Live API verification created `B007`, retained it as cancelled, created/deleted test booking `B008`, and confirmed the seven-record state after backend restart.
- `npm run lint` and `npm run build` pass after the Vue update.
- Browser automation verified visible hotel search for Harbor and its two stays. Browser CRUD exercise is not verified: the automation browser could not reach newly spawned Vite ports even though local CLI requests could.
- MVC verification compiled all backend modules. TestClient returned HTTP 200 for
  the unchanged Harbor search response (H001 with T001 and T009) and booking
  history response. Reinitialization returned `False`, and
  `PRAGMA foreign_key_check` returned zero violations.
- Mocked ZIP controller and route verification passed: 5 tests passed. The
  route maps missing configuration to 503, an unresolved ZIP to 404, and a
  provider failure to 502 without returning secrets or raw provider errors.
- A live `GET http://127.0.0.1:8000/api/demo/zip-location` returned HTTP 200
  with a validated Geoapify location for `16802`.
- Mocked nearby-hotel controller and route verification passed: 23 backend
  tests passed in total. Success, no-results, provider failure, unresolved ZIP,
  and safe route mappings were checked for both nearby-hotel routes. Provider
  output is limited to place ID, name, available address/locality, latitude,
  and longitude.
- The nearby-hotel route now distinguishes incomplete required provider fields
  or coordinates from a generic provider failure with a safe 502 response.
- The Vue ZIP panel now exposes explicit initial, loading, invalid, unresolved,
  no-results, provider, network, incomplete-data, and success states. Results
  and map markers remain deduplicated by provider `place_id`.
- The browser verified initial/loading/invalid states, successful results for
  ZIPs `16802` and `10001`, leading-zero `00501` preservation with an
  unresolved response, list-to-map selection, map-to-list selection, and
  clearing old results at the start of a new search. The successful `10001`
  result showed 20 cards and 20 markers with visible attribution.
- A live `GET http://127.0.0.1:8000/api/hotels/nearby?zip_code=16802`
  returned HTTP 200 with the resolved search center and 20 sanitized Geoapify
  hotel results. The API key was not returned or logged.

## Limitations

- TestClient emits two third-party deprecation warnings for the installed
  FastAPI/Starlette test client; all 23 backend tests pass.
- A live no-nearby-hotels ZIP and live provider/network outage were not
  reproduced without changing or stopping services; mocked backend coverage
  verifies those safe branches.
- The current backend was started in a managed terminal on port 8000. It is a
  local development process and must be restarted after future backend edits.

## Next task

Review the working tree and requested commit scope. Do not commit or push until
the user approves. Keep shortlist, booking, and later Assignment 2 features
out of the nearby-hotel panel until explicitly requested.
