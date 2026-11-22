"""
Telegram Bot: Ishani - Chelsea Football Assistant
Features:
- Admin Panel with inline buttons
- Auto link delete system for groups
- Scheduled automatic messages
- Help command
- Fixed bot reply logic
- JSON memory system for persistence
- Auto response caching to reduce API calls
- User tracking system
- Document storage and retrieval
"""

import ast
import asyncio
import base64
import hashlib
import hmac
import html
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import math
import os
import random
import re
import secrets
import shutil
import socket
import subprocess
import threading
import atexit
import time as _time
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx
from dotenv import load_dotenv
try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
except ImportError:
    TelegramClient = None
    events = None
    StringSession = None
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction, ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    ApplicationHandlerStop,
)

# ================= CONFIG =================
load_dotenv()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
GROUP_MODE = (os.environ.get("GROUP_MODE") or "all").strip().lower()
if GROUP_MODE not in ("all", "mentions"):
    GROUP_MODE = "all"

# Path B (optional): a real account can DM new members. Disabled unless all four
# values are configured, so the default bot never needs Telethon.
TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")
TG_SESSION = os.environ.get("TG_SESSION")
GROUP_ID = os.environ.get("GROUP_ID")

MASKED_KEY = "••••••"


def _is_masked_key(value: str) -> bool:
    text = (value or "").strip()
    return not text or set(text) <= set("•*·.x")


def _mask_key(value: str) -> str:
    key = (value or "").strip()
    if len(key) < 8:
        return MASKED_KEY if key else ""
    return key[:4] + "…" + key[-4:]


# ================= JSON MEMORY SYSTEM =================
class DataManager:
    """Handle all JSON file operations for persistent storage"""
    
    def __init__(self, file_path="data.json"):
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self.data = self._load_data()
    
    def _load_data(self) -> Dict[str, Any]:
        """Load data from JSON file, create if doesn't exist"""
        with self._lock:
            if self.file_path.exists():
                try:
                    with open(self.file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    print(f"❌ Error loading JSON: {e}")
                    return self._default_data()
            else:
                print(f"📝 Creating new data file: {self.file_path}")
                default = self._default_data()
                self._save_data(default)
                return default
    
    @staticmethod
    def _default_data() -> Dict[str, Any]:
        """Return default data structure"""
        return {
            "responses": {},
            "leads": {},
            "users": {},
            "pdf_file_id": None,
            "bot_muted": False,
            "stats": {
                "total_messages": 0,
                "total_users": 0,
                "total_broadcasts": 0
            },
            "ai_config": {
                "provider": "custom",
                "endpoint": "http://127.0.0.1:11434/v1",
                "api_key": "123",
                "model": "gptoss-20b"
            }
        }
    
    def _atomic_write(self, path: Path, payload: Dict[str, Any]) -> bool:
        """Write JSON atomically so a crash never leaves a half-written file."""
        with self._lock:
            tmp = path.with_name(path.name + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
                return True
            except Exception as e:
                print(f"❌ Error saving {path.name}: {e}")
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
                return False

    def _save_data(self, data: Dict[str, Any]):
        """Save data to JSON file"""
        self._atomic_write(self.file_path, data)
    
    def save(self):
        """Save current data"""
        self._save_data(self.data)
    
    def get_cached_response(self, prompt: str) -> Optional[str]:
        """Get cached response (case-insensitive)"""
        prompt_key = prompt.lower().strip()
        return self.data["responses"].get(prompt_key)
    
    def cache_response(self, prompt: str, response: str):
        """Cache a response"""
        prompt_key = prompt.lower().strip()
        self.data["responses"][prompt_key] = response
        self.save()
    
    def update_user(self, user_id: int, first_name: str):
        """Update or create user tracking data"""
        user_key = str(user_id)
        if user_key not in self.data["users"]:
            self.data["users"][user_key] = {
                "user_id": user_id,
                "first_name": first_name,
                "message_count": 0,
                "last_seen": None
            }
        
        self.data["users"][user_key]["message_count"] += 1
        self.data["users"][user_key]["last_seen"] = datetime.now().isoformat()
        self.data["stats"]["total_messages"] += 1
        self.save()
    
    def set_pdf_file_id(self, file_id: str):
        """Store PDF file_id"""
        self.data["pdf_file_id"] = file_id
        self.save()
    
    def get_pdf_file_id(self) -> Optional[str]:
        """Get stored PDF file_id"""
        return self.data.get("pdf_file_id")

    def save_media_asset(self, file_id: str, kind: str, name: str = "", description: str = ""):
        assets = self.data.setdefault("media_assets", [])
        asset = {"file_id": file_id, "kind": kind, "name": name, "description": description}
        assets[:] = [item for item in assets if item.get("file_id") != file_id]
        assets.append(asset)
        if kind == "document" and (name.lower().endswith(".pdf") or "pdf" in description.lower()):
            self.data["pdf_file_id"] = file_id
        self.save()

    def get_media_assets(self) -> List[Dict[str, str]]:
        assets = self.data.get("media_assets") or []
        if assets:
            return assets
        legacy_pdf = self.get_pdf_file_id()
        return ([{"file_id": legacy_pdf, "kind": "document", "name": "PDF document", "description": "pdf document details brochure"}]
                if legacy_pdf else [])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        return self.data.get("stats", {})
    
    def set_bot_muted(self, muted: bool):
        """Set bot mute status"""
        self.data["bot_muted"] = muted
        self.save()
    
    def is_bot_muted(self) -> bool:
        """Check if bot is muted"""
        return self.data.get("bot_muted", False)

    @staticmethod
    def _valid_user_id(user_id: Any) -> int:
        """Only a real positive integer user ID may address a chat file."""
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("invalid user id")
        return user_id

    @staticmethod
    def _group_key(group_id: Any) -> str:
        try:
            return str(int(group_id))
        except (TypeError, ValueError):
            return ""

    def audit(self, action: str, actor_id: Any, target: str = "", details: str = "") -> None:
        """Append an immutable-style audit entry for privileged changes."""
        log = self.data.setdefault("audit_log", [])
        if not isinstance(log, list):
            log = self.data["audit_log"] = []
        log.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": str(action)[:80],
            "actor_id": actor_id if isinstance(actor_id, int) else str(actor_id),
            "target": str(target)[:200],
            "details": str(details)[:500],
        })
        del log[:-200]
        self.save()

    def get_groups(self) -> Dict[str, Dict[str, Any]]:
        raw = self.data.setdefault("groups", {})
        if not isinstance(raw, dict):
            raw = self.data["groups"] = {}
        return raw

    def get_group(self, group_id: Any) -> Optional[Dict[str, Any]]:
        key = self._group_key(group_id)
        return self.get_groups().get(key) if key else None

    def get_group_business(self, group_id: Any) -> Dict[str, Any]:
        record = self.get_group(group_id)
        if not record:
            return {}
        business = record.get("business")
        return dict(business) if isinstance(business, dict) else {}

    def get_group_settings(self, group_id: Any) -> Dict[str, Any]:
        record = self.get_group(group_id)
        if not record:
            return {}
        settings = record.get("settings")
        return dict(settings) if isinstance(settings, dict) else {}

    def assign_group(self, admin_id: int, operator_id: int, group_id: Any) -> Dict[str, Any]:
        """Global admin gives one operator control of one group."""
        groups = self.get_groups()
        key = self._group_key(group_id)
        if not key:
            raise ValueError("invalid group id")
        record = groups.get(key) or {"group_id": int(key), "business": {}, "settings": {}}
        record["operator_id"] = int(operator_id)
        record["owner_id"] = int(operator_id)
        record["assigned_by"] = int(admin_id)
        record["assigned_at"] = datetime.now().isoformat(timespec="seconds")
        groups[key] = record
        self.audit("group_assigned", admin_id, key, f"operator={operator_id}")
        return record

    def unassign_group(self, admin_id: int, group_id: Any) -> bool:
        groups = self.get_groups()
        key = self._group_key(group_id)
        if key not in groups:
            return False
        previous = groups[key].get("operator_id")
        groups[key].pop("operator_id", None)
        self.audit("group_unassigned", admin_id, key, f"previous_operator={previous}")
        return True

    def is_operator_for(self, operator_id: Any, group_id: Any) -> bool:
        record = self.get_group(group_id)
        return bool(record and record.get("operator_id") == operator_id)

    def can_manage_group(self, user_id: Any, group_id: Any, admin_id: int) -> bool:
        return user_id == admin_id or self.is_operator_for(user_id, group_id)

    def operator_group_ids(self, operator_id: Any) -> List[int]:
        groups = self.get_groups()
        return [int(key) for key, value in groups.items() if value.get("operator_id") == operator_id]

    def set_group_details(self, actor_id: Any, admin_id: int, group_id: Any, key: str, value: Any) -> bool:
        """Operator may edit ONLY their assigned group's own details/settings."""
        allowed_business = {"name", "join_link", "welcome_message", "notes"}
        allowed_settings = {"bot_muted", "links_allowed", "group_mode"}
        key = (key or "").strip().lower()
        if key not in allowed_business | allowed_settings:
            return False
        if not self.can_manage_group(actor_id, group_id, admin_id):
            return False
        record = self.get_group(group_id)
        if not record:
            return False
        if key == "group_mode":
            mode = str(value).strip().lower()
            record.setdefault("settings", {})[key] = mode if mode in ("all", "mentions") else GROUP_MODE
        elif key in allowed_settings:
            flag = str(value).strip().lower() in {"1", "true", "yes", "on", "haan", "y"}
            record.setdefault("settings", {})[key] = flag
        else:
            record.setdefault("business", {})[key] = str(value).strip()[:500]
        self.audit("group_details_updated", actor_id, str(self._group_key(group_id)), f"{key}={str(value)[:120]}")
        return True

    @staticmethod
    def _hash_token(token: Any) -> str:
        return hashlib.sha256(str(token or "").strip().encode("utf-8")).hexdigest()

    def owner_role(self, user_id: Any) -> str:
        """Master Owner from config; Group Owner from accepted invitations."""
        if user_id == ADMIN_ID:
            return "master"
        owners = self.data.get("owners") or {}
        record = owners.get(str(user_id)) if isinstance(owners, dict) else None
        if isinstance(record, dict) and record.get("status") == "active":
            return str(record.get("role") or "")
        return ""

    def is_group_owner(self, user_id: Any, group_id: Any) -> bool:
        record = self.get_group(group_id)
        if not record:
            return False
        return (user_id == ADMIN_ID or record.get("owner_id") == user_id
                or record.get("operator_id") == user_id)

    def visible_group_ids(self, user_id: Any) -> List[int]:
        """Master sees all groups; owners see only their own."""
        if user_id == ADMIN_ID:
            return [int(key) for key in self.get_groups() if self._group_key(key)]
        return [int(key) for key in self.get_groups() if self.is_group_owner(user_id, key)]

    def create_invitation(self, inviter_id: int, invitee_id: Any = None,
                          invitee_username: str = "", group_id: Any = None) -> str:
        """Create a one-time, expiring Group Owner invitation. Token is stored hashed."""
        token = secrets.token_urlsafe(14)
        invitations = self.data.setdefault("invitations", {})
        if not isinstance(invitations, dict):
            invitations = self.data["invitations"] = {}
        key = self.get_groups()  # normalise groups dict before use
        del key
        now = datetime.now()
        invitations[self._hash_token(token)] = {
            "invited_by": int(inviter_id),
            "invitee_id": int(invitee_id) if invitee_id is not None else None,
            "invitee_username": (invitee_username or "").lstrip("@").strip(),
            "group_id": int(group_id) if self._group_key(group_id) else None,
            "role": "group",
            "created_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(days=7)).isoformat(timespec="seconds"),
            "accepted": False,
        }
        self.audit("owner_invitation_created", inviter_id,
                   str(group_id or ""), f"invitee={invitee_id or invitee_username or 'any'}")
        return token

    def get_invitation(self, token: Any) -> Optional[Dict[str, Any]]:
        invitations = self.data.get("invitations") or {}
        record = invitations.get(self._hash_token(token)) if isinstance(invitations, dict) else None
        return record if isinstance(record, dict) else None

    def accept_invitation(self, token: Any, user_id: int, username: str = "") -> Dict[str, Any]:
        invitations = self.data.setdefault("invitations", {})
        hashed = self._hash_token(token)
        record = invitations.get(hashed) if isinstance(invitations, dict) else None
        if not isinstance(record, dict):
            return {"ok": False, "message": "❌ Invalid invitation token."}
        if record.get("accepted"):
            return {"ok": False, "message": "❌ Ye invitation pehle hi use ho chuki hai."}
        try:
            if record.get("expires_at") and datetime.fromisoformat(record["expires_at"]) < datetime.now():
                return {"ok": False, "message": "❌ Invitation expire ho gayi (7 din). Nayi /assign use karein."}
        except (TypeError, ValueError):
            pass
        expected_id = record.get("invitee_id")
        if expected_id is not None and int(expected_id) != int(user_id):
            return {"ok": False, "message": "❌ Ye invitation doosre user ke liye hai."}
        expected_username = str(record.get("invitee_username") or "").lstrip("@").casefold()
        if expected_username and expected_username != str(username or "").casefold():
            return {"ok": False, "message": "❌ Ye invitation doosre username ke liye hai."}
        now = datetime.now().isoformat(timespec="seconds")
        owners = self.data.setdefault("owners", {})
        if not isinstance(owners, dict):
            owners = self.data["owners"] = {}
        owners[str(user_id)] = {
            "role": "group",
            "status": "active",
            "invited_by": record.get("invited_by"),
            "accepted_at": now,
        }
        group_id = record.get("group_id")
        if group_id:
            self.assign_group(int(record.get("invited_by") or ADMIN_ID), user_id, group_id)
            group_record = self.get_group(group_id)
            if group_record:
                group_record["owner_id"] = int(user_id)
                self.save()
        record["accepted"] = True
        record["accepted_by"] = int(user_id)
        record["accepted_at"] = now
        self.audit("owner_invitation_accepted", user_id, str(group_id or ""),
                   f"inviter={record.get('invited_by')}")
        return {"ok": True, "group_id": group_id}

    def register_group(self, user_id: int, group_id: Any, name: str = "",
                       verified_by: str = "") -> Optional[Dict[str, Any]]:
        if not self.owner_role(user_id):
            return None
        key = self._group_key(group_id)
        if not key:
            return None
        groups = self.get_groups()
        record = groups.get(key) or {"group_id": int(key), "business": {}, "settings": {}}
        if not isinstance(record.get("business"), dict):
            record["business"] = {}
        record["owner_id"] = int(user_id)
        record.setdefault("operator_id", int(user_id))
        record["registered_at"] = datetime.now().isoformat(timespec="seconds")
        record["registration_status"] = "verified" if verified_by else "pending"
        if verified_by:
            record["verified_by"] = str(verified_by)
        if (name or "").strip():
            record["business"]["name"] = name.strip()[:200]
        groups[key] = record
        self.audit("group_registered", user_id, key,
                   f"status={record['registration_status']}")
        return record

    def verify_group(self, admin_id: int, group_id: Any) -> bool:
        if admin_id != ADMIN_ID:
            return False
        record = self.get_group(group_id)
        if not record:
            return False
        record["registration_status"] = "verified"
        record["verified_by"] = int(admin_id)
        record["verified_at"] = datetime.now().isoformat(timespec="seconds")
        self.audit("group_verified", admin_id, str(self._group_key(group_id)), "master verification")
        return True

    def issue_web_token(self, user_id: int) -> Optional[str]:
        role = self.owner_role(user_id)
        if not role:
            return None
        token = secrets.token_urlsafe(20)
        tokens = self.data.setdefault("web_tokens", {})
        if not isinstance(tokens, dict):
            tokens = self.data["web_tokens"] = {}
        now = datetime.now()
        tokens[self._hash_token(token)] = {
            "user_id": int(user_id),
            "role": role,
            "group_ids": self.visible_group_ids(user_id),
            "created_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(days=30)).isoformat(timespec="seconds"),
        }
        self.audit("web_token_issued", user_id, role, "dashboard access granted")
        return token

    def get_web_token(self, token: Any) -> Optional[Dict[str, Any]]:
        tokens = self.data.get("web_tokens") or {}
        record = tokens.get(self._hash_token(token)) if isinstance(tokens, dict) else None
        if not isinstance(record, dict):
            return None
        try:
            if record.get("expires_at") and datetime.fromisoformat(record["expires_at"]) < datetime.now():
                return None
        except (TypeError, ValueError):
            pass
        return record

    def record_broadcast(self, actor_id: int, scope: str, results: List[Dict[str, Any]]) -> None:
        """Persist delivery status so the dashboard can report real outcomes."""
        sent = sum(1 for item in results if item.get("ok"))
        failed = len(results) - sent
        log = self.data.setdefault("broadcast_log", [])
        if not isinstance(log, list):
            log = self.data["broadcast_log"] = []
        log.insert(0, {
            "at": datetime.now().isoformat(timespec="seconds"),
            "actor_id": actor_id,
            "scope": str(scope)[:40],
            "sent": sent,
            "failed": failed,
            "results": results[:100],
        })
        del log[50:]
        self.audit("broadcast_sent", actor_id, str(scope)[:60], f"sent={sent} failed={failed}")

    def get_ai_config(self) -> Dict[str, Any]:
        """Local OpenAI-compatible model settings."""
        defaults = {
            "provider": "custom",
            "endpoint": "http://127.0.0.1:11434/v1",
            "api_key": "123",
            "model": "gptoss-20b"
        }
        stored = self.data.get("ai_config") or {}
        merged = {**defaults, **stored}
        merged["provider"] = "custom"
        if not merged.get("endpoint") or "generativelanguage.googleapis.com" in merged["endpoint"]:
            merged["endpoint"] = defaults["endpoint"]
            merged["api_key"] = defaults["api_key"]
        model_name = str(merged.get("model") or "").strip().lower()
        legacy_model = re.sub(r"[^a-z0-9]+", "", model_name)
        replaced_legacy_model = False
        if not model_name or "qwen" in legacy_model or "gemini" in legacy_model:
            merged["model"] = defaults["model"]
            replaced_legacy_model = True
        self.data["ai_config"] = merged
        if replaced_legacy_model:
            self.save()
        return merged

    def save_ai_config(self, endpoint: str, api_key: str, model: str, provider: str = "custom"):
        current = self.get_ai_config()
        current["provider"] = "custom"
        current["endpoint"] = (endpoint or "").strip()
        if api_key and api_key.strip() and not _is_masked_key(api_key):
            current["api_key"] = api_key.strip()
        current["model"] = (model or "").strip()
        self.data["ai_config"] = current
        self.save()
        return current

    def uses_openai_compatible(self) -> bool:
        cfg = self.get_ai_config()
        return bool(cfg.get("endpoint") and cfg.get("api_key"))

    # ----- per-user chat history (chats/<user_id>.json, date sections) -----
    CHAT_DIR = Path("chats")
    MAX_CHAT_MESSAGES = 80

    def _chat_file(self, user_id: int) -> Path:
        user_id = self._valid_user_id(user_id)
        self.CHAT_DIR.mkdir(exist_ok=True)
        return self.CHAT_DIR / f"{user_id}.json"

    @staticmethod
    def _scope_sections(record: Dict[str, Any], scope: str) -> Dict[str, Any]:
        conv = record.setdefault("conversations", {})
        if not isinstance(conv, dict):
            conv = record["conversations"] = {}
        entry = conv.get(scope)
        if not isinstance(entry, dict):
            entry = conv[scope] = {}
        sections = entry.get("sections")
        if not isinstance(sections, dict):
            sections = entry["sections"] = {}
        return sections

    def load_chat(self, user_id: int, first_name: str = "User", scope: str = "private") -> Dict[str, Any]:
        """Load one user's file. Personal memory is shared; conversation threads are scope-separated."""
        path = self._chat_file(user_id)
        with self._lock:
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "sections" in data:
                        conversations = data.get("conversations")
                        if not isinstance(conversations, dict):
                            conversations = data["conversations"] = {}
                        conversations.setdefault("private", {"sections": data.get("sections") or {}})
                        pref = ((data.get("memory") or {}).get("preferred_name") or "").strip()
                        if pref:
                            data["name"] = pref
                        elif not data.get("name") and first_name:
                            data["name"] = first_name
                        data["telegram_name"] = first_name
                        self._scope_sections(data, scope)
                        return data
                except Exception as e:
                    print(f"⚠️ Chat load error {user_id}: {e}")
        return {
            "user_id": int(user_id),
            "name": first_name or "User",
            "memory": {"about": "", "topics": [], "last_focus": "", "facts": []},
            "sections": {},
            "conversations": {scope: {"sections": {}}},
        }

    def save_chat(self, record: Dict[str, Any]):
        user_id = record.get("user_id")
        if user_id is None:
            return
        with self._lock:
            conv = record.get("conversations")
            if not isinstance(conv, dict):
                conv = record["conversations"] = {}
            if not conv:
                conv["private"] = {"sections": record.get("sections") or {}}
            for entry in conv.values():
                if not isinstance(entry, dict):
                    continue
                sections = entry.get("sections") or {}
                flat: List[tuple] = []
                for day in sorted(sections.keys()):
                    for msg in sections.get(day) or []:
                        flat.append((day, msg))
                if len(flat) > self.MAX_CHAT_MESSAGES:
                    keep = flat[-self.MAX_CHAT_MESSAGES:]
                    trimmed: Dict[str, List] = {}
                    for day, msg in keep:
                        trimmed.setdefault(day, []).append(msg)
                    entry["sections"] = trimmed
            private_entry = conv.get("private") or {}
            record["sections"] = private_entry.get("sections") or {}
            self._atomic_write(self._chat_file(user_id), record)

    def append_chat(self, user_id: int, first_name: str, role: str, text: str, scope: str = "private") -> Dict[str, Any]:
        with self._lock:
            record = self.load_chat(user_id, first_name, scope)
            pref = ((record.get("memory") or {}).get("preferred_name") or "").strip()
            record["name"] = pref or record.get("name") or first_name or "User"
            record["telegram_name"] = first_name
            day = datetime.now().strftime("%Y-%m-%d")
            self._scope_sections(record, scope).setdefault(day, []).append({
                "at": datetime.now().isoformat(timespec="seconds"),
                "role": role,
                "text": (text or "").strip()[:1500],
            })
            if role == "user":
                self._refresh_memory(record, text or "")
            self.save_chat(record)
            user_key = str(user_id)
            if user_key in self.data.get("users", {}):
                self.data["users"][user_key]["chat_file"] = str(self._chat_file(user_id))
                self.data["users"][user_key]["last_focus"] = (record.get("memory") or {}).get("last_focus", "")
                self.save()
            return record

    def recent_chat(self, user_id: int, first_name: str = "User", limit: int = 24,
                    scope: str = "private") -> List[Dict[str, str]]:
        """Recent thread for exactly one scope, oldest first."""
        with self._lock:
            record = self.load_chat(user_id, first_name, scope)
            messages: List[Dict[str, str]] = []
            sections = self._scope_sections(record, scope)
            for day in sorted(sections.keys()):
                messages.extend(sections.get(day) or [])
            return messages[-limit:]

    @staticmethod
    def _refresh_memory(record: Dict[str, Any], user_text: str):
        mem = record.setdefault("memory", {"about": "", "topics": [], "last_focus": "", "preferred_name": "", "facts": []})
        text = (user_text or "").strip()
        mem["last_focus"] = text[:180]
        skip_topics = {
            "hi", "hii", "hello", "hey", "ok", "okay", "haan", "haa", "yes",
            "thanks", "thank you", "bye", "good morning", "good night",
        }
        if text and text.lower() not in skip_topics and len(text) > 8:
            topics = [t for t in (mem.get("topics") or []) if t]
            low = {t.lower() for t in topics}
            snippet = text[:90]
            if snippet.lower() not in low:
                topics.append(snippet)
            mem["topics"] = topics[-10:]
        name_hit = re.search(
            r"(?:mera\s+na+m(?:e)?|my\s+name\s+is)\s+(?:hai\s+)?([A-Za-z\u0900-\u097F]{2,24})",
            text,
            re.IGNORECASE,
        )
        if name_hit:
            raw_name = re.sub(r"[^A-Za-z\u0900-\u097F]", "", name_hit.group(1)).strip()
            if raw_name.lower() not in {"hai", "hoon", "hun", "tha", "from", "the"}:
                nice = raw_name[:1].upper() + raw_name[1:]
                mem["preferred_name"] = nice
                record["name"] = nice
                mem["about"] = f"Unka naam {nice} hai. Telegram pe sir/ji laga ho to ignore karo, naam {nice} hi bolo."
        city = re.search(
            r"(?:i(?:'?m| am) from|reh(?:ta|ti) (?:hoon|hun)|main)\s+([A-Za-z\u0900-\u097F]{3,24})\s+(?:se|from)",
            text,
            re.IGNORECASE,
        )
        if city:
            extra = f"Jagah: {city.group(1).strip()}"
            if extra not in (mem.get("about") or ""):
                mem["about"] = ((mem.get("about") or "") + " " + extra).strip()

        # Explicit self-corrections / remembered facts. Only ever applied to this user's record.
        remembered = re.search(
            r"(?:yaad\s+rakho|yaad\s+rahe\s+ki|remember\s+that|note\s+that|meri\s+jaankari\s*[:\-]?)\s*(.+)",
            text, re.IGNORECASE,
        )
        corrected = re.search(r"(?:actually|correction|sach\s+to\s+yeh\s+hai|asli\s+baat)\s*[,:]?\s*(.+)", text, re.IGNORECASE)
        age_hit = re.search(r"\b(?:i\s+am|i'm|main)\s+(\d{1,2})\s*(?:years?\s+old|saal\s+ka|saal\s+ki)\b", text, re.IGNORECASE)
        work_hit = re.search(
            r"\b(?:i\s+work\s+as|i\s+am\s+a|i\s+am\s+an|main\s+ek)\s+([A-Za-z][A-Za-z -]{2,30})\b|"
            r"\bmain\s+([A-Za-z][A-Za-z -]{2,30}?)\s+(?:hoon|hun|hain)\b",
            text, re.IGNORECASE,
        )

        new_facts: List[str] = []
        if remembered:
            new_facts.append("Facts: " + remembered.group(1).strip()[:140])
        if corrected:
            new_facts.append("Correction: " + corrected.group(1).strip()[:140])
        if age_hit:
            new_facts.append(f"Age: {age_hit.group(1)}")
        if work_hit:
            work_value = (work_hit.group(1) or work_hit.group(2) or "").strip()
            if work_value:
                new_facts.append("Work: " + work_value.title())
        if new_facts:
            facts = [item for item in (mem.get("facts") or []) if isinstance(item, str)]
            known = {item.casefold() for item in facts}
            for fact in new_facts:
                if fact.strip() and fact.casefold() not in known:
                    facts.append(fact)
                    known.add(fact.casefold())
            mem["facts"] = facts[-20:]

# Initialize data manager
dm = DataManager("data.json")

# ========== LEAD STATE (per-user chat memory) ==========
_LEAD_JOINED_RE = re.compile(
    r"\b(?:joined|join (?:kar liya|kar diya|ho gaya|ho gayi|hoon)|"
    r"(?:group|channel) me (?:aa gaya|join ho gaya)|add ho gaya|member ho gaya)\b",
    re.IGNORECASE,
)
_LEAD_DEPOSIT_RE = re.compile(
    r"\b(?:deposit (?:kar diya|ho gaya|done)|paid|payment (?:ho gaya|kar diya)|"
    r"(?:₹|rs\.?\s*)?200 (?:bhej diya|de diya|kar diya)|start (?:kar diya|ho gaya))\b",
    re.IGNORECASE,
)


def _lead_snapshot(lead: Dict[str, Any]) -> Dict[str, Any]:
    try:
        stage = int(lead.get("stage") or 0)
    except (TypeError, ValueError):
        stage = 0
    return {
        "stage": stage,
        "joined": bool(lead.get("joined")),
        "deposit": bool(lead.get("deposit")),
        "dm_nudged": bool(lead.get("dm_nudged")),
        "contained": bool(lead.get("contained")),
    }


def _lead_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    mem = record.get("memory")
    if not isinstance(mem, dict):
        return _lead_snapshot({})
    lead = mem.get("lead")
    if not isinstance(lead, dict):
        lead = {}
    legacy = (dm.data.get("leads") or {}).get(str(record.get("user_id") or ""))
    if isinstance(legacy, dict):
        lead.setdefault("joined", bool(legacy.get("joined")))
        lead.setdefault("deposit", bool(legacy.get("deposited") or legacy.get("deposit")))
    return _lead_snapshot(lead)


def get_lead_state(user_id: int, first_name: str = "User") -> Dict[str, Any]:
    """Read the lead ladder from this user's chat memory (shared by group and DM)."""
    return _lead_from_record(dm.load_chat(user_id, first_name))


