"""Last.fm as a metadata source: track/album search, album detail, cover art.

Everything here deals in plain dicts and URLs — no beets objects, no library
writes — the same contract as `artwork.py`. `library.search_tracks` and
`library.search_albums` fold what comes back in with MusicBrainz so callers
(the wishlist UI, the agent) see one list of candidates rather than one list
per source.

Why a second source at all: MusicBrainz is an editorial database keyed on
release ids. It is authoritative about tracklists, and silent about anything
its editors never catalogued — a fair number of singles, mixtapes and regional
releases — and it says nothing about how popular a record is. Last.fm indexes
what people actually play, so it finds those releases, and it carries
listener/playcount/tag data, which is often the quickest way to tell an
original from a karaoke cover filed under the same artist and title.

Every call needs an API key (https://www.last.fm/api/account/create), read from
LASTFM_API_KEY or the system keychain. With no key configured every lookup here
raises LastfmError; the merged searches treat that like any other dead source
and carry on with MusicBrainz alone.
"""

import re

import requests

from tuney import credentials

SOURCE = "lastfm"

API_ROOT = "https://ws.audioscrobbler.com/2.0/"

_TIMEOUT = 15
_USER_AGENT = "Tuney/0.1 (music library manager)"

# The grey star Last.fm serves for entries that have no artwork. It is the same
# image — same hash — for every one of them, so the hash is the "no cover" test.
_PLACEHOLDER = "2a96cbd8b46e442fc41c2b86b821562f"

# Image URLs look like .../i/u/300x300/<hash>.png. Dropping the size segment
# serves the original upload, which is usually larger than any listed size.
_SIZE_SEGMENT = re.compile(r"/i/u/[^/]+/")

# Sizes Last.fm advertises, smallest first — the last one present wins.
_SIZE_ORDER = ["small", "medium", "large", "extralarge", "mega", ""]


class LastfmError(Exception):
    """A Last.fm lookup failed in a way worth telling the user about."""


def api_key() -> str | None:
    """The configured key, or None. Never raises — a broken keychain must not
    take down a search that MusicBrainz alone could still answer."""
    try:
        return credentials.get_lastfm_key()
    except Exception:
        return None


def available() -> bool:
    """Whether Last.fm can be queried at all (i.e. a key is configured)."""
    return bool(api_key())


def _call(method: str, **params) -> dict:
    """One Last.fm API call, as a dict. Empty parameters are dropped so an
    optional artist/mbid hint can always be passed straight through."""
    key = api_key()
    if not key:
        raise LastfmError(
            "no Last.fm API key configured — set LASTFM_API_KEY or save a key "
            "under Settings to include Last.fm in searches.")
    query = {name: value for name, value in params.items() if value}
    query.update(method=method, api_key=key, format="json")
    try:
        response = requests.get(API_ROOT, params=query, timeout=_TIMEOUT,
                                headers={"User-Agent": _USER_AGENT})
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        raise LastfmError(f"Last.fm request failed ({error})")
    if not isinstance(data, dict):
        return {}
    if data.get("error"):
        # Last.fm answers 200 with an error body for a bad key or bad query.
        raise LastfmError(data.get("message")
                          or f"Last.fm error {data['error']}")
    return data


def _as_list(value) -> list:
    """Last.fm collapses one-element collections to the element itself."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _name(value) -> str:
    """An artist field, which is a bare string in searches and a dict in the
    getInfo responses."""
    if isinstance(value, dict):
        return value.get("name") or ""
    return value or ""


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _image(images) -> str:
    """The largest real image URL in a Last.fm image list, at original size.

    Empty when the entry has no artwork — Last.fm says so by handing back the
    placeholder rather than by omitting the field.
    """
    urls = {entry.get("size") or "": entry.get("#text") or ""
            for entry in _as_list(images) if isinstance(entry, dict)}
    for size in reversed(_SIZE_ORDER):
        url = urls.get(size, "")
        if url and _PLACEHOLDER not in url:
            return _SIZE_SEGMENT.sub("/i/u/", url)
    return ""


def _tags(container) -> list[str]:
    """Tag names out of a `tags`/`toptags` block. Last.fm's tags are listener
    supplied, so they carry genre and mood the other sources don't have."""
    if isinstance(container, dict):
        container = container.get("tag")
    return [tag.get("name") for tag in _as_list(container)
            if isinstance(tag, dict) and tag.get("name")]


