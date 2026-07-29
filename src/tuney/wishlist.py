import sqlite3

class Wishlist:

    # Columns update_item is allowed to set. `id`/`date_added` are immutable and
    # `date_updated` is stamped automatically, so none of them are listed here.
    _UPDATABLE_COLUMNS = (
        "artist", "title", "album", "year", "mb_id",
        "notes", "priority", "status", "acquired_id",
    )

    def _connect(self, db_path):
        # check_same_thread=False: the TUI reads the wishlist from a worker
        # thread (WishlistPane.reload) while the rest of the app uses it on the
        # main thread. Access is light and SQLite serializes writes, so one
        # shared connection is fine.
        #
        # timeout: Tuney.db is shared with the beets library, so several
        # connections (this one, the pane's reload thread, the agent's tools)
        # can try to write at once — e.g. a mass removal while the pane's
        # reconcile pass is running. Without a generous busy timeout the loser
        # of that race fails immediately with "database is locked"; 30s lets it
        # wait for the other writer to commit instead.
        return sqlite3.connect(db_path, check_same_thread=False, timeout=30)

    def _create_table(self):
        self.connection.execute(
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
        )
        self.connection.commit()

    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = self._connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self._create_table()

    def close(self) -> None:
        """Release the underlying SQLite connection. Transient callers (the TUI
        pane's reload/reconcile, the modals) open a Wishlist per operation
        against a DB shared with beets; leaving those connections open holds
        locks that later reads/writes then wait on, which is what left the
        wishlist pane stuck on 'loading…'. Prefer the context-manager form."""
        self.connection.close()

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
        cur = self.connection.execute(
            '''
                INSERT INTO wishlist (artist, title, album, year, mb_id, notes, priority, status)
                VALUES (?,?,?,?,?,?,?,?)
            ''',
            (artist,title,album,year,mb_id,notes,priority,status)
        ) 

        self.connection.commit()
        return cur.lastrowid 

    def remove_item(self, id: int) -> None:
        self.connection.execute("DELETE FROM wishlist WHERE id = ?", (id,))
        self.connection.commit()

    def remove_items(self, ids) -> int:
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        cur = self.connection.execute(
            f"DELETE FROM wishlist WHERE id IN ({placeholders})", ids)
        self.connection.commit()
        return cur.rowcount

    def clear_wishlist(self) -> None:
        self.connection.execute("DELETE FROM wishlist")
        self.connection.commit()

    def update_item(self, id: int, fields: dict) -> None:
        # Only touch known columns so a stray/hostile key can't be spliced into
        # the SQL; the values themselves always go through placeholders.
        columns = [name for name in fields if name in self._UPDATABLE_COLUMNS]
        if not columns:
            return
        assignments = ", ".join(f"{name} = ?" for name in columns)
        values = [fields[name] for name in columns]
        self.connection.execute(
            f"UPDATE wishlist SET {assignments}, date_updated = datetime('now')"
            " WHERE id = ?",
            (*values, id),
        )
        self.connection.commit()

    def all_items(self) -> list[dict]:
        return [dict(r) for r in self.connection.execute("SELECT * FROM wishlist")]

    def get_item(self, id: int) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM wishlist WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None