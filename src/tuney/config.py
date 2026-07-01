from platformdirs import user_config_path
import json

config_file = user_config_path("Tuney") / "settings.json"
config_file.parent.mkdir(parents=True, exist_ok=True)

# TODO: Make this a data class so that preferences persist in memory
# class: abstract config items – within constructor have enum type 

DEFAULTS = {
    "tui_chat_view" : "focus"
}

def load_config():
    try:
        with open(config_file,'r', encoding='utf-8') as file:
            data = json.load(file)
    except (FileNotFoundError,json.JSONDecodeError):
        data = {}

    return {**DEFAULTS, **data}

# TODO: Make this safe
def write_config(item, pref):
    config = load_config()

    config[item] = pref

    with open(config_file, 'w', encoding='utf-8') as file:
        json.dump(config,file)


