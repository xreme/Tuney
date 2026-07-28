import os
import subprocess
from pathlib import Path
import beets
from beets.library import Library
from platformdirs import PlatformDirs

from tuney import config, lastfm

beets.config.read()
CONFIG = Path("config/beets.yaml")
dirs = PlatformDirs("Tuney")
os.makedirs(dirs.user_data_path, exist_ok=True)
DB = dirs.user_data_path/"Tuney.db"

# TODO implement library singleton

def _import_flags():
    mode = config.get_config().import_autotag
    if mode is config.ImportAutotagMode.OFF:
        return ["-A", "-q"]
    fallback = "skip" if mode is config.ImportAutotagMode.SAFE else "asis"
    return ["-q", f"--quiet-fallback={fallback}"]

_metadata_sources_loaded = False

def _ensure_metadata_sources():
    global _metadata_sources_loaded
    if not _metadata_sources_loaded:
        from beets import plugins
        plugins.load_plugins()
        _metadata_sources_loaded = True

def track_candidates(item, artist_hint: str = "", title_hint: str = ""):
    _ensure_metadata_sources()
    from beets import autotag
    return autotag.tag_item(item,
                            search_artist=artist_hint or None,
                            search_name=title_hint or None)

def apply_track_match(item, recording_id: str):
    _ensure_metadata_sources()
    from beets import autotag
    proposal = autotag.tag_item(item, search_ids=[recording_id])
    if not proposal.candidates:
        raise ValueError(f"No MusicBrainz recording found with id {recording_id}")
    match = proposal.candidates[0]   # a TrackMatch holding this same item
    match.apply_metadata()
    item.store()
    item.try_write()
    return match.info


def _track_info_dict(info, score=None):
    """Framework-agnostic view of a beets TrackInfo (a MusicBrainz recording),
    for callers that don't have (or want) a beets Item — e.g. the wishlist."""
    data = {
        "source": MUSICBRAINZ,
        "mb_id": getattr(info, "track_id", "") or "",
        "artist": getattr(info, "artist", "") or "",
        "title": getattr(info, "title", "") or "",
        "album": getattr(info, "album", "") or "",
        "year": getattr(info, "year", None),
    }
    if score is not None:
        data["score"] = score
    return data


MUSICBRAINZ = "musicbrainz"


def musicbrainz_candidates(artist: str = "", title: str = "", album: str = "",
                           limit: int = 5) -> list[dict]:
    """Search MusicBrainz for recordings matching an artist/title (and optional
    album), without needing a track already in the library. Returns up to
    `limit` candidate dicts (mb_id, artist, title, album, year, score), best
    match first; score is 0..1 where 1.0 is a perfect match. Empty list when
    MusicBrainz returns nothing. Use it to offer matches when adding a wishlist
    item; the chosen candidate's mb_id can then be stored on the item."""
    _ensure_metadata_sources()
    from beets import autotag
    from beets.library import Item
    item = Item(artist=artist, title=title, album=album)
    proposal = autotag.tag_item(item,
                                search_artist=artist or None,
                                search_name=title or None)
    return [_track_info_dict(match.info, round(1 - match.distance.distance, 3))
            for match in proposal.candidates[:limit]]


def musicbrainz_track(recording_id: str) -> dict | None:
    """Look up a single MusicBrainz recording by its id and return it as a dict
    (mb_id, artist, title, album, year), or None if no recording has that id.
    Use it to validate and flesh out an mb_id the user typed in directly when
    adding a wishlist item."""
    _ensure_metadata_sources()
    from beets import autotag
    from beets.library import Item
    proposal = autotag.tag_item(Item(), search_ids=[recording_id])
    if not proposal.candidates:
        return None
    return _track_info_dict(proposal.candidates[0].info)


