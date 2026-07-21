import os
import subprocess
from pathlib import Path
import beets
from beets.library import Library
from platformdirs import PlatformDirs

from tuney import config

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
        "mb_id": getattr(info, "track_id", "") or "",
        "artist": getattr(info, "artist", "") or "",
        "title": getattr(info, "title", "") or "",
        "album": getattr(info, "album", "") or "",
        "year": getattr(info, "year", None),
    }
    if score is not None:
        data["score"] = score
    return data


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


def reconcile_wishlist(wishlist) -> list[dict]:
    """Auto-detect which wishlist items the user now owns and mark them
    acquired. For every not-yet-acquired item found in the collection, sets
    its status to "acquired" and links the matching beets item id via
    `acquired_id`. Returns the items that were updated, each as
    {id, acquired_id}. Idempotent — already-acquired items are skipped.

    Builds one in-memory index of the collection (keyed by MusicBrainz id and
    by lowercased artist+title) so the whole wishlist is reconciled with a
    single library read rather than a query per item."""
    by_mb: dict[str, int] = {}
    by_name: dict[tuple, int] = {}
    for item in all_items():
        if item.mb_trackid:
            by_mb.setdefault(item.mb_trackid, item.id)
        if item.artist and item.title:
            by_name.setdefault((item.artist.lower(), item.title.lower()), item.id)

    updated: list[dict] = []
    for entry in wishlist.all_items() or []:
        if entry.get("status") == "acquired" or entry.get("acquired_id"):
            continue
        beets_id = by_mb.get(entry.get("mb_id") or None)
        if beets_id is None and entry.get("artist") and entry.get("title"):
            beets_id = by_name.get(
                (entry["artist"].lower(), entry["title"].lower()))
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