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

import asyncio
import hashlib
import json
import os
import random
import re
import threading
from datetime import datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
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
        self.data = self._load_data()
    
    def _load_data(self) -> Dict[str, Any]:
        """Load data from JSON file, create if doesn't exist"""
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
    
    def _save_data(self, data: Dict[str, Any]):
        """Save data to JSON file"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error saving JSON: {e}")
    
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
        if not merged.get("model") or merged["model"].strip().lower() == "qwen3.5:4b":
            merged["model"] = defaults["model"]
        self.data["ai_config"] = merged
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
        self.CHAT_DIR.mkdir(exist_ok=True)
        return self.CHAT_DIR / f"{int(user_id)}.json"

    def load_chat(self, user_id: int, first_name: str = "User") -> Dict[str, Any]:
        path = self._chat_file(user_id)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "sections" in data:
                    pref = ((data.get("memory") or {}).get("preferred_name") or "").strip()
                    if pref:
                        data["name"] = pref
                    elif not data.get("name") and first_name:
                        data["name"] = first_name
                    data["telegram_name"] = first_name
                    return data
            except Exception as e:
                print(f"⚠️ Chat load error {user_id}: {e}")
        return {
            "user_id": int(user_id),
            "name": first_name or "User",
            "memory": {"about": "", "topics": [], "last_focus": ""},
            "sections": {},
        }

    def save_chat(self, record: Dict[str, Any]):
        user_id = record.get("user_id")
        if user_id is None:
            return
        sections = record.get("sections") or {}
        flat: List[tuple] = []
        for day in sorted(sections.keys()):
            for msg in sections.get(day) or []:
                flat.append((day, msg))
        if len(flat) > self.MAX_CHAT_MESSAGES:
            keep = flat[-self.MAX_CHAT_MESSAGES:]
            trimmed: Dict[str, List] = {}
            for day, msg in keep:
                trimmed.setdefault(day, []).append(msg)
            record["sections"] = trimmed
        try:
            with self._chat_file(user_id).open("w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Chat save error {user_id}: {e}")

    def append_chat(self, user_id: int, first_name: str, role: str, text: str) -> Dict[str, Any]:
        record = self.load_chat(user_id, first_name)
        pref = ((record.get("memory") or {}).get("preferred_name") or "").strip()
        record["name"] = pref or record.get("name") or first_name or "User"
        record["telegram_name"] = first_name
        day = datetime.now().strftime("%Y-%m-%d")
        record.setdefault("sections", {}).setdefault(day, []).append({
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

    def recent_chat(self, user_id: int, first_name: str = "User", limit: int = 24) -> List[Dict[str, str]]:
        """Full recent thread (ChatGPT-style), oldest first."""
        record = self.load_chat(user_id, first_name)
        messages: List[Dict[str, str]] = []
        for day in sorted((record.get("sections") or {}).keys()):
            messages.extend(record["sections"].get(day) or [])
        return messages[-limit:]

    @staticmethod
    def _refresh_memory(record: Dict[str, Any], user_text: str):
        mem = record.setdefault("memory", {"about": "", "topics": [], "last_focus": "", "preferred_name": ""})
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

# Initialize data manager
dm = DataManager("data.json")

# ========== RESPONSE CACHE (IN-MEMORY) ==========
response_cache = {}
MAX_CACHE_SIZE = 100

def get_cache_key(prompt: str, system_instruction: Optional[str] = None) -> str:
    """Generate cache key from prompt"""
    key_str = f"{prompt.lower().strip()}|{system_instruction}"
    return hashlib.md5(key_str.encode()).hexdigest()

async def get_cached_response_api(prompt: str, system_instruction: Optional[str] = None) -> Optional[Any]:
    """Get response from cache (JSON or memory) or call API"""
    # Replies depend on persona and conversation context, so avoid text-only cache hits.
    cache_key = get_cache_key(prompt, system_instruction)
    
    response = await call_ai_with_retry(
        prompt=prompt,
        system_instruction=system_instruction
    )
    
    if response and response.text:
        cleaned = clean_reply_text(response.text)
        response = type('obj', (object,), {'text': cleaned})()
        if len(response_cache) < MAX_CACHE_SIZE:
            response_cache[cache_key] = response
        dm.cache_response(prompt, cleaned)
        print(f"💾 Response cached")
    
    return response

# ========== AI PROVIDER (custom OpenAI-compatible, else Gemini) ==========
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
    raw = re.sub(r"(?<=[a-z])\.(?=[A-Z])", ".\n", raw)
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


def _fit_local_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Keep prompts compact for local model context limits."""
    system = []
    rest = []
    for item in messages:
        if item.get("role") == "system":
            content = item.get("content") or ""
            if len(content) > 2800:
                content = content[:2100].rstrip() + "\n...\n" + content[-500:]
            system.append({"role": "system", "content": content})
        else:
            content = (item.get("content") or "").strip()
            if content:
                rest.append({"role": item.get("role") or "user", "content": content[:700]})
    return system + rest[-6:]


