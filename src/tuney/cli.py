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
def scan(music_dir):
    """Add music into library."""
    library.scan(music_dir)
    typer.echo(f"Scanned {music_dir}")

@app.command()
def search(query):
    """Search your library"""
    results = library.search(query)
    for item in results:
        typer.echo(f"{item.title} ({item.album})")