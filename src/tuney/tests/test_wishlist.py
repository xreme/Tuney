import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from tuney import dbservice, library
from tuney.agents import activity, wishlist_tools
from tuney.wishlist import Wishlist


class WishlistDataLayerTest(unittest.TestCase):
    """CRUD against a real (temp-file) SQLite wishlist."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wl = Wishlist(self.path)

    def tearDown(self):
        self.wl.close()
        dbservice.shutdown(self.path)
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

    def test_remove_items_deletes_only_listed_and_returns_count(self):
        ids = [self.wl.add_item(artist=f"A{i}", title=f"T{i}") for i in range(5)]
        removed = self.wl.remove_items([ids[0], ids[2], ids[4]])
        self.assertEqual(removed, 3)
        self.assertEqual(
            sorted(r["id"] for r in self._reopen().all_items()),
            [ids[1], ids[3]],
        )

    def test_context_manager_closes_connection(self):
        with Wishlist(self.path) as wl:
            new_id = wl.add_item(artist="A", title="B")
        # The write committed before close, and the handle is now unusable.
        self.assertEqual(self._reopen().get_item(new_id)["title"], "B")
        with self.assertRaises(sqlite3.ProgrammingError):
            wl.all_items()

    def test_close_is_explicit(self):
        wl = Wishlist(self.path)
        wl.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            wl.all_items()

    def test_closing_one_handle_leaves_others_working(self):
        """A pane or modal closing its handle must not disturb a long-lived
        one, since they share a connection."""
        other = Wishlist(self.path)
        other.close()
        self.assertEqual(self.wl.add_item(artist="A", title="B"), 1)

    def test_remove_items_ignores_empty_and_missing_ids(self):
        ids = [self.wl.add_item(artist="A", title="B") for _ in range(2)]
        self.assertEqual(self.wl.remove_items([]), 0)
        # Duplicates and non-existent ids don't inflate the count.
        self.assertEqual(self.wl.remove_items([ids[0], ids[0], 99999]), 1)
        self.assertEqual(
            [r["id"] for r in self._reopen().all_items()], [ids[1]])


class _FakeTrack:
    """Minimal stand-in for a beets item — just the fields reconcile reads."""

    def __init__(self, id, mb_trackid="", artist="", title="", album="",
                 albumartist=""):
        self.id = id
        self.mb_trackid = mb_trackid
        self.artist = artist
        self.title = title
        self.album = album
        self.albumartist = albumartist


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
        self.wl.close()
        dbservice.shutdown(self.path)
        os.unlink(self.path)

    def _collection(self, *tracks):
        library.all_items = lambda: list(tracks)

    def test_skips_library_scan_when_nothing_pending(self):
        # An empty wishlist, and one that's already fully acquired, must not
        # trigger the (expensive) whole-collection scan — this is what made the
        # first load slow.
        scanned = []
        library.all_items = lambda: scanned.append(1) or []

        self.assertEqual(library.reconcile_wishlist(self.wl), [])  # empty
        self.wl.add_item(artist="A", title="B", status="acquired")
        self.assertEqual(library.reconcile_wishlist(self.wl), [])  # all acquired
        self.assertEqual(scanned, [], "reconcile scanned the library needlessly")

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

    def test_matches_by_name_when_mb_ids_differ_and_title_has_single_suffix(self):
        # The real "Sanguine Paradise" case: wishlist pinned one MusicBrainz
        # recording, the downloaded file carries a different recording id and a
        # "- Single" suffix baked into the title. The mb_id path misses; the
        # normalized name fallback should still catch it.
        item = self.wl.add_item(
            artist="Lil Uzi Vert", title="Sanguine Paradise", mb_id="rec-wl")
        self._collection(_FakeTrack(
            12284, mb_trackid="rec-file",
            artist="Lil Uzi Vert", title="Sanguine Paradise - Single"))

        updated = library.reconcile_wishlist(self.wl)

        self.assertEqual([u["id"] for u in updated], [item])
        self.assertEqual(self.wl.get_item(item)["status"], "acquired")
        self.assertEqual(self.wl.get_item(item)["acquired_id"], 12284)

    def test_name_match_ignores_whitespace_and_ep_suffix(self):
        item = self.wl.add_item(artist="Some Artist", title="My Record")
        self._collection(_FakeTrack(
            7, artist="  some artist ", title="My Record - EP"))
        self.assertEqual(
            [u["id"] for u in library.reconcile_wishlist(self.wl)], [item])

    def test_name_match_does_not_over_strip(self):
        # "Single" as a real word must not be treated as a release qualifier.
        self.wl.add_item(artist="Beyoncé", title="Single Ladies")
        self._collection(_FakeTrack(9, artist="Beyoncé", title="Single"))
        self.assertEqual(library.reconcile_wishlist(self.wl), [])


class AddWishlistToolTest(unittest.TestCase):
    """The agent-facing add tools: add_wishlist_item and add_wishlist_items."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wl = Wishlist(self.path)
        # Point the tools' shared connection at this temp DB.
        self._saved = wishlist_tools._wishlist
        wishlist_tools._wishlist = self.wl
        # The add tools check the collection; default to an empty one so a
        # test that isn't about ownership never touches the real beets library.
        self._real_all_items = library.all_items
        self._collection()

    def tearDown(self):
        library.all_items = self._real_all_items
        wishlist_tools._wishlist = self._saved
        self.wl.close()
        dbservice.shutdown(self.path)
        os.unlink(self.path)

    def _collection(self, *tracks):
        library.all_items = lambda: list(tracks)

    def _added(self, *items, **kwargs):
        """add_wishlist_items' result, parsed."""
        return json.loads(wishlist_tools.add_wishlist_items.invoke(
            {"items": list(items), **kwargs}))

    def test_add_item_returns_full_row_not_just_id(self):
        row = json.loads(wishlist_tools.add_wishlist_item.invoke(
            {"artist": "Radiohead", "title": "Creep"}))
        self.assertIsInstance(row["id"], int)
        self.assertEqual(row["artist"], "Radiohead")
        self.assertEqual(row["title"], "Creep")
        self.assertEqual(row["status"], "wanted")
        self.assertIsNone(row["already_owned"])

    def test_add_item_persists_all_optional_fields(self):
        row = json.loads(wishlist_tools.add_wishlist_item.invoke({
            "artist": "A", "title": "B", "album": "C", "year": 1999,
            "notes": "n", "priority": 5, "status": "ordered", "mb_id": "rec-1",
        }))
        stored = self.wl.get_item(row["id"])
        self.assertEqual(stored["album"], "C")
        self.assertEqual(stored["year"], 1999)
        self.assertEqual(stored["notes"], "n")
        self.assertEqual(stored["priority"], 5)
        self.assertEqual(stored["status"], "ordered")
        self.assertEqual(stored["mb_id"], "rec-1")

    def test_add_item_reports_a_song_the_user_already_owns(self):
        self._collection(_FakeTrack(55, artist="Radiohead", title="Creep"))
        row = json.loads(wishlist_tools.add_wishlist_item.invoke(
            {"artist": "Radiohead", "title": "Creep"}))
        # A single add is deliberate, so it still happens.
        self.assertEqual(row["already_owned"], 55)
        self.assertEqual(self.wl.get_item(row["id"])["title"], "Creep")

    def test_add_items_returns_every_created_row_in_order(self):
        result = self._added(
            {"artist": "Larry June", "title": "Flex", "album": "Who Coppin",
             "mb_id": "rec-1", "year": 2024},
            {"artist": "Larry June", "title": "Who Coppin", "mb_id": "rec-2"},
        )
        rows = result["added"]
        self.assertEqual([r["title"] for r in rows], ["Flex", "Who Coppin"])
        self.assertEqual(rows[0]["album"], "Who Coppin")
        self.assertEqual(rows[0]["mb_id"], "rec-1")
        self.assertEqual(result["already_owned"], [])
        for r in rows:
            self.assertEqual(self.wl.get_item(r["id"])["title"], r["title"])

    def test_add_items_ignores_unknown_keys(self):
        rows = self._added({"artist": "A", "title": "B",
                            "score": 0.9, "junk": "x"})["added"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("score", self.wl.get_item(rows[0]["id"]))

    def test_add_items_skips_rows_missing_both_artist_and_title(self):
        rows = self._added(
            {"artist": "", "title": ""},
            {"notes": "orphan"},
            {"artist": "Keeps", "title": "This"},
        )["added"]
        self.assertEqual([r["title"] for r in rows], ["This"])
        self.assertEqual(len(self.wl.all_items()), 1)

    def test_add_items_keeps_row_with_only_a_title(self):
        rows = self._added({"title": "Untitled Demo"})["added"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Untitled Demo")

    def test_add_items_skips_owned_tracks_and_reports_them(self):
        # Wishlisting a whole album the user already has.
        self._collection(
            _FakeTrack(101, artist="BabyTron", title="Genesis 1:1"),
            _FakeTrack(102, mb_trackid="rec-myspace", artist="X", title="Y"),
        )
        result = self._added(
            {"artist": "BabyTron", "title": "Genesis 1:1", "album": "BR3"},
            {"artist": "BabyTron", "title": "Myspace", "mb_id": "rec-myspace"},
            {"artist": "BabyTron", "title": "Silly Me", "album": "BR3"},
        )

        self.assertEqual([r["title"] for r in result["added"]], ["Silly Me"])
        self.assertTrue(result["skipped_owned"])
        self.assertEqual(
            [(o["title"], o["beets_id"]) for o in result["already_owned"]],
            [("Genesis 1:1", 101), ("Myspace", 102)])
        self.assertFalse(any(o["added"] for o in result["already_owned"]))
        self.assertEqual([i["title"] for i in self.wl.all_items()], ["Silly Me"])

    def test_add_items_adds_owned_tracks_when_skip_owned_is_off(self):
        # Wanting a better copy of something owned is legitimate.
        self._collection(_FakeTrack(101, artist="BabyTron", title="Genesis 1:1"))
        result = self._added(
            {"artist": "BabyTron", "title": "Genesis 1:1"}, skip_owned=False)

        self.assertEqual([r["title"] for r in result["added"]], ["Genesis 1:1"])
        self.assertFalse(result["skipped_owned"])
        self.assertTrue(result["already_owned"][0]["added"])

    def test_add_items_scans_the_collection_once_for_the_whole_batch(self):
        scans = []
        library.all_items = lambda: scans.append(1) or []
        self._added(*[{"artist": "A", "title": str(n)} for n in range(20)])
        self.assertEqual(len(scans), 1)

    def test_add_item_records_a_change(self):
        before = activity.recorded_changes()
        wishlist_tools.add_wishlist_item.invoke(
            {"artist": "Radiohead", "title": "Creep"})
        self.assertEqual(activity.recorded_changes(), before + 1)

    def test_add_items_records_one_change_for_the_batch(self):
        before = activity.recorded_changes()
        self._added({"artist": "A", "title": "B"}, {"artist": "C", "title": "D"})
        self.assertEqual(activity.recorded_changes(), before + 1)

    def test_add_items_records_nothing_when_everything_was_owned(self):
        self._collection(_FakeTrack(101, artist="BabyTron", title="Genesis 1:1"))
        before = activity.recorded_changes()
        result = self._added({"artist": "BabyTron", "title": "Genesis 1:1"})
        self.assertEqual(result["added"], [])
        self.assertEqual(activity.recorded_changes(), before)


class CollectionHasToolTest(unittest.TestCase):
    """collection_has — the wishlist agent's only window onto the
    collection."""

    def setUp(self):
        self._real_all_items = library.all_items

    def tearDown(self):
        library.all_items = self._real_all_items

    def _collection(self, *tracks):
        library.all_items = lambda: list(tracks)

    def _ask(self, **kwargs):
        return json.loads(wishlist_tools.collection_has.invoke(kwargs))

    def _tron(self):
        self._collection(
            _FakeTrack(1, artist="BabyTron", title="A", album="Megatron"),
            _FakeTrack(2, artist="BabyTron", title="B", album="Megatron"),
            _FakeTrack(3, artist="BabyTron & Cordae", title="Beetleborgs",
                       album="Bin Reaper 2", albumartist="BabyTron"),
            _FakeTrack(4, artist="Larry June", title="C", album="Spaceships"),
        )

    def test_lists_every_album_for_the_artist_with_counts(self):
        self._tron()
        result = self._ask(artist="BabyTron")
        self.assertEqual(result["albums"], {"Megatron": 2, "Bin Reaper 2": 1})
        self.assertEqual(result["owned_tracks"], 3)

    def test_matches_collaborations_via_albumartist(self):
        self._tron()
        self.assertIn("Bin Reaper 2", self._ask(artist="BabyTron")["albums"])

    def test_unknown_artist_is_an_empty_result_not_an_error(self):
        self._tron()
        result = self._ask(artist="Nobody At All")
        self.assertEqual(result["albums"], {})
        self.assertEqual(result["owned_tracks"], 0)

    def test_album_check_confirms_an_owned_album(self):
        self._tron()
        check = self._ask(artist="BabyTron", album="megatron")["album_check"]
        self.assertTrue(check["owned"])
        self.assertEqual(check["matched_album"], "Megatron")
        self.assertEqual(check["tracks_owned"], 2)

    def test_album_check_reports_an_unowned_album(self):
        self._tron()
        check = self._ask(artist="BabyTron",
                          album="Case Dismissed")["album_check"]
        self.assertFalse(check["owned"])
        self.assertEqual(check["related"], [])

    def test_album_check_surfaces_a_different_edition_as_related(self):
        # Owning "6 (Deluxe Edition)" is not owning "6", but reporting "6"
        # as simply missing is the wrong answer.
        self._collection(
            _FakeTrack(1, artist="BabyTron", title="A",
                       album="6 (Deluxe Edition)"))
        check = self._ask(artist="BabyTron", album="6")["album_check"]
        self.assertFalse(check["owned"])
        self.assertEqual(check["related"], [["6 (Deluxe Edition)", 1]])

    def test_track_check_answers_ownership_of_one_song(self):
        self._tron()
        owned = self._ask(artist="BabyTron", title="Beetleborgs")["track_check"]
        self.assertTrue(owned["owned"])
        self.assertEqual(owned["beets_id"], 3)
        self.assertEqual(owned["matches"][0]["artist"], "BabyTron & Cordae")
        missing = self._ask(artist="BabyTron", title="Nowhere")["track_check"]
        self.assertFalse(missing["owned"])
        self.assertIsNone(missing["beets_id"])

    def test_checks_are_absent_unless_asked_for(self):
        self._tron()
        result = self._ask(artist="BabyTron")
        self.assertNotIn("album_check", result)
        self.assertNotIn("track_check", result)


class RemoveWishlistToolTest(unittest.TestCase):
    """The agent-facing batch removal tool: remove_wishlist_items."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wl = Wishlist(self.path)
        self._saved = wishlist_tools._wishlist
        wishlist_tools._wishlist = self.wl

    def tearDown(self):
        wishlist_tools._wishlist = self._saved
        self.wl.close()
        dbservice.shutdown(self.path)
        os.unlink(self.path)

    def test_remove_items_reports_count_and_removed_rows(self):
        ids = [self.wl.add_item(artist=f"A{i}", title=f"T{i}") for i in range(3)]
        result = json.loads(wishlist_tools.remove_wishlist_items.invoke(
            {"item_ids": [ids[0], ids[2]]}))
        self.assertEqual(result["removed"], 2)
        self.assertEqual(
            {(i["id"], i["title"]) for i in result["items"]},
            {(ids[0], "T0"), (ids[2], "T2")})
        # Only the untouched item is left.
        self.assertEqual([r["id"] for r in self.wl.all_items()], [ids[1]])

    def test_remove_items_tolerates_missing_ids(self):
        keep = self.wl.add_item(artist="A", title="B")
        result = json.loads(wishlist_tools.remove_wishlist_items.invoke(
            {"item_ids": [999999]}))
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["items"], [])
        self.assertEqual([r["id"] for r in self.wl.all_items()], [keep])


class ArtistToolTest(unittest.TestCase):
    """The two Last.fm-backed browsing tools; only the source is stubbed."""

    def _lastfm(self, **kwargs):
        return mock.patch.multiple(wishlist_tools.lastfm, **kwargs)

    def test_top_albums_returns_ranked_rows_without_tracklists(self):
        albums = [{"source": "lastfm", "mb_id": "mb-1", "album": "A",
                   "artist": "Sexyy Red", "year": None, "rank": 1,
                   "playcount": 999, "url": "u", "image": "i",
                   "tracks": [], "track_count": None, "listeners": None,
                   "tags": []}]
        with self._lastfm(available=mock.DEFAULT,
                          artist_top_albums=mock.DEFAULT) as patched:
            patched["available"].return_value = True
            patched["artist_top_albums"].return_value = albums
            rows = json.loads(
                wishlist_tools.artist_top_albums.invoke({"artist": "Sexyy Red"}))
        self.assertEqual(rows[0]["album"], "A")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertIsNone(rows[0]["year"])
        # An empty tracklist here would read as "this album has no songs".
        self.assertNotIn("tracks", rows[0])
        self.assertNotIn("track_count", rows[0])

    def test_top_albums_caps_a_runaway_limit(self):
        with self._lastfm(available=mock.DEFAULT,
                          artist_top_albums=mock.DEFAULT) as patched:
            patched["available"].return_value = True
            patched["artist_top_albums"].return_value = []
            wishlist_tools.artist_top_albums.invoke(
                {"artist": "Sexyy Red", "limit": 5000})
        self.assertEqual(patched["artist_top_albums"].call_args.kwargs["limit"],
                         wishlist_tools._MAX_ALBUMS)

    def test_top_albums_without_a_key_answers_in_plain_text(self):
        with self._lastfm(available=mock.DEFAULT) as patched:
            patched["available"].return_value = False
            result = wishlist_tools.artist_top_albums.invoke(
                {"artist": "Sexyy Red"})
        self.assertIn("No Last.fm API key", result)

    def test_correction_reports_the_canonical_spelling(self):
        with self._lastfm(available=mock.DEFAULT,
                          artist_correction=mock.DEFAULT) as patched:
            patched["available"].return_value = True
            patched["artist_correction"].return_value = {
                "source": "lastfm", "artist": "Guns N' Roses", "mb_id": "",
                "url": "u", "corrected": True}
            row = json.loads(wishlist_tools.correct_artist_name.invoke(
                {"artist": "Guns and Roses"}))
        self.assertEqual(row["artist"], "Guns N' Roses")
        self.assertTrue(row["corrected"])

    def test_an_unknown_artist_is_an_answer_not_a_failure(self):
        """An artist Last.fm has never heard of must come back in words,
        not as a broken lookup."""
        error = wishlist_tools.lastfm.LastfmError(
            "The artist you supplied could not be found")
        with self._lastfm(available=mock.DEFAULT,
                          artist_correction=mock.DEFAULT) as patched:
            patched["available"].return_value = True
            patched["artist_correction"].side_effect = error
            result = wishlist_tools.correct_artist_name.invoke(
                {"artist": "zzzznotanartistzzzz"})
        self.assertIn("no artist matching", result)
        self.assertNotIn("lookup failed", result)

    def test_a_genuine_failure_still_reads_as_a_failure(self):
        error = wishlist_tools.lastfm.LastfmError("Last.fm request failed")
        with self._lastfm(available=mock.DEFAULT,
                          artist_correction=mock.DEFAULT) as patched:
            patched["available"].return_value = True
            patched["artist_correction"].side_effect = error
            result = wishlist_tools.correct_artist_name.invoke({"artist": "X"})
        self.assertIn("lookup failed", result)


if __name__ == "__main__":
    unittest.main()