def musicbrainz_albums(artist: str = "", album: str = "",
                       limit: int = 5) -> list[dict]:
    """Search MusicBrainz for full albums (releases) matching an artist and/or
    album name, without needing tracks already in the library. Returns up to
    `limit` distinct album dicts, each carrying its complete tracklist so the
    caller can offer "add the whole album" or let the user pick tracks:

        {mb_id, album, artist, year, track_count,
         tracks: [{mb_id, artist, title, album, year}, ...]}

    The top-level `mb_id` is the MusicBrainz release id; each track's `mb_id`
    is its recording id (what a wishlist item stores). Empty list when nothing
    matched. Album-match scoring is unreliable without real track data, so no
    score is returned — results are ordered as MusicBrainz ranks them."""
    _ensure_metadata_sources()
    from beets import autotag
    from beets.library import Item
    # tag_album needs at least one item; a single placeholder carrying the
    # search terms is enough to get candidates back with full tracklists.
    seed = Item(artist=artist, album=album, title="")
    _, _, proposal = autotag.tag_album(
        [seed], search_artist=artist or None, search_name=album or None)

    albums: list[dict] = []
    seen: set = set()
    for match in proposal.candidates:
        info = match.info
        # Collapse duplicate pressings of the same release (same name, artist,
        # and track count) — the user just wants the album, not a specific CD.
        key = ((info.album or "").lower(), (info.artist or "").lower(),
               len(info.tracks or []))
        if key in seen:
            continue
        seen.add(key)
        year = getattr(info, "year", None)
        tracks = [{
            "mb_id": getattr(track, "track_id", "") or "",
            "artist": getattr(track, "artist", "") or info.artist or "",
            "title": getattr(track, "title", "") or "",
            "album": info.album or "",
            "year": year,
        } for track in (info.tracks or [])]
        albums.append({
            "source": MUSICBRAINZ,
            "mb_id": getattr(info, "album_id", "") or "",
            "album": info.album or "",
            "artist": info.artist or "",
            "year": year,
            "track_count": len(tracks),
            "tracks": tracks,
        })
        if len(albums) >= limit:
            break
    return albums

# --- merged metadata search -------------------------------------------------
#
# One list of candidates from every source, not one list per source. The two
# have complementary blind spots — MusicBrainz has the release ids and the
# authoritative tracklists but only for what its editors catalogued; Last.fm
# has the long tail plus tags and listener counts — so a caller that only
# searched one of them would keep missing records the other could see.
#
# Every entry carries `source`; Last.fm entries additionally carry
# listeners/playcount/tags/url/image, which are absent (not empty) on
# MusicBrainz entries.

_SOURCE_ORDER = {MUSICBRAINZ: 0, lastfm.SOURCE: 1}


def _norm(text: str) -> str:
    """Casefolded, punctuation-light form used to compare names across sources
    that all punctuate differently."""
    return _re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _lastfm_only(entries: list[dict], primary: list[dict],
                 fields: tuple[str, ...]) -> list[dict]:
    """`entries` minus everything `primary` (the MusicBrainz results) already
    covers, matching on `fields`.

    Deliberately coarser than the within-source de-duplication below: the two
    services disagree about tracklist lengths and bonus tracks often enough
    that keying on those would leave a near-duplicate row for most albums, and
    when both know a record the MusicBrainz row is the better one to keep — it
    has the ids the wishlist stores.
    """
    known = {tuple(_norm(entry.get(field)) for field in fields)
             for entry in primary}
    return [entry for entry in entries
            if tuple(_norm(entry.get(field)) for field in fields) not in known]


