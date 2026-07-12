from langchain.tools import tool
from tuney import config, library
from tuney.agents.Agent import Agent
import json
from os import fsdecode

SYSTEM_PROMPT = """
Agent focused on the organization and ordiness of the user's collection
"""

