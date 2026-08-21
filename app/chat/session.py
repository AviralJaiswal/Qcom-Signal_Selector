from typing import Any


class SessionStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def create(self, session_id: str) -> dict[str, Any]:
        return self._data.setdefault(session_id, {})

    def get(self, session_id: str) -> dict[str, Any]:
        return self._data.setdefault(session_id, {})

    def update(self, session_id: str, values: dict[str, Any]) -> dict[str, Any]:
        self.get(session_id).update(values)
        return self.get(session_id)


session_store = SessionStore()