def update_lead_state(user_id: int, user_text: str = "", first_name: str = "User",
                      flags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist confirmed steps in memory as {stage, joined, deposit}."""
    record = dm.load_chat(user_id, first_name)
    mem = record.get("memory")
    if not isinstance(mem, dict):
        mem = record["memory"] = {}
    lead = mem.get("lead")
    if not isinstance(lead, dict):
        lead = mem["lead"] = {}
    legacy = (dm.data.get("leads") or {}).get(str(user_id))
    if isinstance(legacy, dict):
        lead.setdefault("joined", bool(legacy.get("joined")))
        lead.setdefault("deposit", bool(legacy.get("deposited") or legacy.get("deposit")))
    text = user_text or ""
    if _LEAD_JOINED_RE.search(text):
        lead["joined"] = True
    if _LEAD_DEPOSIT_RE.search(text):
        lead["deposit"] = True
    for key, value in (flags or {}).items():
        if key in ("joined", "deposit", "dm_nudged", "contained"):
            lead[key] = bool(value)
    if lead.get("deposit"):
        lead["stage"] = 3
    elif lead.get("joined"):
        lead["stage"] = 2
    elif text or lead.get("dm_nudged"):
        lead["stage"] = 1
    dm.save_chat(record)
    return _lead_snapshot(lead)


def lead_state_about(state: Dict[str, Any]) -> str:
    """Compact lead ladder carried on the memory 'About them' line."""
    note = ""
    if state.get("contained"):
        note = " Their group objection was deleted and they were invited here; continue calmly in DM."
    return (
        f"Lead state: stage={int(state.get('stage') or 0)}, "
        f"joined={'yes' if state.get('joined') else 'no'}, "
        f"deposit={'yes' if state.get('deposit') else 'no'}." + note + " "
        "A completed rung is done — never ask it again; continue from the current stage."
    )


# ========== RESPONSE CACHE (IN-MEMORY) ==========
response_cache = {}
MAX_CACHE_SIZE = 100

def get_cache_key(prompt: str, system_instruction: Optional[str] = None,
                  history: Optional[List[Dict[str, str]]] = None) -> str:
    """Generate a cache key that keeps persona and chat context separate."""
    history_text = "|".join(
        f"{item.get('role')}:{item.get('text') or ''}" for item in (history or [])
    )
    key_str = f"{prompt.lower().strip()}|{system_instruction}|{history_text}"
    return hashlib.md5(key_str.encode()).hexdigest()

async def get_cached_response_api(prompt: str, system_instruction: Optional[str] = None,
                                  history: Optional[List[Dict[str, str]]] = None) -> Optional[Any]:
    """Return a cached reply when context matches; otherwise call the API and cache it."""
    cache_key = get_cache_key(prompt, system_instruction, history)
    cached = response_cache.get(cache_key)
    if cached is not None:
        print("♻️ Response cache hit")
        return cached

    response = await call_ai_with_retry(
        prompt=prompt,
        system_instruction=system_instruction,
        history=history,
    )

    if response and response.text:
        cleaned = clean_reply_text(response.text)
        response = type('obj', (object,), {'text': cleaned})()
        if len(response_cache) < MAX_CACHE_SIZE:
            response_cache[cache_key] = response
        dm.cache_response(prompt, cleaned)
        print("💾 Response cached")

    return response

# ========== AI PROVIDER (custom OpenAI-compatible, else Gemini) ==========
# Remember which transport actually works for an endpoint so we stop paying for
# a failed /api/chat probe on every single request to an OpenAI-compatible host.
_TRANSPORT_CACHE: Dict[str, str] = {}


def _openai_chat_url(endpoint: str) -> str:
    url = (endpoint or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    if "/v1/" in url:
        return url
    return url + "/v1/chat/completions"


def _ollama_chat_url(openai_url: str) -> str:
    """Native Ollama API. This is the endpoint that actually honors think:false."""
    base = (openai_url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/api/chat"


def _simple_text_response(text: str):
    return type("obj", (object,), {"text": text})()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits = []
        for part in content:
            if isinstance(part, str):
                bits.append(part)
            elif isinstance(part, dict):
                bits.append(str(part.get("text") or part.get("content") or ""))
        return "\n".join(bits)
    return ""


_FINAL_MARK = re.compile(
    r"(?:^|\n)\s*(?:final reply|final response|reply to (?:the )?user|message to send)\s*:\s*",
    re.IGNORECASE,
)
_THINKING_ONLY = re.compile(
    r"^\s*(?:thinking process|thinking|analysis|reasoning|let me think|we need to (?:answer|respond)|i should (?:answer|respond))\b|^\s*\d+\.\s+\*\*analyze\b|^\s*<think\b",
    re.IGNORECASE,
)


def final_chat_text(text: str) -> str:
    """Keep only the message a person should read. Drop chain-of-thought from every model format."""
    if not text:
        return ""
    raw = str(text).replace("\r\n", "\n").strip()
    if not raw:
        return ""

    finals = re.findall(
        r"<\|channel\|>final<\|message\|>(.*?)(?:<\|end\|>|<\|start\|>|$)",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if finals:
        raw = finals[-1]
    else:
        # Never expose an analysis-only Harmony turn when no final answer was emitted.
        if re.search(r"<\|channel\|>analysis<\|message\|>", raw, re.IGNORECASE) and not re.search(r"<\|channel\|>final<\|message\|>", raw, re.IGNORECASE):
            return ""
        raw = re.sub(
            r"<\|channel\|>analysis<\|message\|>.*?(?=<\|start\|>|<\|channel\|>|$)",
            "",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )

    raw = re.sub(r"<think\b[^>]*>.*?(?:</think\s*>|$)", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<thinking\b[^>]*>.*?(?:</thinking\s*>|$)", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<\|[^|\n]{1,80}\|>", "", raw)
    raw = re.sub(
        r"(?im)^.*\b(?:the user (?:says|said|wants|is asking)|they want to know|probably ask(?: for clarification)?|the assistant (?:should|means)|i should (?:ask|reply|respond)|my (?:reply|response) should)\b.*$",
        "",
        raw,
    )
    raw = raw.strip()

    marks = list(_FINAL_MARK.finditer(raw))
    if marks:
        raw = raw[marks[-1].end():].strip()
    if _THINKING_ONLY.search(raw):
        return ""
    return raw.strip()


def _visible_model_text(message: Dict[str, Any]) -> str:
    """Ignore explicit reasoning fields and expose only the final answer content."""
    if str(message.get("channel") or message.get("reasoning_channel") or "").lower() == "analysis":
        return ""
    return final_chat_text(_content_to_text(message.get("content")))


def _fit_local_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve the full persona and recent conversation without truncating either."""
    system = []
    rest = []
    for item in messages:
        if item.get("role") == "system":
            system.append({"role": "system", "content": item.get("content") or ""})
        else:
            content = (item.get("content") or "").strip()
            # Tool turns have empty content but must stay attached to their tool_calls.
            if content or item.get("tool_calls") or item.get("role") == "tool":
                normalized: Dict[str, Any] = {
                    "role": item.get("role") or "user",
                    "content": content,
                }
                if item.get("tool_calls"):
                    normalized["tool_calls"] = item["tool_calls"]
                if item.get("tool_call_id"):
                    normalized["tool_call_id"] = item["tool_call_id"]
                if item.get("name"):
                    normalized["name"] = item["name"]
                rest.append(normalized)
    return system + rest[-24:]


_ROMAN_HINDI_MARKERS = re.compile(
    r"\b(haan|nahi|nahin|kya|kaise|kyun|kyu|tum|aap|mujhe|mera|meri|hai|hain|hoon|ho|yaar|acha|accha|chahiye|karna|karo|batao|bhejo)\b",
    re.IGNORECASE,
)


def _language_mismatch(user_text: str, reply: str) -> Optional[str]:
    """Return a language/script correction target when local output clearly drifts."""
    if re.search(r"[\u0900-\u097f]", user_text or ""):
        return "Hindi in Devanagari" if not re.search(r"[\u0900-\u097f]", reply or "") else None
    target_hinglish = bool(_ROMAN_HINDI_MARKERS.search(user_text or ""))
    reply_has_devanagari = bool(re.search(r"[\u0900-\u097f]", reply or ""))
    reply_has_hinglish = bool(_ROMAN_HINDI_MARKERS.search(reply or ""))
    if target_hinglish:
        return "natural Roman Hindi/Hinglish" if reply_has_devanagari or not reply_has_hinglish else None
    if reply_has_devanagari or reply_has_hinglish:
        return "English"
    return None


async def call_custom_openai(
    prompt: str,
    system_instruction: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    extra_messages: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Any]:
    cfg = dm.get_ai_config()
    url = _openai_chat_url(cfg.get("endpoint", ""))
    api_key = cfg.get("api_key") or ""
    model = (cfg.get("model") or "").strip() or "gptoss-20b"
    if not url or not api_key:
        raise RuntimeError("Custom AI provider is not configured")

    hidden = "Keep internal reasoning private. Send only the final message the user should read. Never narrate your thought process, label your answer, or write 'The user says'. Reply in the same language and script as the user's latest message."
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction.strip() + "\n\n" + hidden})
    else:
        messages.append({"role": "system", "content": hidden})
    for item in history or []:
        # Telegram stores replies as "bot"; the dashboard stores them as "assistant".
        # Treat both as model turns or local chat history becomes user/user/user.
        role = "assistant" if str(item.get("role") or "").lower() in {"bot", "assistant"} else "user"
        content = (item.get("text") or "").strip()
        if role == "assistant":
            content = final_chat_text(content)
        if content:
            messages.append({"role": role, "content": content})
    # Tool results are inserted between history and the final user turn so the
    # model sees the same persona and conversation, plus verified tool evidence.
    for item in extra_messages or []:
        if isinstance(item, dict) and item.get("role"):
            messages.append(dict(item))
    messages.append({"role": "user", "content": prompt})
    messages = _fit_local_messages(messages)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _openai_payload(temperature: float, thinking_off: bool) -> dict:
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": 350,
            "temperature": temperature,
        }
        if thinking_off:
            # /v1/chat/completions ignores think:false. These are the switches it reads.
            body["reasoning_effort"] = "none"
            body["reasoning"] = {"effort": "none"}
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        return body

    def _reply_from_openai(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _visible_model_text(message)

    async def _ask(http: httpx.AsyncClient, temperature: float) -> str:
        # Only attempt the native Ollama endpoint while it is known to work.
        # After one failure we reuse the OpenAI-compatible transport directly.
        if tools is None and "api.openai.com" not in url and _TRANSPORT_CACHE.get(url) != "openai":
            try:
                native = await http.post(
                    _ollama_chat_url(url),
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "think": False,
                        "options": {"temperature": temperature, "num_predict": 350},
                    },
                )
                if native.status_code < 400:
                    message = (native.json() or {}).get("message") or {}
                    if message:
                        _TRANSPORT_CACHE[url] = "native"
                        return final_chat_text(str(message.get("content") or "")), []
            except Exception:
                pass
            _TRANSPORT_CACHE[url] = "openai"
        res = await http.post(url, headers=headers, json=_openai_payload(temperature, True))
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code == 400:
            res = await http.post(url, headers=headers, json=_openai_payload(temperature, False))
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code >= 400:
            err = data.get("error", {})
            msg = err.get("message") if isinstance(err, dict) else str(err) or res.text
            raise RuntimeError(f"Custom AI {res.status_code}: {msg}")
        choices = data.get("choices") or []
        message = choices[0].get("message") or {} if choices else {}
        calls: List[Dict[str, Any]] = []
        for index, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (TypeError, ValueError):
                    arguments = {}
            calls.append({
                "id": str(call.get("id") or f"call_{index}"),
                "name": str(name),
                "arguments": arguments if isinstance(arguments, dict) else {},
            })
        return _reply_from_openai(data), calls

    async with httpx.AsyncClient(timeout=90) as http:
        text, calls = await _ask(http, 0.8)
        if not text and not calls:
            print("⚠️ Model returned only thinking. Asking again with thinking off.", flush=True)
            text, calls = await _ask(http, 0.4)
        if text and not calls:
            target_language = _language_mismatch(prompt, text)
            if target_language:
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Rewrite the reply immediately above in {target_language}. "
                        "Keep its meaning, company facts, names, amounts, and URLs unchanged. "
                        "Do not add new claims or commentary. Return only the rewritten reply."
                    ),
                })
                corrected, correction_calls = await _ask(http, 0.2)
                if corrected and not correction_calls:
                    text = corrected
        response = _simple_text_response(text)
        response.tool_calls = calls
        return response


async def call_ai_with_retry(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_retries: int = 3,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Any]:
    """Call the configured local OpenAI-compatible model."""
    for attempt in range(max_retries):
        try:
            return await call_custom_openai(prompt, system_instruction, history=history)
        except Exception as e:
            error_str = str(e)
            is_busy = "503" in error_str or "UNAVAILABLE" in error_str
            is_rate_limited = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            if is_busy or is_rate_limited:
                if attempt < max_retries - 1:
                    wait_time = 10 if is_busy else 2 ** attempt
                    print(f"⏳ Server busy (503). Retrying in {wait_time}s..." if is_busy else f"⏳ Rate limited. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ Rate limit exceeded after {max_retries} retries.")
                    if is_busy:
                        raise
                    return None
            else:
                raise
    return None


# ========== PRE-WRITTEN MESSAGES ==========
# Content lives in persona.json (prewritten_messages).
# Loaded by load_prewritten_messages() with the persona helpers below.
WELCOME_MESSAGES: List[str] = []
LEFT_MESSAGES: List[str] = []
DM_WELCOME_MESSAGES: List[str] = []

# ========== ACKNOWLEDGMENT & CHAT ENDING WORDS ==========
ACKNOWLEDGMENT_WORDS = {
    "ok", "okay", "k", "thanks", "thank you", "thankyou",
    "done", "theek hai", "shukriya", "samajh gaya",
    "samajh gaye", "accha", "achi baat hai", "bilkul",
    "understood", "got it", "yes", "haan",
    "thik hai", "thik h", "alright", "cool", "nice"
}

CHAT_ENDING_WORDS = {
    "bye", "goodbye", "bye bye", "khuda hafiz",
    "alvida", "see you", "tc", "take care",
    "later", "see ya", "cya", "exit", "quit",
    "stop", "band karo", "enough", "jaata hoon"
}

