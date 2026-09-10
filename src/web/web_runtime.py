"""Landfall web runtime helpers.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import datetime as _dt
import logging
import os
import pathlib
from agent_limits import load_limits

PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")


AGENT_NAME = os.environ.get("AGENT_ID", "")  # Foundry agents are addressed by name


STORAGE_URL = os.environ.get("STORAGE_URL", "")  # assessment dashboard reads answers/estimate/*


_cred = DefaultAzureCredential()


_clients: dict = {}


def _openai_client():
    """Lazy — keep import (and container start) free of network / token calls."""
    if "openai" not in _clients:
        proj = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_cred)
        limits = load_limits()
        _clients["openai"] = proj.get_openai_client().with_options(timeout=30, max_retries=limits.retries)
    return _clients["openai"]


_HERE = pathlib.Path(__file__).parent


_EXPORT_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


log = logging.getLogger("landfall.web")
