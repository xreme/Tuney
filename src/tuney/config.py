from platformdirs import user_config_path
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

@dataclass
class Config:
    tui_chat_view: ChatView = ChatView.FOCUS

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
