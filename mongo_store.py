"""Mongo-primary state store for every runtime JSON document.

JSON files are still written as a crash-safe local mirror, but MongoDB is the
source of truth when it is configured. Nothing is deleted here: the first run
seeds Mongo from whatever JSON files already exist, and later reads prefer the
Mongo copy.

The store is intentionally fail-open. A Mongo outage prints a warning and the
bot keeps using/local-writing the last known JSON mirror instead of crashing.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_URI_ENV = "MONGODB_URI"
_DB_ENV = "MONGODB_DB"
_STATE_COLLECTION_ENV = "MONGODB_STATE_COLLECTION"
_NO_DASHBOARD_ENV = "ISHANI_NO_DASHBOARD"
_OPT_OUT_ENV = "ISHANI_MONGO_STORAGE"

DEFAULT_DB = "ai_model_chat_db"
DEFAULT_STATE_COLLECTION = "app_state"

DATA_JSON_KEY = "data_json"
PERSONA_JSON_KEY = "persona_json"
CHAT_KEY_PREFIX = "chat:"

_lock = threading.RLock()
_client = None
_collection = None


def enabled() -> bool:
    """True when Mongo should be the source of truth for runtime state."""
    if os.environ.get(_NO_DASHBOARD_ENV, "").strip() == "1":
        return False
    opt_out = os.environ.get(_OPT_OUT_ENV, "1").strip().lower()
    if opt_out in {"0", "false", "no", "off"}:
        return False
    uri = os.environ.get(_URI_ENV, "").strip()
    return bool(uri) and "<db_password>" not in uri


def database_name() -> str:
    return os.environ.get(_DB_ENV, "").strip() or DEFAULT_DB


def state_collection_name() -> str:
    return os.environ.get(_STATE_COLLECTION_ENV, "").strip() or DEFAULT_STATE_COLLECTION


def chat_state_key(user_id: int) -> str:
    return f"{CHAT_KEY_PREFIX}{int(user_id)}"


def _get_collection():
    global _client, _collection
    if not enabled():
        return None
    with _lock:
        if _collection is not None:
            return _collection
        from pymongo import MongoClient

        uri = os.environ[_URI_ENV].strip()
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
        )
        _collection = _client[database_name()][state_collection_name()]
        return _collection


def load_state(key: str) -> Optional[Any]:
    """Read one state document. Missing/disabled/failed reads return None."""
    collection = _get_collection()
    if collection is None:
        return None
    try:
        document = collection.find_one({"_id": key})
        if not isinstance(document, dict) or "payload" not in document:
            return None
        return document["payload"]
    except Exception as exc:
        print(f"⚠️ Mongo state load failed [{key}]: {exc}", flush=True)
        return None


def save_state(key: str, payload: Any) -> bool:
    """Upsert one state document. Never throws into chat code."""
    collection = _get_collection()
    if collection is None:
        return False
    try:
        collection.update_one(
            {"_id": key},
            {
                "$set": {
                    "payload": copy.deepcopy(payload),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        return True
    except Exception as exc:
        print(f"⚠️ Mongo state save failed [{key}]: {exc}", flush=True)
        return False


def state_keys() -> List[str]:
    collection = _get_collection()
    if collection is None:
        return []
    try:
        return sorted(str(key) for key in collection.distinct("_id"))
    except Exception as exc:
        print(f"⚠️ Mongo state key scan failed: {exc}", flush=True)
        return []


def seed_json_file(path: Path, key: str, force: bool = False) -> bool:
    """Seed one Mongo document from a JSON file without overwriting existing data."""
    if not path.exists():
        return False
    if not force and load_state(key) is not None:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ Mongo seed skipped {path.name}: {exc}", flush=True)
        return False
    if not isinstance(payload, dict):
        return False
    return save_state(key, payload)


def seed_all(root: Path = Path(".")) -> List[str]:
    """Seed data.json, persona.json and every chats/<id>.json into Mongo."""
    if not enabled():
        return []
    seeded: List[str] = []
    for path, key in (
        (root / "data.json", DATA_JSON_KEY),
        (root / "persona.json", PERSONA_JSON_KEY),
    ):
        if seed_json_file(path, key):
            seeded.append(key)
    chat_dir = root / "chats"
    if chat_dir.exists():
        for path in sorted(chat_dir.glob("*.json")):
            key = chat_state_key(int(path.stem)) if path.stem.isdigit() else f"chat:{path.stem}"
            if seed_json_file(path, key):
                seeded.append(key)
    if seeded:
        print(f"☁️ Mongo state seeded: {len(seeded)} document(s)", flush=True)
    return seeded
