# Expedia Lite Project Rules

- Treat this directory as the project root; never create a nested project directory.
- Keep the Vue frontend and FastAPI/Python backend in `frontend/` and `backend/`, respectively.
- Work Part 1 (CSV search) before implementing any Part 2 SQLite functionality.
- Use only supplied CSV files and supplied database records. Do not invent replacement data.
- Preserve supplied IDs. New records must receive unique IDs.
- Before adding a dependency, follow and document: CHECK, TAKE ACTION, VERIFY.
- Route all application actions through Vue, FastAPI, and Python/SQLite as applicable.
- Keep cancelled bookings in history; deletion is limited to test bookings.
- Record changed files, commands run, verification evidence, limitations, and the next task in `handoffs/current.md`.
- Do not state that a check passed unless it was actually run.

## MVC architecture

- Keep `frontend/` as the View. Vue components may manage presentation-only state
  and call documented HTTP endpoints, but must not access SQLite or CSV files.
- Keep entity definitions and relationship rules in `backend/models/`. The
  supplied data model is `Hotel (hotel_id)` → `Trip (hotel_id)`, and
  `User (user_id)` plus `Trip (trip_id)` → `Booking`.
- Keep database opening, schema initialization, CSV seeding, foreign-key checks,
  and model CRUD in `backend/controllers/database_controller.py`.
- Keep search and booking business workflows in separate controllers. Controllers
  may call another controller only through its documented Python input/output
  contract; routes must not issue SQL directly.
- Treat FastAPI routes as the Controller-to-View boundary. Preserve their JSON
  contracts: `GET /api/hotels/search` returns `{ "results": [...] }`,
  booking creation/cancellation returns `{ "booking": {...} }`, history
  returns `{ "bookings": [...] }`, and deletion returns
  `{ "deleted_booking_id": "..." }`.
- Models and controllers return JSON-ready dictionaries or typed model objects.
  Database/relationship errors become controller exceptions; FastAPI converts
  those into the existing HTTP error responses.