async def call_custom_openai(
    prompt: str,
    system_instruction: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
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
        role = "assistant" if item.get("role") == "bot" else "user"
        content = (item.get("text") or "").strip()
        if role == "assistant":
            content = final_chat_text(content)
        if content:
            messages.append({"role": role, "content": content})
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
        return body

    def _reply_from_openai(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _visible_model_text(message)

    async def _ask(http: httpx.AsyncClient, temperature: float) -> str:
        if "api.openai.com" not in url:
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
                try:
                    message = (native.json() or {}).get("message") or {}
                except Exception:
                    message = {}
                if message:
                    return final_chat_text(str(message.get("content") or ""))
        res = await http.post(url, headers=headers, json=_openai_payload(temperature, True))
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code == 400:
            res = await http.post(url, headers=headers, json=_openai_payload(temperature, False))
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code >= 400:
            err = data.get("error", {})
            msg = err.get("message") if isinstance(err, dict) else str(err) or res.text
            raise RuntimeError(f"Custom AI {res.status_code}: {msg}")
        return _reply_from_openai(data)

    async with httpx.AsyncClient(timeout=90) as http:
        text = await _ask(http, 0.8)
        if not text:
            print("⚠️ Model returned only thinking. Asking again with thinking off.", flush=True)
            text = await _ask(http, 0.4)
        return _simple_text_response(text)


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
    """Read welcome/left messages from persona.json with safe fallbacks."""
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
    )


WELCOME_MESSAGES, LEFT_MESSAGES = load_prewritten_messages()


def company_brief(persona: Optional[Dict[str, Any]] = None) -> str:
    """Build the company fact block from the persona.json company_brief template."""
    source = persona if isinstance(persona, dict) else load_persona()
    company = source.get("company") if isinstance(source, dict) else None
    if not isinstance(company, dict):
        company = {}

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


def build_personal_system(user_id: int, first_name: str, history: List[Dict[str, str]], compact: bool = False) -> str:
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
    values = {
        "name": name,
        "about": mem.get("about") or defaults.get("about") or "",
        "topics": ", ".join(mem.get("topics") or []) or defaults.get("topics") or "fresh chat",
        "focus": mem.get("last_focus") or defaults.get("focus") or "-",
    }
    memory_lines = [
        _format_memory_line(labels.get("talking_to", "Talking to: {name}"), **values),
        _format_memory_line(labels.get("about", "About them: {about}"), **values),
        _format_memory_line(labels.get("topics", "Things they talked about: {topics}"), **values),
        _format_memory_line(labels.get("focus", "Right now they are on: {focus}"), **values),
    ]

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
        learning_block = "Admin ki learned instructions:\n" + "\n".join(f"- {item}" for item in learned if isinstance(item, str) and item.strip()) if learned else ""
        parts = [*compact_lines, learning_block, *memory_lines, company_brief(persona)]
    else:
        parts = [
            (persona.get("master_prompt") or FRIENDLY_SYSTEM_PROMPT).strip(),
            company_brief(persona),
            *memory_lines,
            *full_lines,
        ]
    return "\n".join(part for part in parts if part)


# ================= ADMIN PANEL =================
async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with inline buttons"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("📄 Upload Document", callback_data="admin_upload"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🔇 Mute Bot", callback_data="admin_mute"),
            InlineKeyboardButton("🔊 Unmute Bot", callback_data="admin_unmute")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎛️ <b>Admin Panel</b>\n\nChoose an action:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Admin only!")
        return
    
    action = query.data
    
    if action == "admin_upload":
        await query.edit_message_text("📁 Send a PDF, document, or photo. Add a caption describing what it contains so I can send the right file when users ask.")
        context.user_data['awaiting_document'] = True
    
    elif action == "admin_broadcast":
        await query.edit_message_text("📝 Send the message to broadcast to all users.")
        context.user_data['awaiting_broadcast'] = True
    
    elif action == "admin_mute":
        dm.set_bot_muted(True)
        await query.edit_message_text("🔇 Bot muted successfully.")
    
    elif action == "admin_unmute":
        dm.set_bot_muted(False)
        await query.edit_message_text("🔊 Bot unmuted successfully.")
    
    elif action == "admin_stats":
        stats = dm.get_stats()
        users_count = len(dm.data['users'])
        stats_text = (
            f"📊 <b>Bot Statistics</b>\n\n"
            f"Total Messages: {stats.get('total_messages', 0)}\n"
            f"Total Users: {users_count}\n"
            f"Total Broadcasts: {stats.get('total_broadcasts', 0)}"
        )
        await query.edit_message_text(stats_text, parse_mode="HTML")

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
        "• /details - Get the uploaded document\n\n"
        "<b>Admin Commands:</b>\n"
        "• /panel - Open admin panel\n"
        "• /learn <code>instruction</code> - Teach Ishani (admin only)\n"
        "• /stop - Stop the bot\n\n"
        "<i>Just ask questions or send messages for instant replies!</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode="HTML")


