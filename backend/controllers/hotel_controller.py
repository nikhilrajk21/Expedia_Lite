"""Hotel search business controller."""

from .database_controller import DatabaseController


class HotelController:
    """Contract: search(name) returns the established Part 1 results list."""

    def __init__(self, database: DatabaseController) -> None:
        self._database = database

    def search(self, name: str) -> list[dict[str, object]]:
        return self._database.search_hotels(name)
