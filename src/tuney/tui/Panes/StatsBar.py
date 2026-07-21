import os
from collections import Counter

from textual import work
from textual.widgets import Static
from tuney import library


class StatsBar(Static):
    """A one-glance summary of the collection, shown above the workspace."""

    DEFAULT_CSS = """
    StatsBar {
        dock: top;
        height: auto;
        padding: 0 2;
        background: $panel;
        color: $text;
    }
    """

    SPARKS = "▁▂▃▄▅▆▇█"
    TOP_GENRES = 3

    def on_mount(self) -> None:
        self._stats_key = None
        self.update("Crunching collection stats…")
        self.refresh_stats()

    @work(thread=True, exclusive=True)
    def refresh_stats(self) -> None:
        items = library.all_items()
        # Only recompute when something the summary uses actually changed —
        # including metadata edits, which keep the same track ids.
        key = [(item.id, item.artist, item.albumartist, item.album,
                item.year, item.length, item.bitrate, item.genres)
               for item in items]
        if key == self._stats_key:
            return
        summary = self._summarize(items)
        self._stats_key = key
        self.app.call_from_thread(self.update, summary)

    def _item_size(self, item) -> tuple[int, bool]:
        """An item's file size in bytes and whether it was estimated.

        Reads the file's size when it's reachable; otherwise (drive not
        mounted, file gone) falls back to bitrate × duration from the
        database — silently, unlike beets' try_filesize, which logs a
        warning per missing file straight over the TUI.
        """
        try:
            return os.path.getsize(os.fsdecode(item.path)), False
        except OSError:
            return int((item.bitrate or 0) / 8 * (item.length or 0)), True

    def _summarize(self, items) -> str:
        if not items:
            return "Your collection is empty — scan a directory to get started."

        albums = set()
        artists = set()
        seconds = 0.0
        size = 0
        estimated = False
        genres = Counter()
        decades = Counter()
        for item in items:
            if item.album:
                albums.add((item.albumartist or item.artist, item.album))
            if item.artist:
                artists.add(item.artist)
            seconds += item.length or 0
            item_size, item_estimated = self._item_size(item)
            size += item_size
            estimated = estimated or item_estimated
            for genre in item.genres or []:
                genres[genre] += 1
            # Junk metadata puts tracks centuries away; keep plausible years
            # (1940+ also keeps the two-digit decade labels unambiguous).
            if 1940 <= item.year <= 2039:
                decades[item.year // 10 * 10] += 1

        counts = (f"♪ {len(items):,} tracks · {len(albums):,} albums · "
                  f"{len(artists):,} artists · {self._fmt_duration(seconds)} · "
                  f"{'~' if estimated else ''}{self._fmt_size(size)}")

        extras = []
        if genres:
            top = ", ".join(name for name, _ in genres.most_common(self.TOP_GENRES))
            extras.append(f"Top genres: {top}")
        if decades:
            extras.append(f"Decades: {self._decade_spark(decades)}")

        return counts + ("\n[dim]" + "  ·  ".join(extras) + "[/dim]" if extras else "")

    def _fmt_duration(self, seconds: float) -> str:
        minutes, _ = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _fmt_size(self, size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size /= 1024

    def _decade_spark(self, decades: Counter) -> str:
        peak = max(decades.values())
        parts = []
        for decade in sorted(decades):
            bar = self.SPARKS[
                min(len(self.SPARKS) - 1,
                    round(decades[decade] / peak * (len(self.SPARKS) - 1)))
            ]
            parts.append(f"{decade % 100:02d}s{bar}")
        return " ".join(parts)