def _save_persona_learning(lesson: str):
    persona = load_persona()
    learned = persona.setdefault("learned_from_admin", [])
    if isinstance(learned, str):
        learned = persona["learned_from_admin"] = [learned]
    if lesson not in learned:
        learned.append(lesson)
    with PERSONA_PATH.open("w", encoding="utf-8") as f:
        json.dump(persona, f, indent=2, ensure_ascii=False)


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("❌ Admin only!")
        return
    lesson = " ".join(context.args).strip()
    if not lesson:
        context.user_data["awaiting_learning"] = True
        await update.effective_message.reply_text("Tell me what to learn in your next message, or use /learn <instruction>.")
        return
    _save_persona_learning(lesson)
    await update.effective_message.reply_text("✅ Samajh gayi, yaad rakhungi. persona.json mein save kar diya.")


async def handle_admin_learning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.effective_user.id == ADMIN_ID and context.user_data.get("awaiting_learning")
            and update.effective_message and update.effective_message.text):
        _save_persona_learning(update.effective_message.text.strip())
        context.user_data["awaiting_learning"] = False
        await update.effective_message.reply_text("✅ Samajh gayi, yaad rakhungi. persona.json mein save kar diya.")
        raise ApplicationHandlerStop

# ================= SCHEDULED MESSAGES =================
async def scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Send automatic messages based on time of day"""
    if dm.is_bot_muted():
        return
    
    current_hour = datetime.now().hour
    
    messages = {
        6: "🌅 Good Morning! Start your day with Chealsea Football. Daily profits are waiting! 💰",
        12: "☀️ Midday check-in! Remember to follow today's prediction for your daily profit! 📈",
        18: "🌆 Good Evening! Don't forget to check your earnings and share with friends! 👥",
        22: "🌙 Good Night! Rest well and come back tomorrow for more profits! 😴",
    }
    
    if current_hour not in messages:
        return
    
    message = messages[current_hour]
    
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=message)
        except Exception as e:
            print(f"⚠️ Could not send scheduled message: {e}")

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


def _message_is_abuse_or_threat(message) -> bool:
    """Gaali or a threat aimed at a person or a company. A complaint is not abuse."""
    text = message.text or message.caption or ""
    return bool(_ABUSE_OR_THREAT.search(text))


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
        return
    if _message_is_abuse_or_threat(message):
        print(f"🗑️ Deleted abuse or threat from {user.id}", flush=True)
        await _delete_and_verify(message)
        raise ApplicationHandlerStop
    if _message_has_link(message) or _message_has_inline_buttons(message):
        await _delete_and_verify(message)
        raise ApplicationHandlerStop


# ================= MESSAGE HANDLERS =================
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler with improved logic"""
    
    # Check if bot is muted
    if dm.is_bot_muted():
        return
    
    user_text = update.message.text
    if not user_text:
        return
    
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "User"
    
    # Update user tracking
    dm.update_user(user_id, first_name)
    
    # ❌ DON'T REPLY TO REPLIES (message is reply to another) — groups only
    if update.message.reply_to_message and update.effective_chat.type in ["group", "supergroup"]:
        print(f"⏭️ Message is a reply - Not replying")
        return
    
    # Other bots stay silent. People, including group admins, get a reply.
    if update.message.from_user.is_bot:
        print("⏭️ Group or private bot - Not replying", flush=True)
        return
    
    # For non-bot messages in groups
    if not update.message.from_user.is_bot and update.effective_chat.type not in ["group", "supergroup"]:
        print(f"Processing private message from user {user_id}")
    
    # ❌ DON'T REPLY TO OTHER BOTS (double check for private messages)
    if update.message.from_user.is_bot:
        print(f"⏭️ Message from bot - Not replying")
        return
    
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
            await send_media_asset(context.bot, update.effective_chat.id, asset)
            dm.append_chat(user_id, first_name, "user", user_text)
            dm.append_chat(user_id, first_name, "bot", f"Sent file: {asset.get('name') or asset.get('kind', 'file')}")
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    history = dm.recent_chat(user_id, first_name, limit=24)
    dm.append_chat(user_id, first_name, "user", user_text)
    personal_system = build_personal_system(
        user_id,
        first_name,
        history,
        compact=dm.uses_openai_compatible(),
    )
    if has_media_type:
        personal_system += "\nIf the user asks for a file that is not among the files actually sent in this chat, say it is not available yet and suggest asking the admin. Never claim you attached or sent a file unless the bot actually sent it."
    
    try:
        response = await call_ai_with_retry(
            prompt=user_text,
            system_instruction=personal_system,
            history=history,
        )
        
        if response is None:
            await update.message.reply_text(user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            ))
            return
        
        reply = clean_reply_text(response.text) if response and response.text else ""
        if reply:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            await update.message.reply_text(reply)
            dm.append_chat(user_id, first_name, "bot", reply)
        else:
            await update.message.reply_text(user_language_notice(
                user_text, "Sorry, I didn't quite catch that. Could you say it another way?",
                "Sorry yaar, main samajh nahi paayi 😅 Ek baar aur bataoge?",
                "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई 😅 एक बार फिर बताएँगे?",
            ))
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        
        if "503" in error_msg:
            print("⏳ 503 UNAVAILABLE — waiting 10 seconds before sending...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            await asyncio.sleep(10)
            try:
                retry_response = await call_ai_with_retry(
                    prompt=user_text,
                    system_instruction=personal_system,
                    history=history,
                )
                reply = clean_reply_text(retry_response.text) if retry_response and retry_response.text else ""
                if reply:
                    dm.append_chat(user_id, first_name, "bot", reply)
                    await update.message.reply_text(reply)
                    return
            except Exception as retry_error:
                print(f"❌ ERROR after 10s wait: {retry_error}")
            await update.message.reply_text(user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            ))
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text(user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            ))
        else:
            await update.message.reply_text(user_language_notice(
                user_text, "I hit a small technical issue. Please try again in a moment 🙏",
                "Chhota sa technical issue aa gaya yaar, ek minute baad try karna 🙏",
                "तकनीकी दिक्कत आ गई है, एक मिनट बाद फिर कोशिश कीजिए 🙏",
            ))

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
        
        # CASE 1: MEMBER JOINED
        if old_status in ["left", "kicked"] and new_status == "member":
            ai_text = _render_template(random.choice(WELCOME_MESSAGES), {"name": user_name})
        
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
            parse_mode="HTML"
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

