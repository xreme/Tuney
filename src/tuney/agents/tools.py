from langchain.tools import tool
from tuney import config, library
from tuney.agents import activity
import json
import random
from collections import Counter
from datetime import datetime
from os import fsdecode
from os.path import abspath, basename, expanduser, getsize


# A serialized item is ~150 tokens; anything past a few hundred items risks
# blowing the model's context window in one tool result.
_MAX_RESULTS = 100


def _fmt_ts(value):
    """A beets unix timestamp (added/mtime) as a 'YYYY-MM-DD HH:MM' string, or
    None when it's missing or zero (beets stores an unknown time as 0)."""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if not ts:
        return None
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _searched(query: str):
    """library.search, but a bad query comes back as an error string for the
    model to correct instead of an exception that kills the whole run."""
    try:
        return library.search(query)
    except Exception as e:
        return (f"Invalid beets query {query!r}: {e}. Fix the query and "
                "retry. Common cause: regex flags like (?i) must be the very "
                "first thing in the pattern — write field::(?i)^foo, "
                "never field::^(?i)foo.")


def _item_dict(item):
    """Compact view of a beets item for the model to read."""
    return {
        "title": item.title,
        "album": item.album,
        "artist": item.artist,
        "year": item.year,
        "month": item.month,
        "day": item.day,
        "genres": list(item.get("genres") or []),
        "beets_id": item.id,
        "mb_recording_id": item.mb_trackid,
        # When the track was imported into the library and when its tags/file
        # were last modified (beets updates mtime on every tag rewrite).
        "imported": _fmt_ts(item.get("added")),
        "modified": _fmt_ts(item.get("mtime")),
    }


def _serialize(item):
    return json.dumps(_item_dict(item))


def _serialize_with_file(item):
    data = _item_dict(item)
    data["file_name"] = basename(fsdecode(item.path)) if item.path else ""
    return json.dumps(data)


