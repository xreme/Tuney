import os

import typer
from tuney import library
from tuney.wishlist import Wishlist

app = typer.Typer()

wishlist_app = typer.Typer(help="Track music you want to acquire.")
app.add_typer(wishlist_app, name="wishlist")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Launch the interactive Terminal UI"""
    if ctx.invoked_subcommand is None:
        from tuney.tui.tui import TuneyApp
        TuneyApp().run()

@app.command()
def scan(music_dir: str = typer.Argument(None)):
    """Add music into library."""
    if music_dir is None:
        typer.echo("No directory specified scanning current directory")
        library.scan("./")
    else:
        library.scan(music_dir)
        typer.echo(f"Scanned {music_dir}")

@app.command()
def search(query: str):
    """Search your library by metadata or file name"""
    results = library.search_including_filenames(query)
    for item in results:
        typer.echo(f"{item.id} | {item.title or '(untagged)'} ({item.album})")

@app.command("search-file")
def search_file(fragment: str):
    """Search your library by file name, folder, or extension."""
    results = library.search_by_filename(fragment)
    if not results:
        typer.echo(f"No files matching {fragment!r}")
        raise typer.Exit(code=1)
    for item in results:
        title = item.title or "(untagged)"
        typer.echo(f"{item.id} | {title} ({os.fsdecode(item.path)})")

@app.command()
def locate(query:str):
    """Search library for the path of item, by metadata or file name"""
    results = library.search_including_filenames(query)
    for item in results:
        typer.echo(f"{item.id} | {item.title or '(untagged)'} ({os.fsdecode(item.path)})")

@app.command()
def collection():
    results = library.all_items()
    for item in results:
        typer.echo(f"{item.title} ({item.album})")

@app.command()
def duplicates():
    """List songs that exist in more than one file."""
    groups = library.duplicates()
    if not groups:
        typer.echo("No duplicates found")
        return
    for group in groups:
        typer.echo(f"{group[0].artist} - {group[0].title}")
        for item in group:
            typer.echo(f"  {item.filepath}")

@app.command()
def remove(id: int,
          delete: bool = typer.Option(
              False, "--delete", "-d",
              help="Also delete the audio file from disk, not just the library"
          ) 
           ):
    """Remove item based on item id"""
    item = library.get_item(id)
    if item is None:
        typer.echo(f"No item found with id {id}")
        raise typer.Exit(code=1)
    library.remove_item(item, delete=delete)


# --- Wishlist ---------------------------------------------------------------

# Fields scanned by `wishlist list --filter`, mirroring the collection screen's
# "every word must appear somewhere in the row" substring matching.
_WISHLIST_SEARCH_FIELDS = ("artist", "title", "album", "notes", "status")

# Fields a MusicBrainz match can supply to fill in an item being added.
_MUSICBRAINZ_FIELDS = ("artist", "title", "album", "year", "mb_id")


def _wishlist() -> Wishlist:
    return Wishlist(library.DB)


def _format_item(item: dict) -> str:
    """One-line summary: `id | artist - title (album) [status, priority N]`."""
    return (
        f"{item.get('id')} | {item.get('artist', '')} - {item.get('title', '')}"
        f" ({item.get('album', '')})"
        f" [{item.get('status', '')}, priority {item.get('priority', 0)}]"
    )


def _format_candidate(candidate: dict) -> str:
    year = candidate.get("year")
    suffix = f", {year}" if year else ""
    score = candidate.get("score")
    score_text = f"  (score {score})" if score is not None else ""
    return (
        f"{candidate.get('artist', '')} - {candidate.get('title', '')}"
        f" ({candidate.get('album', '')}{suffix}){score_text}"
    )


def _matches_filter(item: dict, query: str) -> bool:
    haystack = " ".join(str(item.get(field, "")) for field in _WISHLIST_SEARCH_FIELDS).lower()
    return all(word in haystack for word in query.lower().split())


def _choose_candidate(artist: str, title: str, album: str) -> dict | None:
    """Show MusicBrainz matches and let the user pick one, or None to skip."""
    candidates = library.musicbrainz_candidates(artist=artist, title=title, album=album) or []
    if not candidates:
        typer.echo("No MusicBrainz matches found.")
        return None
    for index, candidate in enumerate(candidates, start=1):
        typer.echo(f"  {index}. {_format_candidate(candidate)}")
    selection = typer.prompt("Select a match (0 to skip)", type=int, default=0)
    if not 1 <= selection <= len(candidates):
        return None
    return candidates[selection - 1]


def _apply_match(fields: dict, match: dict) -> dict:
    """Fill only the still-empty MusicBrainz fields from a match, so values the
    user typed explicitly always win."""
    merged = dict(fields)
    for field in _MUSICBRAINZ_FIELDS:
        if not merged.get(field):
            merged[field] = match.get(field)
    return merged


@wishlist_app.command("list")
def wishlist_list(
    filter_text: str = typer.Option(
        "", "--filter", "-f",
        help="Only show items where every word appears somewhere in the row.",
    ),
):
    """List wishlist items, one per line."""
    items = _wishlist().all_items() or []
    if filter_text:
        items = [item for item in items if _matches_filter(item, filter_text)]
    if not items:
        typer.echo("Your wishlist is empty.")
        return
    for item in items:
        typer.echo(_format_item(item))


@wishlist_app.command("add")
def wishlist_add(
    artist: str = typer.Option("", "--artist", help="Artist name."),
    title: str = typer.Option("", "--title", help="Track or release title."),
    album: str = typer.Option("", "--album", help="Album name."),
    year: int = typer.Option(None, "--year", help="Release year."),
    notes: str = typer.Option("", "--notes", help="Freeform notes."),
    priority: int = typer.Option(0, "--priority", help="Higher sorts first."),
    status: str = typer.Option("wanted", "--status", help="Item status."),
    mb_id: str = typer.Option("", "--mb-id", help="MusicBrainz recording id."),
    match: bool = typer.Option(
        False, "--match", "-m",
        help="Search MusicBrainz for artist/title and interactively pick a match.",
    ),
):
    """Add an item to the wishlist, optionally matched against MusicBrainz."""
    fields = {"artist": artist, "title": title, "album": album, "year": year, "mb_id": mb_id}

    if match:
        candidate = _choose_candidate(artist, title, album)
        if candidate:
            fields = _apply_match(fields, candidate)
    elif mb_id:
        track = library.musicbrainz_track(mb_id)
        if track:
            fields = _apply_match(fields, track)
        else:
            typer.echo(f"Warning: no MusicBrainz recording found for id {mb_id!r}.")

    new_id = _wishlist().add_item(
        artist=fields["artist"],
        title=fields["title"],
        album=fields["album"],
        year=fields["year"],
        mb_id=fields["mb_id"],
        notes=notes,
        priority=priority,
        status=status,
    )
    typer.echo(f"Added wishlist item {new_id}: {fields['artist']} - {fields['title']}")


@wishlist_app.command("show")
def wishlist_show(id: int):
    """Print full details of a single wishlist item."""
    item = _wishlist().get_item(id)
    if item is None:
        typer.echo(f"No wishlist item found with id {id}")
        raise typer.Exit(code=1)
    for key, value in item.items():
        typer.echo(f"{key}: {value}")


@wishlist_app.command("remove")
def wishlist_remove(id: int):
    """Remove a wishlist item by id."""
    _wishlist().remove_item(id)
    typer.echo(f"Removed wishlist item {id}")


@wishlist_app.command("clear")
def wishlist_clear():
    """Remove every item from the wishlist."""
    if not typer.confirm("Remove all items from your wishlist?"):
        typer.echo("Aborted.")
        raise typer.Exit
    _wishlist().clear_wishlist()
    typer.echo("Wishlist cleared.")


@wishlist_app.command("update")
def wishlist_update(
    id: int,
    artist: str = typer.Option(None, "--artist", help="Artist name."),
    title: str = typer.Option(None, "--title", help="Track or release title."),
    album: str = typer.Option(None, "--album", help="Album name."),
    year: int = typer.Option(None, "--year", help="Release year."),
    notes: str = typer.Option(None, "--notes", help="Freeform notes."),
    priority: int = typer.Option(None, "--priority", help="Higher sorts first."),
    status: str = typer.Option(None, "--status", help="Item status."),
    mb_id: str = typer.Option(None, "--mb-id", help="MusicBrainz recording id."),
):
    """Update one or more fields of a wishlist item."""
    provided = (
        ("artist", artist), ("title", title), ("album", album), ("year", year),
        ("notes", notes), ("priority", priority), ("status", status), ("mb_id", mb_id),
    )
    fields = {name: value for name, value in provided if value is not None}
    if not fields:
        typer.echo("No fields to update. Pass at least one option.")
        raise typer.Exit(code=1)
    _wishlist().update_item(id, fields)
    typer.echo(f"Updated wishlist item {id}: {', '.join(fields)}")