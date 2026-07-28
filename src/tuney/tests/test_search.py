"""The merged metadata search: two sources in, one ranked list out.

The wishlist UI shows exactly what these functions return, so what is tested
here is what the user sees — no duplicate row for a record both services know,
no lost row for a record only one of them knows, and no dead source taking the
whole search down with it.
"""

import json
import unittest
from unittest import mock

from tuney import lastfm, library
from tuney.agents import wishlist_tools


def mb_track(artist="Sexyy Red", title="SkeeYee", album="Hood Hottest Princess",
             score=0.9, mb_id="rec-1") -> dict:
    return {"source": library.MUSICBRAINZ, "mb_id": mb_id, "artist": artist,
            "title": title, "album": album, "year": 2023, "score": score}


def lf_track(artist="Sexyy Red", title="SkeeYee", album="Hood Hottest Princess",
             listeners=1000) -> dict:
    return {"source": "lastfm", "mb_id": "", "artist": artist, "title": title,
            "album": album, "year": None, "listeners": listeners,
            "playcount": 5000, "tags": ["rap"], "url": "https://last.fm/t",
            "image": "https://img/x.png"}


def mb_album(album="Hood Hottest Princess", artist="Sexyy Red", tracks=12,
             mb_id="rel-1") -> dict:
    return {"source": library.MUSICBRAINZ, "mb_id": mb_id, "album": album,
            "artist": artist, "year": 2023, "track_count": tracks,
            "tracks": [{"mb_id": f"t{i}", "artist": artist, "title": f"T{i}",
                        "album": album, "year": 2023} for i in range(tracks)]}


def lf_album(album="Hood Hottest Princess", artist="Sexyy Red", tracks=12,
             listeners=50000) -> dict:
    return {"source": "lastfm", "mb_id": "", "album": album, "artist": artist,
            "year": None, "track_count": tracks, "tracks": [],
            "listeners": listeners, "playcount": 1, "tags": ["rap"],
            "url": "https://last.fm/a", "image": ""}


def search_tracks(mb, lf, **kwargs):
    with mock.patch.object(library, "musicbrainz_candidates", return_value=mb), \
         mock.patch.object(library.lastfm, "search_tracks", return_value=lf):
        return library.search_tracks(**kwargs)


def search_albums(mb, lf, **kwargs):
    with mock.patch.object(library, "musicbrainz_albums", return_value=mb), \
         mock.patch.object(library.lastfm, "search_albums", return_value=lf):
        return library.search_albums(**kwargs)


class SearchTracksTest(unittest.TestCase):
    def test_both_sources_land_in_one_list(self):
        results = search_tracks([mb_track()],
                                [lf_track(title="Pound Town 2")],
                                artist="Sexyy Red", title="SkeeYee")
        self.assertEqual([r["source"] for r in results],
                         [library.MUSICBRAINZ, "lastfm"])

    def test_a_track_both_services_know_appears_once(self):
        results = search_tracks([mb_track()], [lf_track()],
                                artist="Sexyy Red", title="SkeeYee")
        self.assertEqual(len(results), 1)
        # The surviving row is the MusicBrainz one: it has the recording id the
        # wishlist stores.
        self.assertEqual(results[0]["mb_id"], "rec-1")

    def test_punctuation_differences_do_not_make_a_second_row(self):
        results = search_tracks([mb_track(title="Skee Yee")],
                                [lf_track(title="skee-yee")],
                                artist="Sexyy Red", title="Skee Yee")
        self.assertEqual(len(results), 1)

    def test_the_same_song_on_two_albums_stays_two_rows(self):
        """Which release to wishlist is the choice being offered — collapsing
        it would make the list shorter and useless."""
        results = search_tracks(
            [mb_track(album="Hood Hottest Princess", mb_id="a"),
             mb_track(album="In Sexyy We Trust", mb_id="b")],
            [], artist="Sexyy Red", title="SkeeYee")
        self.assertEqual(len(results), 2)

    def test_an_exact_title_match_outranks_a_better_scored_near_match(self):
        results = search_tracks(
            [mb_track(title="SkeeYee (Remix)", score=0.99)],
            [lf_track(title="SkeeYee", listeners=10)],
            artist="Sexyy Red", title="SkeeYee")
        self.assertEqual(results[0]["title"], "SkeeYee")

    def test_lastfm_only_results_are_ordered_by_audience(self):
        results = search_tracks([], [lf_track(album="A", listeners=10),
                                     lf_track(album="B", listeners=9000)],
                                artist="Sexyy Red", title="SkeeYee")
        self.assertEqual([r["album"] for r in results], ["B", "A"])

    def test_a_dead_source_does_not_fail_the_search(self):
        with mock.patch.object(library, "musicbrainz_candidates",
                               side_effect=RuntimeError("network down")), \
             mock.patch.object(library.lastfm, "search_tracks",
                               return_value=[lf_track()]):
            results = library.search_tracks(artist="Sexyy Red", title="SkeeYee")
        self.assertEqual([r["source"] for r in results], ["lastfm"])

    def test_an_unconfigured_lastfm_leaves_musicbrainz_working(self):
        from tuney import lastfm as lastfm_module
        with mock.patch.object(library, "musicbrainz_candidates",
                               return_value=[mb_track()]), \
             mock.patch.object(library.lastfm, "search_tracks",
                               side_effect=lastfm_module.LastfmError("no key")):
            results = library.search_tracks(artist="Sexyy Red", title="SkeeYee")
        self.assertEqual([r["source"] for r in results], [library.MUSICBRAINZ])

    def test_nothing_anywhere_is_an_empty_list(self):
        self.assertEqual(search_tracks([], [], artist="X", title="Y"), [])

    def test_the_limit_is_applied_to_the_merged_list(self):
        results = search_tracks(
            [mb_track(album=f"Album {i}", mb_id=str(i)) for i in range(5)],
            [lf_track(title="Other", album=f"LF {i}") for i in range(5)],
            artist="Sexyy Red", title="SkeeYee", limit=3)
        self.assertEqual(len(results), 3)


