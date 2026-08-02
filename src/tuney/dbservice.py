"""SQLite access for Tuney: one connection per thread, sharing a database file
with beets and the `beet` subprocesses.
"""

import sqlite3
import threading
from pathlib import Path

_BUSY_TIMEOUT_MS = 30_000


def connect(db_path) -> sqlite3.Connection:
    """A connection configured the way every Tuney connection should be."""
    connection = sqlite3.connect(str(db_path), check_same_thread=False,
                                 timeout=_BUSY_TIMEOUT_MS / 1000,
                                 isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def enable_wal(db_path) -> None:
    """Switch `db_path` to WAL mode without starting a service for it, so
    readers on connections Tuney doesn't own stop blocking on the writer.

    The mode is a persistent property of the file, so once is enough."""
    connect(db_path).close()


class DatabaseService:
    """Connections to `db_path`, one per thread that asks for one.

    Reads run on the calling thread and never block each other — that is what
    WAL buys. Writes hold `_write_lock` and run under BEGIN IMMEDIATE, which
    takes SQLite's write lock up front so `busy_timeout` can wait out beets
    instead of failing an upgrade halfway through a transaction."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._write_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._depth = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._state_lock:
            return self._closed

    def read(self, work):
        """Run `work(connection)` on the calling thread, outside any
        transaction of its own."""
        return work(self._connection())

    def write(self, work):
        """Run `work(connection)` in a transaction that commits on return and
        rolls back if it raises.

        Work that calls back into the data layer — reconcile does — joins the
        transaction already open on this thread rather than starting a second
        one."""
        with self._write_lock:
            connection = self._connection()
            if self._depth:
                self._depth += 1
                try:
                    return work(connection)
                finally:
                    self._depth -= 1

            connection.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                result = work(connection)
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")
                return result
            finally:
                self._depth = 0

    def close(self) -> None:
        """Close every connection handed out for this database. Work already
        running on another thread fails rather than hanging."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            connections, self._connections = self._connections, []
        for connection in connections:
            connection.close()

    def _connection(self) -> sqlite3.Connection:
        with self._state_lock:
            if self._closed:
                raise sqlite3.ProgrammingError(
                    f"Database service for {self.db_path} is closed.")
            existing = getattr(self._local, "connection", None)
            if existing is None:
                existing = connect(self.db_path)
                self._local.connection = existing
                self._connections.append(existing)
            return existing


_services: dict[str, DatabaseService] = {}
_services_lock = threading.Lock()


def service(db_path) -> DatabaseService:
    """The process-wide service for `db_path`, opened on first use."""
    key = str(Path(db_path).expanduser().resolve())
    with _services_lock:
        existing = _services.get(key)
        if existing is None or existing.closed:
            _services[key] = DatabaseService(key)
        return _services[key]


def shutdown(db_path=None) -> None:
    """Close the service for `db_path` (or every service). A later `service()`
    call transparently opens a new one."""
    with _services_lock:
        if db_path is None:
            targets = list(_services.values())
            _services.clear()
        else:
            key = str(Path(db_path).expanduser().resolve())
            targets = [_services.pop(key)] if key in _services else []
    for existing in targets:
        existing.close()
