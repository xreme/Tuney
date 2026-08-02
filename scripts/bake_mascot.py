"""Bake the mascot spritesheets into a Python module the TUI can import.

The sheets in `spritesheets/` are the editable source of truth; this turns them
into `tuney.tui.Panes.mascot_frames`, so the running app needs no image
decoding and no packaged data files.

Each sheet is a vertical strip of square 1-bit frames. A cell holds two
vertically stacked pixels as one half-block glyph, so a 16x16 frame becomes 16
columns by 8 rows and the pixels stay roughly square in a terminal.

Usage:  uv run python scripts/bake_mascot.py [--size N]
"""

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "spritesheets"
OUTPUT = ROOT / "src" / "tuney" / "tui" / "Panes" / "mascot_frames.py"

# Pixels per side to bake at; None keeps the sheets' own resolution. Scaling
# 1-bit line art down costs real fidelity — to shrink the mascot, redraw the
# sheets smaller instead.
TARGET_SIZE = None

# Sheet stem -> state key used by the widget. Unlisted sheets are ignored.
STATES = {
    "TuneyIdle": "idle",
    "TuneyThink": "thinking",
    "TuneyTalk": "talking",
    "TuneyWaiting": "waiting",
    "TuneyDone": "done",
    "TuneyError": "error",
    "TuneyInterrupted": "interrupted",
}

# (top pixel, bottom pixel) -> glyph.
GLYPHS = {(False, False): " ", (True, False): "▀",
          (False, True): "▄", (True, True): "█"}

ALPHA_THRESHOLD = 127


def resample(ink: list[list[bool]], size: int) -> list[list[bool]]:
    """Scale a 1-bit grid to `size` square, by majority vote per source block.

    Majority beats nearest-neighbour (which drops 1px lines) and "any ink wins"
    (which fattens them until features merge). See TARGET_SIZE.
    """
    source = len(ink)
    if size == source:
        return ink
    def span(index):
        start = index * source // size
        return range(start, max(start + 1, (index + 1) * source // size))
    scaled = []
    for y in range(size):
        row = []
        for x in range(size):
            block = [ink[b][a] for b in span(y) for a in span(x)]
            row.append(sum(block) * 2 >= len(block))
        scaled.append(row)
    return scaled


def frame_to_rows(frame: Image.Image, size: int) -> list[str]:
    """Collapse one square frame into half-block rows."""
    width, height = frame.size
    ink = [[frame.getpixel((x, y))[3] > ALPHA_THRESHOLD for x in range(width)]
           for y in range(height)]
    ink = resample(ink, size)
    return ["".join(GLYPHS[(ink[y][x], ink[y + 1][x])] for x in range(size))
            for y in range(0, size, 2)]


def load_sheet(path: Path, size: int | None) -> list[list[str]]:
    """Split a vertical strip into its frames, as half-block rows.

    `size` of None keeps the sheet's own resolution — no resampling at all.
    """
    sheet = Image.open(path).convert("RGBA")
    width, height = sheet.size
    size = width if size is None else size
    if height % width:
        raise SystemExit(f"{path.name}: height {height} is not a whole number "
                         f"of {width}x{width} frames")
    if size % 2:
        raise SystemExit(f"target size {size} must be even so rows pair "
                         "into half-blocks")
    if size > width:
        raise SystemExit(f"{path.name}: target size {size} is larger than the "
                         f"{width}px source; upscaling would only blur it")
    # Half-blocks give one colour per cell, so the art has to be single-ink.
    inks = {rgba[:3] for _, rgba in sheet.getcolors(maxcolors=1 << 16)
            if rgba[3] > ALPHA_THRESHOLD}
    if len(inks) > 1:
        raise SystemExit(f"{path.name}: expected 1-bit art, found {len(inks)} "
                         f"opaque colours: {sorted(inks)}")
    return [frame_to_rows(sheet.crop((0, top, width, top + width)), size)
            for top in range(0, height, width)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=TARGET_SIZE,
                        help="pixels per side to bake at (default: the "
                             "sheets' own resolution, which is what you want)")
    size = parser.parse_args().size

    sheets = {}
    for stem, state in STATES.items():
        path = SHEETS / f"{stem}.png"
        if not path.exists():
            print(f"  skip {state}: {path.name} not found")
            continue
        sheets[state] = load_sheet(path, size)
        print(f"  {state}: {len(sheets[state])} frames from {path.name}")
    if not sheets:
        raise SystemExit(f"no spritesheets found in {SHEETS}")

    sizes = {(len(f[0]), len(f[0][0])) for f in sheets.values()}
    if len(sizes) > 1:
        raise SystemExit(f"frames disagree on size: {sorted(sizes)}. Every "
                         "state must share one bounding box or the mascot "
                         "resizes mid-animation and the chat layout jumps.")
    (rows, cols), = sizes

    lines = [
        '"""Mascot animation frames, as half-block glyph rows.',
        "",
        "Generated by scripts/bake_mascot.py from spritesheets/ — do not edit by",
        "hand; edit the PNGs and re-run the script.",
        '"""',
        "",
        f"HEIGHT = {rows}",
        f"WIDTH = {cols}",
        "",
        "FRAMES: dict[str, list[list[str]]] = {",
    ]
    for state, frames in sheets.items():
        lines.append(f"    {state!r}: [")
        for frame in frames:
            lines.append("        [")
            lines += [f"            {row!r}," for row in frame]
            lines.append("        ],")
        lines.append("    ],")
    lines += ["}", ""]

    OUTPUT.write_text("\n".join(lines))
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({rows} rows x {cols} cols)")


if __name__ == "__main__":
    main()
