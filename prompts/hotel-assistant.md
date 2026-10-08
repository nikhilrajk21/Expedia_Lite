# Expedia Lite hotel assistant prompt contract

## Purpose

Answer business questions about hotels that have been saved locally from the
nearby-hotel API. The assistant may read the existing SQLite records, but it
must not create, update, or delete records. API search results that have not
been saved are not part of this assistant's data set.

## Actual SQLite schema used by the assistant

The database is `data/expedia_lite.sqlite3`. The approved tables and columns
are the following (verified against the existing database):

- `saved_hotels`: `hotel_id` (provider place ID, primary key), `name`,
  `address`, `latitude`, `longitude`.
- `saved_hotel_locations`: `hotel_id`, `zip_code`, `latitude`, `longitude`.
  Its composite primary key is `(hotel_id, zip_code)` and it preserves the
  searched ZIP/location association.
- `demo_hotel_nights`: `hotel_id`, `stay_date` (YYYY-MM-DD),
  `nightly_rate_cents`, `rooms_available`. Its composite primary key is
  `(hotel_id, stay_date)` and its foreign key references
  `saved_hotels.hotel_id`.

Required relationships:

1. `saved_hotels.hotel_id = saved_hotel_locations.hotel_id` joins a saved
   provider hotel to the ZIP and search-center context.
2. `saved_hotels.hotel_id = demo_hotel_nights.hotel_id` joins that hotel to
   its dated simulated rate and room-count records.

## Query rules

- Use the searched ZIP as a parameter on
  `saved_hotel_locations.zip_code`; never concatenate user text into SQL.
- When a question specifies dates, filter `demo_hotel_nights.stay_date` with
  parameterized `YYYY-MM-DD` values. The demo rows currently cover
  `2026-10-10` through `2026-10-14`.
- Available rooms means `rooms_available > 0`.
- Price ordering uses `demo_hotel_nights.nightly_rate_cents ASC` (or DESC
  only when the user explicitly asks for the most expensive first).
- Convert cents to dollars by dividing `nightly_rate_cents` by 100. These
  rates and room counts are simulated classroom data and must be labeled as
  such; they do not prove provider availability or a bookable price.
- If the requested date is absent, say that no saved record was found for
  that date. Do not fill the gap with an invented date, price, or room count.
- If no rows match, explain that no matching saved hotel records were found.

Only one parameterized, read-only `SELECT` statement is allowed. The backend
rejects writes (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`), `PRAGMA`,
`ATTACH`, multiple statements, comments, unknown tables, and unknown columns.
The approved tables are limited to the three tables above. A backend row limit
and execution-time limit are applied before results are sent to the final
answer prompt.
