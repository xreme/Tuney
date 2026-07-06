# Tuney

Your local music library assistant — scan, index, search, and chat with your music collection from the terminal.

## Technologies

| Function                                | Library                                                                                                    |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Local music library management          | [Beets](https://beets.io/)                                                                                 |
| CLI parsing / processing                | [Typer](https://typer.tiangolo.com/)                                                                       |
| Platform-dependent directory management | [platformdirs](https://github.com/platformdirs/platformdirs)                                               |
| TUI rendering                           | [Textual](https://textual.textualize.io/)                                                                  |
| AI agent framework                      | [LangChain](https://python.langchain.com/) / LangGraph                                                     |
| LLM access                              | [OpenRouter](https://openrouter.ai/)                                                                       |
| API key storage                         | [keyring](https://github.com/jaraco/keyring) + [python-dotenv](https://github.com/theskumar/python-dotenv) |

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

### AI setup (optional)

The chat assistant talks to an LLM through OpenRouter and needs an API key.
Everything else in Tuney works without one.

```bash
cp .env.example .env
# then edit .env and set:
# OPENROUTER_API_KEY=sk-or-...
```

You can also paste the key into **Settings** inside the TUI, which stores it
in your system keychain — no `.env` needed. Tuney checks the
`OPENROUTER_API_KEY` environment variable (or `.env`) first, then the
keychain. The chat model defaults to `moonshotai/kimi-k2.5` and can be changed
to any OpenRouter model id from the Settings screen.

## How to Use

### Launch the interactive TUI

Running `tuney` with no arguments opens the terminal UI:

```bash
uv run tuney
```

From the main menu you can:

- **View Collection** — browse your entire library in a table (Artist / Title / Album / Year / Format). Press `/` to filter with a search box.
- **Search library** — type a query and browse matching results (Artist / Title / Album) in a table.
- **Chat** — ask an AI assistant about your collection in plain English (see below).
- **Scan Directory** — interactively browse your filesystem and import a folder into the library (see below).
- **Settings** — manage the OpenRouter API key (saved to your system keychain), pick the chat model, and see where Tuney keeps its data.
- **Quit** — exit the application.

The TUI uses your terminal's ANSI color scheme, so it matches however your
terminal is themed.

**Global keys**

| Key       | Action                      |
| --------- | --------------------------- |
| `↑` / `↓` | Move the selection          |
| `Enter`   | Select / submit             |
| `Escape`  | Back to the previous screen |
| `q`       | Quit                        |

#### Chatting with your library

Selecting **Chat** opens Tuney's AI assistant. Ask questions in plain English —
it answers using live queries against your library, for example:

- "How many Beatles songs do I have?"
- "What genres are in my library?" / "Tell me about my collection"
- "Rock or metal tracks from the 90s"
- "What are some duplicates in my collection?"
- "Where on disk is the file for that track?" (if the track lives on a drive
  that isn't mounted right now, it tells you the path it was imported from and
  that the file can't be accessed until the drive is reconnected)

While the model works, its reasoning streams live into the reply box under
_Thinking..._ so you can see what it's doing; the trace is replaced by the
answer as soon as it starts. If the AI service stalls or errors, the failure
is shown in the reply instead of hanging.

There are two views, and Tuney remembers which one you last used:

- **Focus** (default) — the mascot plus the latest question and answer.
- **History** — the full scrolling conversation.

| Key      | Action                                    |
| -------- | ----------------------------------------- |
| `Enter`  | Send the message in the input box         |
| `Ctrl+S` | Swap between focus and history views      |
| `Ctrl+C` | Copy selected text (click-drag to select) |
| `Esc`    | Back to menu                              |

#### Scanning from the TUI

Selecting **Scan Directory** opens a file browser starting in your current working
directory. Navigate to the folder you want to import, then scan it — progress streams
live as files are added to the library.

| Key           | Action                                |
| ------------- | ------------------------------------- |
| `↑` / `↓`     | Move through the list                 |
| `→` / `Enter` | Open the highlighted folder           |
| `←`           | Go up to the parent (or select `../`) |
| `Shift+S`     | Scan the current directory            |
| `Esc`         | Close                                 |

#### Settings

Selecting **Settings** opens a small configuration panel:

- **OpenRouter API key** — shows where the active key comes from, and lets you
  save a new key to your system keychain or remove the stored one. A key set
  via the `OPENROUTER_API_KEY` environment variable always takes precedence
  over the keychain; the panel tells you when that's the case.
- **Chat model** — set any OpenRouter model id (default
  `moonshotai/kimi-k2.5`), or reset to the default. Takes effect the next time
  the chat agent starts, so restart Tuney if you've already chatted.
- **About** — where the library database and settings file live, and how many
  tracks are indexed.

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

### Find duplicate files

List songs that exist as more than one file, grouped by artist and title with
the path of every copy:

```bash
uv run tuney duplicates
```
