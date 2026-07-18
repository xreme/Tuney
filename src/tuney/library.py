import os
import subprocess
from pathlib import Path
import beets
from beets.library import Library
from platformdirs import PlatformDirs

beets.config.read()
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

def get_album(album_id: int):
    lib = Library(DB)
    return lib.get_album(album_id)

class DriveNotMounted(FileNotFoundError):
    """The volume holding the file isn't mounted right now."""

def _volume_root(path: str):
    """The /Volumes/<name> root of a path, or None for non-volume paths."""
    parts = Path(path).parts
    if len(parts) >= 3 and parts[:2] == ("/", "Volumes"):
        return Path(*parts[:3])
    return None

def locate_file(item_id: int):
    """Absolute path of an item's audio file on disk.

    Returns None when no item has this id. Raises DriveNotMounted when the
    file's volume isn't mounted, and FileNotFoundError when the volume is
    there but the file is gone.
    """
    item = get_item(item_id)
    if item is None:
        return None
    path = os.fsdecode(item.path)
    if not os.path.exists(path):
        volume = _volume_root(path)
        if volume is not None and not volume.exists():
            raise DriveNotMounted(path)
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

def remove_item(item, delete=False, with_album=False):
    """Remove item from user's library, optional variable to also delete the file from disk"""
    if delete:
        path = os.fsdecode(item.path)
        volume = _volume_root(path)
        if volume is not None and not volume.exists():
            raise DriveNotMounted(path)
    item.remove(delete=delete,with_album=with_album) 


def remove_album(album, delete=False):
    """Remove an album and all its tracks from the library, optionally
    deleting the audio files (and album art) from disk."""
    if delete:
        for item in album.items():
            path = os.fsdecode(item.path)
            volume = _volume_root(path)
            if volume is not None and not volume.exists():
                raise DriveNotMounted(path)
    album.remove(delete=delete, with_items=True)

def move_item():
    pass