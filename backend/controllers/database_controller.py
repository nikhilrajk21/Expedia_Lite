"""Database controller: SQLite lifecycle, references, and model CRUD.

Public contract:
* search_hotels(name) -> list[dict] using the Part 1 response shape
* create_booking(Booking) -> Booking, after validating user_id and trip_id
* list_booking_history() -> list[dict] with booking display relationships
* cancel_booking(booking_id) -> Booking, retaining the database record
* delete_test_booking(booking_id) -> None, only when is_test is true
"""

import csv
import sqlite3
from pathlib import Path

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from models import Booking, Hotel, Trip
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.models import Booking, Hotel, Trip


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "expedia_lite.sqlite3"
SEED_VERSION = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hotels (
    hotel_id TEXT PRIMARY KEY,
    hotel_name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    nightly_rate_usd INTEGER NOT NULL CHECK (nightly_rate_usd >= 0)
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY,
    hotel_id TEXT NOT NULL,
    trip_name TEXT NOT NULL,
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL,
    FOREIGN KEY (hotel_id) REFERENCES hotels (hotel_id),
    CHECK (check_out > check_in)
);
CREATE TABLE IF NOT EXISTS bookings (
    booking_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    trip_id TEXT NOT NULL,
    booked_on TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('confirmed', 'cancelled')),
    is_test INTEGER NOT NULL DEFAULT 0 CHECK (is_test IN (0, 1)),
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id)
);
CREATE TABLE IF NOT EXISTS app_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trips_hotel_id ON trips (hotel_id);
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_trip_id ON bookings (trip_id);
"""

ASSIGNMENT_2_SAVED_HOTELS_MIGRATION = """
CREATE TABLE IF NOT EXISTS saved_hotels (
    hotel_id TEXT PRIMARY KEY,
    name TEXT,
    address TEXT,
    latitude REAL NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
    longitude REAL NOT NULL CHECK (longitude >= -180 AND longitude <= 180)
);
CREATE TABLE IF NOT EXISTS demo_hotel_nights (
    hotel_id TEXT NOT NULL,
    stay_date TEXT NOT NULL CHECK (
        stay_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND strftime('%Y-%m-%d', stay_date) = stay_date
    ),
    nightly_rate_cents INTEGER NOT NULL DEFAULT 10000
        CHECK (nightly_rate_cents >= 0),
    rooms_available INTEGER NOT NULL DEFAULT 20
        CHECK (rooms_available >= 0),
    PRIMARY KEY (hotel_id, stay_date),
    FOREIGN KEY (hotel_id) REFERENCES saved_hotels (hotel_id)
);
CREATE TABLE IF NOT EXISTS saved_hotel_locations (
    hotel_id TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
    longitude REAL NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
    PRIMARY KEY (hotel_id, zip_code),
    FOREIGN KEY (hotel_id) REFERENCES saved_hotels (hotel_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_hotel_locations_zip_code
    ON saved_hotel_locations (zip_code);
"""

CONVERSATION_HISTORY_MIGRATION = """
CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    stage TEXT NOT NULL CHECK (
        stage IN (
            'user_question', 'sql_proposal', 'executed_sql',
            'retrieved_records', 'assistant_answer', 'error'
        )
    ),
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation
    ON conversation_messages (conversation_id, timestamp, message_id);
"""


class ReferenceNotFoundError(LookupError):
    """A requested user, trip, or booking does not exist."""


class TestBookingDeletionError(PermissionError):
    """A caller attempted to delete a non-test booking."""


class DatabaseController:
    """Owns SQLite connections, relational checks, and model persistence."""

    def open(self) -> sqlite3.Connection:
        """Open a SQLite connection with FK enforcement enabled."""
        DATA_DIRECTORY.mkdir(exist_ok=True)
        connection = sqlite3.connect(DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize_database(self) -> bool:
        """Create schema and seed supplied CSV data exactly once.

        Returns True only during the first seed; later starts do not read CSVs.
        """
        with self.open() as connection:
            connection.executescript(SCHEMA)
            connection.executescript(ASSIGNMENT_2_SAVED_HOTELS_MIGRATION)
            connection.executescript(CONVERSATION_HISTORY_MIGRATION)
            seeded = connection.execute(
                "SELECT 1 FROM app_metadata WHERE metadata_key = ?",
                ("seed_version",),
            ).fetchone()
            if seeded is not None:
                return False
            self._seed_supplied_records(connection)
            connection.execute(
                "INSERT INTO app_metadata (metadata_key, metadata_value) VALUES (?, ?)",
                ("seed_version", SEED_VERSION),
            )
        return True

    def append_conversation_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        timestamp: str,
        role: str,
        stage: str,
        content: str,
    ) -> dict[str, str]:
        """Persist one labeled chat event independently from hotel reads."""
        with self.open() as connection:
            connection.execute(
                """
                INSERT INTO conversation_messages
                    (message_id, conversation_id, timestamp, role, stage, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, timestamp, role, stage, content),
            )
        return {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "timestamp": timestamp,
            "role": role,
            "stage": stage,
            "content": content,
        }

    def list_conversation_messages(self, conversation_id: str) -> list[dict[str, str]]:
        """Read one conversation's labeled history in insertion order."""
        with self.open() as connection:
            rows = connection.execute(
                """
                SELECT message_id, conversation_id, timestamp, role, stage, content
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY rowid
                """,
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_hotels(self, name: str) -> list[dict[str, object]]:
        """Read Hotel and Trip models and preserve the hotel-search contract."""
        search_text = name.strip().casefold()
        if not search_text:
            return []
        with self.open() as connection:
            hotel_rows = connection.execute(
                """
                SELECT hotel_id, hotel_name, city, state, nightly_rate_usd
                FROM hotels WHERE LOWER(hotel_name) LIKE ? ORDER BY hotel_id
                """,
                ("%" + search_text + "%",),
            ).fetchall()
            results = []
            for hotel_row in hotel_rows:
                hotel = Hotel.from_row(hotel_row)
                trip_rows = connection.execute(
                    """
                    SELECT trip_id, hotel_id, trip_name, check_in, check_out
                    FROM trips WHERE hotel_id = ? ORDER BY trip_id
                    """,
                    (hotel.hotel_id,),
                ).fetchall()
                results.append(hotel.to_search_dict([Trip.from_row(row) for row in trip_rows]))
        return results

    def save_saved_hotel(
        self,
        *,
        hotel_id: str,
        name: str | None,
        address: str | None,
        latitude: float,
        longitude: float,
        zip_code: str,
        search_latitude: float,
        search_longitude: float,
        stay_dates: tuple[str, ...],
    ) -> dict[str, object]:
        """Persist a provider hotel, its searched location, and demo nights idempotently."""
        with self.open() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO saved_hotels (hotel_id, name, address, latitude, longitude)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (hotel_id) DO NOTHING
                """,
                (hotel_id, name, address, latitude, longitude),
            )
            connection.execute(
                """
                INSERT INTO saved_hotel_locations
                    (hotel_id, zip_code, latitude, longitude)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (hotel_id, zip_code) DO NOTHING
                """,
                (hotel_id, zip_code, search_latitude, search_longitude),
            )
            for stay_date in stay_dates:
                connection.execute(
                    """
                    INSERT INTO demo_hotel_nights (hotel_id, stay_date)
                    VALUES (?, ?)
                    ON CONFLICT (hotel_id, stay_date) DO NOTHING
                    """,
                    (hotel_id, stay_date),
                )
            saved_row = connection.execute(
                "SELECT hotel_id, name, address, latitude, longitude "
                "FROM saved_hotels WHERE hotel_id = ?",
                (hotel_id,),
            ).fetchone()
            location_row = connection.execute(
                "SELECT zip_code, latitude, longitude FROM saved_hotel_locations "
                "WHERE hotel_id = ? AND zip_code = ?",
                (hotel_id, zip_code),
            ).fetchone()
            night_rows = connection.execute(
                "SELECT stay_date, nightly_rate_cents, rooms_available "
                "FROM demo_hotel_nights WHERE hotel_id = ? ORDER BY stay_date",
                (hotel_id,),
            ).fetchall()
        return {
            "hotel": self._saved_hotel_record(saved_row),
            "location": dict(location_row),
            "nights": [dict(row) for row in night_rows],
        }

    def list_saved_hotels_for_zip(self, zip_code: str) -> list[dict[str, object]]:
        """Return saved provider hotels associated with one searched ZIP."""
        with self.open() as connection:
            rows = connection.execute(
                """
                SELECT saved_hotels.hotel_id, saved_hotels.name,
                    saved_hotels.address, saved_hotels.latitude,
                    saved_hotels.longitude, saved_hotel_locations.zip_code,
                    saved_hotel_locations.latitude AS search_latitude,
                    saved_hotel_locations.longitude AS search_longitude
                FROM saved_hotels
                JOIN saved_hotel_locations
                    ON saved_hotel_locations.hotel_id = saved_hotels.hotel_id
                WHERE saved_hotel_locations.zip_code = ?
                ORDER BY saved_hotels.hotel_id
                """,
                (zip_code,),
            ).fetchall()
            saved_hotels = []
            for row in rows:
                night_rows = connection.execute(
                    "SELECT stay_date, nightly_rate_cents, rooms_available "
                    "FROM demo_hotel_nights WHERE hotel_id = ? ORDER BY stay_date",
                    (row["hotel_id"],),
                ).fetchall()
                saved_hotels.append(
                    {
                        "place_id": row["hotel_id"],
                        "name": row["name"],
                        "address": row["address"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "zip_code": row["zip_code"],
                        "center": {
                            "latitude": row["search_latitude"],
                            "longitude": row["search_longitude"],
                        },
                        "nights": [dict(night) for night in night_rows],
                    }
                )
        return saved_hotels

    def delete_saved_hotel(self, hotel_id: str) -> None:
        """Delete one saved hotel and all dependent local records in one transaction."""
        with self.open() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT 1 FROM saved_hotels WHERE hotel_id = ?", (hotel_id,)
            ).fetchone()
            if row is None:
                raise ReferenceNotFoundError("Saved hotel was not found.")
            connection.execute("DELETE FROM demo_hotel_nights WHERE hotel_id = ?", (hotel_id,))
            connection.execute("DELETE FROM saved_hotel_locations WHERE hotel_id = ?", (hotel_id,))
            connection.execute("DELETE FROM saved_hotels WHERE hotel_id = ?", (hotel_id,))

    @staticmethod
    def _saved_hotel_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "place_id": row["hotel_id"],
            "name": row["name"],
            "address": row["address"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
        }

    def create_booking(
        self, *, user_id: str, trip_id: str, booked_on: str, is_test: bool
    ) -> Booking:
        """Check foreign references and persist a new confirmed Booking model."""
        with self.open() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_reference(connection, "users", "user_id", user_id, "User")
            self._require_reference(connection, "trips", "trip_id", trip_id, "Trip")
            booking_id = self._next_booking_id(connection)
            connection.execute(
                """
                INSERT INTO bookings (booking_id, user_id, trip_id, booked_on, status, is_test)
                VALUES (?, ?, ?, ?, 'confirmed', ?)
                """,
                (booking_id, user_id, trip_id, booked_on, int(is_test)),
            )
            return self._booking_by_id(connection, booking_id)

    def list_booking_history(self) -> list[dict[str, object]]:
        """Read bookings with their User, Trip, and Hotel display relationships."""
        with self.open() as connection:
            rows = connection.execute(
                """
                SELECT bookings.booking_id, bookings.user_id, users.display_name,
                    bookings.trip_id, trips.trip_name, trips.hotel_id,
                    hotels.hotel_name, bookings.booked_on, bookings.status,
                    bookings.is_test
                FROM bookings
                JOIN users ON users.user_id = bookings.user_id
                JOIN trips ON trips.trip_id = bookings.trip_id
                JOIN hotels ON hotels.hotel_id = trips.hotel_id
                ORDER BY bookings.booked_on, bookings.booking_id
                """
            ).fetchall()
        return [self._history_record(row) for row in rows]

    def cancel_booking(self, booking_id: str) -> Booking:
        """Update only the status, retaining the Booking record."""
        with self.open() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_reference(connection, "bookings", "booking_id", booking_id, "Booking")
            connection.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE booking_id = ?",
                (booking_id,),
            )
            return self._booking_by_id(connection, booking_id)

    def delete_test_booking(self, booking_id: str) -> None:
        """Delete only explicitly marked test bookings."""
        with self.open() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT is_test FROM bookings WHERE booking_id = ?",
                (booking_id,),
            ).fetchone()
            if row is None:
                raise ReferenceNotFoundError("Booking " + booking_id + " was not found.")
            if not row["is_test"]:
                raise TestBookingDeletionError("Only test bookings can be deleted.")
            connection.execute("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))

    def _seed_supplied_records(self, connection: sqlite3.Connection) -> None:
        """Seed each supplied CSV in foreign-key-safe order."""
        hotels = self._read_csv_rows("hotels.csv")
        users = self._read_csv_rows("users.csv")
        trips = self._read_csv_rows("trips.csv")
        bookings = self._read_csv_rows("bookings.csv")
        connection.executemany(
            "INSERT INTO hotels (hotel_id, hotel_name, city, state, nightly_rate_usd) VALUES (:hotel_id, :hotel_name, :city, :state, :nightly_rate_usd)",
            hotels,
        )
        connection.executemany(
            "INSERT INTO users (user_id, display_name) VALUES (:user_id, :display_name)",
            users,
        )
        connection.executemany(
            "INSERT INTO trips (trip_id, hotel_id, trip_name, check_in, check_out) VALUES (:trip_id, :hotel_id, :trip_name, :check_in, :check_out)",
            trips,
        )
        connection.executemany(
            "INSERT INTO bookings (booking_id, user_id, trip_id, booked_on, status) VALUES (:booking_id, :user_id, :trip_id, :booked_on, :status)",
            bookings,
        )

    @staticmethod
    def _read_csv_rows(filename: str) -> list[dict[str, str]]:
        with (DATA_DIRECTORY / filename).open(encoding="utf-8-sig", newline="") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _require_reference(
        connection: sqlite3.Connection, table: str, column: str, value: str, model_name: str
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM " + table + " WHERE " + column + " = ?",
            (value,),
        ).fetchone()
        if row is None:
            raise ReferenceNotFoundError(model_name + " " + value + " was not found.")

    @staticmethod
    def _next_booking_id(connection: sqlite3.Connection) -> str:
        booking_ids = connection.execute("SELECT booking_id FROM bookings").fetchall()
        numeric_ids = [
            int(row["booking_id"][1:])
            for row in booking_ids
            if row["booking_id"].startswith("B") and row["booking_id"][1:].isdigit()
        ]
        return "B" + str(max(numeric_ids, default=0) + 1).zfill(3)

    def _booking_by_id(self, connection: sqlite3.Connection, booking_id: str) -> Booking:
        row = connection.execute(
            "SELECT booking_id, user_id, trip_id, booked_on, status, is_test FROM bookings WHERE booking_id = ?",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise ReferenceNotFoundError("Booking " + booking_id + " was not found.")
        return Booking.from_row(row)

    @staticmethod
    def _history_record(row: sqlite3.Row) -> dict[str, object]:
        record = dict(row)
        record["is_test"] = bool(record["is_test"])
        return record
