# Expedia Lite Design

## Frontend responsibilities

Vue performs hotel/stay search, booking creation, history display, cancellation, and test-booking deletion through the FastAPI JSON API. It displays success and error status messages.

## FastAPI and SQLite responsibilities

FastAPI validates requests and serves `GET /api/hotels/search`, `GET /api/bookings`, `POST /api/bookings`, `PATCH /api/bookings/{booking_id}`, and `DELETE /api/bookings/{booking_id}`. Runtime reads and writes use SQLite at `data/expedia_lite.sqlite3`; supplied CSV files are used only for one-time seeding.

SQLite preserves supplied IDs and enforces `trips.hotel_id → hotels.hotel_id`, `bookings.user_id → users.user_id`, and `bookings.trip_id → trips.trip_id` with foreign keys enabled on each connection.

## Data flow

`Vue → JSON request → FastAPI → Python/SQLite → JSON response → Vue`
