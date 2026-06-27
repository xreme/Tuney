# Tuney

Your local music library assistant — scan, index, and search your music collection from the terminal.

## Technologies

| Function                                | Library        |
| --------------------------------------- | -------------- |
| Local music library management          | [Beets](https://beets.io/) |
| CLI parsing / processing                | [Typer](https://typer.tiangolo.com/) |
| Platform-dependent directory management | [platformdirs](https://github.com/platformdirs/platformdirs) |
| TUI rendering                           | [Textual](https://textual.textualize.io/) |

Requires **Python 3.13+**.

## Installation

Tuney uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Clone the repository
git clone https://github.com/osereme/tuney.git
cd tuney

# Install dependencies and the CLI
uv sync
```

> Beets must also be available on your `PATH`. It is installed as a dependency via uv, so after running `uv sync` the `beet` command will be available inside the project's virtual environment.

## How to Use

### Launch the interactive TUI

Running `tuney` with no arguments opens the terminal UI:

```bash
uv run tuney
```

From the main menu you can:

- **View Collection** — browse your entire library in a table (Artist / Title / Album / Year / Format). Press `/` to filter with a search box.
- **Search library** — type a query and browse matching results (Artist / Title / Album) in a table.
- **Scan Directory** — interactively browse your filesystem and import a folder into the library (see below).
- **Quit** — exit the application.

**Global keys**

| Key         | Action                     |
| ----------- | -------------------------- |
| `↑` / `↓`   | Move the selection         |
| `Enter`     | Select / submit            |
| `Escape`    | Back to the previous screen |
| `q`         | Quit                       |

#### Scanning from the TUI

Selecting **Scan Directory** opens a file browser starting in your current working
directory. Navigate to the folder you want to import, then scan it — progress streams
live as files are added to the library.

| Key             | Action                             |
| --------------- | ---------------------------------- |
| `↑` / `↓`       | Move through the list              |
| `→` / `Enter`   | Open the highlighted folder        |
| `←`             | Go up to the parent (or select `../`) |
| `Shift+S`       | Scan the current directory         |
| `Esc`           | Close                              |

> `Shift+S` is the capital `S` key, so it works in every terminal.

### Scan a music directory (CLI)

Index a folder of music files into the Tuney library:

```bash
uv run tuney scan /path/to/music
```

Running `scan` with no path scans the current directory:

```bash
uv run tuney scan
```

Tuney imports the files into a local Beets database stored in your platform's user data directory (e.g. `~/Library/Application Support/Tuney/Tuney.db` on macOS).

### Search from the command line

Run a headless search and print results directly to the terminal:

```bash
uv run tuney search "artist:Radiohead"
```

Results are printed as `Title (Album)` lines. Query syntax follows the [Beets query language](https://beets.readthedocs.io/en/stable/reference/query.html).

### List your collection

Print every item in your library:

```bash
uv run tuney collection
```

Results are printed as `Title (Album)` lines.
