# Tuney

<p align="center">
  <img src="images/tooneyImage.png" alt="Tooney, the Tuney mascot" width="180">
</p>

Your local music library assistant: scan, index, search, and chat with Tuney to maintain your collection, get recommendations, or learn about your favourite artists.

## Installation

Tuney uses [uv](https://docs.astral.sh/uv/) for dependency management and
requires **Python 3.13+**.

```bash
git clone https://github.com/osereme/tuney.git
cd tuney
uv sync
```

Beets is installed by `uv sync`, so `beet` is available inside the project's
virtual environment. Converting audio files also needs
[ffmpeg](https://ffmpeg.org/) on your `PATH` (`brew install ffmpeg`, or
`apt install ffmpeg`) — everything else works without it.

Two optional API keys unlock the AI and richer metadata search. Both can be set
under **Settings** in the TUI, where they are saved to your system keychain:

| Key        | What it enables                                                                                                                        |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| OpenRouter | The chat assistant. Without it, everything else still works.                                                                           |
| Last.fm    | Wishlist searches merge Last.fm results with MusicBrainz, adding releases MusicBrainz never catalogued, plus listener counts and tags. |

## Features

- **Browse and search** your collection in a filterable table, or from the
  command line with the [Beets query language](https://beets.readthedocs.io/en/stable/reference/query.html).
- **Chat** with an AI assistant in plain English — "how many Beatles songs do I
  have?", "rock or metal from the 90s", "clean up my duplicates". It can search,
  retag, fetch cover art and convert files, and asks before changing anything.
- **Scan** any folder into the library, with progress streaming live.
- **Convert** between MP3, AAC, Opus, Ogg, ALAC and FLAC — either exporting
  copies or replacing the files in your library, with the originals archived
  rather than deleted. You see what will be re-encoded before it runs.
- **Wishlist** music you don't own yet, searched across MusicBrainz and Last.fm.
- **Find duplicates**, repair metadata against MusicBrainz, and fetch missing
  cover art.

The TUI uses your terminal's ANSI colours, so it matches however your terminal
is themed.

## Usage

```bash
uv run tuney                              # open the TUI
uv run tuney scan /path/to/music          # index a folder (defaults to .)
uv run tuney search "artist:Radiohead"    # headless search
uv run tuney collection                   # list everything
uv run tuney duplicates                   # songs that exist as several files
uv run tuney convert "artist:Radiohead" --format alac
```

`convert` prints what it would do and asks first; `--dry-run` shows the exact
ffmpeg commands without changing anything. Run any command with `--help` for
its options.

Inside the TUI, `↑`/`↓` moves, `Enter` selects, `Escape` goes back and `q`
quits.

## Model evaluation

Tuney's agents are benchmarked against a fixed set of use cases,
scoring each candidate model on whether it took the right tool trajectory as
well as on latency, token use and cost. The scripts live in
[scripts/agent-evals/](scripts/agent-evals/), and each run writes a CSV to
[scripts/agent-evals/results/](scripts/agent-evals/results/).

## Technologies

| Function                                | Library                                                                                                    |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Local music library management          | [Beets](https://beets.io/)                                                                                 |
| Audio format conversion                 | Beets' `convert` plugin driving [ffmpeg](https://ffmpeg.org/)                                              |
| CLI parsing / processing                | [Typer](https://typer.tiangolo.com/)                                                                       |
| Platform-dependent directory management | [platformdirs](https://github.com/platformdirs/platformdirs)                                               |
| TUI rendering                           | [Textual](https://textual.textualize.io/)                                                                  |
| AI agent framework                      | [LangChain](https://python.langchain.com/) / LangGraph                                                     |
| LLM access                              | [OpenRouter](https://openrouter.ai/)                                                                       |
| Music metadata and cover art            | [MusicBrainz](https://musicbrainz.org/) / [Last.fm](https://www.last.fm/api) / iTunes / Deezer             |
| API key storage                         | [keyring](https://github.com/jaraco/keyring) + [python-dotenv](https://github.com/theskumar/python-dotenv) |
