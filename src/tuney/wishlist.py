import sqlite3
from pathlib import Path

class Wishlist:

    def _connect(self, db_path):
        return sqlite3.connect(db_path)
    
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

    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = self._connect(db_path)

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
        pass

    def remove_item(self, id: int) -> None:
        pass

    def clear_wishlist(self) -> None:
        pass

    def update_item(self, id: int, fields: dict) -> None:
        pass

    def all_items(self) -> list[dict]:
        pass

    def get_item(self, id: int) -> dict | None:
        pass
