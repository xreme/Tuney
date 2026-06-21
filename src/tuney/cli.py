import typer
from tuney import library

app = typer.Typer()

@app.command()
def scan(music_dir):
    library.scan(music_dir)
    typer.echo(f"Scanned {music_dir}")

@app.command()
def search(query):
    typer.echo(library.search(query))