class SearchAlbumsTest(unittest.TestCase):
    def test_a_release_both_services_know_appears_once(self):
        results = search_albums([mb_album()], [lf_album()],
                                artist="Sexyy Red", album="Hood Hottest Princess")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], library.MUSICBRAINZ)

    def test_a_differing_track_count_does_not_resurrect_the_duplicate(self):
        """The two services disagree about bonus tracks constantly; keying the
        cross-source match on the count would leave a near-duplicate row for
        most albums."""
        results = search_albums([mb_album(tracks=12)], [lf_album(tracks=14)],
                                artist="Sexyy Red", album="Hood Hottest Princess")
        self.assertEqual(len(results), 1)

    def test_a_deluxe_edition_stays_its_own_row(self):
        results = search_albums(
            [mb_album(tracks=12, mb_id="std"),
             mb_album(album="Hood Hottest Princess (Deluxe)", tracks=18,
                      mb_id="dlx")],
            [], artist="Sexyy Red", album="Hood Hottest Princess")
        self.assertEqual(len(results), 2)

    def test_two_pressings_of_one_release_collapse(self):
        results = search_albums([mb_album(mb_id="us"), mb_album(mb_id="eu")],
                                [], artist="Sexyy Red",
                                album="Hood Hottest Princess")
        self.assertEqual(len(results), 1)

    def test_an_album_only_lastfm_knows_still_shows_up(self):
        results = search_albums([], [lf_album(album="Mixtape")],
                                artist="Sexyy Red", album="Mixtape")
        self.assertEqual([r["source"] for r in results], ["lastfm"])


class AlbumTracksTest(unittest.TestCase):
    def test_an_included_tracklist_is_used_as_is(self):
        album = mb_album(tracks=3)
        with mock.patch.object(library.lastfm, "album_tracks") as fetch:
            self.assertEqual(len(library.album_tracks(album)), 3)
        fetch.assert_not_called()

    def test_a_lastfm_album_without_one_is_fetched_on_demand(self):
        album = lf_album()
        album["tracks"] = []
        with mock.patch.object(library.lastfm, "album_tracks",
                               return_value=[{"title": "T1"}]) as fetch:
            tracks = library.album_tracks(album)
        fetch.assert_called_once()
        self.assertEqual(tracks, [{"title": "T1"}])

    def test_a_failed_fetch_is_an_empty_tracklist_not_a_crash(self):
        album = lf_album()
        album["tracks"] = []
        with mock.patch.object(library.lastfm, "album_tracks",
                               side_effect=RuntimeError("down")):
            self.assertEqual(library.album_tracks(album), [])