def clean_reply_text(text: str) -> str:
    """Strip thinking dumps and RAG citation junk. Telegram only gets the reply."""
    if not text:
        return text
    text = final_chat_text(text)
    if not text:
        return ""
    text = re.sub(r"\[cite:[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[source:[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r" +([,.!?;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def user_language_notice(user_text: str, english: str, hinglish: str, hindi: str) -> str:
    if re.search(r"[\u0900-\u097f]", user_text or ""):
        return hindi
    if re.search(r"\b(kya|kaise|kyun|mujhe|tum|aap|hai|ho|bhejo|chahiye|haan|nahi|yaar)\b", user_text or "", re.IGNORECASE):
        return hinglish
    return english


# ========== KEYWORD-BASED FAQ ==========
# Content lives in persona.json (keyword_responses).
# Loaded by load_keyword_responses() once the persona helpers are defined below.
KEYWORD_RESPONSES: Dict[str, str] = {}

# ========== ALLOWED LINKS (WHITELIST) ==========
ALLOWED_LINKS = [
]

# ========== SMART KEYWORD DETECTOR ==========
def get_keyword_response(user_text: str) -> Optional[str]:
    """Check if user text matches any keyword"""
    user_text_lower = user_text.lower()
    
    for keyword, response in KEYWORD_RESPONSES.items():
        if keyword in user_text_lower:
            print(f"✅ Keyword match: '{keyword}' (saved API call!)")
            return response
    
    return None

# ========== COMPREHENSIVE LINK DETECTION ==========
def has_any_links(text: str) -> bool:
    """Check if text contains ANY type of link"""
    if not text:
        return False
    
    # Pattern 1: HTTP/HTTPS links
    http_pattern = r'https?://[^\s]+'
    if re.search(http_pattern, text):
        return True
    
    # Pattern 2: Telegram t.me links
    tme_pattern = r't\.me/[^\s]+'
    if re.search(tme_pattern, text):
        return True
    
    # Pattern 3: Telegram usernames (@username)
    username_pattern = r'@[a-zA-Z0-9_]{5,32}'
    if re.search(username_pattern, text):
        return True
    
    # Pattern 4: www links (without http/https)
    www_pattern = r'www\.[^\s]+'
    if re.search(www_pattern, text):
        return True
    
    # Pattern 5: Domain-like patterns (word.word)
    domain_pattern = r'[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}'
    if re.search(domain_pattern, text):
        return True
    
    return False

# ========== SYSTEM PROMPTS (from persona.json) ==========
PERSONA_PATH = Path("persona.json")
PERSONA_LOCK = threading.RLock()


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> bool:
    """Crash-safe JSON write shared by data.json, chats and persona.json."""
    with PERSONA_LOCK:
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            return True
        except Exception as e:
            print(f"❌ Error saving {path.name}: {e}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            return False

_TOKEN_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_template(template: Any, values: Dict[str, Any]) -> str:
    """Replace {token} safely. Unknown tokens stay untouched, no KeyError."""
    return _TOKEN_PATTERN.sub(lambda m: str(values.get(m.group(1), m.group(0))), str(template))


MINIMAL_PERSONA: Dict[str, Any] = {
    "name": "Ishani Sharma",
    "age": 23,
    "master_prompt": "You are Ishani Sharma, a 23-year-old Indian girl chatting in Hinglish.",
    "company": {},
}


def load_persona() -> Dict[str, Any]:
    """Load persona.json; a bad edit falls back to its saved fallback block."""
    try:
        with PERSONA_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ persona.json load error: {e}")
        return dict(MINIMAL_PERSONA)
    if not isinstance(data, dict):
        return dict(MINIMAL_PERSONA)
    if not isinstance(data.get("master_prompt"), str) or not data["master_prompt"].strip():
        fallback = data.get("fallback")
        if isinstance(fallback, dict) and isinstance(fallback.get("master_prompt"), str):
            return dict(fallback)
        return dict(MINIMAL_PERSONA)
    return data


def load_prewritten_messages(persona: Optional[Dict[str, Any]] = None) -> tuple:
    """Read welcome/left/first-DM lines from persona.json with safe fallbacks."""
    source = persona if isinstance(persona, dict) else load_persona()
    raw = source.get("prewritten_messages") if isinstance(source, dict) else None
    if not isinstance(raw, dict):
        raw = {}

    def _clean_list(key: str, fallback: str) -> List[str]:
        value = raw.get(key)
        if isinstance(value, list):
            cleaned = [m.strip() for m in value if isinstance(m, str) and m.strip()]
            if cleaned:
                return cleaned
        return [fallback]

    return (
        _clean_list("welcome", "Swagat hai {name}! Group me aapka swagat hai. 😊"),
        _clean_list("left", "Goodbye {name}. Kabhi bhi wapas aa sakte hain."),
        _clean_list("dm_welcome", "Arre {name}, group me aa gaye to yahan bhi hi bol deti hoon. Group me bheed rehti hai."),
    )


WELCOME_MESSAGES, LEFT_MESSAGES, DM_WELCOME_MESSAGES = load_prewritten_messages()


def company_brief(persona: Optional[Dict[str, Any]] = None, group_business: Optional[Dict[str, Any]] = None) -> str:
    """Build the company fact block from the persona.json company_brief template."""
    source = persona if isinstance(persona, dict) else load_persona()
    company = source.get("company") if isinstance(source, dict) else None
    if not isinstance(company, dict):
        company = {}
    if isinstance(group_business, dict):
        company = dict(company)
        for source_key, target_key in (("name", "name"), ("join_link", "join_link"),
                                       ("end_goal", "end_goal"), ("notes", "rule")):
            override = group_business.get(source_key)
            if isinstance(override, str) and override.strip():
                company[target_key] = override.strip()

    config = source.get("company_brief") if isinstance(source, dict) else None
    if not isinstance(config, dict):
        config = {}
    defaults = config.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    lines = config.get("lines")
    if not isinstance(lines, list) or not lines:
        lines = [
            "Company: {company_name}",
            "{role}",
            "END GOAL (this is the destination of every chat, without sounding like an ad):",
            "{end_goal}",
            "Join link: {join_link}",
            "Join then what:",
            "{join_steps}",
            "Facts:",
            "{facts}",
            "{rule}",
        ]
    prefix = config.get("bullet_prefix")
    if not isinstance(prefix, str):
        prefix = "- "

    facts = company.get("facts")
    if not isinstance(facts, list):
        facts = []
    steps = company.get("join_steps")
    if not isinstance(steps, list):
        steps = []
    values = {
        "company_name": company.get("name") or defaults.get("company_name") or "Chelsea Football",
        "role": company.get("role") or "",
        "end_goal": company.get("end_goal") or defaults.get("end_goal") or "Get them to join Chelsea Football, then start with ₹200 and follow predictions.",
        "join_link": company.get("join_link") or defaults.get("join_link") or "https://t.me/+Qv2p0w48dy81NDFl",
        "join_steps": "\n".join(f"{prefix}{item}" for item in steps),
        "facts": "\n".join(f"{prefix}{item}" for item in facts),
        "rule": company.get("rule") or "",
    }
    rendered = [_render_template(line, values) for line in lines]
    return "\n".join(part for part in rendered if part)


def persona_system_prompt() -> str:
    persona = load_persona()
    return (persona.get("master_prompt") or "").strip()


def load_keyword_responses(persona: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Read keyword FAQ from persona.json. Bad entries are skipped, never fatal."""
    source = persona if isinstance(persona, dict) else load_persona()
    raw = source.get("keyword_responses") if isinstance(source, dict) else None
    if not isinstance(raw, dict):
        print("⚠️ persona.json missing keyword_responses; FAQ keywords disabled", flush=True)
        return {}
    cleaned: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        keyword = key.strip().lower()
        reply = clean_reply_text(value)
        if keyword and reply:
            cleaned[keyword] = reply
    return cleaned


KEYWORD_RESPONSES: Dict[str, str] = load_keyword_responses()

FRIENDLY_SYSTEM_PROMPT = persona_system_prompt()
COMPANY_KNOWLEDGE = company_brief()


def chat_display_name(record: Dict[str, Any], first_name: str) -> str:
    mem = record.get("memory") or {}
    raw = (mem.get("preferred_name") or record.get("name") or first_name or "tum").strip()
    raw = re.sub(r"\s+(sir|ji)$", "", raw, flags=re.IGNORECASE).strip()
    return raw or "tum"


def _format_memory_line(template: Any, **values: str) -> str:
    """Render a persona.json memory line; a bad value never crashes the bot."""
    return _render_template(template, values)


def build_personal_system(user_id: int, first_name: str, history: List[Dict[str, str]],
                          compact: bool = False, group_business: Optional[Dict[str, Any]] = None,
                          include_company: bool = False) -> str:
    """Build the per-user prompt from persona.json plus that chat's saved memory."""
    persona = load_persona()
    record = dm.load_chat(user_id, first_name)
    mem = record.get("memory") or {}
    name = chat_display_name(record, first_name)

    prompts = persona.get("system_prompts")
    if not isinstance(prompts, dict):
        prompts = {}
    labels = prompts.get("memory_labels")
    if not isinstance(labels, dict):
        labels = {}
    defaults = prompts.get("memory_defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    about = mem.get("about") or defaults.get("about") or ""
    lead_state = get_lead_state(user_id, first_name)
    if lead_state.get("joined") or lead_state.get("deposit") or int(lead_state.get("stage") or 0) >= 2:
        # The default "not joined / no deposit" line would contradict the ladder.
        about = re.sub(
            r"(?:\s*,?\s*Group join nahi hui|\s*,?\s*deposit nahi hua|\s*,?\s*Stage: vibe\.)",
            "", about, flags=re.IGNORECASE,
        ).strip(" ,.")
    about = f"{about} | {lead_state_about(lead_state)}".strip(" |")
    values = {
        "name": name,
        "about": about,
        "topics": ", ".join(mem.get("topics") or []) or defaults.get("topics") or "fresh chat",
        "focus": mem.get("last_focus") or defaults.get("focus") or "-",
        "facts": ", ".join(item for item in (mem.get("facts") or []) if isinstance(item, str))
                 or defaults.get("facts") or "-",
    }
    memory_lines = [
        _format_memory_line(labels.get("talking_to", "Talking to: {name}"), **values),
        _format_memory_line(labels.get("about", "About them: {about}"), **values),
        _format_memory_line(labels.get("topics", "Things they talked about: {topics}"), **values),
        _format_memory_line(labels.get("focus", "Right now they are on: {focus}"), **values),
    ]
    if values["facts"] and values["facts"] != "-":
        memory_lines.append(_format_memory_line(
            labels.get("facts", "Things they told you about themselves: {facts}"), **values
        ))

    compact_raw = prompts.get("compact")
    full_raw = prompts.get("full_after_memory")
    compact_lines = [str(line) for line in compact_raw if str(line).strip()] if isinstance(compact_raw, list) else []
    full_lines = [str(line) for line in full_raw if str(line).strip()] if isinstance(full_raw, list) else []
    if not compact_lines:
        compact_lines = [
            "You are Ishani Sharma, 23, on Telegram. Reply in short, natural Hinglish. Send only the reply."
        ]

    if compact:
        learned = persona.get("learned_from_admin") or []
        if isinstance(learned, str):
            learned = [learned]
        learning_block = (
            "Latest admin instructions (follow these over earlier persona/company guidance):\n"
            + "\n".join(f"- {item}" for item in learned if isinstance(item, str) and item.strip())
            if learned else ""
        )
        controls = persona.get("admin_learning_controls") or {}
        link_rule = "Admin instruction: do not output URLs or links." if controls.get("block_all_links") else (
            "Admin instruction: do not repeat any specific URL the admin has blocked." if controls.get("blocked_links") else ""
        )
        # Local models have a smaller prompt budget. Keep the actionable persona,
        # the user's memory and the company facts together instead of truncating
        # the company details or the final response rules from the middle.
        parts = [
            *compact_lines,
            *memory_lines,
            company_brief(persona, group_business) if include_company else "",
            "Answer the exact latest message first. For 'who are you' or 'tell me about yourself', give a coherent, brief introduction as Ishani and explain your connection to the configured company using its persona details; never answer with vague filler.",
            "When asked what the company is, explain only the configured role and facts above. Do not infer services from a familiar company name or invent outcomes, earnings, or features.",
            "When speaking about yourself in Hindi or Hinglish, use feminine forms such as 'karti hoon' or 'bolti hoon', never masculine forms.",
            "Understand the user's need and respond with one useful, truthful next step. Mention Chelsea Football or invite them to join when relevant, naturally and without repeating a pitch. Never pressure someone to deposit, promise profit, or present predictions as guaranteed income.",
            "Use only company features, amounts, steps and links stated above. Match the latest message's language and script exactly: English to English, Roman Hindi to Roman Hindi, Devanagari to Devanagari, even if earlier turns used another language. Never expose internal reasoning; send only the final reply.",
            learning_block,
            link_rule,
        ]
    else:
        learned = persona.get("learned_from_admin") or []
        if isinstance(learned, str):
            learned = [learned]
        learning_block = (
            "Latest admin instructions (follow these over earlier persona/company guidance):\n"
            + "\n".join(f"- {item}" for item in learned if isinstance(item, str) and item.strip())
            if learned else ""
        )
        controls = persona.get("admin_learning_controls") or {}
        link_rule = "Admin instruction: do not output URLs or links." if controls.get("block_all_links") else (
            "Admin instruction: do not repeat any specific URL the admin has blocked." if controls.get("blocked_links") else ""
        )
        parts = [
            (persona.get("master_prompt") or FRIENDLY_SYSTEM_PROMPT).strip(),
            company_brief(persona, group_business) if include_company else "",
            *memory_lines,
            *full_lines,
            learning_block,
            link_rule,
        ]
    return "\n".join(part for part in parts if part)


def apply_admin_link_controls(reply: str) -> str:
    """Enforce explicit admin link blocks even if the model ignores its prompt."""
    controls = (load_persona().get("admin_learning_controls") or {})
    blocked = [str(url).strip() for url in controls.get("blocked_links", []) if str(url).strip()]
    block_all = bool(controls.get("block_all_links"))
    if not blocked and not block_all:
        return reply

    lines = (reply or "").splitlines()
    if block_all:
        lines = [line for line in lines if not re.search(r"\b(link|links|url|urls)\b", line, re.IGNORECASE)]
        lines = [_LEARN_URL.sub("", line).strip() for line in lines]
    else:
        for url in blocked:
            url_pattern = re.compile(re.escape(url.rstrip(".,!?;:)")), re.IGNORECASE)
            lines = [line for line in lines if not url_pattern.search(line)]
    return "\n".join(line for line in lines if line).strip()


# ================= ADMIN PANEL =================
_ADMIN_COMMANDS_TEXT = (
    "<b>📋 Sab Commands — Details</b>\n\n"
    "<b>👤 Sab users:</b>\n"
    "<code>/start</code> — Bot shuru karein / welcome message.\n"
    "<code>/help</code> — Command list aur examples.\n"
    "<code>/pdf</code>, <code>/document</code>, <code>/details</code> — Upload kiya document/photo maangein.\n"
    "<code>/search &lt;query&gt;</code> — Free web search (DuckDuckGo, bina API key). Titles, chhoti summaries aur clickable link. Limit: 8 searches / minute / user.\n"
    "<code>/accept &lt;token&gt;</code> — Group Owner invitation accept karein (sirf private chat).\n"
    "<code>/mygroups</code> — Sirf apne assigned groups dekhein.\n\n"
    "<b>🛠️ Normal language (sab users):</b>\n"
    "• 'latest news kya hai?' / 'search the web for X' → web search; URL bhejein to page read.\n"
    "• 'create an image of a sunrise' → image generate karke yahin bhejti hoon (image API configured ho to).\n"
    "• 'prepare a report from file' / 'read notes.txt' → file analysis; 'write a file' → safe file creation.\n"
    "• 'calculate 125*8+49' → chhota sandboxed calculation (import/file/network/shell nahi).\n"
    "• 'remind me in 30 minutes' / 'schedule for tomorrow 9:30' → reminder.\n"
    "• 'yaad rakho...' / 'what do you remember about me?' → private memory.\n"
    "• 'check admin status of my groups' → real Telegram group stats.\n"
    "• 'generate a python script for CSV' → review ke liye file banegi, execute nahi hogi.\n\n"
    "Tools apne aap choose hoti hain — koi alag mode nahi. Broadcast, delete aur sensitive group changes ke liye approval mangti hoon.\n\n"
    "<b>🛡️ Master Admin:</b>\n"
    "<code>/panel</code> — Ye admin panel.\n"
    "<code>/learn &lt;instruction&gt;</code> — Seekhao / badlo / bhoolo (pehle confirmation mangta hai).\n"
    "<code>/learn what have you learned?</code> — Saved lessons aur link rules dekhein.\n"
    "<code>/assign &lt;user_id|@username&gt; [group_id]</code> — Group Owner invite; token private chat me bheja jata hai.\n"
    "<code>/owners</code> — Owners aur pending invitations.\n"
    "<code>/verifygroup &lt;group_id&gt;</code> — Pending group verify karein.\n"
    "<code>/webtoken</code> — Dashboard token (30 din, sirf private chat).\n"
    "<code>/assigngroup &lt;operator_id&gt; &lt;group_id&gt;</code> / <code>/unassigngroup &lt;group_id&gt;</code> — Direct assignment (legacy).\n"
    "<code>/stop</code> — Bot band karein.\n\n"
    "<b>👥 Group Owner / Operator:</b>\n"
    "<code>/registergroup</code> — Current group register karein (group me chalayein).\n"
    "<code>/grouppanel</code> — Sirf apne groups.\n"
    "<code>/groupset &lt;key&gt; &lt;value&gt;</code> — Sirf apne group ki setting badlein.\n\n"
    "<b>🌐 Dashboard (browser):</b>\n"
    "<code>/</code> AI settings · <code>/groups</code> group management · <code>/health</code> uptime.\n"
    "Token <code>/webtoken</code> se ya env <code>WEB_TOKEN</code> se.\n\n"
    "<i>Search completely free hai. Search unavailable hone par bot honestly batata hai — kuch invent nahi karta.</i>"
)


def _panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 Upload Document", callback_data="admin_upload"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton("🔇 Mute Bot", callback_data="admin_mute"),
            InlineKeyboardButton("🔊 Unmute Bot", callback_data="admin_unmute"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("🔍 Web Search", callback_data="admin_search"),
        ],
        [
            InlineKeyboardButton("📋 All Commands", callback_data="admin_commands"),
            InlineKeyboardButton("👥 Groups & Owners", callback_data="admin_groups"),
        ],
        [
            InlineKeyboardButton("🎓 Learn / Persona", callback_data="admin_learn"),
            InlineKeyboardButton("🔐 Dashboard Token", callback_data="admin_token"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="admin_help")],
    ])


def _panel_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Panel", callback_data="admin_back")]])


async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with inline buttons"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    await update.message.reply_text(
        "🎛️ <b>Admin Panel</b>\n\nChoose an action — har button ke saath details milti hain. "
        "Sab commands ki list ke liye <b>📋 All Commands</b> dabayein.",
        reply_markup=_panel_keyboard(),
        parse_mode="HTML",
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button clicks"""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Admin only!")
        return

    action = query.data

    if action == "admin_back":
        await query.edit_message_text(
            "🎛️ <b>Admin Panel</b>\n\nChoose an action:",
            reply_markup=_panel_keyboard(), parse_mode="HTML",
        )
    elif action == "admin_upload":
        context.user_data['awaiting_search'] = False
        await query.edit_message_text(
            "📁 Send a PDF, document, or photo. Add a caption describing what it contains so I can send the right file when users ask.\n\n<code>cancel</code> likhkar wapas aa sakte hain.",
            parse_mode="HTML",
        )
        context.user_data['awaiting_document'] = True
    elif action == "admin_broadcast":
        context.user_data['awaiting_search'] = False
        await query.edit_message_text("📝 Send the message to broadcast to all users.")
        context.user_data['awaiting_broadcast'] = True
    elif action == "admin_search":
        context.user_data['awaiting_document'] = False
        context.user_data['awaiting_broadcast'] = False
        await query.edit_message_text(
            "🔍 <b>Free Web Search</b>\n\nSearch query likhein (ya URL paste karein). Main DuckDuckGo se "
            "titles, chhoti summaries aur clickable source links bhejunga. Agar 'summarize' bolein to "
            "top page read karke AI se summary banaunga.\n\nLimit: 8 searches / minute. "
            "Band karne ke liye <code>cancel</code> likhein.",
            parse_mode="HTML",
        )
        context.user_data['awaiting_search'] = True
    elif action == "admin_commands":
        await query.edit_message_text(_ADMIN_COMMANDS_TEXT, parse_mode="HTML", reply_markup=_panel_back())
    elif action == "admin_groups":
        await query.edit_message_text(
            "<b>👥 Groups &amp; Owners</b>\n\n"
            "<code>/assign &lt;user_id|@username&gt; [group_id]</code> — Master Owner secure invitation banata hai (token 7 din valid, hash ke saath store).\n"
            "<code>/accept &lt;token&gt;</code> — Invitation accept karke Group Owner bante hain.\n"
            "<code>/registergroup</code> — Group me chalayein; Telegram admin status verify hota hai.\n"
            "<code>/verifygroup &lt;group_id&gt;</code> — Master pending registration verify karta hai.\n"
            "<code>/owners</code> — Owners + pending invitations.\n"
            "<code>/mygroups</code> — Owner ko sirf apne groups dikhte hain.\n"
            "<code>/grouppanel</code> / <code>/groupset</code> — Owner sirf apne group ki settings badal sakta hai.\n"
            "<code>/assigngroup</code> / <code>/unassigngroup</code> — Direct assignment (legacy).\n\n"
            "Dashboard par <code>/groups</code> page role-scoped hota hai — owner doosre group ke details nahi dekh sakta.",
            parse_mode="HTML", reply_markup=_panel_back(),
        )
    elif action == "admin_learn":
        await query.edit_message_text(
            "<b>🎓 Learn / Persona</b>\n\n"
            "<code>/learn</code> — Instruction poochega, phir confirm karega. Confirm hone tak kuch save nahi hota.\n"
            "<code>/learn Always reply in Hinglish.</code> — Naya shared lesson.\n"
            "<code>/learn what have you learned?</code> — Saved lessons + link rules.\n"
            "<code>/learn forget last lesson</code> — Aakhri lesson hatao.\n"
            "<code>/learn forget all</code> — Saare lessons + link rules hatao.\n"
            "<code>/learn replace X with Y</code> — Existing lesson badlo.\n"
            "<code>/learn no links please</code> / <code>/learn allow links</code> — Link restrictions.\n\n"
            "Base <code>master_prompt</code> hamesha preserved rehta hai. Sirf master admin /learn use kar sakta hai.",
            parse_mode="HTML", reply_markup=_panel_back(),
        )
    elif action == "admin_token":
        await query.edit_message_text(
            "<b>🔐 Dashboard Token</b>\n\n"
            "<code>/webtoken</code> — Private chat me 30-din ka scoped token deta hai. Master sab groups dekhta hai; "
            "Group Owner sirf apne.\n"
            "Token browser me <code>/groups</code> page par 'Token' field me paste karein.\n"
            "Optional: env <code>WEB_TOKEN</code> se master token set kar sakte hain.\n"
            "Tokens hash karke store hote hain; kisi ke saath share na karein.\n\n"
            "Dashboard routes: <code>/</code> AI settings · <code>/groups</code> · <code>/health</code>.",
            parse_mode="HTML", reply_markup=_panel_back(),
        )
    elif action == "admin_help":
        await query.edit_message_text(_ADMIN_COMMANDS_TEXT, parse_mode="HTML", reply_markup=_panel_back())
    elif action == "admin_mute":
        context.user_data['awaiting_search'] = False
        dm.set_bot_muted(True)
        await query.edit_message_text("🔇 Bot muted successfully.", reply_markup=_panel_back())
    elif action == "admin_unmute":
        context.user_data['awaiting_search'] = False
        dm.set_bot_muted(False)
        await query.edit_message_text("🔊 Bot unmuted successfully.", reply_markup=_panel_back())
    elif action == "admin_stats":
        stats = dm.get_stats()
        users_count = len(dm.data.get('users') or {})
        search_count = len(_search_calls)
        stats_text = (
            f"📊 <b>Bot Statistics</b>\n\n"
            f"Total Messages: {stats.get('total_messages', 0)}\n"
            f"Total Users: {users_count}\n"
            f"Total Broadcasts: {stats.get('total_broadcasts', 0)}\n"
            f"Search users (last hour): {search_count}\n"
            f"Search limit: {SEARCH_RATE_LIMIT} per {SEARCH_RATE_WINDOW_SECONDS}s per user"
        )
        await query.edit_message_text(stats_text, parse_mode="HTML", reply_markup=_panel_back())


async def handle_panel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel se triggered web search query handle karein."""
    message = update.effective_message
    if not message or not message.text or update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get('awaiting_search'):
        return
    query = message.text.strip()
    if query.lower() in ("cancel", "/cancel"):
        context.user_data['awaiting_search'] = False
        await message.reply_text("🔍 Search cancel ho gaya.")
        raise ApplicationHandlerStop
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    url_match = re.search(r"https?://[^\s<>]+", query)
    page_url = url_match.group(0).rstrip(".,!?;:)\"]'") if url_match else ""
    page_question = re.sub(r"https?://[^\s<>]+", " ", query).strip() if page_url else query
    reply = await _run_web_search(page_question, update.effective_user.id,
                                  summarize=bool(page_url) or _wants_summary(query), url=page_url)
    context.user_data['awaiting_search'] = False
    await message.reply_text(reply[:3500], parse_mode="HTML", disable_web_page_preview=True)
    raise ApplicationHandlerStop

# ========== DOCUMENT UPLOAD HANDLER ==========
async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save an admin's PDF, other document, or photo for matching user requests."""
    message = update.effective_message
    if update.effective_user.id != ADMIN_ID or not message:
        return
    if not context.user_data.get('awaiting_document'):
        return
    if message.document:
        file_id = message.document.file_id
        name = message.document.file_name or "document"
        kind = "document"
    elif message.photo:
        file_id = message.photo[-1].file_id
        name = "photo"
        kind = "photo"
    else:
        return
    dm.save_media_asset(file_id, kind, name, message.caption or "")
    context.user_data['awaiting_document'] = False
    await message.reply_text(f"✅ Saved {name}. Add a descriptive caption next time to help me match it to user requests.")

# ========== BROADCAST HANDLER ==========
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast from admin"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.user_data.get('awaiting_broadcast'):
        return
    
    broadcast_message = update.message.text
    sent = 0
    failed = 0
    for user_id in list(dm.data.get("users", {})):
        try:
            await context.bot.send_message(chat_id=int(user_id), text=broadcast_message)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"⚠️ Broadcast failed for {user_id}: {e}", flush=True)
    dm.data.setdefault("stats", {}).setdefault("total_broadcasts", 0)
    dm.data["stats"]["total_broadcasts"] += 1
    dm.save()
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users. Failed: {failed}.")
    context.user_data['awaiting_broadcast'] = False
    raise ApplicationHandlerStop


# ========== GROUP OWNERSHIP (ADMIN -> OPERATOR) ==========
def _group_id_from_command(update, args: List[str], needs_explicit: bool) -> Optional[int]:
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        return chat.id
    if needs_explicit and len(args) >= 3:
        try:
            return int(args[-1])
        except (TypeError, ValueError):
            return None
    return None


async def assign_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: give one operator control of one group."""
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Admin only!")
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /assigngroup &lt;operator_user_id&gt; [group_id] (group_id needed in private chat).", parse_mode="HTML")
        return
    try:
        operator_id = int(args[0])
    except (TypeError, ValueError):
        await update.effective_message.reply_text("Operator ID must be a numeric Telegram user ID.")
        return
    group_id = _group_id_from_command(update, args[1:], needs_explicit=False)
    if group_id is None and len(args) >= 2:
        try:
            group_id = int(args[1])
        except (TypeError, ValueError):
            group_id = None
    if group_id is None:
        await update.effective_message.reply_text("Group ID nahi mila. Group mein chalayein ya /assigngroup &lt;operator_id&gt; &lt;group_id&gt; likhein.", parse_mode="HTML")
        return
    try:
        dm.assign_group(ADMIN_ID, operator_id, group_id)
    except ValueError:
        await update.effective_message.reply_text("Invalid group ID.")
        return
    await update.effective_message.reply_text(
        f"✅ Group {group_id} operator {operator_id} ko assign ho gaya. "
        "Operator sirf isi group ke details/settings badal sakta hai."
    )


async def unassign_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Admin only!")
        return
    args = context.args or []
    group_id = _group_id_from_command(update, args, needs_explicit=False)
    if group_id is None and args:
        try:
            group_id = int(args[0])
        except (TypeError, ValueError):
            group_id = None
    if group_id is None:
        await update.effective_message.reply_text("Usage: /unassigngroup [group_id]")
        return
    ok = dm.unassign_group(ADMIN_ID, group_id)
    await update.effective_message.reply_text(
        f"✅ Group {group_id} ki assignment hata di gayi." if ok else "Ye group assign hi nahi tha."
    )


async def group_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Operator sees ONLY their own groups. No global config, credentials, broadcasts or persona."""
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        groups = dm.get_groups()
    else:
        ids = dm.operator_group_ids(user_id)
        if not ids:
            await update.effective_message.reply_text("❌ Aap kisi group ke assigned operator nahi hain.")
            return
        groups = {str(group_id): dm.get_group(group_id) for group_id in ids}
    if not groups:
        await update.effective_message.reply_text("Abhi koi group assign nahi hai.")
        return
    lines = ["<b>📁 Assigned Groups</b>"]
    for key, record in groups.items():
        if not isinstance(record, dict):
            continue
        business = record.get("business") if isinstance(record.get("business"), dict) else {}
        settings = record.get("settings") if isinstance(record.get("settings"), dict) else {}
        lines.append(
            f"\n<b>Group {key}</b>\n"
            f"Operator: {record.get('operator_id', '-') }\n"
            f"Name: {business.get('name') or '-'}\n"
            f"Link: {business.get('join_link') or '-'}\n"
            f"Welcome: {business.get('welcome_message') or '-'}\n"
            f"Settings: links_allowed={settings.get('links_allowed', True)}, bot_muted={settings.get('bot_muted', False)}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def group_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Operator edits only their assigned group's business details/settings."""
    user_id = update.effective_user.id
    args = context.args or []
    in_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    if in_group:
        if len(args) < 2:
            await update.effective_message.reply_text("Usage: /groupset &lt;key&gt; &lt;value&gt;", parse_mode="HTML")
            return
        key, value, group_id = args[0], " ".join(args[1:]), update.effective_chat.id
    else:
        if len(args) < 3:
            await update.effective_message.reply_text("Usage: /groupset &lt;key&gt; &lt;value&gt; &lt;group_id&gt;", parse_mode="HTML")
            return
        key, value = args[0], args[1]
        try:
            group_id = int(args[2])
        except (TypeError, ValueError):
            await update.effective_message.reply_text("Group ID must be numeric.")
            return
    if not dm.can_manage_group(user_id, group_id, ADMIN_ID):
        await update.effective_message.reply_text("❌ Aap is group ke details change nahi kar sakte.")
        return
    if dm.set_group_details(user_id, ADMIN_ID, group_id, key, value):
        await update.effective_message.reply_text(f"✅ Group {group_id} me '{key}' update ho gaya.")
    else:
        await update.effective_message.reply_text(
            "Allowed keys: name, join_link, welcome_message, notes, bot_muted, links_allowed."
        )


# ========== OWNER INVITATIONS / REGISTRATION ==========
async def assign_owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master Owner invites a Group Owner. Token is delivered privately, never in the group."""
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Master Owner only!")
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text(
            "Usage: /assign &lt;user_id or @username&gt; [group_id] (group_id needed in private chat).",
            parse_mode="HTML")
        return
    target = args[0].strip()
    invitee_id = int(target) if target.isdigit() else None
    invitee_username = target if target.startswith("@") else ""
    if invitee_id is None and not invitee_username:
        await update.effective_message.reply_text("Use a numeric Telegram ID or @username.")
        return
    group_id = _group_id_from_command(update, args[1:], needs_explicit=False)
    if group_id is None and len(args) >= 2:
        try:
            group_id = int(args[1])
        except (TypeError, ValueError):
            group_id = None
    token = dm.create_invitation(ADMIN_ID, invitee_id, invitee_username, group_id)
    text = (
        "🔐 <b>Group Owner invitation</b>\n"
        f"Token: <code>{html.escape(token)}</code>\n"
        f"Group: {group_id or 'not fixed yet (any group they register)'}\n\n"
        "Share this privately. They reply <code>/accept TOKEN</code> in private chat. "
        "Invitation expires in 7 days."
    )
    in_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    if in_group:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
            await update.effective_message.reply_text("✅ Invitation token bhej diya — aapke private chat me check karein.")
            return
        except Exception as e:
            print(f"⚠️ Could not DM invitation to admin: {e}", flush=True)
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def accept_invitation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /accept &lt;invitation_token&gt;", parse_mode="HTML")
        return
    user = update.effective_user
    result = dm.accept_invitation(args[0], user.id, user.username or "")
    if not result["ok"]:
        await update.effective_message.reply_text(result["message"])
        return
    group_text = (f" Group {result['group_id']} aapko assign ho gaya." if result["group_id"]
                  else " Ab /registergroup chalayein (group me) ya master admin group assign karega.")
    await update.effective_message.reply_text(
        "✅ Aap Group Owner ban gaye. Sirf apne group(s) ke details/settings badal sakte hain." + group_text
    )


async def register_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group Owner registers the current group; Telegram admin status is checked."""
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("Ye command group me chalayein.")
        return
    user_id = update.effective_user.id
    if not dm.owner_role(user_id):
        await update.effective_message.reply_text("❌ Pehle master admin se /assign token lekar Group Owner banen.")
        return
    verified = await _is_group_admin(chat, user_id)
    name = " ".join(context.args or [])
    record = dm.register_group(user_id, chat.id, name, verified_by=str(user_id) if verified else "")
    if not record:
        await update.effective_message.reply_text("❌ Group register nahi ho paya.")
        return
    status = "verified" if verified else "pending (master admin verify karega)"
    await update.effective_message.reply_text(
        f"✅ Group {chat.id} register ho gaya — status: {status}. "
        "Aap sirf isi group ke settings badal sakte hain."
    )


async def verify_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Master Owner only!")
        return
    args = context.args or []
    try:
        group_id = int(args[0])
    except (TypeError, ValueError, IndexError):
        await update.effective_message.reply_text("Usage: /verifygroup &lt;group_id&gt;", parse_mode="HTML")
        return
    ok = dm.verify_group(ADMIN_ID, group_id)
    await update.effective_message.reply_text(
        f"✅ Group {group_id} verified." if ok else "❌ Group nahi mila."
    )


async def my_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ids = dm.visible_group_ids(user_id)
    if not ids:
        await update.effective_message.reply_text("Aapke paas abhi koi assigned group nahi hai.")
        return
    lines = [f"<b>📁 Aapke groups ({len(ids)})</b>"]
    for group_id in ids:
        record = dm.get_group(group_id) or {}
        business = record.get("business") if isinstance(record.get("business"), dict) else {}
        lines.append(
            f"\n<b>{html.escape(str(business.get('name') or 'Unnamed'))}</b> — <code>{group_id}</code>\n"
            f"Status: {record.get('registration_status', 'assigned')}\n"
            f"Links allowed: {(record.get('settings') or {}).get('links_allowed', True)}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def owners_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Master Owner only!")
        return
    owners = dm.data.get("owners") or {}
    invitations = dm.data.get("invitations") or {}
    lines = [f"<b>👥 Owners ({len(owners) + 1})</b>", "Master Owner: " + str(ADMIN_ID)]
    for uid, record in owners.items():
        if isinstance(record, dict):
            line = f"\nGroup Owner: {uid} — {record.get('status', '?')}"
            if record.get("invited_by"):
                line += f" (invited by {record['invited_by']})"
            lines.append(line)
    pending = [r for r in invitations.values() if isinstance(r, dict) and not r.get("accepted")]
    lines.append(f"\nPending invitations: {len(pending)}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def web_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        await update.effective_message.reply_text("🔐 Token private chat me bhejne ke liye mujhe DM karein: /webtoken")
        return
    token = dm.issue_web_token(update.effective_user.id)
    if not token:
        await update.effective_message.reply_text("❌ Sirf Master Owner ya accepted Group Owner dashboard token pa sakte hain.")
        return
    await update.effective_message.reply_text(
        "🔐 <b>Dashboard token</b> (30 din valid):\n"
        f"<code>{html.escape(token)}</code>\n\n"
        "Group Management page par 'Token' field me paste karein. Kisi ke saath share na karein.",
        parse_mode="HTML",
    )

# ========== FREE WEB SEARCH COMMAND ==========
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicit /search entry point. Uses the same free, rate-limited search core."""
    user_id = update.effective_user.id
    query = " ".join(context.args or []).strip()
    if not query:
        await update.effective_message.reply_text(
            "🔎 Kya search karein? Example:\n"
            "<code>/search latest IPL news</code>\n"
            "<code>/search current price of gold</code>\n"
            "Ya normal bhasha mein bhi poochh sakte hain: 'latest news kya hai?'",
            parse_mode="HTML",
        )
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    url_match = re.search(r"https?://[^\s<>]+", query)
    page_url = url_match.group(0).rstrip(".,!?;:)\"]'") if url_match else ""
    page_question = re.sub(r"https?://[^\s<>]+", " ", query).strip() if page_url else query
    reply = await _run_web_search(page_question, user_id,
                                  summarize=bool(page_url) or _wants_summary(query), url=page_url)
    chat = update.effective_chat
    scope = f"group:{chat.id}" if chat and chat.type in ("group", "supergroup") else "private"
    dm.append_chat(user_id, update.effective_user.first_name or "User", "user", f"/search {query}", scope=scope)
    dm.append_chat(user_id, update.effective_user.first_name or "User", "bot", reply[:1500], scope=scope)
    await update.effective_message.reply_text(reply[:3500], parse_mode="HTML", disable_web_page_preview=True)


# ================= HELP COMMAND =================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help with all available commands"""
    help_text = (
        "<b>📖 Available Commands</b>\n\n"
        "<b>User Commands:</b>\n"
        "• /start - Start the bot\n"
        "• /help - Show this help message\n"
        "• /pdf - Get the uploaded document\n"
        "• /document - Get the uploaded document\n"
        "• /details - Get the uploaded document\n"
        "• /search <code>query</code> - Free web search (DuckDuckGo, no API key)\n"
        "• Just ask naturally: 'latest news?', 'current price of gold', 'search the web for X', or paste a URL to summarize it.\n\n"
        "<b>Admin Commands:</b>\n"
        "• /panel - Open admin panel\n"
        "• /learn <code>instruction</code> - Add / view / update / forget lessons (admin only, asks confirmation)\n"
        "• /learn what have you learned? - View saved lessons and link rules\n"
        "• /learn forget last lesson / forget all - Remove last or all lessons\n"
        "• /assigngroup <code>operator_id</code> <code>group_id</code> - Assign a group\n"
        "• /unassigngroup <code>group_id</code> - Remove assignment\n"
        "• /assign <code>user_id</code> [group_id] - Invite a Group Owner (secure token)\n"
        "• /accept <code>token</code> - Accept a Group Owner invitation\n"
        "• /registergroup - Register the current group (owners only)\n"
        "• /mygroups - See only your own groups\n"
        "• /owners - List owners (master only)\n"
        "• /verifygroup <code>group_id</code> - Verify a group (master only)\n"
        "• /webtoken - Get your scoped dashboard token (private chat)\n"
        "• Just ask in normal language: search the web, check group admin status, generate a script, or prepare a report. Broadcasts and destructive actions need approval.\n"
        "• /stop - Stop the bot\n\n"
        "<b>Assigned Operator Commands:</b>\n"
        "• /grouppanel - See only your assigned group(s)\n"
        "• /groupset <code>key</code> <code>value</code> - Edit only that group's details\n\n"
        "<i>Just ask questions or send messages for instant replies!</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode="HTML")


_LEARN_URL = re.compile(
    r"(?:https?://|www\.)[^\s<>]+|(?:t\.me|telegram\.me)/[^\s<>]+|"
    r"\b[a-z0-9][a-z0-9.-]*\.(?:com|net|org|online|in|io|co|app)(?:/[^\s<>]*)?",
    re.IGNORECASE,
)
_LEARN_DELETE = re.compile(r"^\s*(?:forget|delete|remove|unlearn|erase)\b\s*:?[ \t]*(.*)$", re.IGNORECASE | re.DOTALL)


def _save_persona_learning(instruction: str) -> Dict[str, Any]:
    """Add an admin rule, or delete matching saved rules with forget/remove/delete."""
    persona = load_persona()
    learned = persona.setdefault("learned_from_admin", [])
    if isinstance(learned, str):
        learned = persona["learned_from_admin"] = [learned]
    elif not isinstance(learned, list):
        learned = persona["learned_from_admin"] = []
    controls = persona.setdefault("admin_learning_controls", {})
    if not isinstance(controls, dict):
        controls = persona["admin_learning_controls"] = {}
    blocked_links = controls.setdefault("blocked_links", [])
    if not isinstance(blocked_links, list):
        blocked_links = controls["blocked_links"] = []

    # Never allow a lesson operation to erase Ishani's base persona.
    if not str(persona.get("master_prompt") or "").strip():
        raise RuntimeError("persona.json master_prompt is missing - refusing to change lessons")

    text = (instruction or "").strip()
    allow_links = bool(re.search(r"\b(allow|enable|resume)\b.{0,30}\b(links?|urls?)\b", text, re.IGNORECASE))
    if allow_links:
        controls["block_all_links"] = False
        controls["blocked_links"] = []
        learned[:] = [item for item in learned if not (
            isinstance(item, str)
            and re.search(r"\b(links?|urls?)\b", item, re.IGNORECASE)
            and re.search(r"\b(no|not|never|don't|dont|stop|mat|nahi)\b", item, re.IGNORECASE)
        )]
        _atomic_write_json(PERSONA_PATH, persona)
        return {"action": "allowed", "count": 1}

    delete_match = _LEARN_DELETE.match(text)
    if delete_match:
        target = delete_match.group(1).strip().strip("\"'“”‘’")
        target = re.sub(r"^(?:(?:the|this|that|last)\s+)?(?:saved\s+)?(?:lesson|instruction|rule|content)(?:\s+(?:about|for|that|this))?\s*", "", target, flags=re.IGNORECASE)
        target = target.strip()
        generic_targets = {"", "that", "this", "it", "that one", "this one", "that content", "this content", "last", "last one", "last lesson", "last instruction", "last content", "the link", "links", "url", "the url"}
        if target.lower() in {"all", "everything", "all lessons", "all instructions", "all content", "all learning"}:
            removed = list(learned)
            learned.clear()
            controls["block_all_links"] = False
            controls["blocked_links"] = []
        elif target.lower() in generic_targets:
            removed = [learned.pop()] if learned else []
        else:
            folded_target = target.casefold()
            removed = [item for item in learned if isinstance(item, str) and folded_target in item.casefold()]
            learned[:] = [item for item in learned if item not in removed]
            if not removed:
                terms = [word for word in re.findall(r"[\w@./:-]+", folded_target) if len(word) > 2]
                if terms:
                    matches = [item for item in learned if isinstance(item, str) and all(term in item.casefold() for term in terms)]
                    if matches:
                        removed = matches
                        learned[:] = [item for item in learned if item not in removed]
        removed_urls = {url.rstrip(".,!?;:)") for item in removed if isinstance(item, str) for url in _LEARN_URL.findall(item)}
        controls["blocked_links"] = [url for url in blocked_links if url not in removed_urls and target.casefold() not in str(url).casefold()]
        removed_link_rule = any(
            isinstance(item, str)
            and re.search(r"\b(links?|urls?)\b", item, re.IGNORECASE)
            and re.search(r"\b(no|not|never|don't|dont|stop|mat|nahi|na)\b", item, re.IGNORECASE)
            for item in removed
        )
        remaining_link_rules = [
            item for item in learned if isinstance(item, str)
            and re.search(r"\b(links?|urls?)\b", item, re.IGNORECASE)
            and re.search(r"\b(no|not|never|don't|dont|stop|mat|nahi|na)\b", item, re.IGNORECASE)
        ]
        if removed_link_rule and not remaining_link_rules:
            controls["block_all_links"] = False
            controls["blocked_links"] = []
        if re.search(r"\b(links?|urls?)\b", target, re.IGNORECASE) and not _LEARN_URL.search(target):
            controls["block_all_links"] = False
            controls["blocked_links"] = []
        _atomic_write_json(PERSONA_PATH, persona)
        return {"action": "deleted" if removed else "not_found", "count": len(removed)}

    if text and text not in learned:
        learned.append(text)
    is_link_restriction = bool(
        re.search(r"\b(links?|urls?)\b", text, re.IGNORECASE)
        and re.search(r"\b(no|not|never|don't|dont|stop|mat|nahi|na)\b", text, re.IGNORECASE)
    )
    if is_link_restriction:
        urls = [url.rstrip(".,!?;:)") for url in _LEARN_URL.findall(text)]
        if urls:
            controls["blocked_links"] = list(dict.fromkeys([*blocked_links, *urls]))
        else:
            controls["block_all_links"] = True
    _atomic_write_json(PERSONA_PATH, persona)
    return {"action": "saved", "count": 1}


_LEARN_CANCEL = re.compile(r"^\s*(?:cancel|abort|drop it|never mind|chhod do|chhodo|band karo)\s*[.!]?$", re.IGNORECASE)
_LEARN_CONFIRM = re.compile(r"^\s*(?:yes|confirm|ok|okay|done|correct|sahi|save it|haan|han|ji haan|karo)\s*[.!]?$", re.IGNORECASE)
_LEARN_REMOVE = re.compile(r"^\s*(?:forget|delete|remove|unlearn|erase|hatao|mitao)\b\s*:?[ \t]*(.*)$", re.IGNORECASE | re.DOTALL)
_LEARN_ALLOW_LINKS = re.compile(r"\b(?:allow|enable|resume|unblock)\b.{0,30}\b(?:links?|urls?)\b", re.IGNORECASE)
_LEARN_BLOCK_LINKS = re.compile(
    r"\b(?:block|stop|ban|avoid|no|never|don'?t|dont|mat|nahi)\b.{0,30}\b(?:links?|urls?)\b|"
    r"\b(?:links?|urls?)\b.{0,24}\b(?:blocked|banned|not allowed|nahi|mat)\b",
    re.IGNORECASE,
)
_LEARN_VIEW = re.compile(
    r"^\s*(?:list|view|show|saved|lessons?|instructions?)\s*[.!]?$|"
    r"\b(?:what\s+have\s+you\s+(?:learned|learnt)|what\s+did\s+you\s+learn|"
    r"what\s+do\s+you\s+know|what\s+have\s+i\s+taught\s+you|"
    r"show\s+(?:me\s+)?(?:all\s+)?(?:saved\s+)?(?:lessons?|instructions?|rules?|learning)|"
    r"list\s+(?:all\s+)?(?:saved\s+)?(?:lessons?|instructions?|rules?)|"
    r"view\s+(?:saved\s+)?(?:lessons?|instructions?)|"
    r"saved\s+(?:lessons?|instructions?)|learned\s+(?:so\s+far|lessons?)|"
    r"kya\s+(?:seekha|sikhaya|sikha)|kya\s+yaad\s+hai|seekha\s+hua|"
    r"kitne\s+lessons?|kaunsi\s+(?:baatein|instructions?)\s+yaad)\b",
    re.IGNORECASE,
)
_LEARN_CHANGE = re.compile(r"\b(?:update|change|replace|instead of|rather than|badal do|badlo|sudharo|theek karo)\b", re.IGNORECASE)
_LEARN_REPLACE = re.compile(r"(?:instead of|replace|change|badal kar)\s+(.+?)\s+(?:to|with|se|into)\s+(.+)", re.IGNORECASE | re.DOTALL)
_LEARN_ALL = re.compile(r"^\s*(?:all|everything|all lessons?|all instructions?|all content|all learning|sab|sab kuch)\s*[.!]?$", re.IGNORECASE)
_LEARN_LAST = re.compile(
    r"\b(?:last|latest|most\s+recent|aakhiri|akhri)\s+(?:lesson|instruction|rule|one|saved|content)\b|"
    r"^\s*(?:last|last one|last lesson|last instruction)\s*[.!]?$",
    re.IGNORECASE,
)
_LEARN_UPDATE_PREFIX = re.compile(
    r"^\s*(?:update|change|replace|edit|modify|badal do|badlo|sudharo|theek karo)\s*[:,-]?\s*",
    re.IGNORECASE,
)


def _learning_view() -> str:
    """Read-only view of saved lessons and link restrictions. Never shows secrets or private chats."""
    persona = load_persona()
    learned = persona.get("learned_from_admin") or []
    if not isinstance(learned, list):
        learned = [str(learned)]
    controls = persona.get("admin_learning_controls") or {}
    if not isinstance(controls, dict):
        controls = {}
    lines = ["<b>📚 Saved lessons</b>"]
    if learned:
        for index, item in enumerate(learned, 1):
            lines.append(f"{index}. {html.escape(str(item)[:300])}")
    else:
        lines.append("Abhi koi saved lesson nahi hai.")
    blocked = controls.get("blocked_links") or []
    lines.append("\n<b>🔗 Link restrictions</b>")
    lines.append(f"Block all links: {'yes' if controls.get('block_all_links') else 'no'}")
    if blocked:
        lines.append("Blocked links: " + html.escape(", ".join(str(url) for url in blocked[:10])[:400]))
    else:
        lines.append("Specific blocked links: none")
    lines.append("\nBase persona hamesha safe rehti hai; /learn sirf saved lessons badalta hai.")
    return "\n".join(lines)


def parse_learning_intent(text: str) -> Dict[str, Any]:
    """Infer one shared-instruction action from natural language. Never writes anything."""
    raw = re.sub(r"^\s*/learn\b\s*", "", (text or "").strip(), flags=re.IGNORECASE).strip()
    if not raw:
        return {"action": "empty", "steps": [], "summary": ""}
    if _LEARN_ALLOW_LINKS.search(raw) and not _LEARN_REMOVE.match(raw):
        return {"action": "allow_links", "steps": [raw], "summary": "Clear saved link restrictions."}
    if _LEARN_VIEW.search(raw) and not _LEARN_REMOVE.match(raw):
        return {"action": "view", "steps": [], "summary": "Show saved lessons and link restrictions."}
    remove = _LEARN_REMOVE.match(raw)
    if remove:
        target = remove.group(1).strip().strip("\"'“”‘’")
        if _LEARN_ALL.match(target):
            return {"action": "remove_all", "steps": ["forget all"],
                    "summary": "Remove ALL saved lessons and link restrictions (base persona kept)."}
        if _LEARN_LAST.search(target) or not target:
            return {"action": "remove_last", "steps": ["forget last lesson"],
                    "summary": "Remove the most recent saved lesson."}
        return {"action": "remove", "steps": [raw],
                "summary": f"Remove saved instruction: {target[:140]}"}
    if _LEARN_CHANGE.search(raw):
        replace = _LEARN_REPLACE.search(raw)
        if replace:
            old, new = replace.group(1).strip(), replace.group(2).strip()
            if old and new:
                return {
                    "action": "update",
                    "steps": [f"forget {old}", new],
                    "summary": f"Replace “{old[:90]}” with “{new[:90]}”.",
                }
        new_text = _LEARN_UPDATE_PREFIX.sub("", raw).strip(" \t:;,-")
        if new_text:
            return {
                "action": "update_last",
                "steps": ["forget last lesson", new_text],
                "summary": f"Replace the most recent saved lesson with: {new_text[:120]}",
            }
        return {"action": "update_last", "steps": ["forget last lesson"],
                "summary": "Replace the most recent saved lesson."}
    if _LEARN_BLOCK_LINKS.search(raw):
        return {"action": "block_links", "steps": [raw], "summary": f"Restrict links: {raw[:140]}"}
    return {"action": "add", "steps": [raw], "summary": f"Add shared instruction: {raw[:140]}"}


def _learn_confirm_prompt(draft: Dict[str, Any]) -> str:
    action = {
        "add": "add karna",
        "update": "purani instruction badalna",
        "update_last": "aakhri lesson update karna",
        "remove": "matching instruction remove karna",
        "remove_last": "aakhri lesson remove karna",
        "remove_all": "saare saved lessons remove karna",
        "block_links": "link restriction save karna",
        "allow_links": "link restrictions hataana",
    }.get(draft.get("action"), "save karna")
    return (
        f"Samajh gayi: main {action} chahti hoon.\n{draft.get('summary', '')}\n\n"
        "Confirm karein? Reply 'yes' ya 'confirm'. "
        "Badalne ke liye nayi baat likhein, ya 'cancel'."
    )


def _execute_learning(steps: List[str]) -> Dict[str, Any]:
    results = [_save_persona_learning(step) for step in steps if step and step.strip()]
    removed = sum(1 for result in results if result.get("action") == "deleted")
    if any(result.get("action") == "allowed" for result in results):
        return {"action": "allowed", "count": 1}
    if removed:
        return {"action": "deleted", "count": removed}
    return {"action": "saved", "count": len(results)}


def _learn_result_message(result: Dict[str, Any]) -> str:
    if result["action"] == "deleted":
        return f"✅ Theek hai, {result['count']} saved lesson(s) remove ho gaye. Base persona safe hai."
    if result["action"] == "not_found":
        return "Koi matching saved lesson nahi mila. Exact word/phrase ke saath /learn forget <text> try karo."
    if result["action"] == "allowed":
        return "✅ Link restrictions removed."
    return "✅ Samajh gayi, yaad rakhungi. persona.json mein save kar diya."


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single admin-only entry point. Understand first, save only after confirmation."""
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Admin only!")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        context.user_data["learning_session"] = None
        context.user_data["awaiting_learning"] = True
        await update.effective_message.reply_text(
            "Kya seekhana hai? Ek instruction likho (add, view, change ya forget — main khud samajh lungi)."
        )
        return
    draft = parse_learning_intent(text)
    if draft["action"] == "view":
        context.user_data["learning_session"] = None
        context.user_data["awaiting_learning"] = False
        await update.effective_message.reply_text(_learning_view(), parse_mode="HTML")
        return
    context.user_data["learning_session"] = draft
    context.user_data["awaiting_learning"] = False
    await update.effective_message.reply_text(_learn_confirm_prompt(draft))


async def handle_admin_learning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation / correction loop for /learn. Non-admins are ignored completely."""
    message = update.effective_message
    if not message or not message.text or update.effective_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    session = context.user_data.get("learning_session")

    # Migrate an old-style /learn-without-args session safely.
    if not session and context.user_data.get("awaiting_learning"):
        draft = parse_learning_intent(text)
        if draft["action"] == "view":
            context.user_data["awaiting_learning"] = False
            await message.reply_text(_learning_view(), parse_mode="HTML")
            raise ApplicationHandlerStop
        context.user_data["learning_session"] = draft
        context.user_data["awaiting_learning"] = False
        await message.reply_text(_learn_confirm_prompt(draft))
        raise ApplicationHandlerStop
    if not session:
        return

    if _LEARN_CANCEL.match(text):
        context.user_data["learning_session"] = None
        await message.reply_text("OK, /learn session cancel kar diya. Kuch save nahi hua.")
        raise ApplicationHandlerStop

    if _LEARN_CONFIRM.match(text):
        result = _execute_learning(session["steps"])
        context.user_data["learning_session"] = None
        dm.audit("admin_learning_saved", update.effective_user.id, "persona.json",
                 f"{session['action']}: {session['summary'][:160]}")
        await message.reply_text(_learn_result_message(result))
        raise ApplicationHandlerStop

    draft = parse_learning_intent(text)
    if draft["action"] == "view":
        context.user_data["learning_session"] = None
        await message.reply_text(_learning_view(), parse_mode="HTML")
        raise ApplicationHandlerStop
    context.user_data["learning_session"] = draft
    await message.reply_text("Theek hai, samajh badal diya:\n" + _learn_confirm_prompt(draft))
    raise ApplicationHandlerStop


# ================= SCHEDULED MESSAGES =================
SCHEDULED_MESSAGES = {
    6: "🌅 Good morning! Chelsea Football updates are ready when you are.",
    12: "☀️ Midday check-in: today's match updates are available in the group.",
    18: "🌆 Good Evening! Don't forget to check your earnings and share with friends! 👥",
    22: "🌙 Good Night! Rest well and come back tomorrow for more profits! 😴",
}


async def scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Send the message for the scheduled slot that triggered this job."""
    if dm.is_bot_muted():
        return

    job = getattr(context, "job", None)
    job_data = getattr(job, "data", None) if job else None
    hour = int((job_data or {}).get("hour") or datetime.now().hour)
    message = SCHEDULED_MESSAGES.get(hour)
    if not message:
        return

    now = datetime.now()
    for group_id, record in dm.get_groups().items():
        if not isinstance(record, dict) or record.get("registration_status") != "verified":
            continue
        schedule_key = f"{now.date()}:{hour}:{group_id}"
        sent = context.application.bot_data.setdefault("scheduled_sent", set())
        if schedule_key in sent:
            continue
        try:
            await context.bot.send_message(chat_id=int(group_id), text=message)
            sent.add(schedule_key)
        except Exception as e:
            print(f"⚠️ Could not send scheduled message to {group_id}: {e}", flush=True)

# ================= GROUP MODERATION =================
def _message_has_link(message) -> bool:
    text = message.text or message.caption or ""
    if has_any_links(text):
        return True
    entities = list(message.entities or []) + list(message.caption_entities or [])
    return any(getattr(entity, "type", "") in ("url", "text_link") for entity in entities)


def _message_has_inline_buttons(message) -> bool:
    markup = message.reply_markup
    return bool(markup and getattr(markup, "inline_keyboard", None))


_ABUSE_OR_THREAT = re.compile(
    r"("
    r"\b(i will kill|i'll kill|kill you|murder you|rape you|beat you)\b|"
    r"mar dunga|maar dunga|jaan se maar|goli mar|bomb maar|kat dunga|thappad marunga|"
    r"madarchod|behenchod|bhosdik|chutiya|chutiye|gaandu|randi|harami|kameena|kamini|"
    r"\b(fuck you|bastard|bitch|asshole|motherfucker)\b|"
    r"\b(company|chelsea|user|bande|ladki|ladke|admin)\b.{0,24}\b(kutta|kutti|suar|bewakoof|nalayak|haramkhor)\b|"
    r"\b(kutta|kutti|suar|bewakoof|nalayak|haramkhor)\b.{0,24}\b(company|chelsea|user|bande|ladki|ladke|admin)\b"
    r")",
    re.IGNORECASE,
)


_FRAUD = re.compile(
    r"\b(fraud|fake|scam|thug|loot|dhoka|bakwas|pagal bana|paisa doob|paise doob|"
    r"paisa kat|withdraw nahi|mat join)\b",
    re.IGNORECASE,
)
_GROUP_CONTAINMENT_LINE = "yahan bheed hai, DM me aao — 2 minute me clear kar dungi."
_DM_CONTAINMENT_LINE = "group me tumhari baat delete hui, yahan baat karte hain."


def _message_is_abuse_or_threat(message) -> bool:
    """Gaali or a threat aimed at a person or a company. A complaint is not abuse."""
    text = message.text or message.caption or ""
    return bool(_ABUSE_OR_THREAT.search(text))


def _message_has_fraud_claim(message) -> bool:
    text = message.text or message.caption or ""
    return bool(_FRAUD.search(text))


def _mention_text(user) -> str:
    """Username tag when available, tg:// link otherwise."""
    if getattr(user, "username", None):
        return f"@{user.username}"
    name = html.escape(str(getattr(user, "first_name", None) or "Friend"))
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _contain_group_message(update, context, user, chat, label: str) -> None:
    """Delete in group, answer with one calm line, then best-effort DM the user."""
    await _delete_and_verify(update.effective_message)
    tag = _mention_text(user)
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"{tag} {_GROUP_CONTAINMENT_LINE}",
        parse_mode="HTML",
    )
    print(f"🧹 {label} contained from {user.id}", flush=True)

    try:
        update_lead_state(user.id, "", user.first_name or "User", flags={"contained": True})
    except Exception as e:
        print(f"⚠️ Could not flag contained lead {user.id}: {e}", flush=True)

    # Bot API cannot start a DM unless the user pressed /start; that is expected.
    contained = dm.data.setdefault("dm_contained", {})
    key = str(user.id)
    if key not in contained:
        try:
            await context.bot.send_message(chat_id=user.id, text=_DM_CONTAINMENT_LINE)
            contained[key] = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            contained[key] = {"failed_at": datetime.now().isoformat(timespec="seconds"),
                              "error": str(e)[:120]}
            print(f"⚠️ Could not DM {user.id} after containment: {e}", flush=True)
        dm.save()


async def _is_group_admin(chat, user_id: int) -> bool:
    try:
        member = await chat.get_member(user_id)
    except Exception as e:
        print(f"⚠️ Could not check member {user_id}: {e}", flush=True)
        return False
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def _delete_and_verify(message) -> bool:
    """Delete a group message, then delete again. 'not found' on the second try means it is gone."""
    try:
        await message.delete()
    except Exception as e:
        err = str(e).lower()
        if "not found" in err:
            print(f"✅ Message {message.message_id} already gone", flush=True)
            return True
        print(f"⚠️ Could not delete message {message.message_id}: {e}", flush=True)
        return False
    try:
        await message.delete()
        print(f"⚠️ Message {message.message_id} still existed after the first delete", flush=True)
        return False
    except Exception as e:
        gone = "not found" in str(e).lower()
        print(
            f"✅ Verified message {message.message_id} deleted" if gone else f"⚠️ Recheck failed for {message.message_id}: {e}",
            flush=True,
        )
        return gone


async def moderate_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove non-admin bots, links, and inline-button posts. Confirm the message is gone."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type not in ("group", "supergroup"):
        return
    if user.id == context.bot.id:
        return

    is_admin = await _is_group_admin(chat, user.id)
    if user.is_bot and not is_admin:
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            print(f"🚫 Banned non-admin bot {user.id} from {chat.id}", flush=True)
        except Exception as e:
            print(f"⚠️ Could not ban bot {user.id}: {e}", flush=True)
        await _delete_and_verify(message)
        raise ApplicationHandlerStop

    if is_admin:
        raise ApplicationHandlerStop
    if _message_has_fraud_claim(message):
        await _contain_group_message(update, context, user, chat, "Fraud claim")
        raise ApplicationHandlerStop
    if _message_is_abuse_or_threat(message):
        await _contain_group_message(update, context, user, chat, "Abuse or threat")
        raise ApplicationHandlerStop
    if _message_has_link(message) or _message_has_inline_buttons(message):
        await _delete_and_verify(message)
        raise ApplicationHandlerStop


# ================= MESSAGE HANDLERS =================

# ========== AUTHORIZATION FOR EXTERNAL / OTHER-PERSON ACTIONS ==========
_PRIVILEGED_REQUESTS = (
    re.compile(r"\b(?:broadcast|send (?:this|it|the message) to (?:all|every)\s+users?|message all users|send to all groups|post to all groups)\b", re.IGNORECASE),
    re.compile(r"\b(?:delete|ban|mute|modify)\s+(?:all|every)\s+(?:users?|groups?|messages?)\b", re.IGNORECASE),
    re.compile(r"\b(?:change|edit|show|read|access)\s+(?:me\s+|please\s+)*(?:the\s+)?(?:global|shared)\s+(?:settings?|persona|instructions?|credentials?|api key)\b", re.IGNORECASE),
    re.compile(r"\b(?:show|read|access|reveal)\s+(?:me\s+)?(?:the\s+)?(?:api\s+key|credentials?|password)\b", re.IGNORECASE),
    re.compile(r"\b(?:read|access|edit|change|delete)\s+(?:another|other|someone(?:'s)?)\s+user(?:'s)?\s+(?:memory|data|details|chat)\b", re.IGNORECASE),
    re.compile(r"\b(?:assign|reassign)\s+(?:a\s+)?group\s+to\b", re.IGNORECASE),
)


def request_needs_authorization(text: str) -> bool:
    """A phrase like 'do this' is a request, never permission by itself."""
    return any(pattern.search(text or "") for pattern in _PRIVILEGED_REQUESTS)


def actor_may_authorize(user_id: int, chat) -> bool:
    if user_id == ADMIN_ID:
        return True
    if chat and chat.type in ("group", "supergroup"):
        return dm.is_group_owner(user_id, chat.id)
    return False



# ========== LIGHTWEIGHT CONSTRAINED AI AGENT ==========
GENERATED_DIR = Path("generated")

AGENT_TOOL_NAMES = {
    "list_groups_admin_status", "broadcast_groups", "set_group_welcome",
    "set_group_setting", "delete_group_message", "generate_python_script",
    "read_work_file", "write_work_file", "report_from_document", "web_research",
}

AGENT_SCHEMA = [
    ("list_groups_admin_status", "Report the actor's authorized Telegram groups and their real admin status.", {}, []),
    ("broadcast_groups", "Send an announcement to selected authorized groups. Requires user approval.",
     {"message": {"type": "string"}, "group_ids": {"type": "array", "items": {"type": "integer"}}}, ["message"]),
    ("set_group_welcome", "Update the welcome message of one group owned by the actor.",
     {"group_id": {"type": "integer"}, "message": {"type": "string"}}, ["message"]),
    ("set_group_setting", "Change a group's links_allowed or bot_muted setting. Requires approval.",
     {"group_id": {"type": "integer"}, "key": {"type": "string"}, "value": {"type": "string"}}, ["group_id", "key", "value"]),
    ("delete_group_message", "Delete one specific message in the actor's own group. Requires approval.",
     {"group_id": {"type": "integer"}, "message_id": {"type": "integer"}}, ["group_id", "message_id"]),
    ("generate_python_script", "Generate a reviewed Python script file. The bot never executes generated code.",
     {"filename": {"type": "string"}, "purpose": {"type": "string"}}, []),
    ("read_work_file", "Read a text file from the sandboxed generated folder only.",
     {"filename": {"type": "string"}}, ["filename"]),
    ("write_work_file", "Create a text file in the sandboxed generated folder only.",
     {"filename": {"type": "string"}, "content": {"type": "string"}}, ["filename", "content"]),
    ("report_from_document", "Summarize a supported text/CSV/JSON file into a saved report.",
     {"filename": {"type": "string"}}, []),
    ("web_research", "Fetch a public web page or run a basic web search.",
     {"url": {"type": "string"}, "query": {"type": "string"}}, []),
    # Unified assistant tools below. All run under Ishani's existing persona;
    # none of them introduces a new identity or a separate chat mode.
    ("web_search", "Search the public web for current information using a short query.",
     {"query": {"type": "string"}}, ["query"]),
    ("read_webpage", "Read one public web page URL and summarize it.",
     {"url": {"type": "string"}, "question": {"type": "string"}}, ["url"]),
    ("generate_image", "Create an image from a description and send it in this chat when an image API is configured.",
     {"prompt": {"type": "string"}}, ["prompt"]),
    ("analyze_file", "Analyse a saved text/CSV/JSON file and write a factual report.",
     {"filename": {"type": "string"}, "question": {"type": "string"}}, []),
    ("execute_code", "Run a tiny sandboxed calculation. No imports, files, network, shell, or arbitrary code.",
     {"expression": {"type": "string"}}, ["expression"]),
    ("schedule_message", "Schedule a reminder or message for later. Group messages need an authorized owner.",
     {"message": {"type": "string"}, "when": {"type": "string"}, "group_id": {"type": "integer"}}, ["message", "when"]),
    ("remember_fact", "Save one factual note about this user in their private memory.",
     {"fact": {"type": "string"}}, ["fact"]),
    ("recall_memory", "Recall what is currently saved about this user.", {}, []),
]

AGENT_TOOLS = [
    {"type": "function", "function": {"name": name, "description": description,
     "parameters": {"type": "object", "properties": properties, "required": required}}}
    for name, description, properties, required in AGENT_SCHEMA
]

_TOOL_LABELS = {
    "list_groups_admin_status": "group admin check",
    "broadcast_groups": "group broadcast",
    "set_group_welcome": "welcome message update",
    "set_group_setting": "group setting update",
    "delete_group_message": "message delete",
    "generate_python_script": "script generation",
    "read_work_file": "file read",
    "write_work_file": "file creation",
    "report_from_document": "document report",
    "web_research": "web research",
    "web_search": "web search",
    "read_webpage": "page read",
    "generate_image": "image generation",
    "analyze_file": "file analysis",
    "execute_code": "safe calculation",
    "schedule_message": "scheduling",
    "remember_fact": "memory save",
    "recall_memory": "memory recall",
}
# Broadcasts, destructive changes and sensitive group actions always pause for approval.
_APPROVAL_TOOLS = {
    "broadcast_groups", "set_group_setting", "delete_group_message",
}

_AGENT_PATTERNS = (
    ("broadcast_groups", re.compile(
        r"\b(?:broadcast|send|post)\b.{0,60}\b(?:to|in)\b.{0,30}\b(?:my|all|the)\b.{0,10}\bgroups?\b|"
        r"\bbroadcast\s+to\s+(?:my|all)\s+groups?\b|"
        r"\bbroadcast\b.{0,100}-\d{6,15}\b", re.IGNORECASE)),
    ("list_groups_admin_status", re.compile(
        r"\b(?:check|show|report|tell)\b.{0,50}\badmin\s+status\b|"
        r"\bgroups?\b.{0,35}\badmin\s+status\b|"
        r"\badmin\s+status\b.{0,35}\bgroups?\b", re.IGNORECASE)),
    ("set_group_welcome", re.compile(
        r"\b(?:update|change|set)\b.{0,40}\bwelcome\s+message\b|"
        r"\bwelcome\s+message\b.{0,30}\b(?:update|change|set)\b", re.IGNORECASE)),
    ("delete_group_message", re.compile(r"\bdelete\s+(?:this|that|the)?\s*message\b", re.IGNORECASE)),
    ("set_group_setting", re.compile(
        r"\b(?:turn|set|change)\b.{0,30}\b(?:links|links_allowed|bot_muted|mute)\b", re.IGNORECASE)),
    ("generate_python_script", re.compile(
        r"\b(?:create|write|generate|make)\b.{0,40}\b(?:python\s+)?(?:script|code)\b", re.IGNORECASE)),
    ("report_from_document", re.compile(
        r"\b(?:prepare|make|create|write|generate)\b.{0,30}\breport\b.{0,40}\b(?:document|file|excel|csv|json)\b|"
        r"\bsummaris(?:e|z)e\b.{0,25}\b(?:document|file)\b", re.IGNORECASE)),
    ("web_research", re.compile(
        r"\b(?:search|research|look\s+up|find\s+out)\b.{0,25}\b(?:web|online|internet)\b|"
        r"\b(?:google|research)\b\s+.{4,}", re.IGNORECASE)),
    ("read_work_file", re.compile(r"\bread\b.{0,25}\bfile\b.{0,40}", re.IGNORECASE)),
    ("write_work_file", re.compile(r"\b(?:create|write|make)\b.{0,25}\b(?:a\s+)?(?:text\s+)?file\b", re.IGNORECASE)),
)


def detect_agent_request(text: str) -> Optional[str]:
    """Deterministic first pass: only clear task requests become tool calls."""
    for name, pattern in _AGENT_PATTERNS:
        if pattern.search(text or ""):
            return name
    return None


def _agent_args_from_text(text: str, tool: str) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    if tool in ("broadcast_groups", "set_group_welcome", "write_work_file"):
        quoted = re.search(r"[\"“'](.{4,300}?)[\"”']", text)
        labelled = re.search(
            r"\b(?:message|announcement|welcome(?:\s+message)?|content|saying)\b\s*[:=]?\s*(.{4,300})$",
            text, re.IGNORECASE)
        colon = re.search(r":\s*(.{4,300})$", text)
        match = quoted or labelled or colon
        if match:
            args["message" if tool != "write_work_file" else "content"] = match.group(1).strip()
        else:
            stripped = re.sub(
                r"^(?:please\s+|plz\s+)?(?:send|broadcast|post|update|change|set|create|write)\b.{0,50}?\b(?:to|in|for|as)\b.{0,30}",
                "", text, flags=re.IGNORECASE).strip()
            args["message" if tool != "write_work_file" else "content"] = stripped[:300]
        ids = re.findall(r"-\d{6,15}|\d{6,15}", text)
        if ids:
            args["group_ids"] = [int(item) for item in ids]
    if tool in ("generate_python_script", "report_from_document", "read_work_file", "write_work_file", "web_research"):
        filename = re.search(r"([A-Za-z0-9 _-]{1,60}\.(?:py|txt|md|json|csv|xlsx|xls))", text, re.IGNORECASE)
        if filename:
            args["filename"] = filename.group(1)
        url = re.search(r"https?://[^\s<>]+", text)
        if url:
            args["url"] = url.group(0)
        query = re.search(r"\b(?:search|research|look\s+up|find\s+out|google)\b\s+(?:the\s+)?(?:web\s+|online\s+)?(?:for\s+)?(.+)$",
                          text, re.IGNORECASE)
        if query:
            args["query"] = query.group(1).strip()[:200]
        args["purpose"] = text[:300]
    if tool == "delete_group_message":
        nums = re.findall(r"\d{1,15}", text)
        if len(nums) >= 2:
            args["group_id"], args["message_id"] = int(nums[-2]), int(nums[-1])
    return args


async def _model_tool_call(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Best-effort native OpenAI tool-calls. Local models that lack tools simply return none."""
    try:
        response = await call_custom_openai(
            prompt=f"User request: {text}\nPick one tool or reply NONE. Do not claim any action was done.",
            system_instruction="Select a tool only when the user clearly asks for a supported task. Never invent success.",
            tools=AGENT_TOOLS,
        )
        for call in getattr(response, "tool_calls", []) or []:
            if call.get("name") in AGENT_TOOL_NAMES:
                return call["name"], call.get("arguments") or {}
    except Exception as e:
        print(f"⚠️ Model tool selection unavailable: {e}", flush=True)
    return None, {}


def _safe_work_path(filename: str, suffix: str = "") -> Optional[Path]:
    name = (filename or "").strip()
    if suffix:
        name = f"{Path(name).stem}_{suffix}{Path(name).suffix}"
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,70}\.(py|txt|md|json|csv|png|jpg|jpeg|webp)", name, re.IGNORECASE):
        return None
    GENERATED_DIR.mkdir(exist_ok=True)
    return GENERATED_DIR / name


def _unique_work_path(filename: str) -> Optional[Path]:
    base = _safe_work_path(filename)
    if not base:
        return None
    if not base.exists():
        return base
    for index in range(1, 100):
        candidate = _safe_work_path(filename, str(index))
        if candidate is not None and not candidate.exists():
            return candidate
    return None


def _public_http_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".local"):
            return None
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return None
        except ValueError:
            pass
        return parsed.geturl()
    except Exception:
        return None


async def _agent_broadcast(bot_obj, actor_id: int, group_ids: List[int], message: str) -> str:
    results = []
    for group_id in group_ids:
        item = {"group_id": int(group_id), "ok": False, "error": ""}
        try:
            await bot_obj.send_message(chat_id=int(group_id), text=message)
            item["ok"] = True
        except Exception as e:
            item["error"] = str(e)[:200]
        results.append(item)
    dm.record_broadcast(actor_id, "agent:groups", results)
    sent = sum(1 for item in results if item.get("ok"))
    failed = len(results) - sent
    detail = "; ".join(f"{r['group_id']}: {'sent' if r['ok'] else r['error']}" for r in results)
    return f"Broadcast verified — sent {sent}, failed {failed}. {detail}"


async def _tool_group_admin_status(actor_id: int) -> str:
    ids = dm.visible_group_ids(actor_id)
    if not ids:
        return "Aapke paas koi registered/assigned group nahi hai."
    if not BOT_APP:
        return "Abhi bot connect nahi hai; main group status verify nahi kar sakta. Kuch claim nahi kar raha."
    lines = [f"📊 Group admin report ({len(ids)} groups):"]
    for group_id in ids:
        record = dm.get_group(group_id) or {}
        business = record.get("business") if isinstance(record.get("business"), dict) else {}
        name = business.get("name") or f"Group {group_id}"
        admins = 0
        members = 0
        verified = True
        try:
            admins = len(await BOT_APP.bot.get_chat_administrators(int(group_id)))
        except Exception as e:
            verified = False
            print(f"⚠️ admin check failed {group_id}: {e}", flush=True)
        try:
            members = await BOT_APP.bot.get_chat_member_count(int(group_id))
        except Exception:
            verified = False
        stats = dict(record.get("stats") or {})
        stats.update({"administrators": admins, "members": members,
                      "checked_at": datetime.now().isoformat(timespec="seconds")})
        record["stats"] = stats
        lines.append(
            f"\n• {name} ({group_id}) — admins: {admins if verified else 'unknown'}, "
            f"members: {members if verified else 'unknown'}, "
            f"status: {record.get('registration_status', 'assigned')}, "
            f"verified: {'yes' if verified else 'no'}"
        )
    dm.save()
    return "\n".join(lines)


async def _tool_set_welcome(actor_id: int, args: Dict[str, Any], chat) -> str:
    group_id = args.get("group_id")
    try:
        group_id = int(group_id) if group_id is not None else (chat.id if chat and chat.type in ("group", "supergroup") else None)
    except (TypeError, ValueError):
        group_id = None
    if group_id is None:
        return "Group ID nahi mila. Group me chalayein ya group ID batayein."
    if not dm.is_group_owner(actor_id, group_id):
        return "❌ Aap is group ke welcome message ko change nahi kar sakte."
    message = str(args.get("message") or "").strip()
    if not message:
        return "Naya welcome message batayein."
    if not dm.set_group_details(actor_id, ADMIN_ID, group_id, "welcome_message", message):
        return "❌ Welcome message save nahi hua."
    saved = dm.get_group_business(group_id).get("welcome_message")
    return (f"✅ Verified: group {group_id} ka welcome message ab “{saved}” hai."
            if saved == message else "❌ Save ke baad verification fail hua; kuch guarantee nahi kar sakta.")


def _script_content(purpose: str) -> str:
    header = "# Generated by Ishani. Review before running; the bot never executes generated code.\n"
    task = purpose or ""
    if re.search(r"excel|xlsx|xls", task, re.IGNORECASE):
        lines = [
            '"""Excel workbook to CSV summary (needs: pip install openpyxl)."""',
            "from pathlib import Path",
            "",
            "",
            'def excel_to_csv(input_path, output_path="excel_report.csv"):',
            "    try:",
            "        from openpyxl import load_workbook",
            "    except ImportError:",
            '        raise SystemExit("Install dependency first: pip install openpyxl")',
            "    workbook = load_workbook(input_path, read_only=True, data_only=True)",
            "    sheet = workbook.active",
            "    rows = list(sheet.values)",
            "    if not rows:",
            '        raise SystemExit("Workbook is empty")',
            "    target = Path(output_path)",
            '    with target.open("w", encoding="utf-8", newline="") as handle:',
            "        import csv",
            "        writer = csv.writer(handle)",
            "        writer.writerows(rows)",
            '    return f"Wrote {len(rows)} rows to {target}"',
            "",
            "",
            'if __name__ == "__main__":',
            '    raise SystemExit("Usage: python excel_script.py <input.xlsx> [output.csv]")',
        ]
    elif re.search(r"csv", task, re.IGNORECASE):
        lines = [
            '"""Summarize a CSV file using only the Python standard library."""',
            "import csv",
            "from pathlib import Path",
            "",
            "",
            "def summarize_csv(path):",
            '    with Path(path).open("r", encoding="utf-8", newline="") as handle:',
            "        rows = list(csv.reader(handle))",
            "    if not rows:",
            '        return "CSV is empty"',
            '    return f"Rows: {len(rows) - 1}, Columns: {len(rows[0])}"',
            "",
            "",
            'if __name__ == "__main__":',
            '    raise SystemExit("Usage: python csv_script.py <input.csv>")',
        ]
    else:
        lines = [
            '"""Safe starting point for a text-processing task."""',
            "from pathlib import Path",
            "",
            "",
            "def process_text(path):",
            '    text = Path(path).read_text(encoding="utf-8")',
            '    return {"characters": len(text), "lines": len(text.splitlines())}',
            "",
            "",
            'if __name__ == "__main__":',
            '    raise SystemExit("Usage: python ishani_script.py <input.txt>")',
        ]
    return header + "\n".join(lines) + "\n"


async def _tool_generate_script(args: Dict[str, Any]) -> str:
    filename = args.get("filename") or "ishani_script.py"
    if not str(filename).lower().endswith(".py"):
        filename = f"{filename}.py"
    target = _unique_work_path(str(filename))
    if not target:
        return "❌ File name rejected. Use a simple name like report_script.py inside generated/."
    target.write_text(_script_content(str(args.get("purpose") or "")), encoding="utf-8")
    verified = target.exists() and target.read_text(encoding="utf-8").startswith("# Generated by Ishani")
    return (f"✅ Script generated and verified: {target}. It was NOT executed; review it before running."
            if verified else "❌ Script write could not be verified.")


async def _tool_read_file(args: Dict[str, Any]) -> str:
    target = _safe_work_path(str(args.get("filename") or ""))
    if not target or not target.exists() or not target.is_file():
        return "File nahi mila. Sirf generated/ folder ke andar ke text files padhe ja sakte hain."
    content = target.read_text(encoding="utf-8", errors="replace")[:12000]
    return f"📄 {target.name}:\n{content}"


async def _tool_report_document(args: Dict[str, Any]) -> str:
    filename = str(args.get("filename") or "").strip()
    if filename.lower().endswith((".xlsx", ".xls")):
        return ("Excel binary file directly parse nahi kar sakti (openpyxl optional dependency hai). "
                "Main us file ko process karne ka Python script bana sakti hoon; script execute nahi karti.")
    if not filename:
        candidates = [p for p in (GENERATED_DIR.glob("*") if GENERATED_DIR.exists() else [])
                      if p.suffix.lower() in (".txt", ".csv", ".json", ".md")]
        if not candidates:
            return "Koi supported file nahi mila. .txt/.csv/.json file upload karein ya filename batayein."
        target = max(candidates, key=lambda p: p.stat().st_mtime)
    else:
        target = _safe_work_path(filename)
    if not target or not target.exists():
        return "File nahi mila. Sirf generated/ folder ke andar ke files view kar sakti hoon."
    content = target.read_text(encoding="utf-8", errors="replace")[:20000]
    stats = f"File: {target.name}, characters: {len(content)}"
    if target.suffix.lower() == ".csv":
        stats += f", lines: {len(content.splitlines())}"
    if target.suffix.lower() == ".json":
        try:
            parsed = json.loads(content)
            stats += f", json_type: {type(parsed).__name__}"
        except (TypeError, ValueError):
            stats += ", json_invalid: yes"
    try:
        response = await call_ai_with_retry(
            prompt="Write a concise, factual report from this content. Never invent numbers or claims.\n\n" + content,
            system_instruction="You write short bullet-point reports using only supplied evidence.",
        )
        report = clean_reply_text(response.text) if response and response.text else "AI report unavailable; source was not modified."
    except Exception as e:
        report = f"AI report unavailable: {e}"
    full = f"# Report for {target.name}\n\n{stats}\n\n{report}\n"
    report_path = _unique_work_path(f"report_{target.stem}.md")
    if report_path:
        report_path.write_text(full, encoding="utf-8")
        verified = report_path.exists() and report_path.read_text(encoding="utf-8") == full
        if verified:
            return f"{report}\n\n✅ Report saved and verified: {report_path}"
    return report + "\n\n⚠️ Report save could not be verified."


# ========== FREE WEB SEARCH (DuckDuckGo HTML — no API key, no paid service) ==========
SEARCH_TIMEOUT_SECONDS = 12
SEARCH_RATE_LIMIT = 8
SEARCH_RATE_WINDOW_SECONDS = 60
SEARCH_MAX_RESULTS = 5
_SEARCH_USER_AGENT = "Mozilla/5.0 (compatible; IshaniBot/1.0; web-search)"
_search_calls: Dict[int, List[float]] = {}
_search_lock = threading.Lock()

_WEB_SEARCH_SIGNALS = (
    re.compile(r"\b(?:search|google|look\s*up|find\s+out|web\s*search|internet\s*search)\b", re.IGNORECASE),
    re.compile(r"\b(?:latest|current|recent|today|now|newest|up[\s-]?to[\s-]?date)\b", re.IGNORECASE),
    re.compile(r"\b(?:news|headlines|updates?)\b", re.IGNORECASE),
    re.compile(r"\b(?:price|prices|rate|rates|score|scores|result|results|weather|forecast|stock|crypto)\b", re.IGNORECASE),
    re.compile(r"\b(?:website|site|url|link|article|page)\b.{0,40}\b(?:details?|info|content|summ?ar(?:y|ise|ize)|read)\b", re.IGNORECASE),
    re.compile(r"\b(?:summ?ar(?:y|ise|ize)|read|explain)\b.{0,40}\b(?:page|website|site|article|url|link)\b", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(?:kya\s+chal\s+raha|news\s+(?:bhejo|do|de)|search\s+kar|google\s+kar|pata\s+karo|jaan\s+kar|latest\s+kya)\b", re.IGNORECASE),
)


def needs_web_search(text: str) -> bool:
    """True only when the message clearly asks for current/external information."""
    return any(pattern.search(text or "") for pattern in _WEB_SEARCH_SIGNALS)


def _wants_summary(text: str) -> bool:
    return bool(re.search(
        r"\b(?:summ?ar(?:y|ise|ize)|read|explain|details?\s+of|what\s+does\s+(?:it|this|that)\s+say)\b",
        text or "", re.IGNORECASE,
    ))


def _web_query_from_text(text: str) -> str:
    """Turn a natural question into a short search query without inventing anything."""
    had_url = bool(re.search(r"https?://", text or ""))
    raw = re.sub(r"https?://\S+", " ", (text or ""))
    raw = re.sub(r"\b(?:hey\s+)?ishani\b", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\b(?:can|could|would|will)\s+you\b", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\b(?:please|plz|kya|kripya)\b", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(
        r"\b(?:search\s+(?:the\s+)?(?:web|internet)?\s*(?:for)?|google|lookup|look\s+up|find\s+out|"
        r"tell\s+me\s+about|what(?:'s|\s+is)|who(?:'s|\s+is)|latest\s+news\s+(?:on|about|for)?|"
        r"current\s+(?:news|info(?:rmation)?|price|rate)?|news\s+(?:on|about|for)|summ?ar(?:y|ise|ize))\b",
        " ", raw, flags=re.IGNORECASE,
    )
    raw = re.sub(r"[?.!]+$", "", raw)
    cleaned = re.sub(r"\s+", " ", raw).strip(" ,:;-")
    # A pasted URL with only a filler word ("karo", "read", ...) is a page-read
    # request. Return no query so the URL flow supplies a sensible question.
    if had_url and (not cleaned or cleaned.lower() in {
        "karo", "kar", "do", "de", "bhejo", "bhej", "read", "summary", "summarize", "summarise"
    }):
        return ""
    return cleaned[:200]


def _check_search_rate(user_id: int) -> Optional[str]:
    """Simple in-memory sliding-window limiter. Returns a friendly message if limited."""
    now = datetime.now().timestamp()
    with _search_lock:
        calls = [t for t in _search_calls.get(user_id, []) if now - t < SEARCH_RATE_WINDOW_SECONDS]
        if len(_search_calls) > 500:
            for uid in list(_search_calls):
                if not [t for t in _search_calls[uid] if now - t < SEARCH_RATE_WINDOW_SECONDS]:
                    _search_calls.pop(uid, None)
        if len(calls) >= SEARCH_RATE_LIMIT:
            wait = int(SEARCH_RATE_WINDOW_SECONDS - (now - calls[0])) + 1
            _search_calls[user_id] = calls
            return (f"⏳ Aapne {SEARCH_RATE_LIMIT} searches already kiye hain. "
                    f"Rate limit ke liye {wait} second wait karein. Kuch galat info nahi bana raha.")
        calls.append(now)
        _search_calls[user_id] = calls[-SEARCH_RATE_LIMIT:]
    return None


def _decode_ddg_url(href: str) -> Optional[str]:
    raw = html.unescape(href or "").strip()
    if "uddg=" in raw:
        raw = unquote(raw.split("uddg=", 1)[1].split("&", 1)[0])
    if raw.startswith("//"):
        raw = "https:" + raw
    return _public_http_url(raw)


class _SearchResultParser(HTMLParser):
    """Extract results from DuckDuckGo and Bing HTML without depending on attribute order."""

    LINK_CLASSES = {"result__a", "result-link", "result__url"}
    SNIPPET_CLASSES = {"result__snippet", "result-snippet", "b_caption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self.bing_depth = 0
        self.bing_heading_depth = 0
        self.link_href = ""
        self.link_parts: List[str] = []
        self.snippet_tag = ""
        self.snippet_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "li" and "b_algo" in classes:
            self.bing_depth += 1
        if tag == "h2" and self.bing_depth:
            self.bing_heading_depth += 1
        if tag == "a" and (classes & self.LINK_CLASSES or (self.bing_depth and self.bing_heading_depth)):
            self.link_href = values.get("href") or ""
            self.link_parts = []
        if (classes & self.SNIPPET_CLASSES or (self.bing_depth and tag == "p")) and not self.snippet_tag:
            self.snippet_tag = tag
            self.snippet_parts = []

    def handle_data(self, data: str):
        if self.link_href:
            self.link_parts.append(data)
        if self.snippet_tag:
            self.snippet_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag == "a" and self.link_href:
            title = " ".join("".join(self.link_parts).split())
            url = _decode_ddg_url(self.link_href)
            if url and title:
                self.results.append({"title": title[:160], "url": url, "snippet": ""})
            self.link_href = ""
            self.link_parts = []
        if tag == self.snippet_tag and self.snippet_tag:
            if self.results:
                self.results[-1]["snippet"] = " ".join("".join(self.snippet_parts).split())[:300]
            self.snippet_tag = ""
            self.snippet_parts = []
        if tag == "h2" and self.bing_heading_depth:
            self.bing_heading_depth -= 1
        if tag == "li" and self.bing_depth:
            self.bing_depth -= 1


async def _ddg_search(query: str) -> List[Dict[str, str]]:
    """Search free HTML providers, falling back to Bing if DuckDuckGo is unavailable."""
    endpoints = (
        ("DuckDuckGo", "https://html.duckduckgo.com/html/?q=" + quote(query)),
        ("DuckDuckGo Lite", "https://lite.duckduckgo.com/lite/?q=" + quote(query)),
        ("Bing", "https://www.bing.com/search?q=" + quote(query)),
    )
    failures: List[str] = []
    received_html = False
    valid_empty_results = False
    for provider, endpoint in endpoints:
        safe_url = _public_http_url(endpoint)
        if not safe_url:
            continue
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True, max_redirects=3) as http:
                res = await http.get(safe_url, headers={
                    "User-Agent": _SEARCH_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9,hi;q=0.7",
                })
            if res.status_code >= 400:
                failures.append(f"{provider} HTTP {res.status_code}")
                continue
            if "html" not in res.headers.get("content-type", "").lower():
                failures.append(f"{provider} returned non-HTML")
                continue
            received_html = True
            parser = _SearchResultParser()
            parser.feed(res.text[:250000])
            if parser.results:
                # Keep only unique, public links in case the page repeats sitelinks.
                unique: Dict[str, Dict[str, str]] = {}
                for item in parser.results:
                    unique.setdefault(item["url"], item)
                return list(unique.values())[:SEARCH_MAX_RESULTS]
            if re.search(r"no results(?: found| for)?|did not match any documents", res.text[:250000], re.IGNORECASE):
                valid_empty_results = True
            else:
                failures.append(f"{provider} returned no parseable results")
        except Exception as e:
            failures.append(f"{provider}: {str(e)[:100]}")
            print(f"⚠️ {provider} search failed: {e}", flush=True)
    if failures:
        print("⚠️ All web search providers failed: " + "; ".join(failures), flush=True)
    if not received_html:
        raise RuntimeError("Search providers could not be reached: " + "; ".join(failures[:3]))
    if not valid_empty_results and failures:
        raise RuntimeError("Search providers responded, but their result pages could not be parsed")
    return []

async def _fetch_page_text(url: str) -> Tuple[str, str]:
    """Fetch a public page and return (title, readable text). Never returns private-network content."""
    safe_url = _public_http_url(url)
    if not safe_url:
        raise RuntimeError("URL is invalid or points to a private address")
    headers = {
        "User-Agent": _SEARCH_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json,application/xml;q=0.9,*/*;q=0.5",
    }
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=False) as http:
        current_url = safe_url
        for _ in range(6):
            res = await http.get(current_url, headers=headers)
            if res.status_code not in (301, 302, 303, 307, 308):
                break
            location = res.headers.get("location")
            redirect_url = _public_http_url(urljoin(current_url, location or ""))
            if not redirect_url:
                raise RuntimeError("Page redirected to an invalid or private address")
            current_url = redirect_url
        else:
            raise RuntimeError("Too many page redirects")
    if res.status_code >= 400:
        raise RuntimeError(f"HTTP {res.status_code}")
    content_type = res.headers.get("content-type", "").lower()
    is_html = "html" in content_type or not content_type
    is_text = is_html or any(kind in content_type for kind in (
        "text/plain", "application/json", "application/xml", "text/xml",
        "application/rss+xml", "application/atom+xml",
    ))
    if not is_text:
        raise RuntimeError(f"Unsupported page type: {content_type[:80] or 'unknown'}")
    body = res.text[:200000]
    if not is_html:
        return current_url[:160], body[:12000].strip()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""
    text = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", body, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</(?:p|div|li|h[1-6]|br)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", html.unescape(text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return title[:160], text[:12000]


async def _ai_summarize_web(title: str, url: str, text: str, question: str = "") -> str:
    """Summarize only the supplied page text. Never invent facts, dates or numbers."""
    if not text:
        return "Page ka text read nahi ho paya (site empty ya blocked). Main kuch invent nahi kar raha."
    prompt = (
        "Using ONLY the Source text below, answer in 3-5 short bullets. "
        "If the answer is not in the source, say that clearly. Never invent facts, numbers or dates.\n"
        + (f"Question: {question}\n" if question else "")
        + f"Source title: {title}\nSource URL: {url}\n\n{text[:7000]}"
    )
    try:
        response = await call_ai_with_retry(
            prompt,
            system_instruction="You write short factual bullet summaries using only supplied text.",
        )
        if response and response.text:
            return clean_reply_text(response.text)
    except Exception as e:
        print(f"⚠️ Web summary unavailable: {e}", flush=True)
    return "AI summary abhi unavailable hai. Neeche source se mila text hi dekhein — main guess nahi kar raha."


def _search_error(kind: str, exc: Exception) -> str:
    return ("❌ Web " + html.escape(kind) + " fail hua: " + html.escape(str(exc)[:160]) +
            ". Search abhi available nahi hai — main kuch galat jaankari nahi bana raha.")


def _render_search_results(query: str, results: List[Dict[str, str]]) -> str:
    lines = [f"<b>🔎 Search results: {html.escape(query[:120])}</b>", ""]
    for index, item in enumerate(results[:SEARCH_MAX_RESULTS], 1):
        title = html.escape(item.get("title") or "Untitled result")[:180]
        url = html.escape(item.get("url") or "", quote=True)
        snippet = html.escape(item.get("snippet") or "")[:300]
        lines.append(f"{index}. <a href=\"{url}\">{title}</a>")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    lines.append("<i>Sources: DuckDuckGo / Bing free search. Khud verify karke padhein.</i>")
    return "\n".join(lines)


def _render_web_summary(title: str, url: str, summary: str) -> str:
    return ("\n<b>📄 Page summary: " + html.escape(title[:120]) + "</b>\n" +
            html.escape(summary)[:1600] +
            "\n\n🔗 <a href=\"" + html.escape(url, quote=True) + "\">Read the original source</a>")


async def _run_web_search(query: str, user_id: int, summarize: bool = False, url: str = "") -> str:
    """Single entry point shared by /search, the agent tool and the admin panel."""
    limited = _check_search_rate(int(user_id or 0))
    if limited:
        return limited
    query = (query or "").strip()[:200]
    safe_url = _public_http_url(url) if url else ""
    if url and not safe_url:
        return "❌ Yeh public web URL nahi hai; private ya invalid addresses fetch nahi kar sakti."
    if safe_url:
        try:
            title, text = await _fetch_page_text(safe_url)
        except Exception as e:
            return _search_error("page read", e)
        summary = await _ai_summarize_web(title or safe_url, safe_url, text, query or f"Summarize {safe_url}")
        return "<b>🔎 Page read</b>\n" + _render_web_summary(title or safe_url, safe_url, summary)
    if not query:
        return "Search query batayein. Example: <code>/search latest news</code>"
    try:
        results = await _ddg_search(query)
    except Exception as e:
        return _search_error("search", e)
    if not results:
        return ("❌ Abhi web search available nahi hai ya koi result nahi mila. "
                "Main kuch invent nahi kar raha. Thodi der baad try karein ya direct URL bhejein.")
    rendered = _render_search_results(query, results)
    if summarize or _wants_summary(query):
        top = results[0]
        try:
            title, text = await _fetch_page_text(top["url"])
            summary = await _ai_summarize_web(title or top["title"], top["url"], text, query)
            rendered += _render_web_summary(title or top["title"], top["url"], summary)
        except Exception as e:
            rendered += "\n\n⚠️ Top page summary unavailable: " + html.escape(str(e)[:120])
    return rendered


async def _tool_web_research(args: Dict[str, Any], user_id: int = 0) -> str:
    return await _run_web_search(
        query=str(args.get("query") or ""),
        user_id=user_id,
        summarize=bool(args.get("summarize")),
        url=str(args.get("url") or ""),
    )


# ================= UNIFIED AI TOOL CALLING (one Ishani, one conversation) =================
# The model picks from this whitelist. Nothing outside it can ever be executed.
_TOOL_SCHEMAS = {name: (properties, required) for name, _, properties, required in AGENT_SCHEMA}
_NATIVE_TOOL_SUPPORT: Dict[str, bool] = {}
_PENDING_TOOL_CONTEXT: Dict[str, Dict[str, Any]] = {}
_MAX_TOOLS_PER_TURN = 4

_EXTRA_TOOL_INTENT = re.compile(
    r"\b(?:generate|create|make|draw|banao|bana)\b.{0,45}\b(?:image|photo|picture|tasveer)\b|"
    r"\b(?:image|photo|picture|tasveer)\b.{0,45}\b(?:generate|create|make|draw|banao|bana)\b|"
    r"\b(?:remind|reminder|schedule|calendar|later|kal|tomorrow)\b|"
    r"\b(?:yaad\s+rakho|remember\s+that|note\s+that|recall|what\s+do\s+you\s+remember)\b|"
    r"\b(?:calculate|compute|evaluate|solution|solve|kitna\s+hoga)\b|"
    r"\b(?:analyse|analyze|summ?arise|summ?arize)\b.{0,35}\b(?:file|document|csv|json|report)\b",
    re.IGNORECASE,
)


def _deterministic_tool(text: str) -> Optional[str]:
    """Cheap intent gate so ordinary chat keeps its cached, single-call path."""
    tool = detect_agent_request(text)
    if tool:
        return tool
    if needs_web_search(text):
        return "read_webpage" if re.search(r"https?://", text or "") else "web_research"
    if not _EXTRA_TOOL_INTENT.search(text or ""):
        return None
    if re.search(r"\b(image|photo|picture|tasveer)\b", text or "", re.I):
        return "generate_image"
    if re.search(r"\b(remind|reminder|schedule|kal|tomorrow|later|calendar)\b", text or "", re.I):
        return "schedule_message"
    if re.search(r"\b(recall|what do you remember|yaad hai)\b", text or "", re.I):
        return "recall_memory"
    if re.search(r"\b(yaad rakho|remember that|note that)\b", text or "", re.I):
        return "remember_fact"
    if re.search(r"\b(calculate|compute|evaluate|solve|kitna hoga)\b", text or "", re.I):
        return "execute_code"
    if re.search(r"\b(file|document|csv|json|report)\b", text or "", re.I):
        return "analyze_file"
    return "execute_code"


# A conjunction usually means more than one job, so keep the model router for it.
_MULTI_INTENT_HINT = re.compile(
    r"\b(?:and|also|then|plus|aur|phir|ke\s+saath|along\s+with)\b", re.IGNORECASE,
)


def _deterministic_tools(text: str) -> List[str]:
    """All clearly signalled tools, so one explicit intent can skip AI routing."""
    found: List[str] = []

    def add(tool: Optional[str]) -> None:
        if tool and tool not in found:
            found.append(tool)

    agent_tool = detect_agent_request(text)
    add(agent_tool)
    # An explicit task (e.g. "broadcast ... Team update") outranks loose web
    # signals like the word "update"; otherwise we would fire an extra search.
    if not agent_tool and needs_web_search(text):
        add("read_webpage" if re.search(r"https?://", text or "") else "web_research")
    body = text or ""
    if re.search(r"\b(image|photo|picture|tasveer)\b", body, re.I) and re.search(
            r"\b(generate|create|make|draw|banao|bana)\b", body, re.I):
        add("generate_image")
    if re.search(r"\b(remind|reminder|schedule|calendar|kal|tomorrow|later)\b", body, re.I):
        add("schedule_message")
    if re.search(r"\b(recall|what do you remember|yaad hai)\b", body, re.I):
        add("recall_memory")
    if re.search(r"\b(yaad rakho|remember that|note that)\b", body, re.I):
        add("remember_fact")
    if re.search(r"\b(calculate|compute|evaluate|solve|kitna hoga)\b", body, re.I):
        add("execute_code")
    if re.search(
            r"\b(analyse|analyze|summ?arise|summ?arize)\b.{0,35}\b(file|document|csv|json|report)\b",
            body, re.I):
        add("analyze_file")
    if not found:
        add(_deterministic_tool(text))
    return found


async def _plan_tool_calls(text: str, personal_system: str, history: List[Dict[str, str]]
                           ) -> Tuple[List[Dict[str, Any]], str, bool]:
    """Skip the routing AI call when the request names exactly one clear tool."""
    detected = _deterministic_tools(text)
    if len(detected) == 1 and not _MULTI_INTENT_HINT.search(text or ""):
        name = detected[0]
        calls = [{
            "id": secrets.token_hex(4),
            "name": name,
            "arguments": _default_args_for(text, name),
        }]
        return calls, "", await _current_tool_mode()
    calls, routed_reply, native = await _select_tools(text, personal_system, history)
    for name in detected:
        if not any(call.get("name") == name for call in calls):
            calls.insert(0, {
                "id": secrets.token_hex(4),
                "name": name,
                "arguments": _default_args_for(text, name),
            })
    return calls, routed_reply, native


def _validate_tool_args(name: str, args: Any) -> Optional[Dict[str, Any]]:
    """Only whitelisted names, whitelisted keys and typed values reach a tool."""
    spec = _TOOL_SCHEMAS.get(name)
    if not spec:
        return None
    properties, required = spec
    source = args if isinstance(args, dict) else {}
    for key in required:
        if source.get(key) in (None, "", [], {}):
            return None
    clean: Dict[str, Any] = {}
    for key, value in source.items():
        if key not in properties or value is None:
            continue
        kind = properties[key].get("type")
        if kind == "string":
            if not isinstance(value, (str, int, float)):
                return None
            clean[key] = str(value)[:4000]
        elif kind == "integer":
            try:
                clean[key] = int(value)
            except (TypeError, ValueError):
                return None
        elif kind == "array":
            if not isinstance(value, list):
                return None
            clean[key] = value[:50]
        elif kind == "boolean":
            clean[key] = str(value).strip().lower() in ("true", "1", "yes", "haan")
        else:
            return None
    return clean if all(key in clean for key in required) else None


def _default_args_for(text: str, tool: str) -> Dict[str, Any]:
    """Deterministic argument extraction used when the model cannot select tools."""
    args: Dict[str, Any] = {}
    if tool in AGENT_TOOL_NAMES:
        args = _agent_args_from_text(text, tool)
    if tool in ("broadcast_groups", "set_group_welcome", "write_work_file") and not args.get(
            "message" if tool != "write_work_file" else "content"):
        key = "content" if tool == "write_work_file" else "message"
        quoted = re.search(r"[\"“'](.{1,400}?)[\"”']", text or "")
        args[key] = (quoted.group(1) if quoted else text).strip()[:400]
    if tool in ("web_research", "web_search", "read_webpage"):
        url = re.search(r"https?://[^\s<>]+", text or "")
        if url:
            args["url"] = url.group(0).rstrip(".,!?;:)\"]'")
        args["query"] = _web_query_from_text(text)
        args["summarize"] = _wants_summary(text) or tool == "read_webpage"
        if tool == "read_webpage":
            args["question"] = args.get("query") or "Summarize this page"
    elif tool == "generate_image":
        quoted = re.search(r"[\"“'](.{4,300}?)[\"”']", text or "")
        args["prompt"] = (quoted.group(1) if quoted else _web_query_from_text(text)) or text[:300]
    elif tool == "execute_code":
        expr = re.search(
            r"\b(?:calculate|compute|evaluate|solve|kitna\s+hoga)\s+(?:this\s+)?(.+)",
            text or "", re.IGNORECASE,
        )
        args["expression"] = (expr.group(1) if expr else text).strip()[:400]
    elif tool == "schedule_message":
        quoted = re.search(r"[\"“'](.{4,400}?)[\"”']", text or "")
        if quoted:
            args["message"] = quoted.group(1)
        else:
            args["message"] = re.sub(
                r"^(?:please\s+)?(?:schedule|remind\s+me|reminder)\b.{0,50}?(?:to\s+)?",
                "", text or "", flags=re.IGNORECASE,
            ).strip()[:300]
        when = re.search(
            r"\b(?:in\s+\d+\s*(?:min(?:ute)?s?|hours?)|tomorrow|kal|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}T[^\s]+)",
            text or "", re.IGNORECASE,
        )
        args["when"] = when.group(0) if when else "in 60 minutes"
    elif tool == "remember_fact":
        fact = re.search(r"\b(?:yaad\s+rakho|remember\s+that|note\s+that)\s*(.+)", text or "", re.I)
        args["fact"] = (fact.group(1) if fact else text).strip()[:300]
    elif tool == "analyze_file":
        args.setdefault("filename", "")
        args["question"] = _web_query_from_text(text)
    return args


def _augment_tool_args(name: str, args: Dict[str, Any], update, is_group: bool,
                       user_id: int) -> Dict[str, Any]:
    """Fill chat-implied arguments before schema validation (never invent content)."""
    local = dict(args or {})
    if name in ("set_group_welcome", "set_group_setting", "delete_group_message") \
            and local.get("group_id") is None and is_group and update is not None:
        local["group_id"] = update.effective_chat.id
    if name == "delete_group_message" and not local.get("message_id") and update is not None \
            and getattr(update.message, "reply_to_message", None):
        local["message_id"] = update.message.reply_to_message.message_id
    if name == "broadcast_groups":
        if not str(local.get("message") or "").strip():
            local.pop("message", None)
        ids = dm.visible_group_ids(user_id)
        if local.get("group_ids") is not None:
            try:
                local["group_ids"] = [int(gid) for gid in local["group_ids"] if int(gid) in ids]
            except (TypeError, ValueError):
                local.pop("group_ids", None)
    return local


async def _current_tool_mode() -> bool:
    """Native tool support from the persisted probe result, probing only if unknown."""
    cfg = dm.get_ai_config()
    key = f"{cfg.get('endpoint', '')}|{cfg.get('model', '')}"
    if key in _NATIVE_TOOL_SUPPORT:
        return _NATIVE_TOOL_SUPPORT[key]
    persisted = str(cfg.get("tool_calling") or "").lower()
    if persisted in ("native", "structured"):
        supported = persisted == "native"
        _NATIVE_TOOL_SUPPORT[key] = supported
        return supported
    return await native_tool_support()


async def native_tool_support() -> bool:
    """Verify once per endpoint/model that the configured provider really calls tools."""
    cfg = dm.get_ai_config()
    key = f"{cfg.get('endpoint', '')}|{cfg.get('model', '')}"
    if key in _NATIVE_TOOL_SUPPORT:
        return _NATIVE_TOOL_SUPPORT[key]
    probe = [{
        "type": "function",
        "function": {
            "name": "probe_ping",
            "description": "Return a ping value. Used once to verify tool calling.",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        },
    }]
    supported = False
    try:
        response = await call_custom_openai(
            prompt="Call the probe_ping tool with value 'ping' now. Do not answer in plain text.",
            system_instruction="Use the available tool whenever the user asks you to call it.",
            tools=probe,
        )
        supported = any(
            str(call.get("name")) == "probe_ping"
            for call in (getattr(response, "tool_calls", None) or [])
        )
    except Exception as e:
        print(f"⚠️ Tool-calling probe unavailable: {str(e)[:160]}", flush=True)
    _NATIVE_TOOL_SUPPORT[key] = supported
    try:
        dm.data.setdefault("ai_config", {})["tool_calling"] = "native" if supported else "structured"
        dm.save()
    except Exception:
        pass
    print(f"🧰 Tool mode for {cfg.get('model')}: "
          f"{'native tool calls' if supported else 'safe structured routing'}", flush=True)
    return supported


def _parse_structured_tools(text: str) -> Tuple[List[Dict[str, Any]], str]:
    """Parse the fallback JSON envelope. Unknown tools or bad types are discarded."""
    raw = (text or "").strip()
    if not raw:
        return [], ""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else ""
    if not candidate:
        start = raw.find("{")
        if start < 0:
            return [], final_chat_text(raw)
        depth = 0
        end = None
        for index in range(start, len(raw)):
            if raw[index] == "{":
                depth += 1
            elif raw[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        candidate = raw[start:end] if end else ""
    try:
        envelope = json.loads(candidate)
    except (TypeError, ValueError):
        return [], final_chat_text(raw)
    if not isinstance(envelope, dict):
        return [], final_chat_text(raw)
    calls: List[Dict[str, Any]] = []
    for item in envelope.get("tools") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        arguments = _validate_tool_args(name, item.get("arguments"))
        if arguments is not None:
            calls.append({"id": secrets.token_hex(4), "name": name, "arguments": arguments})
    reply = str(envelope.get("reply") or "")[:2000]
    return calls[:_MAX_TOOLS_PER_TURN], reply


_ROUTING_CONTRACT = (
    "Tool routing (internal instruction, never mention it to the user): "
    "Reply with ONLY a JSON object: "
    '{"tools":[{"name":"tool_name","arguments":{...}}],"reply":"natural reply if no tool is needed"}. '
    "Allowed tools: " + ", ".join(sorted(AGENT_TOOL_NAMES)) + ". "
    "Use tools only when the request truly needs one. Never invent tool results. "
    "Never put commands, shell text, code, or unlisted tool names in the JSON."
)


async def _select_tools(text: str, personal_system: str, history: List[Dict[str, str]]
                        ) -> Tuple[List[Dict[str, Any]], str, bool]:
    """Return (validated calls, direct reply, native_mode). Persona stays untouched."""
    # Routing only needs the latest request plus a little context, not the whole
    # persona and 24 prior turns. The final answer still gets the full prompt.
    routing_history = (history or [])[-4:]
    if await _current_tool_mode():
        try:
            response = await call_custom_openai(
                prompt=text,
                system_instruction=personal_system,
                history=routing_history,
                tools=AGENT_TOOLS,
                tool_choice="auto",
            )
            calls = []
            for call in (getattr(response, "tool_calls", None) or []):
                arguments = _validate_tool_args(call.get("name"), call.get("arguments"))
                if arguments is not None:
                    calls.append({
                        "id": str(call.get("id") or secrets.token_hex(4)),
                        "name": str(call.get("name")),
                        "arguments": arguments,
                    })
            return calls[:_MAX_TOOLS_PER_TURN], "", True
        except Exception as e:
            print(f"⚠️ Native tool selection failed: {str(e)[:160]}", flush=True)
            return [], "", True
    try:
        response = await call_custom_openai(
            prompt=text + "\n\n" + _ROUTING_CONTRACT,
            system_instruction=personal_system,
            history=routing_history,
        )
        calls, reply = _parse_structured_tools(response.text if response else "")
        return calls, reply, False
    except Exception as e:
        print(f"⚠️ Structured tool routing failed: {str(e)[:160]}", flush=True)
        return [], "", False


def _safe_math_eval(node, env: Dict[str, Any]):
    """Evaluate arithmetic only. No attribute access, imports, calls to unknown names."""
    if isinstance(node, (ast.Expression, ast.Expr)):
        return _safe_math_eval(node.value, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in ("pi", "e") and hasattr(math, node.id):
            return getattr(math, node.id)
        raise ValueError("name blocked")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _safe_math_eval(node.operand, env)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
        left = _safe_math_eval(node.left, env)
        right = _safe_math_eval(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        return left ** right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id
        allowed = {
            "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
            "len": len, "int": int, "float": float, "pow": pow,
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "log": math.log, "log10": math.log10, "exp": math.exp,
            "floor": math.floor, "ceil": math.ceil,
        }
        function = allowed.get(name)
        if function is None:
            raise ValueError("function blocked")
        return function(*[_safe_math_eval(arg, env) for arg in node.args])
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_safe_math_eval(item, env) for item in node.elts]
    raise ValueError("expression blocked")


async def _tool_execute_code(args: Dict[str, Any]) -> str:
    code = str(args.get("expression") or args.get("code") or "").strip()[:1500]
    if not code:
        return "Calculate karna ho to expression batayein."
    env: Dict[str, Any] = {}
    output: List[str] = []
    try:
        tree = ast.parse(code, mode="exec")
        if len(tree.body) > 20:
            return "⚠️ Itne steps nahi chalati. Chhota expression dein."
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1 \
                    and isinstance(statement.targets[0], ast.Name):
                env[statement.targets[0].id] = _safe_math_eval(statement.value, env)
            elif isinstance(statement, ast.Expr):
                output.append(str(_safe_math_eval(statement, env)))
            else:
                return ("⚠️ Sirf simple calculations allowed hain. "
                        "Import, file, network, shell aur arbitrary code block hain.")
        return "🧮 " + ("\n".join(output) if output else "Expression chal gaya (result store ho gaya).")
    except Exception as e:
        return f"⚠️ Safe calculator ne ye expression block kiya: {str(e)[:120]}"


async def _tool_generate_image(args: Dict[str, Any], chat_id: Optional[int], bot_obj) -> str:
    prompt = str(args.get("prompt") or "").strip()[:1000]
    if not prompt:
        return "Image banane ke liye description batayein."
    cfg = dm.get_ai_config()
    base = os.environ.get("ISHANI_IMAGE_ENDPOINT", "").strip().rstrip("/")
    if not base:
        base = _openai_chat_url(str(cfg.get("endpoint") or "")).rsplit("/chat/completions", 1)[0].rstrip("/")
    api_key = os.environ.get("ISHANI_IMAGE_KEY", "").strip() or str(cfg.get("api_key") or "")
    model = os.environ.get("ISHANI_IMAGE_MODEL", "").strip() or "gpt-image-1"
    if not base or _is_masked_key(api_key):
        return "❌ Image API configured nahi hai. Endpoint/API key set kiye bina main image nahi bana sakti."
    target = _safe_work_path(f"ishani_image_{int(datetime.now().timestamp())}.png")
    if not target:
        return "❌ Image save karne ka safe path nahi mila."
    try:
        async with httpx.AsyncClient(timeout=120) as http:
            response = await http.post(
                base + "/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"},
            )
            if response.status_code >= 400:
                detail = response.text[:200]
                return f"❌ Image API error {response.status_code}: {detail}"
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            item = ((data.get("data") or [{}])[0] if isinstance(data, dict) else {})
            encoded = item.get("b64_json") if isinstance(item, dict) else None
            remote = item.get("url") if isinstance(item, dict) else None
            if encoded:
                target.write_bytes(base64.b64decode(encoded))
            elif remote and _public_http_url(str(remote)):
                fetched = await http.get(str(remote))
                if fetched.status_code >= 400:
                    return f"❌ Image download fail hua ({fetched.status_code})."
                target.write_bytes(fetched.content)
            else:
                return "❌ Image API ne koi image return nahi ki; kuch claim nahi kar raha."
        if not target.exists() or target.stat().st_size < 100:
            return "❌ Image verify nahi ho payi."
        if bot_obj and chat_id and hasattr(bot_obj, "send_photo"):
            try:
                with target.open("rb") as photo:
                    await bot_obj.send_photo(chat_id=chat_id, photo=photo,
                                             caption="Yeh rahi image jo mainne banayi 🌸")
            except Exception as e:
                return f"✅ Image save ho gayi: {target} (bhejne me dikkat: {str(e)[:120]})"
        return f"✅ Image ban gayi: {target}"
    except Exception as e:
        return f"❌ Image generate nahi ho payi: {str(e)[:160]}"


def _parse_when(value: Any, now: Optional[datetime] = None) -> Optional[datetime]:
    now = now or datetime.now()
    raw = str(value or "").strip()
    match = re.search(r"(?:in|after)\s+(\d+)\s*(minute|minutes|min|hour|hours|ghante?|ghanta)",
                      raw, re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        delta = timedelta(hours=amount) if "hour" in unit or "ghant" in unit else timedelta(minutes=amount)
        return now + delta
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        pass
    if re.fullmatch(r"\d{1,2}:\d{2}", raw):
        hour, minute = (int(part) for part in raw.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target if target > now else target + timedelta(days=1)
    if re.search(r"\b(tomorrow|kal)\b", raw, re.IGNORECASE):
        clock = re.search(r"(\d{1,2}):(\d{2})", raw)
        hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (9, 0)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return None


async def _tool_schedule_message(args: Dict[str, Any], user_id: int, first_name: str,
                                 chat_id: Optional[int]) -> str:
    message = str(args.get("message") or "").strip()[:1000]
    if not message:
        return "Schedule karne ke liye message batayein."
    due = _parse_when(args.get("when"))
    if due is None or due <= datetime.now():
        return "Time samajh nahi aaya. Jaise 'in 30 minutes', 'tomorrow 9:30' ya '18:00' likhein."
    jobs = dm.data.setdefault("scheduled_jobs", [])
    if not isinstance(jobs, list):
        jobs = dm.data["scheduled_jobs"] = []
    job = {
        "id": secrets.token_hex(4),
        "actor_id": int(user_id),
        "message": message,
        "due_at": due.isoformat(timespec="seconds"),
        "group_id": args.get("group_id"),
        "chat_id": chat_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sent": False,
    }
    jobs.append(job)
    dm.audit("scheduled_message_created", user_id, job["id"], f"due={job['due_at']}")
    dm.save()
    target = f"group {job['group_id']}" if job["group_id"] else "is chat"
    return f"✅ Schedule ho gaya: “{message[:120]}” {target} ke liye {due.strftime('%d %b %H:%M')} par."


async def _scheduled_job_ticker(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send due scheduled messages created through the scheduling tool."""
    jobs = dm.data.get("scheduled_jobs")
    if not isinstance(jobs, list) or not jobs:
        return
    now = datetime.now()
    changed = False
    for job in jobs:
        if not isinstance(job, dict) or job.get("sent"):
            continue
        try:
            due = datetime.fromisoformat(str(job.get("due_at") or ""))
            if due.tzinfo:
                due = due.astimezone().replace(tzinfo=None)
        except (TypeError, ValueError):
            job["sent"] = True
            job["status"] = "invalid_time"
            changed = True
            continue
        if due > now:
            continue
        job["sent"] = True
        changed = True
        try:
            if job.get("group_id") and not dm.is_group_owner(job.get("actor_id"), job["group_id"]):
                job["status"] = "unauthorized"
                continue
            target = int(job.get("group_id") or job.get("chat_id") or job.get("actor_id"))
            await context.bot.send_message(chat_id=target, text=str(job.get("message") or "")[:3000])
            job["status"] = "sent"
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)[:200]
    if changed:
        dm.save()


async def _tool_remember(args: Dict[str, Any], user_id: int, first_name: str) -> str:
    fact = str(args.get("fact") or "").strip()[:300]
    if not fact:
        return "Yaad rakhne ke liye kuch batayein."
    record = dm.load_chat(user_id, first_name)
    memory = record.setdefault("memory", {})
    facts = [item for item in (memory.get("facts") or []) if isinstance(item, str)]
    if fact not in facts:
        facts.append(fact)
    memory["facts"] = facts[-20:]
    dm.save_chat(record)
    saved = fact in ((dm.load_chat(user_id, first_name).get("memory") or {}).get("facts") or [])
    return f"✅ Yaad rakha: {fact}" if saved else "❌ Save verify nahi hua."


async def _tool_recall(user_id: int, first_name: str) -> str:
    memory = dm.load_chat(user_id, first_name).get("memory") or {}
    facts = [item for item in (memory.get("facts") or []) if isinstance(item, str)]
    topics = [item for item in (memory.get("topics") or []) if isinstance(item, str)]
    lines = ["🧠 Mere paas ye hai:"]
    lines.append(f"• Naam: {memory.get('preferred_name') or first_name}")
    if memory.get("about"):
        lines.append(f"• Baare me: {str(memory['about'])[:200]}")
    if facts:
        lines.append("• Yaad kiye gaye points: " + "; ".join(facts[-8:]))
    if topics:
        lines.append("• Recent topics: " + "; ".join(topics[-5:]))
    if len(lines) == 1:
        lines.append("• Abhi khas kuch save nahi hai.")
    return "\n".join(lines)


async def _execute_one_tool(name: str, args: Dict[str, Any], text: str, user_id: int,
                            first_name: str, update, context, chat_scope: str) -> str:
    """Dispatch one validated tool. Never receives raw model text as a command."""
    bot_obj = getattr(context, "bot", None) if context is not None else None
    chat_id = int(update.effective_chat.id) if update is not None and update.effective_chat else None
    if name == "list_groups_admin_status":
        return await _tool_group_admin_status(user_id)
    if name in ("web_research", "web_search", "read_webpage"):
        local = dict(args)
        if name == "read_webpage":
            local["summarize"] = True
            if not local.get("query"):
                local["query"] = str(local.get("question") or f"Summarize {local.get('url', '')}")
        elif not local.get("query"):
            local["query"] = _web_query_from_text(text)
        return await _tool_web_research(local, user_id)
    if name == "generate_python_script":
        return await _tool_generate_script(args)
    if name == "read_work_file":
        return await _tool_read_file(args)
    if name == "write_work_file":
        content = str(args.get("content") or args.get("message") or "").strip()
        target = _unique_work_path(str(args.get("filename") or "ishani_note.txt"))
        if not target or not content:
            return "Filename aur content dono chahiye."
        target.write_text(content, encoding="utf-8")
        return f"✅ File saved and verified: {target}" if target.exists() else "❌ File save verify nahi hua."
    if name in ("report_from_document", "analyze_file"):
        return await _tool_report_document(args)
    if name == "set_group_welcome":
        return await _tool_set_welcome(user_id, args, update.effective_chat if update else None)
    if name == "generate_image":
        return await _tool_generate_image(args, chat_id, bot_obj)
    if name == "execute_code":
        return await _tool_execute_code(args)
    if name == "schedule_message":
        return await _tool_schedule_message(args, user_id, first_name, chat_id)
    if name == "remember_fact":
        return await _tool_remember(args, user_id, first_name)
    if name == "recall_memory":
        return await _tool_recall(user_id, first_name)
    return "❌ Ye tool ab supported nahi hai; kuch change nahi hua."


async def _emit_activity(update, lines: List[str]) -> None:
    if update is None or not getattr(update, "effective_message", None):
        return
    text = "\n".join(line for line in lines if line)[:3000]
    if not text:
        return
    try:
        await update.effective_message.reply_text(text)
    except Exception as e:
        print(f"⚠️ Tool activity message fail: {e}", flush=True)


async def _finalize_with_results(text: str, personal_system: str, history: List[Dict[str, str]],
                                 calls: List[Dict[str, Any]], results: List[str], native: bool
                                 ) -> Tuple[str, bool]:
    """Feed verified results back into the SAME conversation for a natural final answer."""
    evidence = []
    for call, result in zip(calls, results):
        if result is None:
            continue
        label = _TOOL_LABELS.get(call["name"], call["name"])
        evidence.append(f"[{label}] {re.sub(r'<[^>]+>', '', str(result))[:900]}")
    block = "\n\n".join(evidence) or "Tool ne koi result return nahi kiya."
    if native:
        extra: List[Dict[str, Any]] = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": str(call.get("id") or f"call_{index}"),
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                },
            } for index, call in enumerate(calls)],
        }]
        for call, result in zip(calls, results):
            extra.append({
                "role": "tool",
                "tool_call_id": str(call.get("id") or ""),
                "content": str(result or "no result")[:1400],
            })
    else:
        extra = [{"role": "user", "content": "Verified tool results:\n" + block}]
    final_prompt = (
        f"{text}\n\n(Tool results already fetched are above. Use them to answer me naturally "
        "in your own style; do not invent anything extra.)"
    )
    try:
        response = await call_custom_openai(
            prompt=final_prompt,
            system_instruction=personal_system,
            history=history,
            extra_messages=extra,
        )
        reply = clean_reply_text(getattr(response, "text", "") or "")
        if reply:
            return apply_admin_link_controls(reply), True
    except Exception as e:
        print(f"⚠️ Final tool answer failed: {str(e)[:160]}", flush=True)
    return apply_admin_link_controls(block), False


