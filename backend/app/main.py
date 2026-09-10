"""FastAPI endpoints for Expedia Lite Part 1 CSV search."""

import csv
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Query


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = PROJECT_ROOT / "data"
HOTELS_FILE = DATA_DIRECTORY / "hotels.csv"
TRIPS_FILE = DATA_DIRECTORY / "trips.csv"

app = FastAPI(title="Expedia Lite API")


def read_csv_rows(file_path: Path) -> list[dict[str, str]]:
    """Read a supplied CSV file with its header names preserved as JSON keys."""
    with file_path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


@app.get("/api/hotels/search")
def search_hotels(name: str = Query(default="", description="Hotel-name search text")) -> dict:
    """Return hotels whose names contain the query and their connected trip rows."""
    search_text = name.strip().casefold()
    if not search_text:
        return {"results": []}

    trips_by_hotel_id: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for trip in read_csv_rows(TRIPS_FILE):
        trips_by_hotel_id[trip["hotel_id"]].append(trip)

    results = []
    for hotel in read_csv_rows(HOTELS_FILE):
        if search_text in hotel["hotel_name"].casefold():
            results.append(
                {
                    **hotel,
                    "available_stays": trips_by_hotel_id[hotel["hotel_id"]],
                }
            )

    return {"results": results}
