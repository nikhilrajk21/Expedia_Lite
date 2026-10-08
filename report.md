# Expedia Lite — Part 2

## Repository and commit

Repository: [https://github.com/nikhilrajk21/Expedia_Lite.git](https://github.com/nikhilrajk21/Expedia_Lite.git)

Assessed branch: rag_integration

Final RAG commit: ed75360167530492f858dc289a84077159d61238 — Complete business-aware hotel RAG integration

This report update is intentionally uncommitted so it can be reviewed separately.

## Research and design

The implementation uses the server-side OpenAI Responses API through the official [OpenAI Python API reference](https://developers.openai.com/api/reference/python) and its [responses.create contract](https://developers.openai.com/api/reference/python/resources/responses/methods/create). The backend supplies the configured model, question, schema, and hotel-assistant instructions; the browser never receives the API key.

The read-only SQL design follows SQLite's [SELECT documentation](https://www.sqlite.org/lang_select.html), which states that a SELECT returns rows without changing the database, and SQLite's [authorizer API](https://www.sqlite.org/c3ref/set_authorizer.html), which is used as an additional read-only and column-approval boundary. No separate RAG paper or grounded-generation reference was recorded as part of the implementation; grounding is enforced by executing one validated query and answering only from its returned rows.

The preserved location/map design records the relevant [Geoapify Forward Geocoding API](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/), [Geoapify Places API](https://apidocs.geoapify.com/docs/places/), [Leaflet reference](https://leafletjs.com/reference.html), and [OpenStreetMap attribution](https://www.openstreetmap.org/copyright) sources. The nearby search uses resolved ZIP coordinates as the center of a 5 km (5000 metre) circle. A useful interaction decision was to keep the search input labeled and explicit, then separate technical SQL/retrieval stages from the readable final answer. Early mockup: Not verified; no separate pre-implementation mockup is currently recorded.

## Implementation

The implemented workflow is:

Vue question → FastAPI /api/chat → OpenAI proposes SQL → backend validates SQL → SQLite executes one read-only query → retrieved records are sent to OpenAI → OpenAI generates a grounded answer → Vue displays the SQL stages, retrieved records, and final answer.

The main endpoints are:

- POST /api/chat accepts message and an optional conversation_id, and returns the persistent conversation ID and safe reply.
- GET /api/chat/history?conversation_id=<uuid> reloads labeled history after refresh or backend restart.

The actual SQLite database is data/expedia_lite.sqlite3. The assistant's approved tables are:

- saved_hotels(hotel_id, name, address, latitude, longitude), where hotel_id is the provider place ID;
- saved_hotel_locations(hotel_id, zip_code, latitude, longitude), preserving each searched ZIP and center;
- demo_hotel_nights(hotel_id, stay_date, nightly_rate_cents, rooms_available), with (hotel_id, stay_date) as the key and defaults of 10000 cents and 20 rooms.

The required joins are:

1. saved_hotels.hotel_id = saved_hotel_locations.hotel_id for ZIP/location context;
2. saved_hotels.hotel_id = demo_hotel_nights.hotel_id for dated demo rates and room counts.

ZIP filters use parameterized saved_hotel_locations.zip_code; date filters use parameterized demo_hotel_nights.stay_date; available rooms mean rooms_available > 0; price questions order by nightly_rate_cents ASC; and cents are divided by 100 for display. Rates and room counts are always labeled simulated classroom data. Missing dates and empty results are reported as no matching saved records rather than filled with invented values.

Only one parameterized read-only SELECT is accepted. The backend rejects writes, PRAGMA, ATTACH, comments, multiple statements, unapproved tables, and unapproved columns, then applies a global row limit and finite SQLite execution limit. A request for the three cheapest hotels also receives a request-specific maximum of three rows.

The local-storage foundation remains in place: Add to Local saves provider hotels and the searched ZIP, Remove from Local deletes the hotel association and demo nights transactionally, and local-first lookup calls GET /api/saved-hotels before falling back to the frozen nearby-hotel API. Saving creates exactly five fictional nightly rows for October 10–14, 2026, without overwriting existing rates or availability. Assignment 1 tables and records, ZIP search, the nearby hotel list, Leaflet map, and synchronized list/map behavior remain preserved.

## Verification

### Automated checks

| Check | Expected | Observed | Status |
| --- | --- | --- | --- |
| backend/.venv Python pytest | Backend/RAG, history, safety, schema, saved-hotel, and route tests pass. | 58 passed, with one third-party Starlette/AnyIO deprecation warning. | Pass |
| npm run lint from frontend | Frontend lint passes. | Passed. | Pass |
| npm run build from frontend | Production bundle builds. | Vite 8.3.0 build completed successfully. | Pass |

### Manual browser and read-only SQLite observations

| Action | Expected | Observed | Status |
| --- | --- | --- | --- |
| Basic live chatbot: Hello | A normal assistant response is returned. | The browser displayed a greeting response through the configured backend model. | Pass |
| Successful RAG query for ZIP 16802, October 11, 2026 | Return only matching saved SQLite records. | The transcript showed Sleep Inn, 20 rooms, and a 10000-cent nightly record. | Pass |
| SQL proposal | A single parameterized hotel query is shown or persisted. | SQL Proposal showed approved saved-hotel tables, named ZIP/date parameters, availability filtering, and price ordering. | Pass |
| SQL validation | Unsafe or unapproved SQL is rejected. | Controller and safety tests rejected writes, unknown tables/columns, comments, and multiple statements. | Pass |
| Executed SQL | SQLite executes the validated query only. | Executed SQL matched the proposal and used the existing database path. | Pass |
| Retrieved records | Rows match SQLite exactly. | Read-only inspection and transcript both showed Sleep Inn, nightly_rate_cents 10000, and rooms_available 20. | Pass |
| Grounded final answer | Answer uses retrieved values and no invented hotel. | The answer named only Sleep Inn and labeled rate/rooms as simulated classroom data. | Pass |
| Three-result limit | Three-cheapest requests return no more than three rows. | The corrected query recorded LIMIT 3 and row_limit 3; one matching record was returned. | Pass |
| Follow-up: What about October 12? | Reuse conversation and ZIP while changing only the date. | Same conversation ID; ZIP 16802 remained; date became 2026-10-12 and matched SQLite. | Pass |
| No-match ZIP 00501 | Clearly report no matching saved records. | Transcript displayed the no-match answer without inventing a hotel. | Pass |
| Missing date December 1, 2026 | Missing availability is not treated as available. | Query returned zero rows and answer stated no matching saved records were found. | Pass |
| Blocked UPDATE | Database remains unchanged. | Rejected by validation; saved-hotel counts remained unchanged. | Pass |
| Blocked DELETE | Database remains unchanged. | Rejected by validation; saved-hotel counts remained unchanged. | Pass |
| Blocked unknown table | Query is rejected. | Rejected before successful retrieval. | Pass |
| Blocked multiple statements | Query is rejected. | Rejected before execution. | Pass |
| Browser refresh and history reload | Conversation remains available. | Refresh restored the transcript; GET /api/chat/history returned HTTP 200 with labeled stages. | Pass |
| Backend restart and history persistence | History survives restart. | After restarting only the project backend, the same conversation and stages reloaded. | Pass |
| Saved/nightly preservation | Existing local records remain unchanged. | Read-only counts were saved_hotels=1, saved_hotel_locations=1, demo_hotel_nights=5; dates remained October 10–14, 2026 with 10000 cents and 20 rooms. | Pass |
| ZIP search and nearby results | Existing Assignment 2 Part 1 behavior remains available. | ZIP 16802 showed saved-local data; unsaved ZIP 16803 showed 15 API results and map markers. | Pass |
| List/map selection | Selecting either surface selects the same provider place ID. | List-to-map and map-to-list selection were observed for API results; Leaflet/OpenStreetMap attribution remained present. | Pass |
| Add/Remove, local-first, nightly data | Controls and local-first behavior remain functional. | Saved state showed disabled Saved locally and visible Remove from Local; temporary-database mutation tests passed; network capture showed saved lookup before nearby API fallback. Live mutation clicks were not repeated during final read-only verification. | Partially verified |

The read-only inspection used Python SQLite URI mode against the existing database. Native DB Browser GUI observations were Not verified. The database still contains the supplied Assignment 1 counts: 9 hotels, 12 trips, 8 users, and 10 bookings. Chat verification necessarily appended conversation-history records, but it did not change hotel, location, nightly, booking, or Assignment 1 records.

## Demonstration

[Assignment 2 Part 2 RAG demonstration video](https://drive.google.com/file/d/1gznW7HkB5uFd_XmLFeD4tAiitpqBOqn0/view?usp=sharing)

The supplied recording is intended to demonstrate the chatbot question, proposed SQL, retrieved records, grounded answer, and relevant interaction. The Drive link was not independently checked for accessibility, so its access status is Not verified.

## AI disclosure and evidence log

- OpenAI Codex was used for repository inspection, implementation, tests, documentation, terminal verification, and browser interaction. The system identifies this agent as GPT-5-based; the exact Codex model variant and reasoning effort for this task are Not verified in the repository or recorded evidence.
- The OpenAI API was used only by the backend to produce basic chat responses, constrained SQL proposals, and final answers from retrieved rows.
- Configured API model: gpt-5-mini, verified from backend configuration; no credential value is included here.
- Selected prompts: prompts/hotel-assistant.md and prompts/assignment-2-part1.md.
- Revised approach: the initial basic-chat flow was extended into a two-stage business-aware RAG flow: proposal, validation/execution, then a grounded final answer. The earlier fixed ZIP demonstration was revised to accept validated ZIP strings while preserving leading zeros.
- Failed/revised approach: an inherited process-level OPENAI_API_KEY took precedence over the project .env value and caused sanitized provider failures. The backend was restarted after clearing inherited configuration; no key, authorization header, or raw provider exception is recorded here.

## Project context and next steps

- [README.md](README.md) — setup, startup, proxy, database, and .env guidance.
- [AGENTS.md](AGENTS.md) — project rules and MVC boundaries.
- [docs/design.md](docs/design.md) — Geoapify, Leaflet, MVC, 5 km search, and preserved Part 1 design evidence.
- [docs/zip-lookup-controller.md](docs/zip-lookup-controller.md) — backend ZIP controller contract.
- [prompts/hotel-assistant.md](prompts/hotel-assistant.md) — actual schema, joins, filters, read-only rules, and simulated-data rules.
- [prompts/assignment-2-part1.md](prompts/assignment-2-part1.md) — existing Assignment 2 Part 1 development prompt.
- [handoffs/current.md](handoffs/current.md) — implementation status and verification history.

Remaining limitations are that answers are limited to saved local hotel records; rates and room counts are simulated classroom data; provider/model availability, quota, or network conditions can affect responses; natural-language requests cannot modify the database; native DB Browser evidence and Drive-link accessibility were not verified in this report; and live Add/Remove mutation clicks were intentionally not repeated during read-only final verification. No shortlist functionality is included in this revised Part 2 scope.
