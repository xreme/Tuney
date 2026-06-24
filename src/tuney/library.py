import os
import subprocess
from pathlib import Path
from beets.library import Library
from platformdirs import PlatformDirs

CONFIG = Path("config/beets.yaml")
dirs = PlatformDirs("Tuney")
os.makedirs(dirs.user_data_path, exist_ok=True)
DB = dirs.user_data_path/"Tuney.db"

def scan(music_dir):
    subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import", "-A", "-q", music_dir],
        check=True
    )

def search(query):
    lib = Library(DB)
    return list(lib.items(query))

def all_items():
    lib = Library(DB)
    return list(lib.items())
        