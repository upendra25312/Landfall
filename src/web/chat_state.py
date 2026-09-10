"""Landfall chat state helpers.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

import json
import web_runtime
import web_storage


def _chat_blob(eid: str) -> str:
    return f"engagements/{eid}/_chat.json"


def _load_chat(eid: str) -> dict:
    try:
        return json.loads(web_storage._estimate_container().download_blob(_chat_blob(eid)).readall())
    except Exception:  # noqa: BLE001
        return {"engagement": eid, "current_response_id": None, "started_at": web_runtime._now(),
                "turns": [], "archived": []}


def _save_chat(eid: str, chat: dict) -> None:
    web_storage._estimate_container().upload_blob(
        _chat_blob(eid), json.dumps(chat, default=str).encode(), overwrite=True)
