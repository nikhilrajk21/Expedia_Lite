# Expedia Lite — Part 2

## Repository and commit

The active branch is `assignment-1-part2-sqlite-crud`, created from Part 1 commit `f42f1548715981a1b06a6ac2e4cab3a90f882842` (`Document Expedia Lite Part 1`). No Part 2 commit has been made.

## Implementation

The backend initializes `data/expedia_lite.sqlite3`, seeds the supplied CSV rows once, and uses SQLite for hotel/stay search and booking CRUD. The Vue app provides hotel search, booking creation/history, cancellation, and test-booking deletion. Vite defaults to port-8000 API proxying and accepts `VITE_API_TARGET` for a local alternate backend port.

## Verification

- Hotel search — expected Harbor result with connected stays; observed HTTP 200 with `H001`, `T001`, and `T009` from the live SQLite backend. Browser search also displayed the two stays.
- Booking creation — expected unique new ID; observed `POST /api/bookings` created `B007` for supplied `U006`/`T012`.
- Booking history — expected the new record; observed `B007` in history with traveler, trip, hotel, and confirmed status.
- Cancellation while retaining the record — expected status change without deletion; observed `PATCH` changed `B007` to `cancelled` and history retained it.
- Deletion of a test booking — expected only test deletion; observed test `B008` deleted and absent from history; seeded `B001` deletion returned 409 in prior direct API verification.
- Browser refresh persistence — Not verified for booking CRUD because the automation browser could not reach the newly spawned Vite ports.
- Backend/frontend restart persistence — backend restart verified `B007` remains cancelled and `B008` remains absent; frontend-service/browser restart persistence Not verified.
- No duplicate seed records — expected 8/12/6/6 starter rows; observed unchanged counts across repeated initialization.
- Backend pytest — pytest import passed; test run collected 0 tests and exited 5.
- Frontend lint — `npm run lint` passed after the Vue change.
- Frontend production build — `npm run build` passed after the Vue change.

## Project context and next steps

Port 8000 is occupied by an unrelated stale service, so live Part 2 verification used port 8001 and `VITE_API_TARGET`. Review the uncommitted Part 2 changes, then approve the exact commit scope before any commit or push.
