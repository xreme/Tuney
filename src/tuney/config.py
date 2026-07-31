from platformdirs import user_config_path, user_music_path
import json
from enum import StrEnum
from dataclasses import dataclass, fields, asdict
import os

config_file = user_config_path("Tuney") / "settings.json"
config_file.parent.mkdir(parents=True, exist_ok=True)
_config = None


class ChatView(StrEnum):
    FOCUS =  'focus'
    HISTORY = 'history'


class ChatDetail(StrEnum):
    """How much information the chat assistant packs into its replies.
    Declaration order is the hotkey cycling order."""
    LOW = 'low'          # essentials only
    NORMAL = 'normal'    # essentials plus a little extra
    HIGH = 'high'        # lots of information, allowed to be verbose

class ImportAutotagMode(StrEnum):
    """What to do about metadata when songs are imported."""
    OFF = 'off'      # import files as-is, no metadata lookup
    SAFE = 'safe'    # autotag; skip albums without a confident match
    KEEP = 'keep'    # autotag; import uncertain albums with their existing tags


class ConvertFormat(StrEnum):
    """Target formats for conversion."""
    MP3 = 'mp3'      # lossy, universal
    AAC = 'aac'      # lossy, .m4a — Apple devices
    OPUS = 'opus'    # lossy, best quality per byte
    OGG = 'ogg'      # lossy, Vorbis
    ALAC = 'alac'    # lossless, .m4a — Apple devices
    FLAC = 'flac'    # lossless


LOSSY_FORMATS = frozenset({ConvertFormat.MP3, ConvertFormat.AAC,
                           ConvertFormat.OPUS, ConvertFormat.OGG})


class ConvertQuality(StrEnum):
    """How hard the encoder works. For lossy formats BEST raises the bitrate;
    for lossless ones the audio is identical either way and BEST only
    compresses harder."""
    NORMAL = 'normal'
    BEST = 'best'

DEFAULT_CHAT_MODEL = "google/gemini-2.5-flash"


def default_convert_dest() -> str:
    """Where converted copies land when the user hasn't chosen a folder."""
    return str(user_music_path() / "Tuney Converted")


def default_convert_archive() -> str:
    """Where originals are moved when a conversion replaces them in the
    library."""
    return str(user_music_path() / "Tuney Originals")

@dataclass
class Config:
    tui_chat_view: ChatView = ChatView.FOCUS
    chat_model: str = DEFAULT_CHAT_MODEL
    chat_detail: ChatDetail = ChatDetail.NORMAL
    import_autotag: ImportAutotagMode = ImportAutotagMode.OFF
    convert_format: ConvertFormat = ConvertFormat.MP3
    convert_quality: ConvertQuality = ConvertQuality.NORMAL
    # Empty means "use the default_convert_* path", resolved below.
    convert_dest: str = ""
    convert_archive: str = ""
    workspace_layout: dict | None = None

    @property
    def convert_dest_path(self) -> str:
        return self.convert_dest.strip() or default_convert_dest()

    @property
    def convert_archive_path(self) -> str:
        return self.convert_archive.strip() or default_convert_archive()

    def __post_init__ (self):
        for f in fields(self):
            # try to coerce the set field into the ENUM if not use the default
            if isinstance(f.type, type) and issubclass(f.type, StrEnum):
                raw_value = getattr(self, f.name)
                try:
                    setattr(self, f.name, f.type(raw_value))
                except (ValueError,TypeError):
                    setattr(self, f.name, f.default)

    @classmethod
    def load(cls):
        try:
            with open(config_file,'r', encoding='utf-8') as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        
        known_fields = {f.name for f in fields(cls)}
        user_config = {k: v for k, v in data.items() if k in known_fields}

        return cls(**user_config)
    
    def save(self):
        preferences = asdict(self)
        tmp_path = config_file.with_suffix(".tmp")

        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(preferences, file, indent=2)
        
        os.replace(tmp_path, config_file)

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    
    return _config
