import unittest
from unittest import mock

from tuney import lastfm


def image_list(hash_="abc123") -> list[dict]:
    base = "https://lastfm.freetls.fastly.net/i/u"
    return [{"size": size, "#text": f"{base}/{size}/{hash_}.png"}
            for size in ("small", "medium", "large", "extralarge")]


def track_search(*names) -> dict:
    return {"results": {"trackmatches": {"track": [
        {"name": name, "artist": "Sexyy Red", "mbid": "", "listeners": "1000",
         "url": f"https://last.fm/{name}", "image": image_list()}
        for name in names]}}}


def album_search(*pairs) -> dict:
    return {"results": {"albummatches": {"album": [
        {"name": album, "artist": artist, "mbid": "",
         "url": "https://last.fm/a", "image": image_list()}
        for album, artist in pairs]}}}


def album_info(name="Hood Hottest Princess", artist="Sexyy Red",
               tracks=("Pound Town 2", "SkeeYee")) -> dict:
    return {"album": {
        "name": name,
        "artist": artist,
        "mbid": "mb-release",
        "url": "https://last.fm/album",
        "listeners": "50000",
        "playcount": "900000",
        "image": image_list(),
        "tags": {"tag": [{"name": "hip hop"}, {"name": "rap"}]},
        "tracks": {"track": [
            {"name": title, "artist": {"name": artist}} for title in tracks]},
        "wiki": {"summary": "A 2023 album. <a href='x'>Read more</a>"},
    }}


class CallTest(unittest.TestCase):
    """Every other function goes through `_call`, so the key check, the
    error-body check and the parameter shaping all live or die here."""

    def test_without_a_key_it_raises_instead_of_calling_out(self):
        with mock.patch.object(lastfm, "api_key", return_value=None), \
             mock.patch.object(lastfm.requests, "get") as get:
            with self.assertRaises(lastfm.LastfmError):
                lastfm._call("track.search", track="x")
        get.assert_not_called()

    def _get(self, payload):
        response = mock.Mock()
        response.json.return_value = payload
        return mock.patch.object(lastfm.requests, "get", return_value=response)

    def test_sends_json_format_and_drops_empty_parameters(self):
        with mock.patch.object(lastfm, "api_key", return_value="k"), \
             self._get({"ok": True}) as get:
            lastfm._call("track.getInfo", artist="A", track="T", mbid="")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["method"], "track.getInfo")
        self.assertEqual(params["format"], "json")
        self.assertEqual(params["api_key"], "k")
        self.assertNotIn("mbid", params)

    def test_an_error_body_raises_even_though_the_status_was_200(self):
        with mock.patch.object(lastfm, "api_key", return_value="k"), \
             self._get({"error": 6, "message": "Track not found"}):
            with self.assertRaises(lastfm.LastfmError) as caught:
                lastfm._call("track.getInfo", artist="A", track="T")
        self.assertIn("Track not found", str(caught.exception))

    def test_an_unreadable_body_raises_a_lastfm_error(self):
        response = mock.Mock()
        response.json.side_effect = ValueError("not json")
        with mock.patch.object(lastfm, "api_key", return_value="k"), \
             mock.patch.object(lastfm.requests, "get", return_value=response):
            with self.assertRaises(lastfm.LastfmError):
                lastfm._call("track.search", track="x")


class ImageTest(unittest.TestCase):
    """Last.fm answers "no artwork" with a placeholder image rather than with
    an empty field, so an unfiltered pick would hand every album the same grey
    star and call it a cover."""

    def test_picks_the_largest_size_at_original_resolution(self):
        self.assertEqual(
            lastfm._image(image_list()),
            "https://lastfm.freetls.fastly.net/i/u/abc123.png")

    def test_the_placeholder_star_counts_as_no_image(self):
        self.assertEqual(lastfm._image(image_list(lastfm._PLACEHOLDER)), "")

    def test_no_images_at_all_is_no_image(self):
        self.assertEqual(lastfm._image(None), "")
        self.assertEqual(lastfm._image([]), "")