# ================= CUSTOM AI WEB PAGE + UPTIMEROBOT HEALTH =================
WEB_PORT = int(os.environ.get("WEB_PORT") or os.environ.get("PORT") or "8080")
CONFIG_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Custom AI Configuration</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh;
    font-family: Inter, Segoe UI, system-ui, sans-serif;
    background: #07080f;
    color: #eef0ff;
    display: flex; align-items: center; justify-content: center;
    padding: 24px;
  }
  .card {
    width: 100%; max-width: 460px;
    background: #12141f;
    border: 1px solid #2a2d44;
    border-radius: 16px;
    padding: 22px;
  }
  h1 { font-size: 20px; margin: 0 0 16px; }
  .note {
    background: #161b33;
    border: 1px solid #3d4aa8;
    color: #c9d2ff;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 13px;
    margin-bottom: 18px;
  }
  label { display: block; font-size: 13px; font-weight: 600; margin: 12px 0 6px; }
  input, select {
    width: 100%;
    background: #0b0c14;
    color: #fff;
    border: 1px solid #2b2e45;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
  }
  input:disabled { opacity: 0.75; }
  .hint { color: #7d829a; font-size: 12px; margin-top: 6px; }
  .btn {
    width: 100%; margin-top: 18px; padding: 12px;
    border-radius: 10px; cursor: pointer; font-weight: 700;
    background: #0b0c14; color: #fff;
    border: 1px solid transparent;
    background-image: linear-gradient(#0b0c14,#0b0c14), linear-gradient(90deg,#3b82f6,#a855f7,#ec4899);
    background-origin: border-box; background-clip: padding-box, border-box;
  }
  .save { margin-top: 10px; background: #1d4ed8; border: 0; color: #fff; border-radius: 10px; padding: 11px; width: 100%; font-weight: 700; cursor: pointer; }
  .msg { margin-top: 12px; font-size: 13px; min-height: 18px; }
  .ok { color: #4ade80; } .err { color: #f87171; }
  .uptime {
    margin-top: 18px; padding-top: 14px; border-top: 1px solid #2a2d44;
    font-size: 13px; color: #b8bdd6;
  }
  a { color: #93c5fd; }
  code { background: #0b0c14; padding: 2px 6px; border-radius: 6px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Custom AI Configuration</h1>
    <div class="note" id="note">Configure your local OpenAI-compatible model server.</div>
    <label>Local API Endpoint:</label>
    <input id="endpoint" placeholder="http://127.0.0.1:11434/v1">
    <label>API Key:</label>
    <input id="api_key" type="password" placeholder="Local server API key">
    <label>Model Name:</label>
    <input id="model" placeholder="gptoss-20b" autocomplete="off">
    <div class="hint" id="hint">Enter the exact model name installed in your local model server.</div>
    <button class="btn" id="test">Test Connection</button>
    <button class="save" id="save">Save Provider</button>
    <div class="msg" id="msg"></div>
    <div class="uptime">
      <b>UptimeRobot</b> checks this site at <code id="health"></code><br>
      Add an HTTP(s) monitor (5 min) on
      <a href="https://uptimerobot.com/" target="_blank" rel="noopener">uptimerobot.com</a>
      using that URL so this page stays watched continuously.
    </div>
  </div>
<script>
const msg = (t, ok) => { const el = document.getElementById('msg'); el.textContent = t; el.className = 'msg ' + (ok ? 'ok' : 'err'); };
document.getElementById('health').textContent = location.origin + '/health';
async function load() {
  try {
    const r = await fetch('/api/config', {cache:'no-store'});
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.message || 'Could not load configuration');
    document.getElementById('endpoint').value = d.endpoint || 'http://127.0.0.1:11434/v1';
    document.getElementById('api_key').value = d.has_key ? '••••••' : '';
    document.getElementById('model').value = d.model || 'gptoss-20b';
  } catch (e) { msg('Could not load settings: ' + e.message, false); }
}
function body() {
  return {
    endpoint: document.getElementById('endpoint').value,
    api_key: document.getElementById('api_key').value,
    model: document.getElementById('model').value
  };
}
document.getElementById('test').onclick = async () => {
  msg('Testing...', true);
  try { const r = await fetch('/api/test', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body()) });
    const d = await r.json(); msg(d.message || (d.ok ? 'Connected' : 'Failed'), !!r.ok && !!d.ok);
  } catch (e) { msg('Connection test failed: ' + e.message, false); }
};
document.getElementById('save').onclick = async () => {
  const save = document.getElementById('save');
  const values = body();
  if (!values.endpoint.trim() || !values.model.trim()) { msg('Endpoint and model name are required.', false); return; }
  save.disabled = true; msg('Saving...', true);
  try {
    const r = await fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(values) });
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.message || 'Save failed');
    msg('Saved model ' + d.model + '.', true);
  } catch (e) { msg('Save failed: ' + e.message, false); }
  finally { save.disabled = false; }
};
load();
</script>
</body>
</html>
"""


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
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self._send(code, raw, "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, CONFIG_PAGE.encode("utf-8"))
            return
        if path == "/health":
            self._json(200, {"status": "ok", "service": "ishani-bot", "uptime_monitor": "uptimerobot"})
            return
        if path == "/api/config":
            cfg = dm.get_ai_config()
            self._json(200, {
                "ok": True,
                "endpoint": cfg.get("endpoint") or "http://127.0.0.1:11434/v1",
                "model": cfg.get("model") or "gptoss-20b",
                "has_key": bool(cfg.get("api_key")),
            })
            return
        self._json(404, {"ok": False, "message": "Not found"})

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path in ("/", "/health", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if path == "/health" else "text/html; charset=utf-8")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except Exception:
            self._json(400, {"ok": False, "message": "Invalid JSON"})
            return
        if path == "/api/config":
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
            self._json(200, _test_ai_connection(data))
            return
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
    print(f"🌐 Custom AI page: http://127.0.0.1:{WEB_PORT}/", flush=True)
    print(f"⏱ UptimeRobot URL: http://127.0.0.1:{WEB_PORT}/health", flush=True)


# ================= MAIN BOT START =================
async def configure_command_menu(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show available commands"),
        BotCommand("pdf", "Get the uploaded document"),
        BotCommand("document", "Get the uploaded document"),
        BotCommand("details", "Get the uploaded document"),
        BotCommand("panel", "Open admin controls"),
        BotCommand("learn", "Teach Ishani (admin only)"),
        BotCommand("stop", "Stop the bot (admin only)"),
    ])


if __name__ == "__main__":
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).post_init(configure_command_menu).build()
    
    # ===== COMMAND HANDLERS =====
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("panel", admin_panel_command))
    app.add_handler(CommandHandler("pdf", handle_pdf_request))
    app.add_handler(CommandHandler("document", handle_pdf_request))
    app.add_handler(CommandHandler("details", handle_pdf_request))
    app.add_handler(CommandHandler("learn", learn_command))
    
    # ===== CALLBACK HANDLERS =====
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # ===== MESSAGE HANDLERS =====
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
    job_queue.run_daily(
        scheduled_messages,
        time=datetime.now().time(),
        name="scheduled_messages"
    )
    
    start_config_web_server()
    print("🚀 Ishani Bot is Live!", flush=True)
    print(f"📝 Data file: data.json", flush=True)
    print(f"👤 Admin ID: {ADMIN_ID}", flush=True)
    print(f"✅ Ready to serve!", flush=True)
    print("=" * 50, flush=True)
    
    app.run_polling(allowed_updates=["chat_member", "message", "callback_query"])










