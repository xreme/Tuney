import typer
from tuney import config, library, output
from tuney.wishlist import Wishlist

app = typer.Typer()

wishlist_app = typer.Typer(help="Track music you want to acquire.")
app.add_typer(wishlist_app, name="wishlist")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Option(
        None, "--print", "-p", metavar="PROMPT",
        help="Ask the assistant one question, print the answer and exit, "
             "instead of opening the TUI."),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="With -p, approve actions the assistant asks to confirm. "
             "Without a terminal to ask on, they are declined."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="With -p, hide the tool activity notes."),
):
    """Launch the interactive Terminal UI, or answer one question with -p."""
    if ctx.invoked_subcommand is not None:
        return
    if prompt is not None:
        from tuney.agents.terminal import ask
        ask(prompt, approve_all=yes, quiet=quiet)
        return
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
def search(query: str,
           page: int = output.PAGE,
           limit: int = output.LIMIT,
           show_all: bool = output.ALL):
    """Search your library by metadata or file name"""
    results = library.search_including_filenames(query)
    if not results:
        output.empty(f"No tracks matching {query!r}")
        raise typer.Exit(code=1)
    shown = output.paginate(results, page, limit, show_all)
    output.render(shown.rows, "tracks", shown)

@app.command("search-file")
def search_file(fragment: str,
                page: int = output.PAGE,
                limit: int = output.LIMIT,
                show_all: bool = output.ALL):
    """Search your library by file name, folder, or extension."""
    results = library.search_by_filename(fragment)
    if not results:
        output.empty(f"No files matching {fragment!r}")
        raise typer.Exit(code=1)
    shown = output.paginate(results, page, limit, show_all)
    output.render(shown.rows, "files", shown, paths=True)

@app.command()
def locate(query: str,
           page: int = output.PAGE,
           limit: int = output.LIMIT,
           show_all: bool = output.ALL):
    """Search library for the path of item, by metadata or file name"""
    results = library.search_including_filenames(query)
    if not results:
        output.empty(f"No tracks matching {query!r}")
        raise typer.Exit(code=1)
    shown = output.paginate(results, page, limit, show_all)
    output.render(shown.rows, "tracks", shown, paths=True)

def _collection_order(item):
    """Artist, then album, then disc and track — the order the songs were
    meant to be read in, rather than beets' insertion order."""
    return (
        (item.albumartist or item.artist or "").lower(),
        (item.album or "").lower(),
        item.disc or 0,
        item.track or 0,
    )

@app.command()
def collection(
    filter_text: str = typer.Option(
        "", "--filter", "-f",
        help="Only show tracks where every word appears somewhere in the row."),
    page: int = output.PAGE,
    limit: int = output.LIMIT,
    show_all: bool = output.ALL,
):
    """List every track in your library."""
    items = library.all_items()
    if filter_text:
        items = [item for item in items
                 if output.track_matches(item, filter_text)]
        if not items:
            output.empty(f"No tracks matching {filter_text!r}")
            raise typer.Exit(code=1)
    if not items:
        output.empty("Your library is empty. Run `tuney scan <folder>` to add music.")
        return
    items.sort(key=_collection_order)
    shown = output.paginate(items, page, limit, show_all)
    output.render(shown.rows, "tracks", shown)

@app.command()
def duplicates(page: int = output.PAGE,
               limit: int = output.LIMIT,
               show_all: bool = output.ALL,
               across_releases: bool = typer.Option(
                   False, "--across-releases", "-x",
                   help="Also show songs repeated across different releases "
                        "(deluxe editions, compilations, singles).")):
    """List songs that exist in more than one file."""
    groups = library.duplicates(across_releases=across_releases)
    if not groups:
        output.empty("No duplicates found." if across_releases else
                     "No duplicated files found. Use --across-releases to see "
                     "songs that repeat across editions and compilations.")
        return
    shown = output.paginate(groups, page, limit, show_all)
    for group in shown.rows:
        output.duplicate_group(group)
    output.footer(shown, "duplicated songs")

def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1_073_741_824:
        return f"{num_bytes / 1_073_741_824:.1f} GB"
    return f"{num_bytes / 1_048_576:.0f} MB"


def _echo_plan(plan: dict, fmt: str, dest: str, replace: bool) -> None:
    scope = "your ENTIRE library" if plan["whole_library"] else "the query"
    typer.echo(f"{plan['matched']} tracks match {scope}.")
    typer.echo(f"  to transcode: {plan['transcode']} "
               f"({_format_size(plan['source_bytes'])} of source audio)")
    if plan["skipped"]:
        typer.echo(f"  already {fmt}: {plan['skipped']} (copied, not re-encoded)")
    if plan["unreachable"]:
        reasons = ", ".join(f"{count} {reason}"
                            for reason, count in plan["unreachable_by_reason"].items())
        typer.echo(f"  unreachable:  {plan['unreachable']} ({reasons}) — skipped")
    if plan["lossy_reencode"]:
        typer.secho(
            f"  warning: {plan['lossy_reencode']} of these are lossy -> lossy "
            "re-encodes, which lose quality.",
            fg=typer.colors.YELLOW)
    if replace:
        typer.secho(
            f"REPLACE mode: the library will point at the new {fmt} files.\n"
            f"The original files are MOVED to {dest} — nothing is deleted.",
            fg=typer.colors.YELLOW)
    else:
        typer.echo(f"Converted copies go to {dest}. "
                   "Your library and originals are untouched.")