class ShapeTest(unittest.TestCase):
    """Last.fm collapses single-element collections to the element itself and
    types every number as a string — both would break callers that expect the
    same dicts MusicBrainz results come in."""

    def test_a_lone_result_is_still_a_list(self):
        self.assertEqual(lastfm._as_list({"name": "x"}), [{"name": "x"}])

    def test_counts_come_back_as_integers(self):
        with mock.patch.object(lastfm, "_call",
                               return_value=track_search("SkeeYee")):
            tracks = lastfm.search_tracks(artist="Sexyy Red", title="SkeeYee",
                                          detail=False)
        self.assertEqual(tracks[0]["listeners"], 1000)
        self.assertEqual(tracks[0]["source"], "lastfm")

    def test_a_search_with_no_title_never_calls_out(self):
        with mock.patch.object(lastfm, "_call") as call:
            self.assertEqual(lastfm.search_tracks(artist="Sexyy Red"), [])
        call.assert_not_called()

    def test_the_wiki_link_is_stripped_from_the_summary(self):
        with mock.patch.object(lastfm, "_call", return_value=album_info()):
            info = lastfm.album_info("Sexyy Red", "Hood Hottest Princess")
        self.assertEqual(info["summary"], "A 2023 album.")


class AlbumTest(unittest.TestCase):
    def test_album_info_carries_the_tracklist_and_its_count(self):
        with mock.patch.object(lastfm, "_call", return_value=album_info()):
            info = lastfm.album_info("Sexyy Red", "Hood Hottest Princess")
        self.assertEqual(info["track_count"], 2)
        self.assertEqual([t["title"] for t in info["tracks"]],
                         ["Pound Town 2", "SkeeYee"])
        # Album tracklists carry no recording ids — a wishlist row added from
        # one has to be matched later, not silently given a wrong mb_id.
        self.assertEqual({t["mb_id"] for t in info["tracks"]}, {""})
        self.assertEqual(info["tags"], ["hip hop", "rap"])

    def test_search_prefers_albums_credited_to_the_named_artist(self):
        payload = album_search(("Hood Hottest Princess", "Someone Else"),
                               ("Hood Hottest Princess", "Sexyy Red"))
        with mock.patch.object(lastfm, "_call", return_value=payload):
            albums = lastfm.search_albums(artist="Sexyy Red",
                                          album="Hood Hottest Princess",
                                          detail=False)
        self.assertEqual([a["artist"] for a in albums], ["Sexyy Red"])

    def test_an_artist_nobody_is_credited_to_keeps_every_result(self):
        """Last.fm credits plenty of releases to a name the user wouldn't have
        typed; filtering to nothing would be worse than showing what matched
        the album name."""
        payload = album_search(("Hood Hottest Princess", "Various Artists"))
        with mock.patch.object(lastfm, "_call", return_value=payload):
            albums = lastfm.search_albums(artist="Sexyy Red",
                                          album="Hood Hottest Princess",
                                          detail=False)
        self.assertEqual(len(albums), 1)

    def test_a_failed_detail_fetch_leaves_a_usable_result(self):
        payload = album_search(("Hood Hottest Princess", "Sexyy Red"))
        calls = [payload, lastfm.LastfmError("down")]

        def call(method, **params):
            result = calls.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(lastfm, "_call", side_effect=call):
            albums = lastfm.search_albums(artist="Sexyy Red",
                                          album="Hood Hottest Princess")
        self.assertEqual(albums[0]["album"], "Hood Hottest Princess")
        self.assertEqual(albums[0]["tracks"], [])


class CoversTest(unittest.TestCase):
    def test_returns_one_artwork_shaped_candidate(self):
        with mock.patch.object(lastfm, "_call", return_value=album_info()):
            covers = lastfm.covers("Sexyy Red", "Hood Hottest Princess")
        self.assertEqual(len(covers), 1)
        self.assertEqual(covers[0]["source"], "lastfm")
        self.assertEqual(covers[0]["track_count"], 2)
        self.assertTrue(covers[0]["url"].startswith("https://"))
        # Nothing was downloaded, so no width is claimed for it.
        self.assertIsNone(covers[0]["expected_width"])

    def test_a_missing_key_yields_no_covers_rather_than_an_error(self):
        """search_covers must survive an unconfigured source — Last.fm is
        optional and the other three providers carry the search."""
        with mock.patch.object(lastfm, "api_key", return_value=None):
            self.assertEqual(lastfm.covers("Sexyy Red", "Anything"), [])

    def test_an_album_with_only_the_placeholder_yields_no_covers(self):
        payload = album_info()
        payload["album"]["image"] = image_list(lastfm._PLACEHOLDER)
        with mock.patch.object(lastfm, "_call", return_value=payload):
            self.assertEqual(lastfm.covers("Sexyy Red", "Hood Hottest Princess"),
                             [])