def _summary(wiki) -> str:
    """The wiki blurb, stripped of its trailing "Read more on Last.fm" link."""
    if not isinstance(wiki, dict):
        return ""
    text = wiki.get("summary") or ""
    text = re.sub(r"<a .*?</a>", "", text, flags=re.S)
    return " ".join(text.split()).strip()


# --- tracks ----------------------------------------------------------------


def _track(raw: dict, album: str = "") -> dict:
    """A search hit as a candidate dict, shaped like `library`'s MusicBrainz
    candidates plus the fields only Last.fm has."""
    return {
        "source": SOURCE,
        "mb_id": raw.get("mbid") or "",
        "artist": _name(raw.get("artist")),
        "title": raw.get("name") or "",
        "album": album,
        "year": None,
        "listeners": _int(raw.get("listeners")),
        "playcount": _int(raw.get("playcount")),
        "tags": [],
        "url": raw.get("url") or "",
        "image": _image(raw.get("image")),
    }


def track_info(artist: str, title: str, mbid: str = "") -> dict | None:
    """Everything Last.fm knows about one recording, or None if it knows none.

    `autocorrect` is on: Last.fm maps common misspellings onto its canonical
    artist/track names, which is exactly what a hand-typed wishlist row needs.
    """
    data = _call("track.getInfo", artist=artist, track=title, mbid=mbid,
                 autocorrect=1)
    raw = data.get("track")
    if not isinstance(raw, dict):
        return None
    album = raw.get("album") if isinstance(raw.get("album"), dict) else {}
    info = _track(raw, album=album.get("title") or "")
    info["artist"] = _name(raw.get("artist")) or artist
    info["tags"] = _tags(raw.get("toptags"))
    info["summary"] = _summary(raw.get("wiki"))
    info["image"] = _image(album.get("image")) or info["image"]
    info["album_url"] = album.get("url") or ""
    return info


def search_tracks(artist: str = "", title: str = "", limit: int = 5,
                  detail: bool = True) -> list[dict]:
    """Recordings matching `title` (and `artist` when given), best first.

    `detail` fills each hit in with a track.getInfo call — one per result, all
    of them off the UI thread. It is worth the round trips: track.search alone
    returns no album at all, and the album is half of what makes a candidate
    recognisable in a list.
    """
    if not title.strip():
        return []
    data = _call("track.search", track=title, artist=artist,
                 limit=max(limit, 1))
    matches = _as_list(((data.get("results") or {})
                        .get("trackmatches") or {}).get("track"))
    tracks = [_track(match) for match in matches[:limit]
              if isinstance(match, dict)]
    if detail:
        for track in tracks:
            _fill_track_detail(track)
    return tracks


def _fill_track_detail(track: dict) -> None:
    """Fold track.getInfo into a search hit, in place. Best effort — a result
    that can't be detailed is still a usable candidate."""
    try:
        info = track_info(track["artist"], track["title"], track["mb_id"])
    except LastfmError:
        return
    if not info:
        return
    for field in ("album", "playcount", "tags", "summary", "image"):
        if info.get(field) and not track.get(field):
            track[field] = info[field]
    track["mb_id"] = track["mb_id"] or info.get("mb_id", "")


# --- albums ----------------------------------------------------------------


def _album(raw: dict) -> dict:
    """A search hit as an album dict, shaped like `library.musicbrainz_albums`
    entries (so the two can share one table) plus the Last.fm-only fields."""
    return {
        "source": SOURCE,
        "mb_id": raw.get("mbid") or "",
        "album": raw.get("name") or raw.get("title") or "",
        "artist": _name(raw.get("artist")),
        "year": None,                    # Last.fm publishes no release date
        "track_count": None,
        "tracks": [],
        "listeners": _int(raw.get("listeners")),
        "playcount": _int(raw.get("playcount")),
        "tags": [],
        "url": raw.get("url") or "",
        "image": _image(raw.get("image")),
    }


