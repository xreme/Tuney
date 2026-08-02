import sqlite3

from tuney import dbservice

class Wishlist:

    # Columns update_item is allowed to set. `id`/`date_added` are immutable and
    # `date_updated` is stamped automatically, so none of them are listed here.
    _UPDATABLE_COLUMNS = (
        "artist", "title", "album", "year", "mb_id",
        "notes", "priority", "status", "acquired_id",
    )

    def _create_table(self):
        self._write(lambda connection: connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS wishlist(
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                artist              TEXT    NOT NULL DEFAULT '',
                title               TEXT    NOT NULL DEFAULT '',
                album               TEXT    NOT NULL DEFAULT '',
                year                INTEGER,
                date_added          TEXT    NOT NULL DEFAULT (datetime('now')),
                date_updated        TEXT    NOT NULL DEFAULT (datetime('now')),
                mb_id               TEXT    NOT NULL DEFAULT '',
                notes               TEXT    NOT NULL DEFAULT '',
                priority            INTEGER NOT NULL DEFAULT 0,
                status              TEXT    NOT NULL DEFAULT 'wanted',
                acquired_id         INTEGER
            );
            '''
        ))

    def __init__(self, db_path):
        # No connection of its own: statements run on this thread's connection
        # to the shared database (see tuney/dbservice.py).
        self.db_path = db_path
        self._service = dbservice.service(db_path)
        self._closed = False
        self._create_table()

    def _read(self, work):
        self._check_open()
        return self._service.read(work)

    def _write(self, work):
        self._check_open()
        return self._service.write(work)

    def _check_open(self) -> None:
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed Wishlist.")

    def close(self) -> None:
        """Stop using the wishlist through this object. Connections are shared
        and outlive any one Wishlist, so this only marks the instance closed."""
        self._closed = True

    def __enter__(self) -> "Wishlist":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def add_item(
        self,
        artist: str = "",
        title: str = "",
        album: str = "",
        year: int | None = None,
        mb_id: str = "",
        notes: str = "",
        priority: int = 0,
        status: str = "wanted",
    ) -> int:
        def work(connection):
            cur = connection.execute(
                '''
                    INSERT INTO wishlist (artist, title, album, year, mb_id, notes, priority, status)
                    VALUES (?,?,?,?,?,?,?,?)
                ''',
                (artist,title,album,year,mb_id,notes,priority,status)
            )
            return cur.lastrowid

        return self._write(work)

    def remove_item(self, id: int) -> None:
        self._write(lambda connection: connection.execute(
            "DELETE FROM wishlist WHERE id = ?", (id,)))

    def remove_items(self, ids) -> int:
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))

        def work(connection):
            cur = connection.execute(
                f"DELETE FROM wishlist WHERE id IN ({placeholders})", ids)
            return cur.rowcount

        return self._write(work)

    def clear_wishlist(self) -> None:
        self._write(lambda connection: connection.execute("DELETE FROM wishlist"))

    def update_item(self, id: int, fields: dict) -> None:
        # Only touch known columns so a stray/hostile key can't be spliced into
        # the SQL; the values themselves always go through placeholders.
        columns = [name for name in fields if name in self._UPDATABLE_COLUMNS]
        if not columns:
            return
        assignments = ", ".join(f"{name} = ?" for name in columns)
        values = [fields[name] for name in columns]
        self._write(lambda connection: connection.execute(
            f"UPDATE wishlist SET {assignments}, date_updated = datetime('now')"
            " WHERE id = ?",
            (*values, id),
        ))

    def all_items(self) -> list[dict]:
        return self._read(lambda connection: [
            dict(r) for r in connection.execute("SELECT * FROM wishlist")])

    def get_item(self, id: int) -> dict | None:
        def work(connection):
            row = connection.execute(
                "SELECT * FROM wishlist WHERE id = ?", (id,)
            ).fetchone()
            return dict(row) if row else None

        return self._read(work)
