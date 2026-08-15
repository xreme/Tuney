"""Shared rendering for the CLI: tables, pagination and empty states.

Listings default to one page rather than the whole library, so a command can
never flood the terminal with thousands of lines. `--all` opts back out.
"""

import os
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

PAGE_SIZE = 25

console = Console()

# Shared across every listing command so the flags mean the same thing
# everywhere. Reusing one OptionInfo per flag is safe: they are read-only
# metadata that click copies per parameter.
PAGE = typer.Option(1, "--page", "-p", min=1,
                    help="Which page of results to show.")
ALL = typer.Option(False, "--all", "-a",
                   help="Print every result instead of one page.")
LIMIT = typer.Option(PAGE_SIZE, "--limit", "-n", min=1,
                     help="Results per page.")

# Fields a listing filter searches, mirroring the collection screen's
# "every word must appear somewhere in the row" matching.
TRACK_FIELDS = ("artist", "title", "album", "year", "format", "id")


@dataclass
class Page:
    """One slice of a result set, plus what the footer needs to describe it."""
    rows: list
    number: int
    count: int
    total: int
    size: int

    @property
    def complete(self) -> bool:
        """Whether this page is the entire result set."""
        return self.count <= 1


def paginate(rows, page: int = 1, limit: int = PAGE_SIZE,
             show_all: bool = False) -> Page:
    """Slice `rows` for display. Out-of-range pages clamp to the last one so a
    stale `--page 9` shows the end of the list instead of nothing."""
    rows = list(rows)
    total = len(rows)
    if show_all or total <= limit:
        return Page(rows, 1, 1, total, limit)
    count = -(-total // limit)
    number = min(page, count)
    start = (number - 1) * limit
    return Page(rows[start:start + limit], number, count, total, limit)


def footer(page: Page, noun: str) -> None:
    """A summary line under a table, naming the flags that reveal the rest."""
    if page.complete:
        counted = noun[:-1] if page.total == 1 and noun.endswith("s") else noun
        console.print(f"[dim]{page.total} {counted}[/dim]")
        return
    first = (page.number - 1) * page.size + 1
    last = first + len(page.rows) - 1
    console.print(
        f"[dim]{first}-{last} of {page.total} {noun}  ·  "
        f"page {page.number}/{page.count}  ·  "
        f"--page N for more, --all for everything[/dim]"
    )


def matches(text_parts, query: str) -> bool:
    """True when every word in `query` appears somewhere in the row."""
    haystack = " ".join(str(part or "") for part in text_parts).lower()
    return all(word in haystack for word in query.lower().split())


def track_matches(item, query: str) -> bool:
    return matches((getattr(item, field, "") for field in TRACK_FIELDS), query)


def duration(seconds) -> str:
    """Track length as m:ss, blank when beets has no length for the file."""
    if not seconds:
        return ""
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def size(num_bytes) -> str:
    if not num_bytes:
        return ""
    if num_bytes >= 1_073_741_824:
        return f"{num_bytes / 1_073_741_824:.1f} GB"
    return f"{num_bytes / 1_048_576:.0f} MB"


def _text(value) -> str:
    """Blank out the falsy values beets uses for "unknown" (None, "", year 0)."""
    return "" if value in (None, "", 0) else str(value)


def _title(item) -> str:
    return _text(item.title) or "[dim italic](untagged)[/dim italic]"


def _table(*columns: str) -> Table:
    table = Table(box=None, pad_edge=False, header_style="bold",
                  show_edge=False)
    for column in columns:
        table.add_column(column)
    return table


def track_table(items, paths: bool = False) -> Table:
    """The standard track listing, matching the TUI's collection columns."""
    table = _table("ID", "Artist", "Title", "Album", "Year", "Fmt", "Time")
    table.columns[0].style = "dim"
    table.columns[0].justify = "right"
    for column in table.columns[4:]:
        column.style = "dim"
    if paths:
        table.add_column("Path", style="dim", overflow="fold")

    for item in items:
        row = [
            str(item.id),
            _text(item.artist),
            _title(item),
            _text(item.album),
            _text(item.year),
            _text(item.format),
            duration(item.length),
        ]
        if paths:
            row.append(os.fsdecode(item.path) if item.path else "")
        table.add_row(*row)
    return table


def render(items, noun: str, page: Page, paths: bool = False) -> None:
    console.print(track_table(items, paths=paths))
    footer(page, noun)


def _bitrate(value) -> str:
    return f"{round(value / 1000)}k" if value else ""


def duplicate_group(group) -> None:
    """One duplicated song: a heading, then a row per copy on disk.

    The per-copy format, bitrate and size are the numbers you actually need to
    pick a keeper, and `reclaimable` is what deleting all but the largest copy
    would free."""
    head = group[0]
    sizes = [getattr(item, "filesize", 0) or 0 for item in group]
    reclaimable = sum(sizes) - max(sizes) if sizes else 0
    console.print(
        f"[bold]{_text(head.artist) or 'Unknown artist'}[/bold] - "
        f"{_text(head.title) or '(untagged)'}  "
        f"[dim]{len(group)} copies · {size(reclaimable)} reclaimable[/dim]"
    )
    table = _table("ID", "Fmt", "Bitrate", "Size", "Path")
    table.columns[0].style = "dim"
    table.columns[0].justify = "right"
    table.columns[4].overflow = "fold"
    for item in group:
        table.add_row(
            str(item.id),
            _text(item.format),
            _bitrate(getattr(item, "bitrate", 0)),
            size(getattr(item, "filesize", 0)),
            os.fsdecode(item.path) if item.path else "",
        )
    console.print(table)
    console.print()


WISHLIST_FIELDS = ("artist", "title", "album", "notes", "status")


def wishlist_table(items) -> Table:
    table = _table("ID", "Artist", "Title", "Album", "Year", "Status", "Pri")
    table.columns[0].style = "dim"
    table.columns[0].justify = "right"
    table.columns[4].style = "dim"
    table.columns[6].justify = "right"
    for item in items:
        status = _text(item.get("status"))
        table.add_row(
            _text(item.get("id")),
            _text(item.get("artist")),
            _text(item.get("title")) or "[dim italic](untitled)[/dim italic]",
            _text(item.get("album")),
            _text(item.get("year")),
            f"[green]{status}[/green]" if status == "acquired" else status,
            _text(item.get("priority")),
        )
    return table


def empty(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")