async def _deliver_reply(user_text: str, user_id: int, first_name: str, update, context,
                         reply: str, chat_scope: str, is_group: bool, fraud_dm: bool = False) -> None:
    """One delivery path for normal chat AND tool-backed answers (persona shaping intact)."""
    reply = apply_admin_link_controls(clean_reply_text(reply or ""))
    if not reply and ((load_persona().get("admin_learning_controls") or {}).get("block_all_links")
                      or (load_persona().get("admin_learning_controls") or {}).get("blocked_links")):
        reply = user_language_notice(
            user_text, "I can explain it here without sharing a link.",
            "Link ke bina yahin samjha deti hoon 🙂",
            "लिंक के बिना मैं यहीं समझा देती हूँ 🙂",
        )
    if not reply:
        reply = user_language_notice(
            user_text, "Sorry, I didn't quite catch that. Could you say it another way?",
            "Sorry yaar, main samajh nahi paayi 😅 Ek baar aur bataoge?",
            "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई 😅 एक बार फिर बताएँगे?",
        )
    bubbles = _shape_reply(reply, is_group, max_lines=3 if fraud_dm else 2)
    if is_group and not get_lead_state(user_id, first_name).get("dm_nudged"):
        nudge = "Yahan bheed hai, mujhe DM kar de — aaram se baat karte hain."
        if bubbles:
            bubbles[0] = (bubbles[0] + " " + nudge)[:1000]
        else:
            bubbles = [nudge]
        update_lead_state(user_id, "", first_name, flags={"dm_nudged": True})
    target = update.effective_message if getattr(update, "effective_message", None) else update.message
    for bubble in bubbles:
        await _send_paced(target, bubble)
    dm.append_chat(user_id, first_name, "bot", " | ".join(bubbles), scope=chat_scope)


