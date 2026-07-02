#!/usr/bin/env python3
"""Profile import (startup) cost of a module or statement.

Usage:
    uv run python scripts/importprofile.py "from tuney.tui.tui import TuneyApp"
    uv run python scripts/importprofile.py "import tuney.library" --top 25
    uv run python scripts/importprofile.py "from tuney.tui.tui import TuneyApp" --min-ms 20

Runs the statement in a fresh subprocess with `-X importtime` so nothing is
cached, then ranks imports by cumulative time (total cost including children).
"""
import argparse
import re
import subprocess
import sys

LINE = re.compile(r"import time:\s*(\d+)\s*\|\s*(\d+)\s*\|(.*)")


def profile(statement: str) -> list[tuple[int, int, str]]:
    """Return [(self_us, cumulative_us, name), ...] for one cold import."""
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", statement],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"Statement failed:\n{proc.stderr}")

    rows = []
    for line in proc.stderr.splitlines():
        m = LINE.match(line)
        if m:
            self_us, cum_us, name = m.groups()
            rows.append((int(self_us), int(cum_us), name.strip()))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("statement", help="Python import statement to profile")
    ap.add_argument("--top", type=int, default=20, help="How many rows to show")
    ap.add_argument("--min-ms", type=float, default=0.0,
                    help="Hide imports whose cumulative time is below this")
    ap.add_argument("--sort", choices=["cumulative", "self"], default="cumulative")
    args = ap.parse_args()

    rows = profile(args.statement)
    total = max((cum for _, cum, _ in rows), default=0)

    key = (lambda r: r[1]) if args.sort == "cumulative" else (lambda r: r[0])
    rows.sort(key=key, reverse=True)

    print(f"\nTotal cold-import time: {total / 1000:.1f} ms")
    print(f"Ranked by {args.sort} time:\n")
    print(f"{'cumulative':>11}  {'self':>8}   module")
    print("-" * 60)
    shown = 0
    for self_us, cum_us, name in rows:
        if cum_us / 1000 < args.min_ms:
            continue
        depth = len(name) - len(name.lstrip("."))  # not reliable, names are stripped
        print(f"{cum_us / 1000:9.1f} ms  {self_us / 1000:6.1f} ms   {name}")
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
