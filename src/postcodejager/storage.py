"""SQLite persistence: tokens, collected PC4 set, last sync, seen activities."""
import json
import sqlite3
import threading


class Store:
    def __init__(self, db_path: str):
        # check_same_thread=False lets FastAPI's threadpool reuse one connection;
        # a reentrant lock then serializes access so concurrent requests (e.g. a
        # read endpoint racing the background sync) never misuse the connection.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.RLock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY)"
        )
        self._conn.commit()

    # --- meta key/value helpers -------------------------------------------
    def _set(self, key: str, value) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def _get(self, key: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    # --- token ------------------------------------------------------------
    def save_token(self, data: dict) -> None:
        self._set("token", data)

    def load_token(self) -> dict | None:
        return self._get("token")

    # --- collected PC4 set (union semantics) ------------------------------
    def set_collected(self, codes: set[str]) -> None:
        with self._lock:  # atomic read-modify-write (union, never shrink)
            merged = self.get_collected() | set(codes)
            self._set("collected", sorted(merged))

    def get_collected(self) -> set[str]:
        return set(self._get("collected") or [])

    # --- planned set (postcodes selected for the next route) --------------
    def get_planned(self) -> set[str]:
        return set(self._get("planned") or [])

    def set_planned(self, codes: set[str]) -> None:
        self._set("planned", sorted(set(codes)))

    def toggle_planned(self, code: str) -> set[str]:
        with self._lock:  # atomic read-modify-write
            planned = self.get_planned()
            planned.discard(code) if code in planned else planned.add(code)
            self.set_planned(planned)
            return planned

    def add_planned(self, codes: set[str]) -> set[str]:
        with self._lock:  # union many at once (box-select)
            merged = self.get_planned() | set(codes)
            self.set_planned(merged)
            return merged

    def clear_planned(self) -> None:
        self._set("planned", [])

    # --- last sync timestamp ----------------------------------------------
    def set_last_sync(self, epoch: int) -> None:
        self._set("last_sync", int(epoch))

    def get_last_sync(self) -> int | None:
        value = self._get("last_sync")
        return int(value) if value is not None else None

    # --- seen activity ids ------------------------------------------------
    def mark_activity(self, activity_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO activities (id) VALUES (?)", (activity_id,)
            )
            self._conn.commit()

    def seen_activity_ids(self) -> set[int]:
        with self._lock:
            return {row[0] for row in self._conn.execute("SELECT id FROM activities")}
