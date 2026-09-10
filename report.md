# Expedia Lite — Part 1

## Repository and commit

GitHub repository: [https://github.com/nikhilrajk21/Expedia_Lite.git](https://github.com/nikhilrajk21/Expedia_Lite.git)

Submitted commit: `cb7363dec9a800c740bb22db83c18beb2bff2116` (`Initialize Expedia Lite Part 1`) on branch `master`. The working tree was clean when this report was prepared.

## Implementation

The Vue JavaScript frontend provides one labeled hotel-name input and Search button. It requests `/api/hotels/search?name=...`, renders matching hotels and their stays in a semantic HTML table, and shows distinct no-results and request-error messages. Vite forwards `/api` requests to the local FastAPI server during development.

The FastAPI/Python backend defines `GET /api/hotels/search`. It reads the supplied `data/hotels.csv` and `data/trips.csv` using project-relative paths, performs a case-insensitive hotel-name search, and returns JSON with a `results` collection. Each result preserves the hotel CSV fields and includes `available_stays`. Trips are connected to hotels through the supplied `hotel_id` field. The CSV reader uses `utf-8-sig` so the supplied UTF-8 BOM does not alter the first header name.

## Verification

- Backend compilation: `python -m compileall app` completed successfully.
- Backend dependency checks: FastAPI imported successfully as `0.141.1`; Uvicorn `0.52.4` was available; `python -m pip check` reported no broken requirements.
- Successful hotel search: FastAPI's in-process test client verified `/api/hotels/search?name=harbor` returns `H001` (`Harbor Lantern Hotel`) with the connected stays `T001` and `T009`. A live HTTP request to the same endpoint returned HTTP 200 with that result.
- No-results search: the in-process test verified both `name=not a hotel` and a blank query return `{"results": []}`.
- Frontend checks: `npm run lint` completed successfully with no warnings or errors after ESLint formatting. `npm run build` completed successfully with Vite after transforming 11 modules.
- Frontend availability check: the local frontend server returned HTTP 200 and served the Vue application root.
- Manual browser review: Not verified. No manually captured visual walkthrough was recorded.
- Screenshots: Not verified. No project screenshots were found; therefore, no screenshot links are included.

## Project context and next steps

Project context is documented in [README.md](README.md), [AGENTS.md](AGENTS.md), [docs/design.md](docs/design.md), [prompts/assignment-1-part1.md](prompts/assignment-1-part1.md), and [handoffs/current.md](handoffs/current.md). The referenced `prompts/assignment-1-part1.md` file is not present, so its content is Not verified.

SQLite and booking CRUD are deferred to Part 2.
