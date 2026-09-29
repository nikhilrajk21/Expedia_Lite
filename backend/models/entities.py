"""Entity models and supplied-CSV relationships for Expedia Lite.

CSV contracts:
* hotels.csv: hotel_id, hotel_name, city, state, nightly_rate_usd
* trips.csv: trip_id, hotel_id, trip_name, check_in, check_out
* users.csv: user_id, display_name
* bookings.csv: booking_id, user_id, trip_id, booked_on, status

Relationships:
* one Hotel has many Trips through trips.hotel_id
* one User has many Bookings through bookings.user_id
* one Trip has many Bookings through bookings.trip_id
"""

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class Hotel:
    hotel_id: str
    hotel_name: str
    city: str
    state: str
    nightly_rate_usd: int

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "Hotel":
        return cls(
            hotel_id=str(row["hotel_id"]),
            hotel_name=str(row["hotel_name"]),
            city=str(row["city"]),
            state=str(row["state"]),
            nightly_rate_usd=int(row["nightly_rate_usd"]),
        )

    def to_search_dict(self, stays: list["Trip"]) -> dict[str, object]:
        """Preserve the Part 1 hotel-search response contract."""
        return {
            **asdict(self),
            "nightly_rate_usd": str(self.nightly_rate_usd),
            "available_stays": [stay.to_dict() for stay in stays],
        }


@dataclass(frozen=True)
class Trip:
    trip_id: str
    hotel_id: str
    trip_name: str
    check_in: str
    check_out: str

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "Trip":
        return cls(
            trip_id=str(row["trip_id"]),
            hotel_id=str(row["hotel_id"]),
            trip_name=str(row["trip_name"]),
            check_in=str(row["check_in"]),
            check_out=str(row["check_out"]),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class User:
    user_id: str
    display_name: str

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "User":
        return cls(user_id=str(row["user_id"]), display_name=str(row["display_name"]))


@dataclass(frozen=True)
class Booking:
    booking_id: str
    user_id: str
    trip_id: str
    booked_on: str
    status: str
    is_test: bool = False

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "Booking":
        return cls(
            booking_id=str(row["booking_id"]),
            user_id=str(row["user_id"]),
            trip_id=str(row["trip_id"]),
            booked_on=str(row["booked_on"]),
            status=str(row["status"]),
            is_test=bool(row["is_test"]),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
