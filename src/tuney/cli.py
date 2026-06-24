import typer
from tuney import library

app = typer.Typer()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Launch the interactive Terminal UI"""
    if ctx.invoked_subcommand is None:
        from tuney.tui import TuneyApp
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
        typer.echo(f"{item.title} ({item.album})")

@app.command()
def collection():
    results = library.all_items()
    for item in results:
        typer.echo(f"{item.title} ({item.album})")