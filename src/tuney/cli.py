import os

import typer
from tuney import library

app = typer.Typer()

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