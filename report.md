# Expedia Lite — Part 1

## Repository and commit

Repository: [https://github.com/nikhilrajk21/Expedia_Lite.git](https://github.com/nikhilrajk21/Expedia_Lite.git)

Assessed branch: `main`
Assessed commit: `7e710028496807f29b22061a68b689756e7658ae` — `Complete nearby hotel map experience`

The report and the related documentation updates are currently working-tree
changes and were not included in the assessed commit. They have not been
committed or pushed in this task.

## Implementation

Expedia Lite uses Vue with JavaScript for the View and FastAPI/Python for the
backend boundary and controllers. The existing hotel-name search remains in
place. Assignment 2 Part 1 adds a ZIP-driven nearby-hotel flow:

- `GET /api/hotels/nearby?zip_code=<five-digit-zip>` validates the ZIP as a
  string, preserves leading zeros, geocodes it through Geoapify, and searches
  a 5 km (`5000` metre) circle around the resolved coordinates.
- Geoapify Geocoding and Places requests, finite timeouts, response
  validation, and safe error mapping remain backend-only. The Vue app calls
  only the local `/api/...` route; the API key is never placed in frontend
  code or responses.
- Returned hotels contain only provider-backed `place_id`, `name`, optional
  `address`/`locality`, `latitude`, and `longitude`. Results do not prove
  price, room availability, ratings, or booking eligibility.
- Leaflet centers on the resolved ZIP, displays valid hotel coordinates with
  markers, and includes visible OpenStreetMap attribution. The list and map
  use `place_id` to deduplicate and synchronize selection.

**Startup and local configuration**

From the project root, store the local `GEOAPIFY_API_KEY` value in the
project-root `.env` file. The key value is intentionally omitted from this
report. Restart the backend after changing `.env`.

Backend:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend:

```powershell
Set-Location frontend
npm run dev
```

The documented local services are FastAPI at
`http://127.0.0.1:8000` and Vite at `http://127.0.0.1:5174/` for the browser
verification session. Vite proxies relative `/api` requests to the backend.

**Research and design decisions**

- [Geoapify Forward Geocoding API](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/)
- [Geoapify Places API](https://apidocs.geoapify.com/docs/places/)
- [Leaflet reference](https://leafletjs.com/reference.html)
- [OpenStreetMap attribution](https://www.openstreetmap.org/copyright)

The design keeps location lookup, Places retrieval, validation, and provider
error handling in Python controllers; FastAPI adapts those contracts to JSON;
Vue owns presentation state and interaction. The observed useful interaction
was a labeled location input with an explicit submit action, visible loading
feedback, and a distinct result/error area. The verified local UI is
[http://127.0.0.1:5174/](http://127.0.0.1:5174/), observed on 2026-09-29.

Early mockup link: **Not verified** — no separate mockup URL is recorded in
the repository or handoff history.
Screen-recorded demonstration: [video1697873008.mp4](<C:/Users/nikhi/Documents/Zoom/2026-09-29 15.49.13 Nikhil Raj K's Zoom Meeting/video1697873008.mp4>)
  (verified local recording; not hosted in this GitHub repository).

## Verification

Observation date: **2026-09-29**. Tested ZIPs were `16802`, `10001`, and
leading-zero `00501`.

| Action | Expected result | Observed result |
| --- | --- | --- |
| Backend mocked tests using `backend/.venv` | Cover valid and leading-zero ZIPs, invalid input, unresolved ZIP, missing configuration, nearby success, no results, incomplete data, provider failure, and safe route mappings. | **23 tests passed**; TestClient emitted two third-party deprecation warnings. |
| Live `GET /api/hotels/nearby?zip_code=16802` | HTTP 200 with the resolved center and sanitized provider hotels, without credentials. | HTTP 200 with 20 sanitized Geoapify hotel results; the API key was not returned or logged. |
| Browser ZIP `16802` | Successful location and nearby results. | Successful provider results displayed. |
| Browser ZIP `10001` | Successful results, ZIP-centered map, valid markers, and attribution. | 20 hotel cards and 20 markers displayed with visible OpenStreetMap attribution. |
| Browser ZIP `00501` | Preserve the input as a string and distinguish an unresolved ZIP from success. | Leading zero was preserved and the unresolved state/message was shown. |
| Empty, four-digit, six-digit, and non-digit ZIP input | Clear validation feedback without a provider request. | Distinct validation messages were observed. |
| New ZIP search while results are present | Show loading, disable the button, and clear stale results, markers, and selection. | Loading feedback and disabled-button behavior were observed; old results and selection cleared. |
| List hotel selection | Highlight the selected list item and open/highlight its matching marker. | Selecting the observed `Faena hotel` item selected/opened the matching marker. |
| Map marker selection | Highlight the matching list hotel using the provider `place_id`. | Selecting the observed `The Holland Hotel` marker highlighted the matching list item. |
| Existing hotel-name search | Preserve the Part 1 hotel search and connected stays. | Earlier browser verification displayed Harbor and its two connected stays. |
| No nearby hotels and provider/network outage | Remain distinct from a successful empty search. | Mocked backend tests verified these safe branches; live outage/no-results reproduction was not verified. |
| Frontend lint | Pass without new lint errors. | `npm run lint` passed. |
| Frontend production build | Produce a successful production build. | `npm run build` passed. |

The browser called the local backend route rather than Geoapify directly, and
the Geoapify key did not appear in frontend code, browser responses, or the
live API response.

**Revised or failed approach**

The first ZIP demonstration was fixed to `16802`. It was revised to accept
any validated five-digit ZIP string while preserving leading zeros, then the
nearby route was added as a separate controller flow. The `00501` live test
also showed why unresolved ZIPs must remain a distinct state rather than an
empty successful result. A live provider outage and live no-results ZIP could
not be reproduced without stopping or changing services, so those branches
remain mock-tested rather than claimed as live observations.

**AI disclosure**

This project and report were developed with OpenAI Codex, a GPT-5-based coding
agent. Tool use included PowerShell/terminal inspection and verification,
`apply_patch` file edits, embedded-browser automation for the UI checks, and
web lookup of the official Geoapify, Leaflet, and OpenStreetMap references.
No credentials were supplied to or included in the report.

## Project context and next steps

- [README.md](README.md) — setup, startup, proxy, and local `.env` guidance.
- [AGENTS.md](AGENTS.md) — project rules and MVC boundaries.
- [docs/design.md](docs/design.md) — Assignment 2 Part 1 design, sources,
  response contract, and limitations.
- [prompts/assignment-1-part2.md](prompts/assignment-1-part2.md) — selected
  SQLite/CRUD development prompt.
- [prompts/assignment-2-part1.md](prompts/assignment-2-part1.md) — selected
  nearby-hotels and Leaflet development prompt.
- [handoffs/current.md](handoffs/current.md) — current evidence, limitations,
  and handoff status.

Remaining limitations are the provider's external availability, dependence on
network-loaded map tiles, and the lack of live reproduction for no-results or
provider-outage states. Geoapify results remain informational and do not
establish booking availability. The next task is **Assignment 2 Part 2:
shortlist**.