def _dedupe(entries: list[dict], fields: tuple[str, ...]) -> list[dict]:
    """First entry wins for each distinct combination of `fields`. Names are
    compared normalized; anything else (a track count) compares as it is."""
    def part(value):
        return _norm(value) if isinstance(value, str) else value

    seen, unique = set(), []
    for entry in entries:
        key = tuple(part(entry.get(field)) for field in fields)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def search_tracks(artist: str = "", title: str = "", album: str = "",
                  limit: int = 5) -> list[dict]:
    """Candidate recordings for one song from every metadata source, best
    first — MusicBrainz and (when a key is configured) Last.fm, merged.

    Same dicts as `musicbrainz_candidates`, plus `source` and the Last.fm-only
    fields. A source that errors, is unconfigured or finds nothing simply
    contributes nothing; only an empty list means nothing matched anywhere.
    """
    try:
        primary = musicbrainz_candidates(artist=artist, title=title,
                                         album=album, limit=limit)
    except Exception:
        primary = []
    try:
        extra = lastfm.search_tracks(artist=artist, title=title, limit=limit)
    except Exception:
        extra = []

    # Same artist and title from both services is one candidate, but the same
    # artist and title on two different albums is two — that is the choice the
    # user is being asked to make.
    primary = _dedupe(primary, ("artist", "title", "album"))
    candidates = primary + _lastfm_only(extra, primary, ("artist", "title"))

    wanted = _norm(title)

    def rank(candidate: dict):
        # Exact title matches first; then MusicBrainz (it scores its own
        # matches and carries the recording id) ahead of Last.fm, whose only
        # ordering signal is how many people listen to the track.
        return (_norm(candidate.get("title")) != wanted,
                _SOURCE_ORDER.get(candidate.get("source"), 9),
                -(candidate.get("score") or 0),
                -(candidate.get("listeners") or 0))

    return sorted(candidates, key=rank)[:limit]


def search_albums(artist: str = "", album: str = "",
                  limit: int = 5) -> list[dict]:
    """Candidate releases from every metadata source, best first, each with
    its tracklist where the source provides one.

    Same dicts as `musicbrainz_albums`, plus `source` and the Last.fm-only
    fields. Last.fm entries can come back with an empty `tracks` list — use
    `album_tracks` rather than reading `tracks` directly.
    """
    try:
        primary = musicbrainz_albums(artist=artist, album=album, limit=limit)
    except Exception:
        primary = []
    try:
        extra = lastfm.search_albums(artist=artist, album=album, limit=limit)
    except Exception:
        extra = []

    # Two pressings of one release are one row; a standard and a deluxe edition
    # share a title but not a track count, and stay two.
    primary = _dedupe(primary, ("artist", "album", "track_count"))
    albums = primary + _lastfm_only(extra, primary, ("artist", "album"))

    wanted = _norm(album)

    def rank(entry: dict):
        return (_norm(entry.get("album")) != wanted,
                _SOURCE_ORDER.get(entry.get("source"), 9),
                -(entry.get("listeners") or 0))

    return sorted(albums, key=rank)[:limit]


def album_tracks(album: dict) -> list[dict]:
    """The tracklist of an album from `search_albums`, fetched on demand when
    its source didn't include one. Empty when the source has no tracklist for
    it at all."""
    tracks = album.get("tracks") or []
    if tracks or album.get("source") != lastfm.SOURCE:
        return tracks
    try:
        return lastfm.album_tracks(album.get("artist", ""),
                                   album.get("album", ""),
                                   album.get("mb_id", ""))
    except Exception:
        return []


def preview_track_match(item, recording_id: str) -> list[tuple[str, object, object]]:
    """The field changes `apply_track_match` would make: (field, old, new)
    rows. Nothing is stored or written — but the item is mutated in memory,
    so pass a throwaway instance (a fresh `get_item`), not one you keep."""
    _ensure_metadata_sources()
    from beets import autotag
    proposal = autotag.tag_item(item, search_ids=[recording_id])
    if not proposal.candidates:
        raise ValueError(f"No MusicBrainz recording found with id {recording_id}")
    before = dict(item)
    proposal.candidates[0].apply_metadata()
    return [(field, before.get(field), value)
            for field, value in dict(item).items()
            if value != before.get(field)]

def set_item_fields(item, fields: dict):
    item.update(fields)
    item.store()
    item.try_write()

def retag(query: str = ""):
    query = _fix_regex_flags(query)
    out = subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import",
         "-q", "-L", "--quiet-fallback=skip", *query.split()],
        capture_output=True,
        text=True,
    )
    log = (out.stdout + out.stderr).strip()
    if out.returncode != 0:
        log += f"\n(beets exited with status {out.returncode})"
    return log