def album_info(artist: str, album: str, mbid: str = "") -> dict | None:
    """One release with its tracklist, tags and cover, or None if unknown."""
    data = _call("album.getInfo", artist=artist, album=album, mbid=mbid,
                 autocorrect=1)
    raw = data.get("album")
    if not isinstance(raw, dict):
        return None
    info = _album(raw)
    info["artist"] = _name(raw.get("artist")) or artist
    info["tags"] = _tags(raw.get("tags"))
    info["summary"] = _summary(raw.get("wiki"))
    info["tracks"] = [{
        "source": SOURCE,
        "mb_id": "",                     # album tracklists carry no recording id
        "artist": _name(track.get("artist")) or info["artist"],
        "title": track.get("name") or "",
        "album": info["album"],
        "year": None,
    } for track in _as_list((raw.get("tracks") or {}).get("track"))
        if isinstance(track, dict)]
    info["track_count"] = len(info["tracks"])
    return info


def album_tracks(artist: str, album: str, mbid: str = "") -> list[dict]:
    """Just the tracklist for one release — for filling an album in after the
    user picks it, rather than paying for every result up front."""
    info = album_info(artist, album, mbid)
    return info["tracks"] if info else []


def search_albums(artist: str = "", album: str = "", limit: int = 5,
                  detail: bool = True) -> list[dict]:
    """Releases matching `album`, preferring those credited to `artist`.

    album.search takes no artist parameter, so the artist is applied as a
    filter here — and only when it matches something, since Last.fm credits
    plenty of releases to a name the user wouldn't have typed ("Various
    Artists", a featured-artist string). `detail` pulls each result's tracklist.
    """
    if not album.strip():
        return []
    # Over-fetch: the artist filter below is applied to whatever comes back,
    # and the wanted release is often not in the first `limit` global hits.
    data = _call("album.search", album=album, limit=max(limit * 4, limit))
    matches = [match for match in _as_list(
        ((data.get("results") or {}).get("albummatches") or {}).get("album"))
        if isinstance(match, dict)]

    wanted = _norm(artist)
    if wanted:
        credited = [match for match in matches
                    if _norm(_name(match.get("artist"))) == wanted]
        matches = credited or matches

    albums = [_album(match) for match in matches[:limit]]
    if detail:
        for entry in albums:
            _fill_album_detail(entry)
    return albums


def _fill_album_detail(entry: dict) -> None:
    """Fold album.getInfo into a search hit, in place. Best effort — an album
    with no tracklist yet is still offerable; `album_tracks` can fetch it when
    the user actually picks it."""
    try:
        info = album_info(entry["artist"], entry["album"], entry["mb_id"])
    except LastfmError:
        return
    if not info:
        return
    entry["tracks"] = info["tracks"]
    entry["track_count"] = info["track_count"]
    for field in ("listeners", "playcount", "tags", "summary", "image"):
        if info.get(field) and not entry.get(field):
            entry[field] = info[field]


# --- cover art -------------------------------------------------------------


def covers(artist: str, album: str) -> list[dict]:
    """The album's Last.fm image, shaped like `artwork.py`'s other providers.

    At most one candidate: Last.fm stores a single image per release, not a
    gallery. Empty when the release is unknown or carries the placeholder.
    """
    try:
        info = album_info(artist, album)
    except LastfmError:
        return []
    if not info or not info.get("image"):
        return []
    return [{
        "source": SOURCE,
        "title": info["album"],
        "artist": info["artist"],
        "track_count": info["track_count"],
        "year": None,
        "url": info["image"],
        # Last.fm advertises no dimensions for the original upload; whether it
        # clears the size floor is settled when the image is downloaded.
        "expected_width": None,
    }]


def _norm(text: str) -> str:
    """Casefolded, punctuation-light form for comparing names that different
    sources punctuate differently."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