async def _finalize_approved(token: str, result: str, context) -> None:
    """After approval/denial, return the outcome to the same AI conversation."""
    saved = _PENDING_TOOL_CONTEXT.pop(token, None)
    if not saved:
        return
    calls = list(saved.get("calls") or [])
    results = list(saved.get("results") or [])
    tool = str(saved.get("tool") or "")
    replaced = False
    for index, call in enumerate(calls):
        if index < len(results) and results[index] is None and call.get("name") == tool:
            results[index] = result
            replaced = True
            break
    if not replaced:
        calls.append({"id": secrets.token_hex(4), "name": tool, "arguments": {}})
        results.append(result)
    reply, ai_ok = await _finalize_with_results(
        str(saved.get("text") or ""), str(saved.get("system") or ""),
        list(saved.get("history") or []), calls, results, bool(saved.get("native")),
    )
    if not ai_ok:
        return  # The verified result was already shown in the approval message.
    bot_obj = getattr(context, "bot", None)
    chat_id = saved.get("chat_id")
    if not bot_obj or not chat_id:
        return
    try:
        await bot_obj.send_message(chat_id=int(chat_id), text=reply[:3500])
        dm.append_chat(int(saved.get("user_id") or 0), str(saved.get("first_name") or "User"),
                       "bot", reply[:1500], scope=str(saved.get("chat_scope") or "private"))
    except Exception as e:
        print(f"⚠️ Approved-tool final reply failed: {e}", flush=True)