def fetch_album_art(query: str = "", force: bool = False,
                    embed: bool = True) -> str:
    """Download cover art for the album(s) matching `query` and, when `embed`
    is set, write it into their audio files.

    `query` is a beets query that matches whole ALBUMS (same language as a
    search; `id:NNN` targets a specific album id). An empty query covers the
    whole library — allowed for fetching, but embedding is skipped in that case
    so an empty query can't rewrite every file. `force` re-downloads even for
    albums that already have art. Returns the combined beets log."""
    query = _fix_regex_flags(query)
    tokens = query.split()

    fetch_cmd = ["beet", "-c", str(CONFIG), "-l", str(DB), "fetchart"]
    if force:
        fetch_cmd.append("-f")
    fetch = subprocess.run(fetch_cmd + tokens, capture_output=True, text=True)
    log = (fetch.stdout + fetch.stderr).strip()
    if fetch.returncode != 0:
        log += f"\n(beets fetchart exited with status {fetch.returncode})"

    # embedart with no query would embed art into every album's files; only
    # embed when the caller actually narrowed to something.
    if embed and tokens:
        emb = subprocess.run(
            ["beet", "-c", str(CONFIG), "-l", str(DB), "embedart", "-y", *tokens],
            capture_output=True, text=True)
        emb_log = (emb.stdout + emb.stderr).strip()
        if emb.returncode != 0:
            emb_log += f"\n(beets embedart exited with status {emb.returncode})"
        log = f"{log}\n{emb_log}".strip()

    return log


def album_has_art(album_id: int) -> bool:
    """Whether the album now has a linked art file on disk — used to confirm a
    fetch actually landed something."""
    album = get_album(album_id)
    if album is None or not album.artpath:
        return False
    return os.path.exists(os.fsdecode(album.artpath))


def scan(music_dir):
    subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import", *_import_flags(), music_dir],
        check=True
    )

