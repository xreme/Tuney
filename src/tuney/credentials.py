import os, keyring
from dotenv import load_dotenv

_SERVICE = "tuney"
_KEY = "openrouter_openai_key"

load_dotenv()
def get_api_key():
    return env_api_key() or keychain_api_key()

def env_api_key():
    return os.getenv("OPENROUTER_API_KEY")

def keychain_api_key():
    return keyring.get_password(_SERVICE, _KEY)

def save_api_key(value):
    keyring.set_password(_SERVICE, _KEY,value)

def delete_api_key():
    try:
        keyring.delete_password(_SERVICE, _KEY)
    except keyring.errors.PasswordDeleteError:
        return False
    return True