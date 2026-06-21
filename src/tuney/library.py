import subprocess
from pathlib import Path
from beets.library import Library

CONFIG = Path("config/beets.yaml")
DB = "tuney_library.db"

def scan(music_dir):
    subprocess.run(
        ["beet", "-c", str(CONFIG), "import", "-A","-q", music_dir],
        check=True
    )

def search(query):
    lib = Library(DB)
    return list(lib.items(query))


        