async def _run_tool_turn(update, context, text: str, user_id: int, first_name: str,
                         chat_scope: str, personal_system: str,
                         history: List[Dict[str, str]]) -> bool:
    """AI selects whitelisted tools -> bot executes -> results return to AI -> final reply."""
    is_group = bool(update is not None and update.effective_chat
                    and update.effective_chat.type in ("group", "supergroup"))
    dm.append_chat(user_id, first_name, "user", text, scope=chat_scope)

    calls, routed_reply, native = await _plan_tool_calls(text, personal_system, history)
    for call in calls:
        call["arguments"] = _augment_tool_args(
            str(call.get("name") or ""), dict(call.get("arguments") or {}), update, is_group, user_id,
        )
    calls = [call for call in calls if _validate_tool_args(call.get("name"), call.get("arguments")) is not None]
    if not calls:
        if routed_reply:
            await _deliver_reply(text, user_id, first_name, update, context,
                                 routed_reply, chat_scope, is_group)
            return True
        return False

    labels = [_TOOL_LABELS.get(call["name"], call["name"]) for call in calls]
    await _emit_activity(update, [f"🛠️ Ishani tool use: {', '.join(labels)}"])
    results: List[Any] = [None] * len(calls)
    pending_token = ""
    for index, call in enumerate(calls):
        name = str(call["name"])
        args = dict(call.get("arguments") or {})
        if name in _APPROVAL_TOOLS:
            if update is None or not actor_may_authorize(
                    user_id, update.effective_chat if update else None):
                results[index] = "❌ Ye action sirf master admin ya apne group ke owner kar sakte hain. Kuch nahi hua."
                dm.audit("blocked_agent_request", user_id, name, text[:160])
                continue
            if name == "set_group_setting" and args.get("group_id") is None and is_group:
                args["group_id"] = update.effective_chat.id
            if name == "delete_group_message" and args.get("group_id") is None and is_group:
                args["group_id"] = update.effective_chat.id
            if name == "delete_group_message" and not args.get("message_id") \
                    and getattr(update.message, "reply_to_message", None):
                args["message_id"] = update.message.reply_to_message.message_id
            if name == "broadcast_groups":
                allowed = [gid for gid in (args.get("group_ids") or dm.visible_group_ids(user_id))
                           if gid in dm.visible_group_ids(user_id)]
                if not allowed or not str(args.get("message") or "").strip():
                    results[index] = "❌ Broadcast ke liye message ya authorized group nahi mila. Kuch nahi bheja gaya."
                    continue
                args["group_ids"] = allowed
                description = f"Broadcast to {len(allowed)} group(s): {str(args['message'])[:160]}"
            else:
                description = f"{name}: {str(args)[:220]}"
            pending_token = _queue_approval(user_id, int(update.effective_chat.id), name, args, description)
            _PENDING_TOOL_CONTEXT[pending_token] = {
                "text": text,
                "system": personal_system,
                "history": list(history),
                "calls": calls,
                "results": results,
                "native": native,
                "tool": name,
                "user_id": user_id,
                "first_name": first_name,
                "chat_scope": chat_scope,
                "chat_id": int(update.effective_chat.id),
            }
            await _ask_approval(update, context, pending_token, name, description)
            results[index] = "⏳ Approval pending"
            continue
        try:
            result = await _execute_one_tool(name, args, text, user_id, first_name,
                                             update, context, chat_scope)
        except Exception as e:
            result = f"❌ Task complete nahi hua: {str(e)[:200]}"
        results[index] = str(result)[:4000]
        dm.audit("tool_executed", user_id, name, str(result)[:250])

    if pending_token:
        await _emit_activity(update, [
            f"🛠️ Tools: {', '.join(labels)}",
            "⏳ Sensitive action approval ke liye rokha gaya hai. Approve hone par main result ke saath baat karungi.",
        ])
        dm.append_chat(user_id, first_name, "bot",
                       f"🛠️ Tool activity: {', '.join(labels)} — approval pending", scope=chat_scope)
        return True

    summary = [f"🛠️ Tools: {', '.join(labels)}"]
    for call, result in zip(calls, results):
        label = _TOOL_LABELS.get(call["name"], call["name"])
        short = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(result or "")))[:160]
        mark = "⚠️" if str(result or "").lstrip().startswith(("❌", "⚠️")) else "✅"
        summary.append(f"{mark} {label}: {short}")
    await _emit_activity(update, summary)
    dm.append_chat(user_id, first_name, "bot", "🛠️ " + " | ".join(summary[:4])[:700], scope=chat_scope)

    reply, _ = await _finalize_with_results(text, personal_system, history, calls, results, native)
    await _deliver_reply(text, user_id, first_name, update, context, reply, chat_scope, is_group)
    return True


async def _run_tool_turn_headless(
    text: str, user_id: int, first_name: str, chat_scope: str,
    personal_system: str, history: List[Dict[str, str]],
    confirmed: bool = False, group_id: Optional[int] = None,
) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
    """
    Dashboard variant of the unified tool loop (no Telegram update object).

    Same persona, same whitelist, same verified-result feedback. Sensitive tools
    use the dashboard's confirm:true flow instead of Telegram inline approval.

    Returns (reply, activity_lines, confirmation_request). History is written
    by the caller so nothing gets appended twice.
    """
    calls, routed_reply, native = await _plan_tool_calls(text, personal_system, history)
    for call in calls:
        name = str(call.get("name") or "")
        args = _augment_tool_args(
            name, dict(call.get("arguments") or {}), None, group_id is not None, user_id,
        )
        if group_id is not None:
            if name in ("set_group_welcome", "set_group_setting", "delete_group_message") \
                    and args.get("group_id") is None:
                args["group_id"] = int(group_id)
            if name == "broadcast_groups" and not args.get("group_ids"):
                args["group_ids"] = [int(group_id)]
        call["arguments"] = args
    calls = [
        call for call in calls
        if _validate_tool_args(str(call.get("name") or ""), call.get("arguments")) is not None
    ]
    if not calls:
        return routed_reply or "", [], None

    labels = [_TOOL_LABELS.get(call["name"], call["name"]) for call in calls]
    activity: List[str] = [f"🛠️ Ishani tool use: {', '.join(labels)}"]

    if any(call["name"] in _APPROVAL_TOOLS for call in calls) and not confirmed:
        proposed = {
            "type": "confirmed_tool",
            "tools": [{"name": call["name"], "arguments": call["arguments"]} for call in calls],
        }
        activity.append("⏳ Sensitive action — confirmation required")
        return (
            "Ye action sensitive hai (broadcast / message delete / group setting). "
            "Confirm & execute dabayein — tabhi chalega, abhi kuch nahi hua.",
            activity,
            {"requires_confirmation": True, "proposed_action": proposed},
        )

    bot_obj = getattr(BOT_APP, "bot", None) if BOT_APP else None
    results: List[str] = []
    for call in calls:
        name = str(call["name"])
        args = dict(call.get("arguments") or {})
        try:
            if name in _APPROVAL_TOOLS:
                if not actor_may_authorize(user_id, None):
                    result = "❌ Ye action sirf master admin ya group owner kar sakte hain. Kuch nahi hua."
                    dm.audit("blocked_web_tool", user_id, name, "unauthorized")
                else:
                    description = f"web: {name}: {str(args)[:200]}"
                    token = _queue_approval(user_id, int(group_id or 0), name, args, description)
                    result = await _execute_approved_tool(token, user_id, bot_obj)
                    pending = dm.data.get("pending_tools") or {}
                    if isinstance(pending, dict):
                        pending.pop(token, None)
                    dm.save()
            else:
                result = await _execute_one_tool(
                    name, args, text, user_id, first_name, None, None, chat_scope,
                )
        except Exception as e:
            result = f"❌ Task complete nahi hua: {str(e)[:200]}"
        results.append(str(result)[:4000])
        dm.audit("web_tool_executed", user_id, name, str(result)[:250])

    for call, result in zip(calls, results):
        label = _TOOL_LABELS.get(call["name"], call["name"])
        short = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(result or "")))[:160]
        mark = "⚠️" if str(result or "").lstrip().startswith(("❌", "⚠️")) else "✅"
        activity.append(f"{mark} {label}: {short}")

    reply, _ = await _finalize_with_results(text, personal_system, history, calls, results, native)
    return reply, activity, None


def _queue_approval(actor_id: int, chat_id: int, tool: str, args: Dict[str, Any], description: str) -> str:
    pending = dm.data.setdefault("pending_tools", {})
    if not isinstance(pending, dict):
        pending = dm.data["pending_tools"] = {}
    token = secrets.token_hex(5)
    pending[token] = {
        "actor_id": int(actor_id),
        "chat_id": int(chat_id),
        "tool": tool,
        "args": args,
        "description": description[:400],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    dm.audit("tool_approval_requested", actor_id, tool, description[:200])
    return token


async def _ask_approval(update, context, token: str, tool: str, description: str):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"tool_approve_{token}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"tool_deny_{token}"),
    ]])
    await update.effective_message.reply_text(
        f"⚠️ <b>Approval required</b>\n{description}\n\nApproval ID: <code>{token}</code>\n"
        "Sirf requested actor ya master admin approve kar sakte hain. Kuch abhi execute nahi hua.",
        parse_mode="HTML", reply_markup=keyboard,
    )


async def _execute_approved_tool(token: str, actor_id: int, bot_obj) -> str:
    pending = dm.data.get("pending_tools") or {}
    record = pending.get(token) if isinstance(pending, dict) else None
    if not isinstance(record, dict):
        return "❌ Approval request expire ho gaya ya pehle use ho chuka hai."
    tool = record.get("tool")
    args = dict(record.get("args") or {})
    if tool == "broadcast_groups":
        ids = dm.visible_group_ids(actor_id)
        requested = args.get("group_ids") or ids
        try:
            requested = [int(x) for x in requested]
        except (TypeError, ValueError):
            return "❌ Group list invalid tha; kuch bheja nahi gaya."
        outside = [gid for gid in requested if gid not in ids]
        if outside:
            return "❌ Scope violation: unauthorized groups detected; kuch nahi bheja gaya."
        if not requested:
            return "❌ Koi authorized group nahi tha; kuch nahi bheja gaya."
        return await _agent_broadcast(bot_obj, actor_id, requested, str(args.get("message") or ""))
    if tool == "set_group_setting":
        try:
            group_id = int(args.get("group_id"))
        except (TypeError, ValueError):
            return "❌ Group ID invalid."
        if not dm.is_group_owner(actor_id, group_id):
            return "❌ Aap is group ki setting change nahi kar sakte."
        key = str(args.get("key") or "")
        if key not in ("links_allowed", "bot_muted", "group_mode"):
            return "❌ Sirf links_allowed, bot_muted ya group_mode change ho sakte hain."
        if not dm.set_group_details(actor_id, ADMIN_ID, group_id, key, args.get("value", "")):
            return "❌ Setting save nahi hui."
        current = dm.get_group_settings(group_id).get(key)
        return f"✅ Verified: group {group_id} me {key} = {current}."
    if tool == "delete_group_message":
        try:
            group_id, message_id = int(args.get("group_id")), int(args.get("message_id"))
        except (TypeError, ValueError):
            return "❌ Group ya message ID invalid."
        if not dm.is_group_owner(actor_id, group_id):
            return "❌ Aap is group ka message delete nahi kar sakte."
        try:
            await bot_obj.delete_message(chat_id=group_id, message_id=message_id)
        except Exception as e:
            if "not found" not in str(e).lower():
                return f"❌ Delete fail hua: {e}"
        try:
            await bot_obj.forward_message(chat_id=actor_id, from_chat_id=group_id, message_id=message_id)
            return f"❌ Verification fail: message {message_id} abhi bhi maujood hai."
        except Exception as e:
            gone = "not found" in str(e).lower() or "deleted" in str(e).lower()
            return (f"✅ Verified: message {message_id} delete ho gaya."
                    if gone else f"⚠️ Delete attempt kiya, par verify nahi ho paya: {e}")
    return "❌ Ye approved tool ab supported nahi hai; kuch change nahi hua."


async def tool_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    parts = (query.data or "").split("_", 2)
    if len(parts) != 3 or parts[0] != "tool":
        return
    action, token = parts[1], parts[2]
    pending = dm.data.get("pending_tools") or {}
    record = pending.get(token) if isinstance(pending, dict) else None
    if not isinstance(record, dict):
        await query.edit_message_text("❌ Ye approval request expire ho gaya.")
        return
    if query.from_user.id not in (record.get("actor_id"), ADMIN_ID):
        dm.audit("tool_approval_denied", query.from_user.id, token, "unauthorized approver")
        await query.edit_message_text("❌ Sirf requested actor ya master admin approve kar sakte hain.")
        return
    if action == "deny":
        pending.pop(token, None)
        dm.audit("tool_approval_denied", query.from_user.id, str(record.get("tool")), "user denied")
        await query.edit_message_text("✅ Request denied. Kuch execute nahi hua.")
        await _finalize_approved(token, "✅ Request denied. Kuch execute nahi hua.", context)
        return
    result = await _execute_approved_tool(token, record.get("actor_id"), context.bot)
    pending.pop(token, None)
    dm.audit("tool_approved_executed", query.from_user.id, str(record.get("tool")), result[:300])
    await query.edit_message_text(result[:1200])
    await _finalize_approved(token, result, context)


async def handle_agent_request(update, context, text: str, user_id: int, first_name: str,
                               chat_scope: str) -> bool:
    """One assistant: intent -> whitelisted tools -> results -> same persona, same chat."""
    if not _deterministic_tool(text):
        return False
    is_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    history = dm.recent_chat(user_id, first_name, limit=40, scope=chat_scope)
    personal_system = build_personal_system(
        user_id, first_name, history, compact=False,
        group_business=dm.get_group_business(update.effective_chat.id) if is_group else {},
        include_company=bool(re.search(
            r"\b(chelsea|company|join|signup|sign up|link|earning|profit|deposit|withdraw|prediction|app)\b",
            text, re.I,
        )),
    )
    return await _run_tool_turn(update, context, text, user_id, first_name, chat_scope,
                                personal_system, history)


_LINK_ONLY_RE = re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE)
_buf: Dict[int, List[str]] = {}
_tasks: Dict[int, asyncio.Task] = {}
DEBOUNCE_SEC = 8
_last_send = 0.0


async def should_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """One gate for every text message: DMs get answers, groups stay human-quiet."""
    msg = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat:
        return False
    text = (msg.text or "").strip()
    if not text or user.is_bot:
        return False
    if getattr(msg, "sticker", None) or _LINK_ONLY_RE.match(text):
        return False
    norm = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if norm in ACKNOWLEDGMENT_WORDS or norm in CHAT_ENDING_WORDS:
        return False
    if chat.type not in ("group", "supergroup"):
        return True

    bot = context.bot
    username = getattr(bot, "username", None)
    if username and re.search(rf"@{re.escape(username)}\b", text, re.IGNORECASE):
        return True
    replied = msg.reply_to_message
    if replied and getattr(replied, "from_user", None) and replied.from_user.id == getattr(bot, "id", None):
        return True
    if user.id == ADMIN_ID or await _is_group_admin(chat, user.id):
        return False

    mode = GROUP_MODE
    override = str(dm.get_group_settings(chat.id).get("group_mode") or "").lower()
    if override in ("all", "mentions"):
        mode = override
    return mode == "all"


async def _send_paced(msg, text: str) -> None:
    """Keep a gap between sends so a fast lead cannot trip Telegram's flood limit."""
    global _last_send
    wait = _last_send + 1.2 - _time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    await msg.reply_text(text)
    _last_send = _time.monotonic()


def _shape_reply(reply: str, is_group: bool, max_lines: int = 2) -> List[str]:
    """Groups: one short bubble. DMs: at most two lines (three for a fraud counter)."""
    lines = [line.strip() for line in (reply or "").splitlines() if line.strip()]
    if is_group:
        return [lines[0][:600]] if lines else []
    return [line[:1000] for line in lines[:max_lines]]


async def _answer(user_text: str, user_id: int, first_name: str, update, context) -> None:
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ("group", "supergroup"))
    chat_scope = f"group:{chat.id}" if is_group else "private"
    fraud_dm = bool(not is_group and _FRAUD.search(user_text))

    history = dm.recent_chat(user_id, first_name, limit=40, scope=chat_scope)
    dm.append_chat(user_id, first_name, "user", user_text, scope=chat_scope)

    has_media_type = bool(re.search(
        r"\b(pdf|document|file|brochure|guide|details?|photo|picture|image|poster|form|attachment)\b|"
        r"(pdf|brochure|tasveer|chitra)", user_text, re.IGNORECASE
    ))
    media_request = has_media_type and bool(re.search(
        r"\b(send|share|show|give|get|need|want|upload|forward|provide|bhejo|bhej|dikhao|chahiye|please|plz)\b",
        user_text, re.IGNORECASE
    ))
    if media_request:
        asset = find_media_asset(user_text)
        if asset:
            await send_media_asset(context.bot, chat.id, asset)
            dm.append_chat(user_id, first_name, "bot",
                           f"Sent file: {asset.get('name') or asset.get('kind', 'file')}", scope=chat_scope)
            return

    keyword_reply = None if fraud_dm else get_keyword_response(user_text)
    if keyword_reply:
        reply = apply_admin_link_controls(clean_reply_text(keyword_reply))
        if reply:
            for bubble in _shape_reply(reply, is_group):
                await _send_paced(update.message, bubble)
            dm.append_chat(user_id, first_name, "bot", reply, scope=chat_scope)
            return

    group_business: Dict[str, Any] = {}
    group_settings: Dict[str, Any] = {}
    if is_group:
        group_business = dm.get_group_business(chat.id)
        group_settings = dm.get_group_settings(chat.id)

    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    personal_system = build_personal_system(
        user_id,
        first_name,
        history,
        compact=False,
        group_business=group_business,
        include_company=bool(re.search(
            r"\b(chelsea|company|join|signup|sign up|link|earning|profit|deposit|withdraw|prediction|app)\b",
            user_text, re.I,
        )),
    )
    if has_media_type:
        personal_system += "\nIf the user asks for a file that is not among the files actually sent in this chat, say it is not available yet and suggest asking the admin. Never claim you attached or sent a file unless the bot actually sent it."
    if group_settings.get("links_allowed") is False:
        personal_system += "\nLinks are not permitted in this group. Explain without sharing any link."
    if fraud_dm:
        personal_system += (
            "\nFRAUD OBJECTION IN DM: answer in at most 3 short lines. "
            "Pattern: one-word validate, then reframe, then one small truth, then one small ask. "
            "Never stop at 'haan sahi keh rahe ho' and never argue or get defensive. "
            "Use naturally where relevant: 'kitne din se chala rahe ho?', '₹200 ka test kar liya?', "
            "'withdraw minimum ₹500 hai isliye chhota amount atka lagta hai', "
            "'predictions 100% nahi hoti, isliye chhota amount bolti hoon', "
            "'screenshot bhejo, dekh leti hoon'. No guarantees, no pressure."
        )

    try:
        response = await get_cached_response_api(
            prompt=user_text,
            system_instruction=personal_system,
            history=history,
        )
        if response is None:
            await _send_paced(update.message, user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            ))
            return

        await _deliver_reply(
            user_text, user_id, first_name, update, context,
            response.text if response and response.text else "",
            chat_scope, is_group, fraud_dm,
        )

    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        fallback = user_language_notice(
            user_text, "I hit a small technical issue. Please try again in a moment 🙏",
            "Chhota sa technical issue aa gaya yaar, ek minute baad try karna 🙏",
            "तकनीकी दिक्कत आ गई है, एक मिनट बाद फिर कोशिश कीजिए 🙏",
        )
        if "503" in error_msg:
            print("⏳ 503 UNAVAILABLE — waiting 10 seconds before sending...")
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
            await asyncio.sleep(10)
            try:
                retry_response = await call_ai_with_retry(
                    prompt=user_text,
                    system_instruction=personal_system,
                    history=history,
                )
                retry_reply = apply_admin_link_controls(
                    clean_reply_text(retry_response.text) if retry_response and retry_response.text else ""
                )
                if retry_reply:
                    for bubble in _shape_reply(retry_reply, is_group,
                                               max_lines=3 if fraud_dm else 2):
                        await _send_paced(update.message, bubble)
                    dm.append_chat(user_id, first_name, "bot", retry_reply, scope=chat_scope)
                    return
            except Exception as retry_error:
                print(f"❌ ERROR after 10s wait: {retry_error}")
            fallback = user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            )
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            fallback = user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            )
        await _send_paced(update.message, fallback)


async def _flush(user_id: int, first_name: str, update, context) -> None:
    try:
        await asyncio.sleep(DEBOUNCE_SEC)
        merged = " | ".join(_buf.pop(user_id, [])).strip()
        if merged:
            await _answer(merged, user_id, first_name, update, context)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"❌ Debounced reply error: {e}", flush=True)
    finally:
        _tasks.pop(user_id, None)


async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gate, buffer, then answer once per lead."""
    if dm.is_bot_muted():
        return

    user_text = update.message.text
    if not user_text:
        return
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "User"
    chat = update.effective_chat
    chat_scope = f"group:{chat.id}" if chat and chat.type in ("group", "supergroup") else "private"

    if not await should_reply(update, context):
        return

    update_lead_state(user_id, user_text, first_name)
    dm.update_user(user_id, first_name)

    if request_needs_authorization(user_text) and not actor_may_authorize(user_id, chat):
        dm.audit("blocked_unauthorized_request", user_id, str(chat.id), user_text[:160])
        await _send_paced(
            update.message,
            "Ye ek request hai — sirf main admin ya assigned operator hi aisa kar sakte hain. "
            "Mainne kuch change nahi kiya.",
        )
        return

    if await handle_agent_request(update, context, user_text, user_id, first_name, chat_scope):
        return

    _buf.setdefault(user_id, []).append(user_text)
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    task = _tasks.get(user_id)
    if task is not None and not task.done():
        return
    _tasks[user_id] = asyncio.create_task(_flush(user_id, first_name, update, context))

# ================= WELCOME & EXIT LOGIC =================
async def welcome_new_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle member join/leave events"""
    if not update.chat_member:
        return
    
    old_member = update.chat_member.old_chat_member
    new_member = update.chat_member.new_chat_member
    
    old_status = old_member.status
    new_status = new_member.status
    
    try:
        user = new_member.user if new_status == "member" else old_member.user
        user_name = user.first_name if user and user.first_name else "Friend"
        user_id = user.id
        
        reply_markup = None
        # CASE 1: MEMBER JOINED
        if old_status in ["left", "kicked"] and new_status == "member":
            custom_welcome = ""
            if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                custom_welcome = dm.get_group_business(update.effective_chat.id).get("welcome_message") or ""
            if custom_welcome:
                ai_text = _render_template(html.escape(custom_welcome), {"name": user_name})
            else:
                ai_text = _render_template(random.choice(WELCOME_MESSAGES), {"name": user_name})
            username = getattr(context.bot, "username", None) or "IshaniBot"
            deep = f"https://t.me/{username}?start=join_{user_id}"
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("Ishani se baat karo", url=deep)
            ]])
        
        # CASE 2: MEMBER LEFT/KICKED
        elif old_status == "member" and new_status in ["left", "kicked"]:
            ai_text = _render_template(random.choice(LEFT_MESSAGES), {"name": user_name})
        
        else:
            return
        
        user_tag = f'<b><a href="tg://user?id={user_id}">{user_name}</a></b>'
        final_message = f"{user_tag} — {ai_text}"
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=final_message,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    
    except Exception as e:
        print(f"❌ Welcome/Exit error: {e}")

