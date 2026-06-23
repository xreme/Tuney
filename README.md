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

From the menu you can:

- **Search library** — opens a search screen where you can type a query and browse results (Artist / Title / Album) in a table.
- **Quit** — exits the application.

**Keyboard shortcuts**

| Key      | Action              |
| -------- | ------------------- |
| `Enter`  | Submit search query |
| `Escape` | Back to main menu   |
| `q`      | Quit                |

### Scan a music directory

Index a folder of music files into the Tuney library:

```bash
uv run tuney scan /path/to/music
```

Tuney imports the files into a local Beets database stored in your platform's user data directory (e.g. `~/Library/Application Support/Tuney/Tuney.db` on macOS).

### Search from the command line

Run a headless search and print results directly to the terminal:

```bash
uv run tuney search "artist:Radiohead"
```

Results are printed as `Title (Album)` lines. Query syntax follows the [Beets query language](https://beets.readthedocs.io/en/stable/reference/query.html).
