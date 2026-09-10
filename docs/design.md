# Expedia Lite Design

## Frontend responsibilities

The Vue application will provide the hotel-name search field, Search button, readable result table, and a clear no-results state. It will send JSON requests to FastAPI and render JSON responses.

## FastAPI responsibilities

The FastAPI application will define the HTTP API, validate request inputs, coordinate search and later booking operations, and return JSON responses. It will not contain Vue UI code.

## Backend responsibilities

For Part 1, Python backend logic will read the supplied `hotels.csv` and `trips.csv`, connect records using `hotel_id`, and return matching hotels with available stays.

For Part 2, after the supplied data is seeded, Python backend logic will use SQLite exclusively for all reads and writes. It will preserve supplied IDs, allocate unique IDs for new records, retain cancelled bookings in history, and permit deletion only for test bookings.

## Data flow

`Vue → JSON request → FastAPI → Python data layer → JSON response → Vue`

Part 1 uses supplied CSV files. Part 2 replaces runtime CSV access with SQLite after seeding.