# ================= DOCUMENT REQUEST HANDLERS =================
_MEDIA_WORDS = {"pdf", "document", "file", "photo", "picture", "image"}
_MEDIA_STOP_WORDS = {"send", "share", "show", "give", "get", "me", "please", "the", "a", "an", "your", "you", "can", "could", "want", "need", "mujhe", "bhejo", "bhej", "do", "dikhao", "chahiye", "karo", "hai", "hey", "hi", "please"}


def find_media_asset(request: str = "", preferred_kind: Optional[str] = None) -> Optional[Dict[str, str]]:
    assets = [asset for asset in dm.get_media_assets() if isinstance(asset, dict) and asset.get("file_id")]
    if not assets:
        return None
    query = (request or "").lower()
    if not preferred_kind:
        if re.search(r"\b(photo|picture|image|poster)\b|photo|tasveer|chitra", query):
            preferred_kind = "photo"
        elif re.search(r"\b(pdf|document|file|brochure|guide|details|form)\b|pdf|document|brochure", query):
            preferred_kind = "document"
    candidates = [item for item in assets if item.get("kind") == preferred_kind] if preferred_kind else assets
    if not candidates:
        return None
    terms = {word for word in re.findall(r"[\w-]+", query) if len(word) > 2 and word not in _MEDIA_STOP_WORDS and word not in _MEDIA_WORDS}
    if terms:
        ranked = []
        for order, item in enumerate(candidates):
            labels = f"{item.get('name', '')} {item.get('description', '')}".lower()
            score = sum(1 for term in terms if term in labels)
            if score:
                ranked.append((score, order, item))
        if ranked:
            return max(ranked, key=lambda row: (row[0], row[1]))[2]
        return None
    return candidates[-1]


async def send_media_asset(bot, chat_id: int, asset: Dict[str, str]):
    file_id = asset["file_id"]
    caption = asset.get("description") or None
    if asset.get("kind") == "photo":
        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
    else:
        await bot.send_document(chat_id=chat_id, document=file_id, caption=caption)


async def handle_pdf_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF, document, or details requests"""
    asset = find_media_asset("pdf", preferred_kind="document")
    if not asset:
        await update.message.reply_text(
            "📄 Document not available yet. Please contact admin."
        )
        return
    try:
        await send_media_asset(context.bot, update.effective_chat.id, asset)
        print(f"✅ Sent document to user {update.effective_user.id}")
    except Exception as e:
        print(f"❌ Error sending document: {e}")
        await update.message.reply_text("❌ Error sending document. Please try again.")

# ================= COMMAND HANDLERS =================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    first_name = update.effective_user.first_name or "User"
    dm.update_user(update.effective_user.id, first_name)

    payload = (context.args[0] if getattr(context, "args", None) else "") or ""
    if str(payload).startswith("join_"):
        name = update.effective_user.first_name or "yaar"
        await update.message.reply_text(
            f"Arre {name}, aa gaye. Group me bheed rehti hai, yahan aaram se baat karte hain.\n"
            f"Ek baat bata — side income dekh rahe ho ya bas football dekhne aaye ho?"
        )
        return

    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            f"🎉 Welcome Admin! Ishani is ready to serve.\n\nUse /panel to access admin controls."
        )
    else:
        await update.message.reply_text(
            f"👋 Hello {first_name}! I'm Ishani, your Chelsea Football assistant.\n\n"
            f"Ask me anything about earning, investments, or use /help for commands. 😊"
        )

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    await update.message.reply_text("🛑 Bot stopping... Goodbye!")
    print("🛑 Bot stopped by admin")
    os._exit(0)

# ================= ERROR HANDLER =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    print(f"❌ GLOBAL ERROR: {context.error}")
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text("⚠️ An error occurred. Please try again.")
        except:
            pass

# ================= DASHBOARD PROXY + UPTIMEROBOT HEALTH =================
WEB_PORT = int(os.environ.get("WEB_PORT") or os.environ.get("PORT") or "8080")
WEB_TOKEN = (os.environ.get("WEB_TOKEN") or "").strip()
BOT_APP = None
BOT_LOOP = None

# The Next.js app is the only UI. It runs on an internal port; bot.py proxies
# all non-API traffic to it so the browser only ever uses WEB_PORT.
DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT") or "3000")
DASHBOARD_PROCESS = None

_PROXY_SKIP_REQUEST_HEADERS = {
    "host", "connection", "proxy-connection", "keep-alive",
    "transfer-encoding", "upgrade", "te", "trailer",
}
_PROXY_SKIP_RESPONSE_HEADERS = {
    "connection", "proxy-connection", "keep-alive", "transfer-encoding",
    "upgrade", "content-length",
}


def _public_origin(handler: BaseHTTPRequestHandler) -> str:
    """Origin the browser actually used, so proxied links stay on the same port."""
    host = (handler.headers.get("Host") or "").strip()
    if not host or host.startswith("0.0.0.0"):
        host = f"127.0.0.1:{WEB_PORT}"
    if ":" not in host and not host.startswith("["):
        host = f"{host}:{WEB_PORT}"
    return f"http://{host}"


def _rewrite_proxy_location(handler: BaseHTTPRequestHandler, value: str) -> str:
    public = _public_origin(handler)[len("http://"):]
    for internal in (f"127.0.0.1:{DASHBOARD_PORT}", f"localhost:{DASHBOARD_PORT}"):
        value = value.replace(internal, public)
    return value


def _proxy_dashboard(handler: BaseHTTPRequestHandler, method: str = "GET") -> None:
    """Serve Next.js pages/assets through WEB_PORT; API and health stay local."""
    if not _dashboard_port_open():
        handler._send(
            503,
            json.dumps({"ok": False, "message": "Dashboard is starting or unavailable."}).encode("utf-8"),
            "application/json; charset=utf-8",
        )
        return

    request_headers = {
        key: value for key, value in handler.headers.items()
        if key.lower() not in _PROXY_SKIP_REQUEST_HEADERS
    }
    request_headers["Host"] = f"127.0.0.1:{DASHBOARD_PORT}"

    connection = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", DASHBOARD_PORT, timeout=30)
        connection.request(method, handler.path, headers=request_headers)
        upstream = connection.getresponse()
        body = upstream.read()

        content_type = (upstream.getheader("Content-Type") or "").lower()
        if content_type.startswith(("text/html", "text/x-component", "application/json")):
            public = _public_origin(handler).encode("utf-8")
            for internal in (
                f"http://127.0.0.1:{DASHBOARD_PORT}".encode("utf-8"),
                f"http://localhost:{DASHBOARD_PORT}".encode("utf-8"),
            ):
                body = body.replace(internal, public)

        handler.send_response(upstream.status, upstream.reason)
        for key, value in upstream.getheaders():
            lower = key.lower()
            if lower in _PROXY_SKIP_RESPONSE_HEADERS:
                continue
            if lower == "location":
                value = _rewrite_proxy_location(handler, value)
            handler.send_header(key, value)
        if not any(key.lower() == "content-type" for key, _ in upstream.getheaders()):
            handler.send_header("Content-Type", "text/html; charset=utf-8")

        if method == "HEAD":
            handler.send_header("Content-Length", upstream.getheader("Content-Length") or "0")
        else:
            handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        if method != "HEAD" and body:
            handler.wfile.write(body)
    except Exception as e:
        try:
            handler._send(
                502,
                json.dumps({"ok": False, "message": f"Dashboard proxy error: {e}"}).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        except Exception:
            pass
    finally:
        if connection is not None:
            connection.close()


def _dashboard_port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", DASHBOARD_PORT), timeout=0.4):
            return True
    except OSError:
        return False


def _start_dashboard() -> None:
    """Install/build if needed, then run `next start` as a child of bot.py."""
    global DASHBOARD_PROCESS, DASHBOARD_PORT
    if os.environ.get("ISHANI_NO_DASHBOARD") == "1":
        print("🖥 Dashboard auto-start disabled by ISHANI_NO_DASHBOARD=1.", flush=True)
        return
    if DASHBOARD_PORT == WEB_PORT:
        DASHBOARD_PORT = WEB_PORT + 1
        print(f"⚠️ DASHBOARD_PORT cannot equal WEB_PORT; using internal port {DASHBOARD_PORT}.", flush=True)
    if _dashboard_port_open():
        print(f"🖥 Internal Next.js already listening on port {DASHBOARD_PORT}.", flush=True)
        return
    node = shutil.which("node")
    if not node or not DASHBOARD_DIR.exists():
        print("⚠️ Dashboard not started: Node.js or dashboard/ folder is missing.", flush=True)
        return
    next_bin = DASHBOARD_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
    print(
        f"🧩 Dashboard source check: {DASHBOARD_DIR} "
        f"(app={(DASHBOARD_DIR / 'app').exists()}, "
        f"components={(DASHBOARD_DIR / 'components').exists()}, "
        f"lib={(DASHBOARD_DIR / 'lib').exists()})",
        flush=True,
    )
    try:
        npm = shutil.which("npm")
        if not npm:
            print("⚠️ Dashboard not started: npm is missing (run npm install in dashboard/).", flush=True)
            return
        # Always reconcile dependencies: a previous production-only install may
        # have left node_modules without typescript/@types even though next exists.
        print("📦 Ensuring dashboard dependencies (including dev tools)…", flush=True)
        install_env = os.environ.copy()
        install_env.pop("NODE_ENV", None)
        subprocess.run(
            [npm, "install", "--include=dev"],
            cwd=str(DASHBOARD_DIR), env=install_env, check=True, timeout=600,
        )
        if not next_bin.exists():
            print("⚠️ Dashboard not started: next binary missing after install.", flush=True)
            return
        if not (DASHBOARD_DIR / ".next" / "BUILD_ID").exists():
            print("🔨 Building dashboard (first run)…", flush=True)
            subprocess.run([node, str(next_bin), "build"], cwd=str(DASHBOARD_DIR), check=True, timeout=600)
        env = os.environ.copy()
        env["API_BACKEND_URL"] = f"http://127.0.0.1:{WEB_PORT}"
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        DASHBOARD_PROCESS = subprocess.Popen(
            [node, str(next_bin), "start", "-p", str(DASHBOARD_PORT)],
            cwd=str(DASHBOARD_DIR), env=env, creationflags=flags,
        )
        atexit.register(_stop_dashboard)
        print(f"🖥 Dashboard: http://127.0.0.1:{WEB_PORT}", flush=True)
        print(f"🔗 Bot API on the same port: http://127.0.0.1:{WEB_PORT}/api  ·  health: /health", flush=True)
        print(f"🧩 Internal Next.js port: {DASHBOARD_PORT}", flush=True)
    except Exception as e:
        print(f"⚠️ Dashboard auto-start failed: {e}", flush=True)


def _stop_dashboard() -> None:
    process = DASHBOARD_PROCESS
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass


async def _refresh_group_stats_async(group_ids: List[int]) -> None:
    """Read real Telegram group stats; never fail the whole dashboard for one group."""
    if not BOT_APP:
        return
    for group_id in group_ids:
        record = dm.get_group(group_id)
        if not record:
            continue
        stats = dict(record.get("stats") or {})
        try:
            chat = await BOT_APP.bot.get_chat(int(group_id))
            stats["title"] = getattr(chat, "title", "") or ""
        except Exception as e:
            stats["title"] = ""
            stats["title_error"] = str(e)[:120]
        for key, call in (
            ("members", lambda: BOT_APP.bot.get_chat_member_count(int(group_id))),
            ("administrators", lambda: BOT_APP.bot.get_chat_administrators(int(group_id))),
        ):
            try:
                value = await call()
                stats[key] = len(value) if isinstance(value, list) else int(value)
            except Exception as e:
                stats[key] = 0
                stats[key + "_error"] = str(e)[:120]
        stats["checked_at"] = datetime.now().isoformat(timespec="seconds")
        record["stats"] = stats
    dm.save()


def _prepare_broadcast_media(raw: Any) -> Tuple[Optional[Dict[str, str]], str]:
    """Validate media input; return (prepared_media, error). Never guess a source."""
    if raw is None:
        return None, ""
    if not isinstance(raw, dict):
        return None, "media must be an object."
    media_type = str(raw.get("type") or "").strip().lower()
    if media_type not in ("photo", "video", "document"):
        return None, "media.type must be one of photo, video, document."
    caption = str(raw.get("caption") or "")[:1024]
    file_id = str(raw.get("file_id") or "").strip()
    if file_id:
        if len(file_id) > 512:
            return None, "media.file_id is too long."
        return {"type": media_type, "source": file_id, "caption": caption}, ""
    public_url = _public_http_url(str(raw.get("url") or ""))
    if public_url:
        return {"type": media_type, "source": public_url, "caption": caption}, ""
    return None, "Provide a usable media.file_id or a public http(s) media.url."


async def _broadcast_groups_async(actor_id: int, group_ids: List[int], message: str,
                                  media: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Send text or real media; report the real per-group outcome."""
    results: List[Dict[str, Any]] = []
    for group_id in group_ids:
        item: Dict[str, Any] = {"group_id": int(group_id), "ok": False, "error": ""}
        try:
            chat_id = int(group_id)
            sent = None
            if media:
                caption = media.get("caption") or message
                source = media.get("source") or ""
                if media["type"] == "photo":
                    sent = await BOT_APP.bot.send_photo(chat_id=chat_id, photo=source, caption=caption)
                elif media["type"] == "video":
                    sent = await BOT_APP.bot.send_video(chat_id=chat_id, video=source, caption=caption)
                else:
                    sent = await BOT_APP.bot.send_document(chat_id=chat_id, document=source, caption=caption)
                item["media_type"] = media["type"]
            else:
                sent = await BOT_APP.bot.send_message(chat_id=chat_id, text=message)
            item["ok"] = True
            message_id = getattr(sent, "message_id", None)
            if message_id is not None:
                item["message_id"] = message_id
        except Exception as e:
            item["error"] = str(e)[:200]
        results.append(item)
    dm.record_broadcast(actor_id, "web:groups", results)
    return results


def _run_bot_coro(coro):
    """Bridge the HTTP thread to the bot's asyncio loop."""
    if not BOT_APP or not BOT_LOOP:
        coro.close()
        return None
    future = None
    try:
        future = asyncio.run_coroutine_threadsafe(coro, BOT_LOOP)
        return future.result(timeout=45)
    except Exception as e:
        print(f"⚠️ Bot operation failed: {e}", flush=True)
        if future is not None and not future.done():
            future.cancel()
        return None


# ----- Dashboard-only helpers (read real data; never invent Telegram facts) -----
def _web_alerts(group_ids: List[int]) -> List[Dict[str, Any]]:
    """Derive alerts from persisted group records only."""
    alerts: List[Dict[str, Any]] = []
    for group_id in group_ids:
        record = dm.get_group(group_id) or {}
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        checked = str(stats.get("checked_at") or "")
        admins = int(stats.get("administrators") or 0)
        if checked and admins == 0:
            alerts.append({
                "level": "warning", "group_id": int(group_id), "at": checked,
                "text": f"Group {group_id}: bot may have lost admin access",
            })
        status = str(record.get("registration_status") or "")
        if status == "pending":
            alerts.append({
                "level": "info", "group_id": int(group_id),
                "at": str(record.get("registered_at") or ""),
                "text": f"Group {group_id}: registration pending master verification",
            })
        for key, value in stats.items():
            if str(key).endswith("_error") and value:
                alerts.append({
                    "level": "warning", "group_id": int(group_id), "at": checked,
                    "text": f"Group {group_id}: {key} - {str(value)[:160]}",
                })
    return alerts


def _known_members_of(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise observed users only; this is not a full Telegram member list."""
    raw = record.get("known_members") if isinstance(record, dict) else None
    items: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                item = dict(value)
                if item.get("id") is None and str(key).lstrip("-").isdigit():
                    item["id"] = int(key)
                items.append(item)
            elif str(key).lstrip("-").isdigit():
                items.append({"id": int(key), "username": str(value or ""), "first_name": str(value or "")})
    elif isinstance(raw, list):
        items = [dict(item) if isinstance(item, dict) else {"id": item}
                 for item in raw if isinstance(item, (dict, int, str))]
    result = []
    for item in items:
        result.append({
            "id": item.get("id") if item.get("id") is not None else item.get("user_id"),
            "username": item.get("username") or "",
            "first_name": item.get("first_name") or item.get("first") or "",
            "last_seen": item.get("last_seen") or item.get("seen_at") or "",
            "source": item.get("source") or "",
        })
    return result


def _scoped_audit_entries(session: Dict[str, Any], limit: int = 15) -> List[Dict[str, Any]]:
    """Master sees all; a group owner sees own-group targets and own actions."""
    log = dm.data.get("audit_log") or []
    if not isinstance(log, list):
        return []
    visible = {str(gid) for gid in (session.get("group_ids") or [])}
    uid = session.get("user_id")
    entries: List[Dict[str, Any]] = []
    for entry in reversed(log):
        if not isinstance(entry, dict):
            continue
        if session.get("role") != "master":
            if str(entry.get("target") or "") not in visible and entry.get("actor_id") != uid:
                continue
        entries.append(dict(entry))
        if len(entries) >= limit:
            break
    return entries


def _group_activity(group_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Audit rows whose target is this group or whose details mention its id."""
    log = dm.data.get("audit_log") or []
    if not isinstance(log, list):
        return []
    needle = str(group_id)
    entries = []
    for entry in reversed(log):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("target") or "") == needle or needle in str(entry.get("details") or ""):
            entries.append(dict(entry))
        if len(entries) >= limit:
            break
    return entries


async def _chat_administrators_async(group_id: int) -> List[Dict[str, Any]]:
    """Real Telegram administrators via Bot API; never fabricate members."""
    if not BOT_APP:
        raise RuntimeError("Bot is not connected")
    members = await BOT_APP.bot.get_chat_administrators(int(group_id))
    admins: List[Dict[str, Any]] = []
    for member in members or []:
        user = getattr(member, "user", None)
        status = getattr(member, "status", "")
        admins.append({
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", "") or "",
            "first_name": getattr(user, "first_name", "") or "",
            "status": str(getattr(status, "value", status)) if status is not None else "",
            "is_bot": bool(getattr(user, "is_bot", False)),
        })
    return admins


async def _apply_group_action_async(action: str, group_id: int,
                                    message_id: Any = None) -> Tuple[bool, bool, str]:
    """Execute one bot action; return (executed, verified, note)."""
    if not BOT_APP:
        return False, False, "Bot is not connected."
    try:
        bot = BOT_APP.bot
        if action == "pin":
            await bot.pin_chat_message(chat_id=int(group_id), message_id=int(message_id))
            try:
                chat = await bot.get_chat(int(group_id))
                pinned = getattr(chat, "pinned_message", None)
                pinned_id = getattr(pinned, "message_id", None)
                if pinned_id is None:
                    return True, False, "Pin executed; verification unavailable (no pinned_message returned)."
                return (True, int(pinned_id) == int(message_id),
                        "Verified pinned message id via get_chat.")
            except Exception as e:
                return True, False, "Pin executed; verification read failed: " + str(e)[:160]
        if action == "unpin":
            await bot.unpin_chat_message(chat_id=int(group_id), message_id=int(message_id))
            try:
                chat = await bot.get_chat(int(group_id))
                pinned = getattr(chat, "pinned_message", None)
                pinned_id = getattr(pinned, "message_id", None)
                if pinned_id is None:
                    return True, True, "Unpin verified: no pinned message reported by get_chat."
                return (True, int(pinned_id) != int(message_id),
                        "Verified via get_chat; pinned message id changed.")
            except Exception as e:
                return True, False, "Unpin executed; verification read failed: " + str(e)[:160]
        if action == "delete":
            await bot.delete_message(chat_id=int(group_id), message_id=int(message_id))
            return (True, False,
                    "Delete executed; Telegram cannot re-read a deleted message, so verification is not possible.")
        return False, False, "Unsupported action."
    except Exception as e:
        return False, False, str(e)[:300]


def _web_diagnostics() -> List[str]:
    """Read-only local diagnostics. Never edits source or JSON files."""
    lines: List[str] = []
    try:
        import subprocess as _subprocess
        import sys as _sys
        proc = _subprocess.run([_sys.executable, "-m", "py_compile", "bot.py"],
                               capture_output=True, text=True, timeout=90)
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        lines.append("bot.py compile: " + ("OK" if proc.returncode == 0 else "FAILED: " + detail))
    except Exception as e:
        lines.append("bot.py compile: unavailable - " + str(e)[:160])
    for name in ("persona.json", "data.json"):
        try:
            json.loads(Path(name).read_text(encoding="utf-8"))
            lines.append(f"{name}: valid JSON")
        except Exception as e:
            lines.append(f"{name}: INVALID - {str(e)[:160]}")
    return lines


def _web_group_report(session: Dict[str, Any]) -> str:
    """Short real-data report for AI group-manager / automation summary."""
    ids = list(session.get("group_ids") or [])
    lines = [f"Visible groups: {len(ids)}"]
    for group_id in ids:
        record = dm.get_group(group_id) or {}
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        business = record.get("business") if isinstance(record.get("business"), dict) else {}
        name = business.get("name") or stats.get("title") or f"Group {group_id}"
        recent = 0
        for entry in (dm.data.get("broadcast_log") or [])[:50]:
            if isinstance(entry, dict) and any(
                    isinstance(r, dict) and str(r.get("group_id")) == str(group_id)
                    for r in (entry.get("results") or [])):
                recent += 1
        lines.append(
            f"- {group_id} ({name}): administrators={int(stats.get('administrators') or 0)}, "
            f"members={int(stats.get('members') or 0)}, "
            f"registration={record.get('registration_status', 'assigned')}, "
            f"recent_broadcasts={recent}"
        )
    return "\n".join(lines)


def _append_web_lesson(instruction: str) -> None:
    """Append one lesson atomically, preserving master_prompt and all old lessons."""
    persona = load_persona()
    if not str(persona.get("master_prompt") or "").strip():
        raise RuntimeError("persona.json master_prompt is missing - refusing to change lessons")
    learned = persona.get("learned_from_admin") or []
    if isinstance(learned, str):
        learned = [learned]
    elif not isinstance(learned, list):
        learned = []
    if instruction not in learned:
        learned.append(instruction)
    persona["learned_from_admin"] = learned
    _atomic_write_json(PERSONA_PATH, persona)


class ConfigPageHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ua = self.headers.get("User-Agent", "")
        if "UptimeRobot" in ua:
            print(f"⏱ UptimeRobot check {self.path}", flush=True)
            return
        print(f"🌐 {self.command} {self.path}", flush=True)

    def _send(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = (self.headers.get("Origin") or "").replace("\r", "").replace("\n", "").strip()
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain; charset=utf-8")

    def _json(self, code: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self._send(code, raw, "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _master_session(self) -> Dict[str, Any]:
        return {
            "user_id": ADMIN_ID,
            "role": "master",
            "group_ids": dm.visible_group_ids(ADMIN_ID),
            "source": "local",
        }

    def _auth(self) -> Optional[Dict[str, Any]]:
        """Dashboard opens without a token. An explicit token still scopes owners."""
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not token:
            query = parse_qs(urlparse(self.path).query)
            token = (query.get("token") or [""])[0]
        if not token:
            return self._master_session()
        if WEB_TOKEN and hmac.compare_digest(token, WEB_TOKEN):
            return self._master_session()
        session = dm.get_web_token(token)
        if not session:
            return None
        session = dict(session)
        session["group_ids"] = dm.visible_group_ids(session.get("user_id"))
        session["source"] = "bot"
        return session

    def _unauthorized(self):
        self._json(401, {"ok": False, "message": "Master access required for this action."})

    def _api_groups(self):
        session = self._auth()
        if not session:
            return self._unauthorized()
        ids = session["group_ids"]
        fresh = False
        for group_id in ids:
            record = dm.get_group(group_id) or {}
            checked = ((record.get("stats") or {}).get("checked_at") or "")
            try:
                fresh = bool(checked) and (datetime.now() - datetime.fromisoformat(checked)).total_seconds() < 300
            except (TypeError, ValueError):
                fresh = False
            if not fresh:
                break
        if not fresh:
            _run_bot_coro(_refresh_group_stats_async(ids))
        groups = []
        owner_ids = set()
        administrators = 0
        members = 0
        for group_id in ids:
            record = dm.get_group(group_id) or {}
            business = record.get("business") if isinstance(record.get("business"), dict) else {}
            settings = record.get("settings") if isinstance(record.get("settings"), dict) else {}
            stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
            if record.get("owner_id"):
                owner_ids.add(int(record["owner_id"]))
            admins = int(stats.get("administrators") or 0)
            mems = int(stats.get("members") or 0)
            administrators += admins
            members += mems
            known = record.get("known_members")
            groups.append({
                "id": int(group_id),
                "name": business.get("name") or stats.get("title") or f"Group {group_id}",
                "owner_id": record.get("owner_id") or record.get("operator_id"),
                "registration_status": record.get("registration_status", "assigned"),
                "business": business,
                "settings": settings,
                "stats": {"administrators": admins, "members": mems, "title": stats.get("title", ""),
                          "checked_at": stats.get("checked_at", "")},
                "username": stats.get("username") or "",
                "is_public": bool(stats.get("username")),
                "invite_link": business.get("join_link") or stats.get("invite_link") or "",
                "created_at": record.get("created_at"),
                "registered_at": record.get("registered_at"),
                "bot_is_admin": stats.get("bot_is_admin"),
                "bot_permissions": stats.get("bot_permissions"),
                "known_members": len(known) if isinstance(known, (list, dict)) else 0,
            })
        broadcasts = []
        allowed = set(ids)

        def broadcast_visible(entry: Dict[str, Any]) -> bool:
            if session["role"] == "master":
                return True
            for item in (entry.get("results") or []):
                if not isinstance(item, dict) or item.get("group_id") is None:
                    continue
                try:
                    if int(item["group_id"]) in allowed:
                        return True
                except (TypeError, ValueError):
                    continue
            return False

        for entry in reversed(dm.data.get("broadcast_log") or []):
            if not isinstance(entry, dict) or not broadcast_visible(entry):
                continue
            broadcasts.append({k: entry.get(k) for k in ("at", "scope", "sent", "failed")})
            if len(broadcasts) >= 20:
                break
        return self._json(200, {
            "ok": True,
            "role": session["role"],
            "user_id": session.get("user_id"),
            "stats": {"groups": len(groups), "owners": len(owner_ids) + (1 if session["role"] == "master" else 0),
                      "administrators": administrators, "members": members},
            "groups": groups,
            "broadcasts": broadcasts,
            "alerts": _web_alerts(ids),
        })

    def _api_group_detail(self):
        session = self._auth()
        if not session:
            return self._unauthorized()
        query = parse_qs(urlparse(self.path).query)
        try:
            group_id = int((query.get("id") or [""])[0])
        except (TypeError, ValueError):
            return self._json(400, {"ok": False, "message": "group id is required"})
        if group_id not in session["group_ids"]:
            return self._json(403, {"ok": False, "message": "This group is outside your scope."})
        record = dm.get_group(group_id) or {}
        business = record.get("business") if isinstance(record.get("business"), dict) else {}
        settings = record.get("settings") if isinstance(record.get("settings"), dict) else {}
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        relevant = []
        for entry in reversed(dm.data.get("broadcast_log") or []):
            if isinstance(entry, dict) and any(
                isinstance(r, dict) and r.get("group_id") == group_id for r in (entry.get("results") or [])
            ):
                relevant.append({k: entry.get(k) for k in ("at", "scope", "sent", "failed")})
            if len(relevant) >= 10:
                break
        return self._json(200, {"ok": True, "group": {
            "id": group_id,
            "name": business.get("name") or stats.get("title") or f"Group {group_id}",
            "owner_id": record.get("owner_id") or record.get("operator_id"),
            "registration_status": record.get("registration_status", "assigned"),
            "business": business, "settings": settings, "stats": stats,
            "broadcasts": relevant,
            "username": stats.get("username") or "",
            "invite_link": business.get("join_link") or stats.get("invite_link") or "",
            "registered_at": record.get("registered_at"),
            "bot_permissions": stats.get("bot_permissions"),
            "known_members": _known_members_of(record),
            "activity": _group_activity(group_id),
        }})

    def _api_overview(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            ids = list(session["group_ids"])
            active = inactive = members = administrators = 0
            owners: set = set()
            bot_admin_groups = muted_groups = link_protected_groups = 0
            for group_id in ids:
                record = dm.get_group(group_id) or {}
                stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
                settings = record.get("settings") if isinstance(record.get("settings"), dict) else {}
                if str(record.get("registration_status") or "") == "verified":
                    active += 1
                else:
                    inactive += 1
                admins = int(stats.get("administrators") or 0)
                administrators += admins
                members += int(stats.get("members") or 0)
                if stats.get("checked_at") and admins > 0:
                    bot_admin_groups += 1
                if record.get("owner_id"):
                    try:
                        owners.add(int(record["owner_id"]))
                    except (TypeError, ValueError):
                        pass
                if bool(settings.get("bot_muted")):
                    muted_groups += 1
                if settings.get("links_allowed") is False:
                    link_protected_groups += 1
            if session["role"] == "master":
                try:
                    owners.add(int(session.get("user_id") or ADMIN_ID))
                except (TypeError, ValueError):
                    pass
            return self._json(200, {
                "ok": True, "role": session["role"],
                "stats": {
                    "groups": len(ids), "active_groups": active, "inactive_groups": inactive,
                    "members": members, "administrators": administrators, "owners": len(owners),
                    "bot_connected": BOT_APP is not None, "bot_admin_groups": bot_admin_groups,
                    "muted_groups": muted_groups, "link_protected_groups": link_protected_groups,
                },
                "alerts": _web_alerts(ids),
                "activity": _scoped_audit_entries(session, 15),
            })
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _api_group_members(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            query = parse_qs(urlparse(self.path).query)
            try:
                group_id = int((query.get("id") or [""])[0])
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "message": "group id is required"})
            if group_id not in session["group_ids"]:
                return self._json(403, {"ok": False, "message": "This group is outside your scope."})
            note = "Telegram Bot API cannot list all non-admin members; only observed users can be tracked."
            administrators = []
            error = ""
            if not BOT_APP:
                error = "Bot is not connected."
            else:
                result = _run_bot_coro(_chat_administrators_async(group_id))
                if result is None:
                    error = "Administrator lookup failed or timed out."
                elif isinstance(result, list):
                    administrators = result
                else:
                    error = "Administrator lookup returned an unexpected result."
            if error:
                note = note + " Error: " + error
            record = dm.get_group(group_id) or {}
            return self._json(200, {
                "ok": True, "group_id": group_id,
                "administrators": administrators,
                "known_members": _known_members_of(record),
                "members_available": False,
                "note": note,
                "error": error,
            })
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _api_owners(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            if session["role"] != "master":
                return self._json(403, {"ok": False, "message": "Master owner only."})
            owners = []
            raw_owners = dm.data.get("owners") or {}
            if isinstance(raw_owners, dict):
                for user_id, record in raw_owners.items():
                    if not isinstance(record, dict):
                        continue
                    numeric = str(user_id).lstrip("-").isdigit()
                    owners.append({
                        "user_id": int(user_id) if numeric else user_id,
                        "role": record.get("role") or "",
                        "status": record.get("status") or "",
                        "accepted_at": record.get("accepted_at") or "",
                        "group_ids": dm.visible_group_ids(int(user_id)) if numeric else [],
                    })
            invitations = []
            raw_invites = dm.data.get("invitations") or {}
            if isinstance(raw_invites, dict):
                for index, record in enumerate(raw_invites.values(), 1):
                    if not isinstance(record, dict):
                        continue
                    invitations.append({
                        "id": index,
                        "invitee": record.get("invitee_id") or record.get("invitee_username") or "",
                        "group_id": record.get("group_id"),
                        "created_at": record.get("created_at") or "",
                        "expires_at": record.get("expires_at") or "",
                        "accepted": bool(record.get("accepted")),
                    })
            return self._json(200, {"ok": True, "owners": owners, "invitations": invitations})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _visible_scheduled(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = dm.data.get("scheduled_messages") or []
        if not isinstance(items, list):
            return []
        allowed = {str(gid) for gid in session["group_ids"]}
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if session["role"] != "master" and str(item.get("group_id")) not in allowed:
                continue
            result.append({k: v for k, v in item.items()
                           if "token" not in str(k).lower() and "api_key" not in str(k).lower()})
        return result

    def _api_schedule(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            return self._json(200, {"ok": True, "items": self._visible_scheduled(session)})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _api_ai_history(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            messages = dm.recent_chat(int(session["user_id"]), "Dashboard", limit=40, scope="web")
            return self._json(200, {"ok": True, "messages": messages})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _visible_tasks(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks = dm.data.get("web_tasks") or []
        if not isinstance(tasks, list):
            return []
        allowed = {str(gid) for gid in session["group_ids"]}
        result = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if (session["role"] == "master"
                    or str(task.get("actor_id")) == str(session.get("user_id"))
                    or str(task.get("group_id")) in allowed):
                result.append(task)
        return result

    def _api_tasks(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            tasks = self._visible_tasks(session)
            query = parse_qs(urlparse(self.path).query)
            wanted = (query.get("id") or [""])[0]
            if wanted:
                match = next((task for task in tasks if str(task.get("id")) == wanted), None)
                if match is None:
                    return self._json(404, {"ok": False, "message": "Task not found."})
                return self._json(200, {"ok": True, "task": match})
            return self._json(200, {"ok": True, "tasks": tasks})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _api_lessons(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            if session["role"] != "master":
                return self._json(403, {"ok": False, "message": "Master owner only."})
            persona = load_persona()
            lessons = persona.get("learned_from_admin") or []
            if isinstance(lessons, str):
                lessons = [lessons]
            if not isinstance(lessons, list):
                lessons = []
            controls = persona.get("admin_learning_controls") or {}
            if not isinstance(controls, dict):
                controls = {}
            return self._json(200, {"ok": True, "lessons": lessons, "link_controls": controls})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _api_activity(self):
        try:
            session = self._auth()
            if not session:
                return self._unauthorized()
            return self._json(200, {"ok": True, "entries": _scoped_audit_entries(session, 15)})
        except Exception as e:
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/groups":
            return self._api_groups()
        if path == "/api/group":
            return self._api_group_detail()
        if path == "/api/group/members":
            return self._api_group_members()
        if path == "/api/overview":
            return self._api_overview()
        if path == "/api/owners":
            return self._api_owners()
        if path == "/api/schedule":
            return self._api_schedule()
        if path == "/api/ai/history":
            return self._api_ai_history()
        if path == "/api/tasks":
            return self._api_tasks()
        if path == "/api/lessons":
            return self._api_lessons()
        if path == "/api/activity":
            return self._api_activity()
        if path == "/health":
            self._json(200, {"status": "ok", "service": "ishani-bot", "uptime_monitor": "uptimerobot"})
            return
        if path == "/api/config":
            session = self._auth()
            if not session or session["role"] != "master":
                return self._unauthorized()
            cfg = dm.get_ai_config()
            self._json(200, {
                "ok": True,
                "endpoint": cfg.get("endpoint") or "http://127.0.0.1:11434/v1",
                "model": cfg.get("model") or "gptoss-20b",
                "has_key": bool(cfg.get("api_key")),
            })
            return
        if path.startswith("/api/"):
            self._json(404, {"ok": False, "message": "Not found"})
            return
        return _proxy_dashboard(self)

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            return
        if path.startswith("/api/"):
            self.send_response(404)
            self.end_headers()
            return
        return _proxy_dashboard(self, "HEAD")

    def _api_ai_chat(self, data: Dict[str, Any]):
        session = self._auth()
        if not session:
            return self._unauthorized()
        try:
            mode = str(data.get("mode") or "assistant").strip().lower()
            allowed_modes = ("assistant", "group_manager", "research", "auto_fix",
                             "script_generator", "automation")
            if mode not in allowed_modes:
                return self._json(400, {"ok": False, "message": "Unsupported AI mode."})
            message = str(data.get("message") or "").strip()[:2000]
            if not message:
                return self._json(400, {"ok": False, "message": "message is required."})
            group_id = data.get("group_id")
            if group_id not in (None, ""):
                try:
                    group_id = int(group_id)
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "Invalid group id."})
                if group_id not in session["group_ids"]:
                    return self._json(403, {"ok": False, "message": "This group is outside your scope."})
            user_id = int(session["user_id"])
            task_id = secrets.token_hex(8)
            tasks = dm.data.setdefault("web_tasks", [])
            if not isinstance(tasks, list):
                tasks = dm.data["web_tasks"] = []
            task: Dict[str, Any] = {
                "id": task_id, "at": datetime.now().isoformat(timespec="seconds"),
                "actor_id": user_id, "mode": mode, "message": message,
                "group_id": group_id, "status": "running", "log": [], "result": None,
            }
            tasks.insert(0, task)
            dm.save()

            def log_step(text: str) -> None:
                task["log"].append({"at": datetime.now().isoformat(timespec="seconds"),
                                    "text": str(text)[:300]})
                del task["log"][:-100]

            def extract_broadcast_text(text: str) -> str:
                """Use quoted text or text after a colon, never the command itself."""
                quoted = re.search(r"[\"“']([^\"”']{1,1000})[\"”']", text)
                if quoted:
                    return quoted.group(1).strip()
                parts = re.split(r":\s*", text, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    return parts[1].strip()[:1000]
                return ""

            def finish(status: str, result: Any) -> None:
                task["status"] = status
                task["result"] = result
                task["finished_at"] = datetime.now().isoformat(timespec="seconds")
                dm.save()

            confirmed = data.get("confirm") is True
            reply = ""
            extra: Dict[str, Any] = {}
            log_step(f"mode={mode} message_length={len(message)}")

            if mode == "assistant":
                history = dm.recent_chat(user_id, "Dashboard", limit=40, scope="web")
                group_business = dm.get_group_business(group_id) if group_id is not None else None
                system = build_personal_system(user_id, "Dashboard", history,
                                               compact=False,
                                               group_business=group_business,
                                               include_company=bool(re.search(r"\b(chelsea|company|join|signup|sign up|link|earning|profit|deposit|withdraw|prediction|app)\b", message, re.I)))
                activity_lines: List[str] = []
                confirmation: Optional[Dict[str, Any]] = None
                if _deterministic_tool(message):
                    # One assistant: intent -> whitelisted tools -> verified results -> persona reply.
                    log_step("tool loop started")
                    reply, activity_lines, confirmation = asyncio.run(
                        _run_tool_turn_headless(
                            message, user_id, "Dashboard", "web", system, history,
                            confirmed=confirmed, group_id=group_id,
                        )
                    )
                    log_step("tool loop finished")
                else:
                    log_step("local model call started")
                    response = asyncio.run(get_cached_response_api(message, system, history=history))
                    raw = getattr(response, "text", "") if response is not None else ""
                    reply = apply_admin_link_controls(clean_reply_text(str(raw or ""))) if raw else ""
                if not reply and not confirmation:
                    reply = "Model ne abhi koi reply nahi diya; dobara try karein."
                # Activity and final answer are shown together; history is written only once.
                visible = "\n".join(activity_lines) + ("\n\n" + reply if reply else "") \
                    if activity_lines else reply
                dm.append_chat(user_id, "Dashboard", "user", message, scope="web")
                dm.append_chat(user_id, "Dashboard", "assistant", visible or reply, scope="web")
                log_step("web chat history updated")
                if confirmation:
                    extra = confirmation
                    finish("awaiting_confirmation", {"activity": activity_lines})
                    reply = visible
                else:
                    finish("done", {"reply": visible[:2000], "activity": activity_lines})

            elif mode == "research":
                log_step("web search started")
                url_match = re.search(r"https?://[^\s<>]+", message)
                page_url = url_match.group(0).rstrip(".,!?;:)\"]'") if url_match else ""
                page_question = re.sub(r"https?://[^\s<>]+", " ", message).strip() if page_url else message
                reply = asyncio.run(_run_web_search(page_question, user_id,
                                                    summarize=True, url=page_url))
                log_step("web search finished")
                finish("done", {"reply_length": len(reply)})

            elif mode == "group_manager":
                reply = _web_group_report(session)
                send_intent = bool(re.search(
                    r"\b(send|broadcast|post|bhejo|bhej)\b", message, re.IGNORECASE))
                mute_intent = bool(re.search(r"\b(mute|unmute)\b", message, re.IGNORECASE))
                if send_intent or mute_intent:
                    proposed: Dict[str, Any]
                    if send_intent:
                        proposed = {"type": "broadcast", "group_ids": list(session["group_ids"]),
                                    "message": extract_broadcast_text(message)}
                    else:
                        target = group_id or (session["group_ids"][0]
                                              if len(session["group_ids"]) == 1 else None)
                        proposed = {"type": "group_action", "group_id": target,
                                    "action": "unmute" if re.search(r"unmute", message, re.I) else "mute"}
                    if not confirmed:
                        finish("awaiting_confirmation", {"proposed_action": proposed})
                        extra = {"requires_confirmation": True, "proposed_action": proposed}
                        reply = ("Confirm karne ke liye /api/ai/chat ko confirm:true ke saath "
                                 "bhejein. Abhi kuch execute nahi hua.")
                        if proposed["type"] == "broadcast" and not proposed["message"]:
                            reply = ("Broadcast ka text nahi mila. Likhein jaise: "
                                     "Send: Hello team  (ya \"Hello team\" quotes mein). Kuch bheja nahi gaya.")
                    else:
                        if proposed["type"] == "broadcast":
                            text = str(proposed.get("message") or "").strip()
                            if not text:
                                finish("error", {"message": "No broadcast text provided"})
                                return self._json(400, {"ok": False, "task_id": task_id,
                                                        "message": "Broadcast text is required."})
                            code, payload = self._perform_broadcast(
                                session, {"message": text, "group_ids": proposed["group_ids"]})
                            reply = f"Broadcast: sent={payload.get('sent')} failed={payload.get('failed')}"
                        else:
                            if proposed.get("group_id") is None:
                                log_step("no authorized target group for mute/unmute")
                                finish("error", {"message": "group_id is required."})
                                return self._json(400, {"ok": False,
                                                        "message": "group_id is required for mute/unmute.",
                                                        "task_id": task_id})
                            code, payload = self._perform_group_action(
                                session, {"group_id": proposed["group_id"],
                                          "action": proposed["action"], "confirm": True})
                            reply = (f"{proposed['action']}: ok={payload.get('ok')} "
                                     f"verified={payload.get('verified')} note={payload.get('note') or payload.get('message')}")
                        extra = {"result": payload}
                        finish("done" if payload.get("ok") else "error", payload)
                        return self._json(code, {"ok": bool(payload.get("ok")), "reply": reply,
                                                 "task_id": task_id, "mode": mode, **extra})
                else:
                    finish("done", {"groups": len(session["group_ids"])})

            elif mode == "script_generator":
                filename_match = re.search(
                    r"([A-Za-z0-9 _-]{1,60}\.py)", message, re.IGNORECASE)
                filename = filename_match.group(1) if filename_match else "web_script.py"
                log_step("script generation started")
                reply = asyncio.run(_tool_generate_script(
                    {"filename": filename, "purpose": message}))
                log_step("script generation finished (not executed)")
                finish("done", {"reply": reply[:2000]})

            elif mode == "auto_fix":
                findings = _web_diagnostics()
                reply = "\n".join(findings)
                if re.search(r"\b(fix|repair|solve|theek karo)\b", message, re.IGNORECASE):
                    proposed = {"type": "manual_fix", "findings": findings,
                                "note": "Automatic source modification is disabled; no file was changed."}
                    finish("awaiting_confirmation", proposed)
                    extra = {"requires_confirmation": True, "proposed_action": proposed}
                    reply += "\n\nSource khud nahi badla gaya; review karke manually fix karein."
                else:
                    finish("done", {"findings": findings})

            elif mode == "automation":
                whitelist = ("diagnose", "summary")
                steps = data.get("steps")
                if steps is None:
                    steps = [step for step in whitelist
                             if re.search(r"\b" + step + r"\b", message, re.IGNORECASE)]
                if not isinstance(steps, list) or any(
                        str(step).strip().lower() not in whitelist for step in steps):
                    proposed = {"type": "automation", "allowed_steps": list(whitelist),
                                "note": "Only predefined read-only steps may run."}
                    finish("awaiting_confirmation", proposed)
                    extra = {"requires_confirmation": True, "proposed_action": proposed}
                    reply = "Sirf predefined steps allowed hain: diagnose, summary. Kuch nahi chala."
                elif not confirmed:
                    proposed = {"type": "automation", "steps": [str(s).strip().lower() for s in steps]}
                    finish("awaiting_confirmation", proposed)
                    extra = {"requires_confirmation": True, "proposed_action": proposed}
                    reply = ("Confirm karne ke liye /api/ai/chat ko confirm:true ke saath "
                             "bhejein. Abhi kuch execute nahi hua.")
                else:
                    outputs = []
                    for step in steps:
                        step_name = str(step).strip().lower()
                        if step_name == "diagnose":
                            outputs.extend(_web_diagnostics())
                        elif step_name == "summary":
                            outputs.append(_web_group_report(session))
                    reply = "\n".join(outputs)
                    finish("done", {"steps": [str(s).strip().lower() for s in steps]})

            dm.audit("web_ai_chat", user_id, mode, f"task={task_id} status={task.get('status')}")
            return self._json(200, {"ok": True, "reply": reply, "task_id": task_id,
                                    "mode": mode, **extra})
        except Exception as e:
            try:
                dm.audit("web_ai_chat_failed", session.get("user_id"), "chat", str(e)[:180])
            except Exception:
                pass
            return self._json(500, {"ok": False, "message": str(e)[:300]})

    def _perform_broadcast(self, session: Dict[str, Any], data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Shared by /api/broadcast and confirmed AI actions. Real sends only."""
        message = str(data.get("message") or "").strip()
        if not message:
            return 400, {"ok": False, "message": "Announcement text is required."}
        requested = data.get("group_ids")
        if requested == "all" or requested is None or requested == "":
            target_ids = list(session["group_ids"])
        elif isinstance(requested, list):
            try:
                target_ids = [int(x) for x in requested]
            except (TypeError, ValueError):
                return 400, {"ok": False, "message": "Invalid group list."}
        else:
            return 400, {"ok": False, "message": "Invalid group list."}
        outside = [gid for gid in target_ids if gid not in session["group_ids"]]
        if outside:
            return 403, {"ok": False, "message": "Groups outside your scope were requested."}
        if not target_ids:
            return 400, {"ok": False, "message": "No authorized groups available."}
        media, error = _prepare_broadcast_media(data.get("media"))
        if error:
            return 400, {"ok": False, "message": error}
        results = _run_bot_coro(_broadcast_groups_async(
            session["user_id"], target_ids, message, media
        ))
        if results is None:
            return 503, {"ok": False, "message": "Bot is not connected yet; nothing was sent."}
        sent = sum(1 for item in results if item.get("ok"))
        payload: Dict[str, Any] = {"ok": True, "sent": sent, "failed": len(results) - sent,
                                   "results": results}
        if media:
            payload["media_type"] = media["type"]
        return 200, payload

    def _perform_group_action(self, session: Dict[str, Any], data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Shared by /api/group/action and confirmed AI actions."""
        try:
            group_id = int(data.get("group_id"))
        except (TypeError, ValueError):
            return 400, {"ok": False, "message": "Invalid group id."}
        if group_id not in session["group_ids"]:
            return 403, {"ok": False, "message": "This group is outside your scope."}
        action = str(data.get("action") or "").strip().lower()
        if action not in ("pin", "unpin", "delete", "mute", "unmute"):
            return 400, {"ok": False, "message": "Allowed actions: pin, unpin, delete, mute, unmute."}
        message_id = None
        if action in ("pin", "unpin", "delete"):
            try:
                message_id = int(data.get("message_id"))
            except (TypeError, ValueError):
                return 400, {"ok": False, "message": "message_id is required for this action."}
        confirmed = data.get("confirm") is True
        dm.audit("web_group_action_attempt", session["user_id"], str(group_id),
                 f"action={action} confirm={confirmed}")
        if action in ("pin", "unpin", "delete") and not confirmed:
            dm.audit("web_group_action_blocked", session["user_id"], str(group_id),
                     f"action={action} missing confirm")
            return 400, {"ok": False, "requires_confirmation": True,
                         "message": "confirm:true is required for this action."}
        try:
            if action in ("mute", "unmute"):
                value = action == "mute"
                changed = dm.set_group_details(session["user_id"], ADMIN_ID, group_id, "bot_muted", value)
                current = dm.get_group_settings(group_id).get("bot_muted")
                result: Dict[str, Any] = {"bot_muted": current}
                verified = bool(changed and current is value)
                note = ("Verified against saved group settings." if verified
                        else "Setting change could not be verified against saved settings.")
            else:
                outcome = _run_bot_coro(_apply_group_action_async(action, group_id, message_id))
                if outcome is None:
                    executed, verified, note = False, False, "Bot is not connected or the operation timed out."
                else:
                    executed, verified, note = outcome
                result = {"executed": executed}
            dm.audit("web_group_action", session["user_id"], str(group_id),
                     f"action={action} verified={verified} note={note[:180]}")
            if not verified and note.startswith("Bot is not connected"):
                return 503, {"ok": False, "message": note, "action": action, "note": note}
            if isinstance(result.get("executed"), bool) and not result["executed"]:
                return 502, {"ok": False, "message": note, "action": action, "note": note}
            return 200, {"ok": True, "verified": verified, "action": action,
                         "result": result, "note": note}
        except Exception as e:
            dm.audit("web_group_action_failed", session["user_id"], str(group_id),
                     f"action={action} error={str(e)[:160]}")
            return 502, {"ok": False, "message": str(e)[:300]}

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except Exception:
            self._json(400, {"ok": False, "message": "Invalid JSON"})
            return
        if path == "/api/config":
            session = self._auth()
            if not session or session["role"] != "master":
                return self._unauthorized()
            endpoint = (data.get("endpoint") or "").strip()
            model = (data.get("model") or "").strip()
            if not endpoint or not model:
                self._json(400, {"ok": False, "message": "Endpoint and model name are required."})
                return
            cfg = dm.save_ai_config(
                endpoint=endpoint,
                api_key=data.get("api_key", ""),
                model=model,
                provider="custom",
            )
            self._json(200, {"ok": True, "message": "Local model settings saved.", "model": cfg["model"]})
            return
        if path == "/api/test":
            session = self._auth()
            if not session or session["role"] != "master":
                return self._unauthorized()
            self._json(200, _test_ai_connection(data))
            return
        if path == "/api/group/settings":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                try:
                    group_id = int(data.get("group_id"))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "Invalid group id."})
                if group_id not in session["group_ids"]:
                    return self._json(403, {"ok": False, "message": "This group is outside your scope."})
                key = str(data.get("key") or "").strip().lower()
                business_keys = {"name", "join_link", "welcome_message", "notes",
                                 "goodbye_message", "ai_instructions"}
                setting_keys = {"bot_muted", "links_allowed", "spam_protection", "active", "group_mode"}
                if key not in business_keys | setting_keys:
                    return self._json(400, {"ok": False, "message": "Setting key not allowed."})
                record = dm.get_group(group_id)
                if not record:
                    return self._json(400, {"ok": False, "message": "Group record not found."})
                value = data.get("value", "")
                if key in business_keys:
                    record.setdefault("business", {})[key] = str(value).strip()[:500]
                elif key == "group_mode":
                    mode = str(value).strip().lower()
                    record.setdefault("settings", {})[key] = mode if mode in ("all", "mentions") else GROUP_MODE
                else:
                    flag = str(value).strip().lower() in {"1", "true", "yes", "on", "haan", "y"}
                    record.setdefault("settings", {})[key] = flag
                dm.audit("group_details_updated", session["user_id"], str(group_id),
                         f"{key}={str(value)[:120]}")
                dm.save()
                return self._json(200, {"ok": True, "message": f"{key} updated for group {group_id}."})
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/broadcast":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                code, payload = self._perform_broadcast(session, data)
                return self._json(code, payload)
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/group/action":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                code, payload = self._perform_group_action(session, data)
                return self._json(code, payload)
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/group/remove":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                if session["role"] != "master":
                    return self._json(403, {"ok": False, "message": "Master owner only."})
                try:
                    group_id = int(data.get("group_id"))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "Invalid group id."})
                removed = dm.unassign_group(ADMIN_ID, group_id)
                dm.audit("group_removed_from_dashboard", ADMIN_ID, str(group_id), "")
                if removed:
                    return self._json(200, {"ok": True, "message": f"Group {group_id} removed from dashboard."})
                return self._json(404, {"ok": False, "message": "Group was not assigned."})
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/owners/invite":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                if session["role"] != "master":
                    return self._json(403, {"ok": False, "message": "Master owner only."})
                invitee_id = data.get("user_id")
                if invitee_id not in (None, ""):
                    try:
                        invitee_id = int(invitee_id)
                    except (TypeError, ValueError):
                        return self._json(400, {"ok": False, "message": "Invalid user_id."})
                else:
                    invitee_id = None
                group_id = data.get("group_id")
                if group_id not in (None, ""):
                    try:
                        group_id = int(group_id)
                    except (TypeError, ValueError):
                        return self._json(400, {"ok": False, "message": "Invalid group_id."})
                else:
                    group_id = None
                token = dm.create_invitation(ADMIN_ID, invitee_id,
                                             str(data.get("username") or ""), group_id)
                record = dm.get_invitation(token) or {}
                dm.audit("web_owner_invite_issued", ADMIN_ID, str(group_id or ""),
                         f"invitee={invitee_id or data.get('username') or 'any'}")
                return self._json(200, {"ok": True, "token": token,
                                        "expires_at": record.get("expires_at") or ""})
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/owners/verify":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                if session["role"] != "master":
                    return self._json(403, {"ok": False, "message": "Master owner only."})
                try:
                    group_id = int(data.get("group_id"))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "Invalid group id."})
                ok = dm.verify_group(ADMIN_ID, group_id)
                return self._json(200 if ok else 400, {
                    "ok": bool(ok),
                    "message": (f"Group {group_id} verified." if ok
                                else "Group not found or verification failed."),
                })
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/schedule":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                try:
                    group_id = int(data.get("group_id"))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "Invalid group id."})
                if group_id not in session["group_ids"]:
                    return self._json(403, {"ok": False, "message": "This group is outside your scope."})
                text = str(data.get("text") or "").strip()[:2000]
                if not text:
                    return self._json(400, {"ok": False, "message": "Message text is required."})
                raw_at = str(data.get("send_at") or "").strip()
                try:
                    send_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False,
                                            "message": "send_at must be a valid ISO datetime."})
                now = datetime.now(send_at.tzinfo) if send_at.tzinfo else datetime.now()
                if send_at <= now:
                    return self._json(400, {"ok": False, "message": "send_at must be in the future."})
                items = dm.data.setdefault("scheduled_messages", [])
                if not isinstance(items, list):
                    items = dm.data["scheduled_messages"] = []
                task_id = secrets.token_hex(8)
                items.append({
                    "id": task_id, "at": datetime.now().isoformat(timespec="seconds"),
                    "actor_id": session["user_id"], "group_id": group_id,
                    "text": text, "send_at": send_at.isoformat(), "status": "pending",
                })
                dm.audit("web_schedule_created", session["user_id"], str(group_id),
                         f"id={task_id} send_at={send_at.isoformat()}")
                dm.save()
                return self._json(200, {
                    "ok": True, "id": task_id,
                    "note": "Delivery is queued for the bot loop; nothing has been sent yet.",
                })
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/schedule/remove":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                wanted = str(data.get("id") or "")
                items = dm.data.get("scheduled_messages") or []
                if not isinstance(items, list):
                    items = []
                match = next((item for item in items if isinstance(item, dict)
                              and str(item.get("id")) == wanted), None)
                if match is None:
                    return self._json(404, {"ok": False, "message": "Scheduled item not found."})
                if (session["role"] != "master"
                        and str(match.get("actor_id")) != str(session.get("user_id"))):
                    return self._json(403, {"ok": False, "message": "Not your scheduled item."})
                items.remove(match)
                dm.audit("web_schedule_removed", session["user_id"],
                         str(match.get("group_id") or ""), f"id={wanted}")
                dm.save()
                return self._json(200, {"ok": True, "message": "Scheduled item removed."})
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/lessons":
            try:
                session = self._auth()
                if not session:
                    return self._unauthorized()
                if session["role"] != "master":
                    return self._json(403, {"ok": False, "message": "Master owner only."})
                instruction = str(data.get("instruction") or "").strip()[:1000]
                if not instruction:
                    return self._json(400, {"ok": False, "message": "instruction is required."})
                draft = parse_learning_intent(instruction)
                if draft.get("action") in ("view", "empty"):
                    return self._json(400, {"ok": False, "message": "instruction must change a lesson."})
                if draft.get("action") == "add" and draft.get("steps"):
                    _append_web_lesson(instruction)
                else:
                    result = _execute_learning(draft.get("steps") or [])
                    if result.get("action") == "not_found":
                        return self._json(400, {"ok": False, "message": "No matching lesson found."})
                persona = load_persona()
                lessons = persona.get("learned_from_admin") or []
                if isinstance(lessons, str):
                    lessons = [lessons]
                if not isinstance(lessons, list):
                    lessons = []
                dm.audit("web_lesson_saved", session["user_id"], "persona.json",
                         f"action={draft.get('action')} lesson={instruction[:120]}")
                return self._json(200, {"ok": True, "lessons": lessons})
            except Exception as e:
                return self._json(500, {"ok": False, "message": str(e)[:300]})
        if path == "/api/ai/chat":
            return self._api_ai_chat(data)
        self._json(404, {"ok": False, "message": "Not found"})


def _test_ai_connection(data: dict) -> dict:
    return _test_openai_connection(data)


def _test_openai_connection(data: dict) -> dict:
    cfg = dm.get_ai_config()
    endpoint = (data.get("endpoint") or cfg.get("endpoint") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    if _is_masked_key(api_key):
        api_key = cfg.get("api_key") or ""
    model = (data.get("model") or cfg.get("model") or "").strip() or "gptoss-20b"
    url = _openai_chat_url(endpoint)
    if not url:
        return {"ok": False, "message": "Enter a custom API endpoint."}
    if not api_key:
        return {"ok": False, "message": "Enter an API key."}
    try:
        with httpx.Client(timeout=30) as http:
            res = http.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with the word pong only."}],
                    "max_tokens": 16,
                    "reasoning_effort": "none",
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
        if res.status_code >= 400:
            try:
                err = res.json().get("error", {})
                detail = err.get("message") if isinstance(err, dict) else str(err)
            except Exception:
                detail = res.text[:240]
            return {"ok": False, "message": f"Connection failed ({res.status_code}): {detail}"}
        payload = res.json()
        text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return {"ok": True, "message": f"Connected. Model responded: {text or 'ok'}"}
    except Exception as e:
        return {"ok": False, "message": f"Connection failed: {e}"}


def start_config_web_server():
    server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), ConfigPageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"🌐 Dashboard (auto-starting on the bot port): http://127.0.0.1:{WEB_PORT}", flush=True)
    print(f"🔗 Bot API on the same port: http://127.0.0.1:{WEB_PORT}/api  ·  health: /health", flush=True)
    threading.Thread(target=_start_dashboard, name="dashboard-launcher", daemon=True).start()


# ================= MAIN BOT START =================
async def capture_bot_app(app):
    """Give the HTTP server a safe bridge to the running bot."""
    global BOT_APP, BOT_LOOP
    BOT_APP = app
    BOT_LOOP = asyncio.get_running_loop()


async def configure_command_menu(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show available commands"),
        BotCommand("pdf", "Get the uploaded document"),
        BotCommand("document", "Get the uploaded document"),
        BotCommand("details", "Get the uploaded document"),
        BotCommand("panel", "Open admin controls"),
        BotCommand("learn", "Teach Ishani (admin only)"),
        BotCommand("search", "Free web search (DuckDuckGo)"),
        BotCommand("assign", "Invite a Group Owner (master only)"),
        BotCommand("mygroups", "See only your groups"),
        BotCommand("webtoken", "Get dashboard token (private)"),
        BotCommand("stop", "Stop the bot (admin only)"),
    ])


# ========== PATH B: OPTIONAL TELETHON USERBOT ==========
tg = None
_userbot_group_id = None
if TelegramClient and events and all((TG_API_ID, TG_API_HASH, TG_SESSION, GROUP_ID)):
    try:
        _userbot_group_id = int(GROUP_ID)
        tg = TelegramClient(StringSession(TG_SESSION), int(TG_API_ID), TG_API_HASH)
    except Exception as e:
        print(f"⚠️ Telethon userbot disabled: {e}", flush=True)
        tg = None


async def dm_new_member(user_id: int, name: str) -> bool:
    """One short first DM per new member; the Path A deep link remains the fallback."""
    if tg is None:
        return False
    sent = dm.data.setdefault("dm_sent", {})
    if str(user_id) in sent:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    counter = dm.data.get("dm_sent_day")
    if not isinstance(counter, dict) or counter.get("date") != today:
        counter = dm.data["dm_sent_day"] = {"date": today, "count": 0}
    if int(counter.get("count") or 0) >= 20:
        return False
    text = _render_template(random.choice(DM_WELCOME_MESSAGES), {"name": name or "Friend"})
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:1000]
    try:
        await tg.send_message(user_id, text)
        sent[str(user_id)] = datetime.now().isoformat(timespec="seconds")
        counter["count"] = int(counter.get("count") or 0) + 1
        dm.save()
        return True
    except Exception as e:
        print(f"DM fail {user_id}: {e}", flush=True)
        return False


if tg is not None:
    @tg.on(events.ChatAction(chats=[_userbot_group_id]))
    async def on_join(event):
        if not (event.user_joined or event.user_added):
            return
        user = await event.get_user()
        if not user or getattr(user, "bot", False):
            return
        # A person who leaves in the first minute is not a lead.
        await asyncio.sleep(random.randint(45, 60))
        try:
            member = await tg.get_permissions(_userbot_group_id, user.id)
            if not member:
                return
        except Exception:
            return
        await dm_new_member(user.id, getattr(user, "first_name", None) or "Friend")


async def post_init(app):
    """Run startup hooks; python-telegram-bot accepts one post_init callback."""
    await capture_bot_app(app)
    await configure_command_menu(app)
    if tg is not None:
        try:
            await tg.start()
        except Exception as e:
            print(f"⚠️ Telethon userbot could not start: {e}", flush=True)


if __name__ == "__main__":
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).post_init(post_init).build()
    
    # ===== COMMAND HANDLERS =====
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("panel", admin_panel_command))
    app.add_handler(CommandHandler("pdf", handle_pdf_request))
    app.add_handler(CommandHandler("document", handle_pdf_request))
    app.add_handler(CommandHandler("details", handle_pdf_request))
    app.add_handler(CommandHandler("learn", learn_command))
    app.add_handler(CommandHandler("assigngroup", assign_group_command))
    app.add_handler(CommandHandler("unassigngroup", unassign_group_command))
    app.add_handler(CommandHandler("grouppanel", group_panel_command))
    app.add_handler(CommandHandler("groupset", group_set_command))
    app.add_handler(CommandHandler("assign", assign_owner_command))
    app.add_handler(CommandHandler("accept", accept_invitation_command))
    app.add_handler(CommandHandler("registergroup", register_group_command))
    app.add_handler(CommandHandler("verifygroup", verify_group_command))
    app.add_handler(CommandHandler("mygroups", my_groups_command))
    app.add_handler(CommandHandler("owners", owners_command))
    app.add_handler(CommandHandler("webtoken", web_token_command))
    
    # ===== CALLBACK HANDLERS =====
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(tool_callback, pattern="^tool_"))
    
    # ===== MESSAGE HANDLERS =====
    # Panel search runs before the learning/broadcast/AI handlers.
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_panel_search), group=-3)
    # Run moderation first, then still allow the chat handler unless a message was removed.
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
        moderate_group,
    ), group=-1)
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_admin_learning), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_broadcast), group=-1)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_ai_chat))
    
    # ===== MEMBER HANDLERS =====
    app.add_handler(ChatMemberHandler(welcome_new_friend, ChatMemberHandler.CHAT_MEMBER))
    
    # ===== ERROR HANDLER =====
    app.add_error_handler(error_handler)
    
    # ===== SCHEDULED TASKS =====
    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError(
            'JobQueue is not available. Install with: pip install "python-telegram-bot[job-queue]==22.5"'
        )
    for hour in sorted(SCHEDULED_MESSAGES):
        job_queue.run_daily(
            scheduled_messages,
            time=time(hour=hour, minute=0),
            data={"hour": hour},
            name=f"scheduled_messages_{hour}",
        )
    # One lightweight ticker delivers reminders created by the scheduling tool.
    job_queue.run_repeating(
        _scheduled_job_ticker, interval=30, first=15, name="tool_scheduled_jobs",
    )
    
    start_config_web_server()
    print("🚀 Ishani Bot is Live!", flush=True)
    print(f"📝 Data file: data.json", flush=True)
    print(f"👤 Admin ID: {ADMIN_ID}", flush=True)
    print(f"✅ Ready to serve!", flush=True)
    print("=" * 50, flush=True)
    
    app.run_polling(allowed_updates=["chat_member", "message", "callback_query"])










