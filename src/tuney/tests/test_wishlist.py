import os
import tempfile
import time
import unittest

from tuney import library
from tuney.wishlist import Wishlist


class WishlistDataLayerTest(unittest.TestCase):
    """CRUD against a real (temp-file) SQLite wishlist."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wl = Wishlist(self.path)

    def tearDown(self):
        self.wl.connection.close()
        os.unlink(self.path)

    def _reopen(self) -> Wishlist:
        """A fresh connection to the same DB — proves a write was committed."""
        return Wishlist(self.path)

    def test_instance(self):
        self.assertIsInstance(self.wl, Wishlist)

    def test_add_returns_id_and_commits(self):
        new_id = self.wl.add_item(artist="Radiohead", title="Creep", year=1993)
        self.assertIsInstance(new_id, int)
        self.assertEqual(self._reopen().get_item(new_id)["title"], "Creep")

    def test_add_applies_defaults(self):
        new_id = self.wl.add_item(artist="A", title="B")
        item = self.wl.get_item(new_id)
        self.assertEqual(item["status"], "wanted")
        self.assertEqual(item["priority"], 0)
        self.assertIsNone(item["acquired_id"])
        self.assertTrue(item["date_added"])

    def test_all_items_returns_dicts_with_every_column(self):
        self.wl.add_item(artist="A", title="B")
        items = self.wl.all_items()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], dict)
        for column in ("id", "artist", "title", "album", "year", "date_added",
                       "date_updated", "mb_id", "notes", "priority", "status",
                       "acquired_id"):
            self.assertIn(column, items[0])

    def test_all_items_empty(self):
        self.assertEqual(self.wl.all_items(), [])

    def test_get_item_missing_returns_none(self):
        self.assertIsNone(self.wl.get_item(999))

    def test_update_changes_fields_and_bumps_timestamp(self):
        item_id = self.wl.add_item(artist="A", title="B")
        before = self.wl.get_item(item_id)["date_updated"]
        time.sleep(1)  # date_updated has one-second granularity
        self.wl.update_item(item_id, {"status": "acquired", "acquired_id": 42})
        item = self._reopen().get_item(item_id)
        self.assertEqual(item["status"], "acquired")
        self.assertEqual(item["acquired_id"], 42)
        self.assertNotEqual(item["date_updated"], before)

    def test_update_ignores_unknown_and_immutable_columns(self):
        item_id = self.wl.add_item(artist="A", title="B")
        self.wl.update_item(item_id, {"bogus": "x", "id": 123, "status": "ordered"})
        item = self.wl.get_item(item_id)
        self.assertEqual(item["id"], item_id)   # id is not updatable
        self.assertEqual(item["status"], "ordered")
        self.assertNotIn("bogus", item)

    def test_update_with_no_known_fields_is_noop(self):
        item_id = self.wl.add_item(artist="A", title="B")
        self.wl.update_item(item_id, {"unknown": 1})  # must not raise
        self.assertEqual(self.wl.get_item(item_id)["artist"], "A")

    def test_remove_item_commits(self):
        item_id = self.wl.add_item(artist="A", title="B")
        self.wl.remove_item(item_id)
        self.assertIsNone(self._reopen().get_item(item_id))

    def test_clear_wishlist(self):
        self.wl.add_item(artist="A", title="B")
        self.wl.add_item(artist="C", title="D")
        self.wl.clear_wishlist()
        self.assertEqual(self._reopen().all_items(), [])


class _FakeTrack:
    """Minimal stand-in for a beets item — just the fields reconcile reads."""

    def __init__(self, id, mb_trackid="", artist="", title=""):
        self.id = id
        self.mb_trackid = mb_trackid
        self.artist = artist
        self.title = title


class ReconcileTest(unittest.TestCase):
    """library.reconcile_wishlist against a real wishlist and a stubbed
    collection."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wl = Wishlist(self.path)
        self._real_all_items = library.all_items

    def tearDown(self):
        library.all_items = self._real_all_items
        self.wl.connection.close()
        os.unlink(self.path)

    def _collection(self, *tracks):
        library.all_items = lambda: list(tracks)

    def test_matches_by_mb_id_then_by_name(self):
        by_mb = self.wl.add_item(artist="X", title="Y", mb_id="rec-1")
        by_name = self.wl.add_item(artist="Boards of Canada", title="Roygbiv")
        unowned = self.wl.add_item(artist="Nobody", title="Owns This")
        self._collection(
            _FakeTrack(101, mb_trackid="rec-1", artist="A", title="B"),
            _FakeTrack(102, artist="boards of canada", title="roygbiv"),
        )
        updated = library.reconcile_wishlist(self.wl)

        self.assertEqual({u["id"] for u in updated}, {by_mb, by_name})
        self.assertEqual(self.wl.get_item(by_mb)["status"], "acquired")
        self.assertEqual(self.wl.get_item(by_mb)["acquired_id"], 101)
        self.assertEqual(self.wl.get_item(by_name)["acquired_id"], 102)
        self.assertEqual(self.wl.get_item(unowned)["status"], "wanted")
        self.assertIsNone(self.wl.get_item(unowned)["acquired_id"])

    def test_is_idempotent(self):
        self.wl.add_item(artist="X", title="Y", mb_id="rec-1")
        self._collection(_FakeTrack(101, mb_trackid="rec-1"))
        library.reconcile_wishlist(self.wl)
        self.assertEqual(library.reconcile_wishlist(self.wl), [])

    def test_no_matches(self):
        self.wl.add_item(artist="X", title="Y")
        self._collection(_FakeTrack(101, artist="Different", title="Track"))
        self.assertEqual(library.reconcile_wishlist(self.wl), [])


if __name__ == "__main__":
    unittest.main()