def scan_stream(music_dir):
    proc = subprocess.Popen(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import", *_import_flags(), music_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        yield line.rstrip()
    proc.wait()

import re as _re

_FLAG_GROUP = _re.compile(r"\(\?([aiLmsux]+)\)")

def _fix_regex_flags(query: str) -> str:
    """Move global regex flags to the front of each ::pattern in a query.

    Python 3.12+ rejects '(?i)' anywhere but position 0 of a pattern, and
    the agents love writing 'field::^(?i)foo' — rewrite it to
    'field::(?i)^foo' instead of failing the whole query.
    """
    def fix(token: str) -> str:
        if "::" not in token:
            return token
        field, _, pattern = token.partition("::")
        flags = "".join(m.group(1) for m in _FLAG_GROUP.finditer(pattern))
        if not flags:
            return token
        stripped = _FLAG_GROUP.sub("", pattern)
        return f"{field}::(?{''.join(sorted(set(flags)))}){stripped}"
    return " ".join(fix(token) for token in query.split(" "))

def search(query):
    lib = Library(DB)
    return list(lib.items(_fix_regex_flags(query)))

def search_by_filename(fragment):
    needle = fragment.lower()
    return [item for item in all_items()
            if item.path and needle in os.fsdecode(item.path).lower()]

def search_including_filenames(query):
    items = search(query)
    seen = {item.id for item in items}
    items += [item for item in search_by_filename(query)
              if item.id not in seen]
    return items

def all_items():
    lib = Library(DB)
    return list(lib.items())
        
def get_item(item_id: int):
    lib = Library(DB)
    return lib.get_item(item_id)

def get_album(album_id: int):
    lib = Library(DB)
    return lib.get_album(album_id)


# Trailing release-type qualifier some sources (e.g. Apple Music) bake into
# the title/album tag — "Sanguine Paradise - Single". The wishlist stores the
# bare song title, so strip it before comparing names.
_RELEASE_SUFFIX = _re.compile(r"\s*-\s*(single|ep)\s*$", _re.IGNORECASE)


def _name_key(artist: str, title: str) -> tuple[str, str]:
    """Normalized (artist, title) used to match a wishlist item against a
    collection track when their MusicBrainz ids differ (different recordings of
    the same song). Lowercases, collapses whitespace, and drops a trailing
    "- Single"/"- EP" from the title — conservative enough not to fuse songs
    that are genuinely different."""
    def norm(s: str) -> str:
        return " ".join(s.strip().lower().split())
    return norm(artist), norm(_RELEASE_SUFFIX.sub("", title.strip()))


def reconcile_wishlist(wishlist) -> list[dict]:
    """Auto-detect which wishlist items the user now owns and mark them
    acquired. For every not-yet-acquired item found in the collection, sets
    its status to "acquired" and links the matching beets item id via
    `acquired_id`. Returns the items that were updated, each as
    {id, acquired_id}. Idempotent — already-acquired items are skipped.

    Builds one in-memory index of the collection (keyed by MusicBrainz id and
    by a normalized artist+title, see `_name_key`) so the whole wishlist is
    reconciled with a single library read rather than a query per item."""
    # Nothing to reconcile? Skip the whole-library scan entirely. Indexing the
    # collection is the expensive part (it loads every beets item), so an empty
    # or already-acquired wishlist — the common case at startup — must not pay
    # for it.
    pending = [entry for entry in (wishlist.all_items() or [])
               if entry.get("status") != "acquired" and not entry.get("acquired_id")]
    if not pending:
        return []

    by_mb: dict[str, int] = {}
    by_name: dict[tuple, int] = {}
    for item in all_items():
        if item.mb_trackid:
            by_mb.setdefault(item.mb_trackid, item.id)
        if item.artist and item.title:
            by_name.setdefault(_name_key(item.artist, item.title), item.id)

    updated: list[dict] = []
    for entry in pending:
        beets_id = by_mb.get(entry.get("mb_id") or None)
        if beets_id is None and entry.get("artist") and entry.get("title"):
            beets_id = by_name.get(_name_key(entry["artist"], entry["title"]))
        if beets_id is not None:
            wishlist.update_item(
                entry["id"], {"status": "acquired", "acquired_id": beets_id})
            updated.append({"id": entry["id"], "acquired_id": beets_id})
    return updated

class DriveNotMounted(FileNotFoundError):
    """The volume holding the file isn't mounted right now."""

def _volume_root(path: str):
    """The /Volumes/<name> root of a path, or None for non-volume paths."""
    parts = Path(path).parts
    if len(parts) >= 3 and parts[:2] == ("/", "Volumes"):
        return Path(*parts[:3])
    return None

def locate_file(item_id: int):
    """Absolute path of an item's audio file on disk.

    Returns None when no item has this id. Raises DriveNotMounted when the
    file's volume isn't mounted, and FileNotFoundError when the volume is
    there but the file is gone.
    """
    item = get_item(item_id)
    if item is None:
        return None
    path = os.fsdecode(item.path)
    if not os.path.exists(path):
        volume = _volume_root(path)
        if volume is not None and not volume.exists():
            raise DriveNotMounted(path)
        raise FileNotFoundError(path)
    return path

def duplicates():
    """Songs that exist as more than one file, as a list of item groups."""
    out = subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "duplicates", "--full", "--format", "$id"],
        check=True,
        capture_output=True,
        text=True,
    )
    lib = Library(DB)
    groups = {}
    for line in out.stdout.splitlines():
        # The plugin prints "<id>: <number of copies>" per item.
        item = lib.get_item(int(line.split(":")[0]))
        groups.setdefault((item.artist, item.title), []).append(item)
    return list(groups.values())

def remove_item(item, delete=False, with_album=False):
    """Remove item from user's library, optional variable to also delete the file from disk"""
    if delete:
        path = os.fsdecode(item.path)
        volume = _volume_root(path)
        if volume is not None and not volume.exists():
            raise DriveNotMounted(path)
    item.remove(delete=delete,with_album=with_album) 


def remove_album(album, delete=False):
    """Remove an album and all its tracks from the library, optionally
    deleting the audio files (and album art) from disk."""
    if delete:
        for item in album.items():
            path = os.fsdecode(item.path)
            volume = _volume_root(path)
            if volume is not None and not volume.exists():
                raise DriveNotMounted(path)
    album.remove(delete=delete, with_items=True)

def move_item():
    pass