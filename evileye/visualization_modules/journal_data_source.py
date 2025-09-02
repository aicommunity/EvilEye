from typing import List, Dict, Tuple, Callable, Optional, Protocol


class EventJournalDataSource(Protocol):
    def fetch(self, page: int, size: int, filters: Dict, sort: List[Tuple[str, str]]) -> List[Dict]:
        """Return list of event dicts for page with filters and sort."""
        ...

    def get_total(self, filters: Dict) -> int:
        """Return total events count for given filters."""
        ...

    def list_available_dates(self) -> List[str]:
        """List available date folders (YYYY_MM_DD)."""
        ...

    def set_base_dir(self, base_dir: str) -> None:
        ...

    def set_date(self, date_folder: Optional[str]) -> None:
        ...

    def watch_live(self, callback: Callable[[List[Dict]], None]) -> None:
        """Optional live updates. Can be no-op."""
        ...

    def close(self) -> None:
        ...