def _capped(items, max: int = _MAX_RESULTS, page: int = 1, serialize=_serialize):
    """Serialize one page of items, with a guidance note when more remain."""
    max = min(max, _MAX_RESULTS) if max > 0 else _MAX_RESULTS
    page = page if page > 0 else 1
    start = (page - 1) * max
    results = [serialize(item) for item in items[start:start + max]]
    if len(items) > start + len(results):
        total_pages = -(-len(items) // max)
        results.append(json.dumps({
            "truncated": True,
            "total_matches": len(items),
            "page": page,
            "total_pages": total_pages,
            "note": (
                f"Showing page {page} of {total_pages} "
                f"({len(items)} matching tracks, {max} per page). Request the "
                "next page to continue, narrow the query (add artist:, "
                "album:, year:, genres: terms) to see specific tracks, or "
                "use count_items / distinct_values to explore the full set."
            ),
        }))
    return results


@tool
def list_collection(max: int = 100, page: int = 1):
    """Return the user's music collection as a list of JSON items.

    Expensive on large libraries — prefer `search_collection` when the user is
    looking for something specific. Results are paginated: `max` sets the page
    size (default and cap 100) and `page` selects a 1-based page. A trailing
    note gives the total count and page number when more tracks remain; use
    `collection_stats` or `distinct_values` for whole-library overviews.
    """
    return _capped(library.all_items(), max=max, page=page)


@tool
def search_collection(query: str, max: int = 100, page: int = 1):
    """Search the user's music collection using a beets query string.

    Pass a beets query built from the query language described in the system
    prompt (e.g. `artist:radiohead year:2000..`). Returns matching items as a
    list of JSON objects (title, album, artist, year, genres, plus `imported`
    and `modified` dates). An empty list means nothing matched. You can also
    filter by those dates with beets date queries — e.g. `added:2024-01..` for
    tracks imported since Jan 2024, or `mtime:2024-06-01..` for ones edited
    since. Results are paginated: `max` sets the page size
    (default and cap 100) and `page` selects a 1-based page; a trailing note
    gives the total count and page number when more matches remain — page
    through or narrow the query rather than re-listing large result sets.

    Matching is literal (substring), so spacing and spelling matter:
    `artist:speakerknockerz` will not match "Speaker Knockerz". On an empty
    result, retry with variations before concluding the item is missing —
    change the spacing, use a spacing-tolerant regex like
    `artist::(?i)speaker.?knockerz`, try a shorter fragment, or correct the
    spelling — as described in the system prompt.
    """
    items = _searched(query)
    if isinstance(items, str):
        return items
    return _capped(items, max=max, page=page)

@tool
def search_by_filename(fragment: str, max: int = 100, page: int = 1):
    """Find tracks whose audio file path on disk contains a fragment.

    Case-insensitive substring match against each track's full file path, so
    it finds file names (`track 01`, `y2mate`), extensions (`.flac`), and
    folder names (`Downloads`). Use it when the user refers to music by file
    name — common for untagged tracks, whose title shows as their file name
    in the collection screen — or asks what's in a folder or of a format.

    Each result includes the usual metadata plus the file_name it matched.
    Results are paginated like `search_collection`: `max` sets the page size
    (default and cap 100) and `page` selects a 1-based page. An empty list
    means no file path contains the fragment — try a shorter fragment before
    concluding the track is missing.
    """
    matches = library.search_by_filename(fragment)
    return _capped(matches, max=max, page=page, serialize=_serialize_with_file)


@tool
def random_sample(query: str = "", count: int = 5):
    """Pick random tracks from the user's collection, optionally filtered by a
    beets query.

    Use this for "play something random", "surprise me", or "pick a few rock
    songs" style requests. Pass a beets query (same language as
    `search_collection`, e.g. `genres:rock year:1990..1999`) to sample within
    a subset, or leave it empty to sample the whole library. `count` sets how
    many tracks to return (default 5, cap 100); if fewer tracks match than
    requested, all matches are returned in random order. An empty list means
    nothing matched the query.
    """
    count = min(count, _MAX_RESULTS) if count > 0 else 5
    items = _searched(query) if query else library.all_items()
    if isinstance(items, str):
        return items
    sample = random.sample(list(items), min(count, len(items)))
    return [_serialize(item) for item in sample]


@tool
def find_missing_metadata(fields: list[str] | None = None, max: int = 100, page: int = 1):
    """Scan the library for tracks with missing metadata.

    `fields` picks which of title/artist/album/albumartist/genres/year to
    check (default: title, artist, album). A field counts as missing when
    it's empty, 0 (year), or a placeholder like "Unknown Artist". Each
    returned track lists exactly which fields it's missing, plus its
    file_name — often the only way to identify an untagged track. Results
    are paginated like `search_collection` (`max` up to 100, 1-based
    `page`), and the summary gives per-field totals for the whole library.

    Use this to answer "what's untagged?" and to pick targets for metadata
    repair (propose/apply_track_tags, set_track_tags, retag_collection).
    """
    valid = ("title", "artist", "album", "albumartist", "genres", "year")
    fields = [f for f in (fields or ["title", "artist", "album"]) if f in valid]
    if not fields:
        return f"No valid fields given — choose from {', '.join(valid)}."
    placeholders = {"unknown", "unknown artist", "unknown album"}

    def missing_fields(item):
        out = []
        for field in fields:
            if field == "genres":
                value = item.get("genres") or item.get("genre")
                empty = not value
            else:
                value = str(item.get(field) or "").strip()
                empty = not value or value == "0" or value.lower() in placeholders
            if empty:
                out.append(field)
        return out

    matches = [(item, gaps) for item in library.all_items()
               if (gaps := missing_fields(item))]

    max = min(max, _MAX_RESULTS) if max > 0 else _MAX_RESULTS
    page = page if page > 0 else 1
    start = (page - 1) * max
    field_counts = Counter(gap for _, gaps in matches for gap in gaps)
    return json.dumps({
        "tracks_with_missing_fields": len(matches),
        "missing_by_field": dict(field_counts.most_common()),
        "page": page,
        "total_pages": -(-len(matches) // max) if matches else 1,
        "tracks": [
            dict(_item_dict(item),
                 file_name=basename(fsdecode(item.path)) if item.path else "",
                 missing=gaps)
            for item, gaps in matches[start:start + max]
        ],
    })

@tool
def count_items(query: str) -> str:
    """
    Count the matches of a given query against the user's music collection using a beets query.

    Pass a beets query built from the query language described in the system
    prompt (e.g. `artist:radiohead year:2000..`). Returns the count of matched items.
    """

    items = _searched(query)
    if isinstance(items, str):
        return items
    return len(items)

@tool
def distinct_values(field: str, query: str = ""):
    """List every unique value of a field in the collection, with track counts.

    Use this to discover what's actually in the library before searching —
    e.g. distinct_values("genres") to see all genres, or
    distinct_values("artist", "genres:rock") for artists within rock.
    Common fields: genres, artist, albumartist, album, year, label, format.
    The optional query uses the same beets query language as search_collection.
    Returns a JSON object mapping each value to how many tracks have it,
    most common first.
    """
    items = _searched(query) if query else library.all_items()
    if isinstance(items, str):
        return items
    counts = Counter(str(item.get(field, "")) for item in items)
    counts.pop("", None)   # tracks missing the field entirely
    counts.pop("0", None)  # beets stores missing numeric fields (year) as 0
    return json.dumps(dict(counts.most_common()))

@tool
def collection_stats():
    """Summary statistics for the whole library: track, album, and artist
    counts, total playtime, and the year range.

    Cheap — prefer this over list_collection for "tell me about my
    collection" style questions.
    """
    items = library.all_items()
    artists = {item.artist for item in items if item.artist}
    albums = {(item.albumartist or item.artist, item.album)
              for item in items if item.album}
    years = [item.year for item in items if item.year]
    total_seconds = int(sum(item.length or 0 for item in items))
    hours, minutes = divmod(total_seconds // 60, 60)[::-1] if False else (total_seconds // 3600, (total_seconds % 3600) // 60)

    return json.dumps({
        "tracks": len(items),
        "albums": len(albums),
        "artists": len(artists),
        "total_playtime": f"{hours}h {minutes}m",
        "earliest_year": min(years) if years else None,
        "latest_year": max(years) if years else None,
    })

@tool
def item_information(itemId: int):
    """
    Retrieve full information about a specific item in the User's internal library DB by beets_id.
    Useful for fetching item specific information.
    Ex: '42'
    """
    item = library.get_item(itemId)
    if item is None:
        return f"No item found with the beets_id {itemId}"
    item_json = {
        k: (fsdecode(v) if isinstance(v, bytes) else v)
        for k, v in dict(item).items()
    }
    # Surface the raw added/mtime floats as readable dates alongside them.
    item_json["imported"] = _fmt_ts(item.get("added"))
    item_json["modified"] = _fmt_ts(item.get("mtime"))

    # Not item.try_filesize(): beets logs a warning for every missing file,
    # which lands on stderr and bleeds through the TUI.
    try:
        size = getsize(fsdecode(item.path))
    except OSError:
        size = 0
    item_json["file_size_bytes"] = size
    # 0 means the file is missing or its drive isn't mounted.
    item_json["file_size"] = f"{size / 1_048_576:.1f} MB" if size else "unavailable"

    return json.dumps(item_json)

@tool
def locate_file(itemId: int):
    """
    Return the absolute path of a track's audio file on disk, looked up by beets_id.

    Find the beets_id with `search_collection` first. Use this when the user asks
    where a track is stored or wants to open the file itself.
    Reports if the item doesn't exist, its drive isn't mounted right now, or
    its file is missing from disk.
    """
    try:
        path = library.locate_file(itemId)
    except library.DriveNotMounted as missing:
        return (
            f"The file was at {missing.args[0]} when it was imported, but the "
            "drive it lives on isn't mounted right now, so the file can't be "
            "accessed. Reconnect the drive to use it."
        )
    except FileNotFoundError as missing:
        return f"The library entry points to {missing.args[0]}, but no file exists there anymore."
    if path is None:
        return f"No item found with the beets_id {itemId}"
    return path

@tool
def find_duplicates():
    """Find songs that exist more than once in the user's collection, grouped
    by matching artist + title.

    Returns a list of groups; each group lists every copy of one song with its
    album, year, format, bitrate, and beets_id. An empty list means no
    duplicates. Scans the whole library — no query needed.

    Interpret each group before reporting; do not present the raw groups:
    - Copies on the SAME album are true file duplicates (the actionable kind).
    - Copies on DIFFERENT albums are usually intentional: deluxe/expanded
      editions, compilations, or singles. Treat albums as editions of the same
      release when one album name extends the other (e.g. "Glockaveli" and
      "Glockaveli: The Don"). Summarize edition overlap at the album level
      ("all 18 tracks of X also appear on Y") instead of listing every track,
      and do not call these duplicates.
    - Only recommend which copy to remove if the user explicitly asks; base
      that on format and bitrate (keep the highest quality). Removal itself
      goes through `remove_item`, which requires explicit per-track user
      confirmation first.
    """
    groups = library.duplicates()
    return json.dumps([
        [{
            "title": it.title, "artist": it.artist, "album": it.album,
            "year": it.year, "format": it.format, "bitrate": it.bitrate,
            "file_location": fsdecode(it.path), "beets_id": it.id,
        } for it in group]
        for group in groups
    ])

@tool
def scan_directory(dir: str):
    """Scan a directory to import its music into the user's collection.

    Pass an absolute path. Runs a beets import of everything under that
    directory and updates the user's library DB. This is a long-running
    operation — on a large directory it may take a very long time.
    Returns the tail of the import log so you can tell the user what happened.
    """
    if not dir.is_dir():
        return "This path is not a directory on this disk"

    library.scan(dir)

@tool
def retag_collection(query: str = ""):
    """Fix the metadata of tracks already in the user's library by re-running
    the autotagger against MusicBrainz.

    Pass a beets query (same language as `search_collection`) to retag a
    subset — e.g. `artist:radiohead`, or `title::^$` for tracks with no
    title — or leave it empty to retag the ENTIRE library. Tracks that get a
    confident match have their metadata corrected in the library DB and
    rewritten into the audio files' own tags; tracks without a confident
    match are skipped and left exactly as they were.

    Calling this tool automatically presents the user with a confirmation
    dialog showing how many tracks the query covers; nothing changes until
    they approve. Do NOT ask for permission in chat first — the dialog is the
    confirmation. Prefer a targeted query over a whole-library retag when the
    user names specific music. This is a long-running operation: every album
    needs a MusicBrainz lookup, so a large query may take a very long time.

    IMPORTANT: the query matches whole ALBUMS, not tracks — `id:...` with a
    track id matches nothing, and one loose track rarely matches its full
    album confidently. To fix an individual track, use `propose_track_tags`
    + `apply_track_tags` instead.

    Returns the tail of the beets log so you can summarize what was fixed
    and what was skipped.
    """
    log = library.retag(query)
    if not log.strip():
        return ("beets matched no albums for this query — nothing was "
                "examined. The query matches whole albums, not tracks; for "
                "a single track use propose_track_tags/apply_track_tags.")
    lines = log.splitlines()
    if len(lines) > 60:
        lines = [f"(… {len(lines) - 60} earlier log lines omitted)"] + lines[-60:]
    skipped = log.count("Skipping.")
    if skipped:
        lines.append(f"({skipped} album(s) were SKIPPED — no confident "
                     "MusicBrainz match, metadata left unchanged. Fix their "
                     "tracks with propose_track_tags/apply_track_tags.)")
    return "\n".join(lines)

@tool
def propose_track_tags(item_id: int, artist_hint: str = "", title_hint: str = ""):
    """Look up MusicBrainz metadata candidates for one track. Read-only.

    Use this to fix a single track's missing or wrong metadata — the case
    `retag_collection` can't handle. When the track's own tags are empty or
    junk, pass hints: whatever artist/title the user said, or your best
    reading of the file name (e.g. from `locate_file`). Hints replace the
    track's own fields in the search, so good hints make good candidates.

    Returns the track's current metadata plus up to 5 candidates with a
    match_quality score (1.0 = perfect). Pick the right one — usually the
    best score, sanity-checked against what the user asked for — then call
    `apply_track_tags` with its recording_id, artist, and title. If nothing
    fits, try different hints before giving up.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with the beets_id {item_id}"
    proposal = library.track_candidates(item, artist_hint, title_hint)
    if not proposal.candidates:
        return ("MusicBrainz returned no candidates. Try again with (better) "
                "artist_hint/title_hint — e.g. names taken from the file "
                "name or from the user's request.")
    return json.dumps({
        "current": {"artist": item.artist, "title": item.title, "album": item.album},
        "candidates": [{
            "artist": match.info.artist,
            "title": match.info.title,
            "recording_id": match.info.track_id,
            "match_quality": round(1 - match.distance.distance, 3),
        } for match in proposal.candidates[:5]],
    })

@tool
def apply_track_tags(item_id: int, recording_id: str, artist: str, title: str):
    """Apply a MusicBrainz recording's metadata to a track, fixing both the
    library entry and the audio file's own tags.

    Get `recording_id` from `propose_track_tags` — never invent one. Pass
    the chosen candidate's artist and title verbatim too: they're shown to
    the user in the confirmation dialog (the actual values written come from
    MusicBrainz via the recording_id). The dialog appears automatically —
    do NOT ask for permission in chat first.

    Returns a before -> after summary of what changed.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with the beets_id {item_id}"
    before = f"{item.artist or '(no artist)'} - {item.title or '(no title)'}"
    try:
        info = library.apply_track_match(item, recording_id)
    except ValueError as e:
        return (f"{e}. Do NOT retry with a guessed or remembered id — call "
                "propose_track_tags now and copy a recording_id exactly from "
                "its output.")
    return (f"Updated track {item_id}: {before} -> {info.artist} - {info.title}. "
            "Library entry and file tags rewritten.")

@tool
def set_track_tags(item_id: int, title: str = "", artist: str = "",
                   album: str = "", albumartist: str = "", genre: str = "",
                   year: int = 0):
    """Manually set metadata fields on one track, fixing both the library
    entry and the audio file's own tags.

    Use this when the user dictates exact values ("set the artist to X") or
    when MusicBrainz has no match for the track — unlike apply_track_tags,
    nothing is looked up; exactly what you pass is written. Only the fields
    you pass are changed: an empty string (or 0 for year) leaves that field
    as it is, so this cannot blank out a field.

    Calling it automatically shows the user a confirmation dialog with each
    old -> new value; nothing is written until they approve. Do NOT ask for
    permission in chat first. Verify the item_id refers to the track the
    user means, and never invent values the user didn't give or that you
    aren't confident of.

    Returns a summary of the fields that changed.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with the beets_id {item_id}"
    requested = {"title": title, "artist": artist, "album": album,
                 "albumartist": albumartist, "genre": genre, "year": year}
    fields = {name: value for name, value in requested.items() if value}
    if not fields:
        return "No fields given — pass at least one of title/artist/album/albumartist/genre/year."
    changes = [f"{name}: {item.get(name) or '(empty)'!r} -> {value!r}"
               for name, value in fields.items()]
    library.set_item_fields(item, fields)
    return f"Updated track {item_id} (library entry and file tags rewritten):\n  " + "\n  ".join(changes)

@tool
def fetch_album_art(item_id: int, force: bool = False):
    """Download cover art for a track's album and embed it into the album's
    audio files, looked up by the track's beets_id.

    Use this when the user wants to add or refresh the artwork for a track or
    album ("add the cover art", "this album has no cover", "fix the artwork").
    It resolves the track's album, downloads art from online sources
    (MusicBrainz Cover Art Archive, iTunes, etc.), stores it beside the album's
    files, and writes it into every track of the album. `force=True`
    re-downloads even when the album already has art (use it to replace a wrong
    or low-quality cover); by default an album that already has art is left
    alone.

    Calling this tool automatically shows the user a confirmation dialog before
    anything is written, so do NOT ask for permission in chat first. Verify the
    beets_id refers to the track the user means with `item_information` first.
    Album art is fetched per ALBUM, so every track on the same album is
    affected, not just this one.

    Returns a message saying whether art was found and embedded, plus the tail
    of the beets log.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with the beets_id {item_id}"
    if not item.album_id:
        return (f"Track {item_id} ({item.artist} - {item.title}) isn't part of "
                "an album in the library, so there's no album to attach art to.")

    log = library.fetch_album_art(f"id:{item.album_id}", force=force, embed=True)
    got_art = library.album_has_art(item.album_id)
    lines = log.splitlines()
    if len(lines) > 30:
        lines = [f"(… {len(lines) - 30} earlier log lines omitted)"] + lines[-30:]
    tail = "\n".join(lines).strip()

    album_name = item.album or "(unknown album)"
    if got_art:
        head = (f"Cover art downloaded and embedded for '{album_name}' "
                f"(album_id {item.album_id}).")
    else:
        head = (f"No cover art could be found for '{album_name}' "
                f"(album_id {item.album_id}) — the album was left unchanged. "
                "The online sources had nothing matching; a manual image may "
                "be needed.")
    return f"{head}\n{tail}".strip() if tail else head

@tool
def convert_tracks(query: str, format: str, replace: bool = False,
                   album: bool = False, quality: str = "normal",
                   destination: str = ""):
    """Convert the audio files of matching tracks to another format
    (transcoding), e.g. FLAC -> MP3 for a phone, or MP3 -> ALAC.

    `query` is a beets query (same language as `search_collection`) selecting
    what to convert; `id:NNN` targets one track. An EMPTY query means the
    user's ENTIRE library — only use it when they clearly asked for that.
    `format` must be one of: mp3, aac, opus, ogg, alac, flac.

    `destination` is a folder path. Leave it EMPTY to use the folder the user
    configured in Settings, which is the right choice unless they named a
    place ("put them on my desktop", "into ~/Music/phone", "onto the USB
    stick") — pass that path when they do, rather than converting into the
    default folder and telling them it went somewhere else. `~` is expanded.

    EXPORT IS THE DEFAULT AND YOU DO NOT ASK ABOUT IT:
    - replace=False (the default) — EXPORT. Converted copies are written to a
      folder; the library and the original files are untouched. Use this for
      every conversion request unless the exception below applies, and do not
      ask the user to choose. "Convert album X to aac", "give me MP3s of…",
      "make me a copy for my phone" are all plain export.
    - replace=True — REPLACE. The library entries are repointed at the
      converted files and the ORIGINAL files are MOVED to the archive folder
      (never deleted, so it is undoable). Pass this ONLY when the user
      explicitly asks for their existing files to be swapped or their library
      changed — "replace my FLACs", "convert my library to mp3 and get rid of
      the originals", "I don't want to keep the FLACs". Anything short of that
      is an export.
    When in doubt, export. It is the reversible one: it adds files and changes
    nothing the user already has, so guessing it wrong costs disk space rather
    than their library.

    Set album=True when the user names albums rather than tracks; the query
    then matches whole albums and every track on them is converted.

    `quality` is "normal" (the default — smaller files at good quality) or
    "best". Use "best" when the user asks for maximum/highest quality or says
    the files are for listening critically; use "normal" when they mention
    saving space or fitting music on a device. Note what "best" means depends
    on the format: for mp3/aac/opus/ogg it raises the bitrate (bigger files),
    but flac and alac are LOSSLESS — their audio is identical either way and
    "best" only compresses harder. Never tell a user that converting to best
    quality improves a file that was already lossy; re-encoding cannot recover
    quality that is already gone.

    Calling this tool automatically shows the user a confirmation dialog with
    the exact counts — how many files will be re-encoded, how many are already
    in that format, and how many would lose quality — so do NOT ask for
    permission in chat first. Files already in the target format are copied
    rather than re-encoded, and files whose drive isn't mounted are skipped.

    This is a long-running operation: transcoding is CPU-bound and a large
    query can take many minutes.

    Returns what the conversion ACTUALLY did, counted from the encoder's own
    log, together with the folder the files are in. Relay those numbers and
    that path as given — do not restate the request as though it succeeded.
    Two outcomes in particular need passing on plainly rather than smoothing
    over: files beets left alone because that name already existed in the
    destination (a re-run converts nothing, which is not a failure), and files
    whose encode failed (nothing was written for those).
    """
    fmt = (format or "").strip().lower()
    if fmt not in library.CONVERT_FORMATS:
        return (f"Unknown format {format!r}. Choose one of: "
                f"{', '.join(library.CONVERT_FORMATS)}.")
    tier = (quality or "normal").strip().lower()
    if tier not in library.CONVERT_QUALITIES:
        return (f"Unknown quality {quality!r}. Choose one of: "
                f"{', '.join(library.CONVERT_QUALITIES)}.")

    try:
        plan = library.convert_plan(query, fmt, album=album)
    except Exception as error:
        return (f"That query isn't valid, so nothing was converted: {error}. "
                "Check it with search_collection first.")
    if not plan["matched"]:
        return (f"No tracks matched {query!r}, so nothing was converted. "
                "Check the query with search_collection first.")
    if not plan["transcode"]:
        if plan["unreachable"] == plan["matched"]:
            return (f"All {plan['matched']} matching tracks are unreachable "
                    f"({plan['unreachable_by_reason']}) — their drive isn't "
                    "mounted or the files are gone, so nothing was converted.")
        return (f"All {plan['matched']} matching tracks are already {fmt} — "
                "nothing needed converting.")

    cfg = config.get_config()
    if destination and destination.strip():
        dest = abspath(expanduser(destination.strip()))
    else:
        dest = cfg.convert_archive_path if replace else cfg.convert_dest_path

    try:
        with activity.long_task():
            log = library.convert(query, fmt, dest, replace=replace,
                                  album=album, quality=tier)
    except OSError as error:
        return (f"Nothing was converted: {dest} could not be used as the "
                f"destination ({error}). Ask the user for a folder they can "
                "write to, or leave the destination empty to use the one from "
                "their settings.")

    # What beets actually wrote, not the plan's forecast — they disagree
    # whenever a target already existed or an encode failed.
    done = library.convert_outcome(log)

    lines = log.splitlines()
    if len(lines) > 40:
        lines = [f"(… {len(lines) - 40} earlier log lines omitted)"] + lines[-40:]

    if not done["wrote"]:
        if done["existing"]:
            head = (f"Nothing was converted: all {done['existing']} files were "
                    f"already present as {fmt} in {dest}, so beets left them "
                    "alone. Tell the user the folder already holds these "
                    "tracks; converting again would need those files moved or "
                    "deleted first.")
        elif done["failed"] or done["unreadable"]:
            head = (f"The conversion FAILED — 0 of {plan['transcode']} files "
                    f"were written to {dest}. The encoder errored on "
                    f"{done['failed'] or done['unreadable']} files; the log "
                    "below says why. The user's files are unchanged.")
        else:
            head = (f"Nothing was written to {dest}, and beets did not say why "
                    "— the log below is the whole record. Do not tell the user "
                    "the conversion succeeded.")
        return f"{head}\n" + "\n".join(lines)

    head = (f"Converted {done['encoded']} tracks to {fmt}. The library now "
            f"points at the new files; the originals were moved to {dest}."
            if replace else
            f"Converted {done['encoded']} tracks to {fmt}. The files are in "
            f"{dest}; the library and the original files are unchanged.")
    head += f" Quality: {tier} ({library.quality_summary(fmt, tier)})."

    notes = []
    if done["copied"]:
        notes.append(f"{done['copied']} were already {fmt} and were copied "
                     "rather than re-encoded")
    if done["existing"]:
        notes.append(f"{done['existing']} were left alone because a file of "
                     f"that name was already in {dest}")
    if done["failed"] or done["unreadable"]:
        notes.append(f"{done['failed'] or done['unreadable']} FAILED to encode "
                     "and were not written")
    if plan["unreachable"]:
        notes.append(f"{plan['unreachable']} were skipped as unreachable "
                     f"({plan['unreachable_by_reason']})")
    if notes:
        head += " " + "; ".join(notes) + "."
    return f"{head}\n" + "\n".join(lines)


@tool
def remove_item(item_id: int, delete_file: bool = False):
    """Remove a track from the user's library, looked up by beets_id.

    With delete_file=False (the default) only the library DB entry is removed;
    the audio file stays on disk. With delete_file=True the audio file is
    PERMANENTLY deleted from disk as well — this cannot be undone.

    Calling this tool automatically presents the user with a confirmation
    dialog showing the track and its file path; nothing is removed until they
    approve. Do NOT ask for permission in chat before calling it — the dialog
    is the confirmation. Just make sure of:
    - The right target: use `item_information`/`search_collection` to verify
      the beets_id refers to the track the user means, so a wrong or stale id
      can't surface the wrong file for deletion.
    - The right mode: only pass delete_file=True if the user clearly wants
      the file itself gone (e.g. deleting a duplicate copy), not just removed
      from the library.

    Returns a message confirming what was removed, or an error if the id
    doesn't exist.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with id: {item_id}"
    library.remove_item(item, delete=delete_file)
    what = "library entry and audio file" if delete_file else "library entry (file kept on disk)"
    return f"Removed {what}: {item.artist} - {item.title} ({item.album})"

@tool
def remove_items(item_ids: list[int], delete_files: bool = False):
    """Remove several tracks from the user's library at once, looked up by beets_id.

    Same semantics as `remove_item`, applied to every id: with
    delete_files=False (the default) only the library DB entries are removed;
    with delete_files=True the audio files are PERMANENTLY deleted from disk
    as well — this cannot be undone.

    Prefer this over many single `remove_item` calls when the user wants
    several tracks gone (e.g. clearing duplicate copies): the user gets ONE
    confirmation dialog listing every track, and approves or rejects the
    batch as a whole. Do NOT ask for permission in chat first — the dialog is
    the confirmation. Verify each id refers to the track the user means
    before calling.

    Returns a per-track summary of what was removed and any ids that failed.
    """
    removed: list[str] = []
    errors: list[str] = []
    for item_id in item_ids:
        item = library.get_item(item_id)
        if item is None:
            errors.append(f"{item_id}: no item with this id")
            continue
        try:
            library.remove_item(item, delete=delete_files)
        except library.DriveNotMounted as e:
            errors.append(f"{item_id}: drive not mounted ({e}) — not removed")
            continue
        removed.append(f"{item.artist} - {item.title} ({item.album})")
    what = "library entry and audio file" if delete_files else "library entry (file kept on disk)"
    lines = [f"Removed {what} for {len(removed)} of {len(item_ids)} tracks:"]
    lines += [f"  {r}" for r in removed]
    if errors:
        lines.append("Failed:")
        lines += [f"  {e}" for e in errors]
    return "\n".join(lines)

@tool
def remove_album(album_id: int, delete_files: bool = False):
    """Remove an entire album — every one of its tracks — from the user's
    library, looked up by the beets album id.

    Find the album id via `item_information` on any track of the album (its
    `album_id` field). With delete_files=False (the default) only the library
    DB entries are removed; with delete_files=True the audio files AND the
    album art are PERMANENTLY deleted from disk — this cannot be undone.

    The user gets one confirmation dialog for the whole album before anything
    is removed. Do NOT ask for permission in chat first — the dialog is the
    confirmation.

    Returns a message confirming what was removed, or an error if the id
    doesn't exist.
    """
    album = library.get_album(album_id)
    if album is None:
        return f"No album found with album_id: {album_id}"
    track_count = len(list(album.items()))
    library.remove_album(album, delete=delete_files)
    what = ("library entries, audio files and album art" if delete_files
            else "library entries (files kept on disk)")
    return (f"Removed {what} for album: {album.albumartist} - {album.album} "
            f"({track_count} tracks)")