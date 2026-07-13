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
    """Search your library"""
    results = library.search(query)
    for item in results:
        typer.echo(f"{item.id} | {item.title} ({item.album})")

@app.command()
def locate(query:str):
    """Search library for the path of item"""
    results = library.search(query)
    for item in results:
        typer.echo(f"{item.id} | {item.title} ({item.path})")

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
def remove(id):
    """Remove item based on item id"""
    item = library.get_item(id)

    library.remove_item(item, delete=True)