# Current Handoff

## Status

Assignment 2 Part 2 local saved-hotel work is active on
`assignment2_part2_in_class` and remains uncommitted. The existing
Assignment 1 records and frozen Assignment 2 Part 1 ZIP, nearby-hotel, and
list/map contracts are preserved.

`DatabaseController.initialize_database()` applies a repeatable migration
against the existing `data/expedia_lite.sqlite3` path. It creates
`saved_hotels`, `saved_hotel_locations`, and `demo_hotel_nights` without
inserting production saved hotels or demo nights.

The backend now exposes `POST /api/saved-hotels`,
`GET /api/saved-hotels?zip_code=<zip>`, and
`DELETE /api/saved-hotels/{place_id}`. Saving is idempotent by provider
`place_id`, associates the searched ZIP and center, and creates the five
fictional October 10–14, 2026 demo nights with defaults of 10000 cents and 20
rooms. Existing nights and rates are never overwritten. Removal deletes the
hotel, all searched-location associations, and demo nights in one transaction.

The Vue nearby-hotel cards now load saved status for the current ZIP, offer
Add to Local and Remove from Local actions, preserve provider IDs, disable
pending/saved actions, and update the UI only after a successful response.

The current ZIP lookup is local-first. It requests
`GET /api/saved-hotels?zip_code=<zip>` before the frozen nearby API. A
non-empty saved response displays the stored ZIP center and five demo nights;
only a successful empty response calls `GET /api/hotels/nearby`. A local
request failure is shown as an error and does not fall through to the API.
Local cards are labeled `Saved locally` and explicitly state that they are not
a complete area inventory. API cards are labeled `API results`.

The Vue frontend keeps the existing hotel-name search and adds a ZIP-driven
nearby-hotel panel. The FastAPI route
`GET /api/hotels/nearby?zip_code=<zip>` resolves the ZIP through
`LocationController`, passes the coordinates to `NearbyHotelController`, and
returns the requested ZIP, search center, and sanitized Geoapify hotel fields.
The Places request uses a 5 km (`5000` metre) circle. Geoapify access and the
environment key remain backend-only. No shortlist behavior was added.

## Evidence

Prior Part 1 observation date: **2026-09-29**. Current persistence verification:
**2026-10-01**.

- The project-local backend imported FastAPI and pytest; Uvicorn was
  available.
- Read-only SQLite inspection preserved 9 hotels, 12 trips, 8 users, and 10
  existing bookings. Existing booking CRUD verification remains as recorded
  in the prior handoff.
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
- Read-only inspection after the migration confirmed the existing database
  path and preserved table counts: 9 hotels, 12 trips, 8 users, and 10
  bookings. The new `saved_hotels` and `demo_hotel_nights` tables exist and
  both contain zero rows.
- `backend/tests/test_saved_hotel_schema.py` covers fresh and existing
  database initialization, repeatability, defaults, composite uniqueness,
  foreign-key enforcement, coordinate checks, ISO date checks, and
  nonnegative rate/room constraints. New temporary-database controller and
  route tests cover idempotent save, ZIP associations, demo nights, removal,
  preservation of unrelated records, and safe errors. The backend suite
  passed: **37 tests passed** with the same two third-party TestClient
  deprecation warnings.
- `npm run lint` passed (`LINT_EXIT=0`) and `npm run build` passed
  (`BUILD_EXIT=0`).
- The running backend returned `GET /api/saved-hotels?zip_code=16802` as
  HTTP 200 with an empty result, and rejected an invalid ZIP with HTTP 400 and
  the safe message `ZIP code must be exactly five ASCII digits.`
- Read-only inspection of `data/expedia_lite.sqlite3` confirmed the three new
  tables exist and each has zero rows; no production saved hotel was inserted
  during this task.
