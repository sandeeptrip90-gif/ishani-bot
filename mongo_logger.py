"""Optional, fail-open MongoDB logger for AI chat analysis.

Every document captures one user turn, the exact reply that was sent, the chat
history that preceded it, and the model/persona context used. Logging never
blocks a reply: documents go through a small daemon queue and a missing Mongo
configuration or a failed write is only printed, never raised into chat code.

Set ISHANI_MONGO_LOGGING=0 (or ISHANI_NO_DASHBOARD=1 in test harnesses) to turn
this off without changing code.
"""

from __future__ import annotations

import os
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_URI_ENV = "MONGODB_URI"
_DB_ENV = "MONGODB_DB"
_COLL_ENV = "MONGODB_COLLECTION"

DEFAULT_DB = "telegram_bot_db"
DEFAULT_COLLECTION = "ai_model_chat_history"

_MAX_TEXT = 4000
_MAX_HISTORY = 40
_MAX_QUEUE = 1000

_client = None
_collection = None
_lock = threading.Lock()
_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=_MAX_QUEUE)
_worker_started = False


def enabled() -> bool:
    """True only when a real URI is configured and logging is not opted out."""
    if os.environ.get("ISHANI_NO_DASHBOARD", "").strip() == "1":
        return False
    opt_out = os.environ.get("ISHANI_MONGO_LOGGING", "1").strip().lower()
    if opt_out in {"0", "false", "no", "off"}:
        return False
    uri = os.environ.get(_URI_ENV, "").strip()
    return bool(uri) and "<db_password>" not in uri


def _clip(value: Any, limit: int = _MAX_TEXT) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…[truncated]"


def _clean_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    cleaned: List[Dict[str, str]] = []
    for item in (history or [])[-_MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "at": _clip(item.get("at"), 40),
            "role": _clip(item.get("role"), 30),
            "text": _clip(item.get("text"), _MAX_TEXT),
        })
    return cleaned


def build_document(
    *,
    user_id: int,
    first_name: str,
    user_text: str,
    model_reply: str,
    history: Optional[List[Dict[str, Any]]] = None,
    raw_model_reply: Optional[str] = None,
    system_instruction: Optional[str] = None,
    provider: Optional[str] = None,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    scope: str = "private",
    source: str = "telegram",
    response_kind: str = "ai",
    status: str = "ok",
    keyword_match: Optional[str] = None,
    persona_version: Optional[int] = None,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one bounded analysis document. No secrets or raw API keys included."""
    return {
        "created_at": datetime.now(timezone.utc),
        "source": _clip(source, 40),
        "scope": _clip(scope, 80),
        "user_id": int(user_id or 0),
        "first_name": _clip(first_name, 120),
        "user_text": _clip(user_text),
        "model_reply": _clip(model_reply),
        "raw_model_reply": _clip(raw_model_reply if raw_model_reply is not None else model_reply),
        "chat_history": _clean_history(history),
        "chat_history_size": len(history or []),
        "system_instruction": _clip(system_instruction, _MAX_TEXT) if system_instruction else "",
        "provider": _clip(provider, 60),
        "endpoint": _clip(endpoint, 300),
        "model": _clip(model, 120),
        "response_kind": _clip(response_kind, 60),
        "status": _clip(status, 60),
        "keyword_match": _clip(keyword_match, 120) if keyword_match else "",
        "persona_version": persona_version,
        "latency_ms": int(latency_ms or 0),
        "error": _clip(error, 500) if error else "",
    }


def _get_collection():
    global _client, _collection
    if not enabled():
        return None
    with _lock:
        if _client is None:
            from pymongo import MongoClient

            _client = MongoClient(
                os.environ[_URI_ENV].strip(),
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000,
                socketTimeoutMS=3000,
            )
        if _collection is None:
            db = _client[os.environ.get(_DB_ENV, DEFAULT_DB).strip() or DEFAULT_DB]
            name = os.environ.get(_COLL_ENV, DEFAULT_COLLECTION).strip() or DEFAULT_COLLECTION
            _collection = db[name]
        return _collection


def insert_now(document: Dict[str, Any]) -> Optional[str]:
    """Synchronous insert. Used by the worker and by setup verification."""
    collection = _get_collection()
    if collection is None:
        return None
    result = collection.insert_one(document)
    return str(result.inserted_id)


def _worker() -> None:
    while True:
        document = _queue.get()
        try:
            insert_now(document)
        except Exception as exc:
            print(f"⚠️ Mongo chat log failed: {exc}", flush=True)
        finally:
            _queue.task_done()


def start_worker() -> bool:
    """Start one daemon writer; safe to call on every log attempt."""
    global _worker_started
    if not enabled() or _worker_started:
        return False
    with _lock:
        if _worker_started:
            return False
        threading.Thread(target=_worker, name="ishani-mongo-logger", daemon=True).start()
        _worker_started = True
    return True


def log_chat(document: Dict[str, Any]) -> bool:
    """Queue one document without ever blocking the chat reply."""
    if not enabled():
        return False
    start_worker()
    try:
        _queue.put_nowait(document)
        return True
    except queue.Full:
        print("⚠️ Mongo chat log queue full; dropped one document", flush=True)
        return False


def ping() -> bool:
    """Verify credentials/network without inserting or deleting anything."""
    collection = _get_collection()
    if collection is None:
        return False
    collection.database.client.admin.command("ping")
    return True