class SearchMusicToolTest(unittest.TestCase):
    """What the chat agent gets back. The tool's return value is the model's
    only ground truth, so an album that arrives without its songs is an album
    the agent will invent songs for."""

    def _invoke(self, **args):
        return json.loads(wishlist_tools.search_music.invoke(args))

    def test_singles_come_back_as_one_list_from_both_sources(self):
        with mock.patch.object(wishlist_tools.library, "search_tracks",
                               return_value=[mb_track(), lf_track()]) as search:
            results = self._invoke(artist="Sexyy Red", title="SkeeYee")
        self.assertEqual([r["source"] for r in results],
                         [library.MUSICBRAINZ, "lastfm"])
        self.assertEqual(search.call_args.kwargs["title"], "SkeeYee")

    def test_kind_album_searches_releases(self):
        with mock.patch.object(wishlist_tools.library, "search_albums",
                               return_value=[mb_album(tracks=2)]), \
             mock.patch.object(wishlist_tools.library, "album_tracks",
                               side_effect=lambda album: album["tracks"]):
            results = self._invoke(artist="Sexyy Red",
                                   album="Hood Hottest Princess", kind="album")
        self.assertEqual(len(results[0]["tracks"]), 2)

    def test_an_album_missing_its_tracklist_is_filled_in_before_answering(self):
        empty = lf_album(tracks=0)
        empty["tracks"] = []
        songs = [{"mb_id": "", "artist": "Sexyy Red", "title": "T1",
                  "album": "Hood Hottest Princess", "year": None}]
        with mock.patch.object(wishlist_tools.library, "search_albums",
                               return_value=[empty]), \
             mock.patch.object(wishlist_tools.library, "album_tracks",
                               return_value=songs):
            results = self._invoke(artist="Sexyy Red",
                                   album="Hood Hottest Princess", kind="album")
        self.assertEqual(results[0]["tracks"], songs)
        self.assertEqual(results[0]["track_count"], 1)


class MusicInformationToolTest(unittest.TestCase):
    INFO = {"listeners": 1000, "playcount": 5000, "tags": ["rap"],
            "summary": "A song.", "image": "https://img/x.png"}

    def _invoke(self, **args):
        return wishlist_tools.music_information.invoke(args)

    def test_a_song_lookup_returns_the_lastfm_facts(self):
        with mock.patch.object(lastfm, "available", return_value=True), \
             mock.patch.object(lastfm, "track_info", return_value=self.INFO):
            result = json.loads(self._invoke(artist="Sexyy Red", title="SkeeYee"))
        self.assertEqual(result["listeners"], 1000)

    def test_an_album_lookup_goes_to_the_album_endpoint(self):
        with mock.patch.object(lastfm, "available", return_value=True), \
             mock.patch.object(lastfm, "album_info",
                               return_value=self.INFO) as album_info:
            self._invoke(artist="Sexyy Red", album="Hood Hottest Princess")
        album_info.assert_called_once()

    def test_no_key_is_reported_rather_than_answered_from_memory(self):
        """The agent is told to relay this sentence; a silent empty result
        would invite it to supply listener counts of its own."""
        with mock.patch.object(lastfm, "available", return_value=False):
            result = self._invoke(artist="Sexyy Red", title="SkeeYee")
        self.assertIn("No Last.fm API key", result)

    def test_an_unknown_record_says_so(self):
        with mock.patch.object(lastfm, "available", return_value=True), \
             mock.patch.object(lastfm, "track_info", return_value=None):
            result = self._invoke(artist="Sexyy Red", title="Nonexistent")
        self.assertIn("nothing on", result)

    def test_a_failed_lookup_is_reported_not_raised(self):
        with mock.patch.object(lastfm, "available", return_value=True), \
             mock.patch.object(lastfm, "track_info",
                               side_effect=lastfm.LastfmError("timed out")):
            result = self._invoke(artist="Sexyy Red", title="SkeeYee")
        self.assertIn("timed out", result)

    def test_artist_alone_asks_for_a_title_or_album(self):
        with mock.patch.object(lastfm, "available", return_value=True), \
             mock.patch.object(lastfm, "track_info") as track_info:
            result = self._invoke(artist="Sexyy Red")
        track_info.assert_not_called()
        self.assertIn("Pass a title", result)