- The restarted live backend returned one actual provider hotel from ZIP
  `16802`; a temporary save/list cycle returned one local result with dates
  `2026-10-10` through `2026-10-14`, 10000-cent nightly rates, and 20 rooms.
  The record was removed through the delete endpoint, and a follow-up read
  returned zero saved results. The live nearby endpoint still returned 20 API
  results for the empty-local ZIP.
- The frontend and backend were restarted only in their project-managed
  terminals. The embedded browser automation helper was unavailable because
  its `sky` service was not configured, so browser-level local-first,
  refresh-persistence, loading, and list/map observations remain **Not
  verified** here.

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
services; mocked coverage verifies those branches. The new demo rates and
room counts are fictional classroom defaults and are created only when a
hotel is explicitly saved.

## Next task

Manually inspect the local-first saved-hotel controls and the three new tables
in the existing database. Shortlist functionality remains out of scope until
explicitly requested.

## Hotel RAG update (2026-10-08)

The existing `POST /api/chat` contract is preserved (`{"reply": "..."}`).
Hotel questions now go through a backend-only, read-only RAG controller:
OpenAI proposes constrained SQL and named parameters, the controller validates
the single SELECT against the three saved-hotel tables, applies a 50-row and
finite execution-time limit, reads `data/expedia_lite.sqlite3`, and asks the
configured model for a final answer. General messages retain the basic chat
fallback. The API key remains backend-only and `OPENAI_MODEL` is read from
configuration.

Sanitized audit records are written to the ignored runtime path
`backend/logs/hotel_rag.jsonl` with `proposed_sql`, `executed_sql`,
`retrieved_rows`, and `error` labels. No hotel records are changed.

Evidence: the new mocked RAG tests and full backend suite passed (**49 tests,
one existing TestClient deprecation warning**); `npm run lint` and
`npm run build` passed; one controlled local `Hello` chat and one hotel
availability question both returned HTTP 200 with a reply. The runtime audit
contained the proposed/executed/retrieved labels and no API-key or
authorization marker. Browser-specific RAG presentation and hostile provider
responses remain **Not verified**.

The RAG contract and actual schema/JOIN rules are documented in
[`prompts/hotel-assistant.md`](../prompts/hotel-assistant.md).

## Conversation history and presentation update (2026-10-08)

Conversation identity and SQLite-backed history are now used by the chat UI.
The frontend keeps the UUID in local storage, sends it with every message,
and reloads `GET /api/chat/history?conversation_id=<uuid>` after refresh and
backend restart. The history table stores labeled user, SQL proposal,
executed SQL, retrieved-record, assistant-answer, and error events without
credentials.

The chat transcript now renders SQL proposals and executed SQL in readable
code blocks. Retrieved records are shown as hotel details with cents converted
to dollars and rates/rooms explicitly labeled simulated classroom data. The
final assistant answer remains separate from the technical trace, and the
heading uses “Hotel data assistant.”

Evidence: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests -q`
passed (**56 tests**, one third-party TestClient deprecation warning). From
`frontend/`, `npm run lint` and `npm run build` both passed with no warnings.
Browser verification observed ZIP `16802` on October 11, follow-up October 12,
the no-match ZIP `00501`, refresh reload, and history reload after restarting
the project backend. The displayed retrieved hotel, date, simulated `$100.00`
rate, and 20 rooms matched the existing SQLite rows. The backend remained at
`http://127.0.0.1:8000` and the frontend at `http://localhost:5173/`.

Next task: continue manual inspection of the preserved ZIP/map/local-storage
flows; no additional RAG features are planned in this handoff.

## Three-cheapest query correction (2026-10-08)

Three-cheapest hotel questions now retain the existing approved SQL,
parameterized filters, ordering, and read-only validation while applying an
effective result cap of three in addition to the global safety limit. The
final answer is rendered from the returned rows for this request, so it
reports fewer than three records when fewer matches exist and never invents
additional hotels.

Evidence: the focused RAG controller tests passed (**9 tests**); the full
backend suite passed (**58 tests**, one third-party TestClient deprecation
warning). From `frontend/`, `npm run lint` and `npm run build` both passed.