@app.command()
def convert(
    query: str = typer.Argument("", help="Beets query. Empty converts everything."),
    format: str = typer.Option(None, "--format", "-f",
                               help=f"Target format: {', '.join(library.CONVERT_FORMATS)}."),
    quality: str = typer.Option(None, "--quality", "-q",
                                help="normal (smaller files, still good) or "
                                     "best (maximum quality)."),
    dest: str = typer.Option(None, "--dest", "-d",
                             help="Destination folder (originals archive in --replace mode)."),
    replace: bool = typer.Option(
        False, "--replace",
        help="Point the library at the converted files and move the originals "
             "to --dest, instead of writing copies there."),
    album: bool = typer.Option(False, "--album", "-a",
                               help="Match whole albums rather than tracks."),
    force: bool = typer.Option(False, "--force", "-F",
                               help="Re-encode even files already in the target format."),
    dry_run: bool = typer.Option(False, "--dry-run", "-p",
                                 help="Show what beets would run, change nothing."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation."),
):
    """Convert tracks to another audio format."""
    cfg = config.get_config()
    fmt = (format or cfg.convert_format).lower()
    if fmt not in library.CONVERT_FORMATS:
        typer.echo(f"Unknown format {fmt!r}. Choose from: "
                   f"{', '.join(library.CONVERT_FORMATS)}")
        raise typer.Exit(code=1)
    tier = (quality or cfg.convert_quality).lower()
    if tier not in library.CONVERT_QUALITIES:
        typer.echo(f"Unknown quality {tier!r}. Choose from: "
                   f"{', '.join(library.CONVERT_QUALITIES)}")
        raise typer.Exit(code=1)
    destination = dest or (cfg.convert_archive_path if replace
                           else cfg.convert_dest_path)

    plan = library.convert_plan(query, fmt, album=album, force=force)
    if not plan["matched"]:
        typer.echo("Nothing matched that query.")
        raise typer.Exit(code=1)
    _echo_plan(plan, fmt, destination, replace)
    typer.echo(f"  quality: {tier} — {library.quality_summary(fmt, tier)}")

    if not plan["transcode"] and not force:
        typer.echo("Nothing to convert.")
        return
    if dry_run:
        typer.echo("\n--- dry run ---")
        typer.echo(library.convert(query, fmt, destination, replace=replace,
                                   force=force, album=album, pretend=True,
                                   quality=tier))
        return
    if not yes and not typer.confirm(f"\nConvert {plan['transcode']} tracks to {fmt}?"):
        typer.echo("Aborted.")
        raise typer.Exit

    for line in library.convert_stream(query, fmt, destination, replace=replace,
                                       force=force, album=album, quality=tier):
        typer.echo(line)


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

# Fields a MusicBrainz match can supply to fill in an item being added.
_MUSICBRAINZ_FIELDS = ("artist", "title", "album", "year", "mb_id")


def _wishlist() -> Wishlist:
    return Wishlist(library.DB)


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
    return output.matches(
        (item.get(field, "") for field in output.WISHLIST_FIELDS), query)


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
    page: int = output.PAGE,
    limit: int = output.LIMIT,
    show_all: bool = output.ALL,
):
    """List wishlist items."""
    wishlist = _wishlist()
    # Auto-detect items now owned, so their status shows as acquired.
    library.reconcile_wishlist(wishlist)
    items = wishlist.all_items() or []
    if filter_text:
        items = [item for item in items if _matches_filter(item, filter_text)]
        if not items:
            output.empty(f"No wishlist items matching {filter_text!r}")
            raise typer.Exit(code=1)
    if not items:
        output.empty("Your wishlist is empty.")
        return
    shown = output.paginate(items, page, limit, show_all)
    output.console.print(output.wishlist_table(shown.rows))
    output.footer(shown, "wishlist items")


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


@wishlist_app.command("sync")
def wishlist_sync():
    """Auto-detect wishlist items you now own and mark them acquired."""
    updated = library.reconcile_wishlist(_wishlist())
    if not updated:
        typer.echo("No new acquisitions detected.")
        return
    typer.echo(f"Marked {len(updated)} item(s) as acquired:")
    for row in updated:
        typer.echo(f"  wishlist {row['id']} -> collection item {row['acquired_id']}")


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