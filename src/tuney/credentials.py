import os, keyring
from dotenv import load_dotenv

_SERVICE = "tuney"
_KEY = "openrouter_openai_key"

load_dotenv()
def get_api_key():
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        return openrouter_key
    
    openrouter_key = keyring.get_password(_SERVICE,_KEY)
    if openrouter_key:
        return openrouter_key


    

def save_api_key(value):
    keyring.set_password(_SERVICE, _KEY,value)


    