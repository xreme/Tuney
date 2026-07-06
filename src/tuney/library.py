import os
import subprocess
from pathlib import Path
from beets.library import Library
from platformdirs import PlatformDirs

CONFIG = Path("config/beets.yaml")
dirs = PlatformDirs("Tuney")
os.makedirs(dirs.user_data_path, exist_ok=True)
DB = dirs.user_data_path/"Tuney.db"

# TODO implement library singleton

def scan(music_dir):
    subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import", "-A", "-q", music_dir],
        check=True
    )

def scan_stream(music_dir):
    proc = subprocess.Popen(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "import", "-A", music_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        yield line.rstrip()
    proc.wait()

def search(query):
    lib = Library(DB)
    return list(lib.items(query))

def all_items():
    lib = Library(DB)
    return list(lib.items())
        
def get_item(item_id: int):
    lib = Library(DB)
    return lib.get_item(item_id)

def locate_file(item_id: int):
    """Absolute path of an item's audio file on disk.

    Returns None when no item has this id. Raises FileNotFoundError when the
    library entry exists but the file is gone (e.g. the drive is unmounted).
    """
    item = get_item(item_id)
    if item is None:
        return None
    path = os.fsdecode(item.path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path

def duplicates():
    """Songs that exist as more than one file, as a list of item groups."""
    out = subprocess.run(
        ["beet", "-c", str(CONFIG), "-l", str(DB), "duplicates", "--full", "--format", "$id"],
        check=True,
        capture_output=True,
        text=True,
    )
    lib = Library(DB)
    groups = {}
    for line in out.stdout.splitlines():
        # The plugin prints "<id>: <number of copies>" per item.
        item = lib.get_item(int(line.split(":")[0]))
        groups.setdefault((item.artist, item.title), []).append(item)
    return list(groups.values())