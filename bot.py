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
from google.genai import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

# Gemini Client (key from .env)
client = Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
GEMINI_DEFAULT_MODEL = "models/gemini-3.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"
MASKED_KEY = "••••••"


def _is_masked_key(value: str) -> bool:
    text = (value or "").strip()
    return not text or set(text) <= set("•*·.x")


def _mask_key(value: str) -> str:
    key = (value or "").strip()
    if len(key) < 8:
        return MASKED_KEY if key else ""
    return key[:4] + "…" + key[-4:]


def reload_gemini_key_from_env() -> str:
    """Re-read GEMINI_API_KEY from .env so Test Connection uses the live key."""
    global GEMINI_API_KEY, client
    load_dotenv(override=True)
    GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if GEMINI_API_KEY:
        client = Client(api_key=GEMINI_API_KEY)
    return GEMINI_API_KEY


def resolve_gemini_key(form_key: str = "") -> str:
    if form_key and not _is_masked_key(form_key):
        return form_key.strip()
    env_key = reload_gemini_key_from_env()
    if env_key:
        return env_key
    return (dm.get_ai_config().get("api_key") or "").strip()


def normalize_gemini_model(model: str) -> str:
    name = (model or "").strip() or GEMINI_DEFAULT_MODEL
    if not name.startswith("models/") and name.startswith("gemini"):
        return f"models/{name}"
    return name

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
                "provider": "gemini",
                "endpoint": "https://generativelanguage.googleapis.com",
                "api_key": "",
                "model": "models/gemini-3.5-flash"
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
        """AI provider settings (Gemini, OpenAI, or custom OpenAI-compatible)."""
        defaults = {
            "provider": "gemini",
            "endpoint": "https://generativelanguage.googleapis.com",
            "api_key": "",
            "model": "models/gemini-3.5-flash"
        }
        stored = self.data.get("ai_config") or {}
        merged = {**defaults, **stored}
        if not merged.get("provider"):
            merged["provider"] = "gemini"
        self.data["ai_config"] = merged
        return merged

    def save_ai_config(self, endpoint: str, api_key: str, model: str, provider: str = "gemini"):
        current = self.get_ai_config()
        current["provider"] = (provider or "gemini").strip().lower()
        current["endpoint"] = (endpoint or "").strip()
        if api_key and api_key.strip() and not _is_masked_key(api_key):
            current["api_key"] = api_key.strip()
        current["model"] = (model or "").strip()
        self.data["ai_config"] = current
        self.save()
        return current

    def uses_openai_compatible(self) -> bool:
        cfg = self.get_ai_config()
        provider = (cfg.get("provider") or "gemini").lower()
        return provider in ("custom", "openai") and bool(cfg.get("endpoint") and cfg.get("api_key"))

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
    # Check JSON cache first
    json_cached = dm.get_cached_response(prompt)
    if json_cached:
        print(f"✅ JSON Cache HIT (saved API call!)")
        return type('obj', (object,), {'text': clean_reply_text(json_cached)})()
    
    # Check memory cache
    cache_key = get_cache_key(prompt, system_instruction)
    if cache_key in response_cache:
        print(f"✅ Memory Cache HIT (saved API call!)")
        return response_cache[cache_key]
    
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
    r"^\s*(?:thinking process|thinking|analysis|reasoning)\s*:|^\s*\d+\.\s+\*\*analyze\b|^\s*<think\b",
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
        raw = re.sub(
            r"<\|channel\|>analysis<\|message\|>.*?(?=<\|start\|>|<\|channel\|>|$)",
            "",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )

    raw = re.sub(r"<think\b[^>]*>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<thinking\b[^>]*>.*?</thinking>", "", raw, flags=re.DOTALL | re.IGNORECASE)
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
    """Use the answer channel only. Reasoning fields are scratch work and stay hidden."""
    return final_chat_text(_content_to_text(message.get("content")))


def _fit_local_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """qwen3.5 on an 8GB GPU uses a 4096 context and drops prompts past ~2050 tokens."""
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
    model = (cfg.get("model") or "").strip() or "gpt-4o-mini"
    if not url or not api_key:
        raise RuntimeError("Custom AI provider is not configured")

    hidden = (
        "Send only the chat message. No thinking, no analysis, no 'The user says'."
    )
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
        return final_chat_text(_visible_model_text(message) or str(choices[0].get("text") or ""))

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


def generate_gemini_content(
    prompt: str,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
):
    key = (api_key or resolve_gemini_key()).strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing in .env")
    gemini_client = client if (client and key == GEMINI_API_KEY) else Client(api_key=key)
    model_name = normalize_gemini_model(model or dm.get_ai_config().get("model") or GEMINI_DEFAULT_MODEL)
    contents = prompt
    if history:
        lines = []
        for item in history:
            who = "Ishani" if item.get("role") == "bot" else "User"
            lines.append(f"{who}: {(item.get('text') or '').strip()}")
        contents = "Previous chat:\n" + "\n".join(lines) + "\n\nCurrent message:\n" + prompt
    return gemini_client.models.generate_content(
        model=model_name,
        contents=contents,
        config={
            "system_instruction": system_instruction or FRIENDLY_SYSTEM_PROMPT,
            "safety_settings": [],
        },
    )


async def call_ai_with_retry(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_retries: int = 3,
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Any]:
    """Call Gemini (default) or a saved OpenAI-compatible custom provider."""
    use_custom = dm.uses_openai_compatible()
    for attempt in range(max_retries):
        try:
            if use_custom:
                return await call_custom_openai(prompt, system_instruction, history=history)
            return generate_gemini_content(prompt, system_instruction, history=history)
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


call_gemini_with_retry = call_ai_with_retry

# ========== PRE-WRITTEN MESSAGES ==========
WELCOME_MESSAGES = [
    "Swagat hai {name}! Aap Chelsea Football group me aa gaye hain. Koi bhi doubt ho to pooch sakte hain. 😊 https://t.me/+Qv2p0w48dy81NDFl",
    # "Welcome {name}! Yahan daily prediction aur updates milti rehti hain. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    # "Hello {name}, group me aapka swagat hai. Aaram se explore karein aur sawal poochein. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    # "{name} ji, welcome to Chelsea Football. Agar guidance chahiye ho to main help kar dungi. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    # "Namaste {name}! Aap yahan se simple steps me start kar sakte hain. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
]

LEFT_MESSAGES = [
    "Goodbye {name}. Aapka time yahan achha raha hoga. Kabhi bhi wapas aa sakte hain.",
    "{name} group se chale gaye. Aapko future ke liye best wishes. 👋",
    "Take care {name}. Agar dobara join karna ho to welcome rahenge.",
]

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


# ========== KEYWORD-BASED FAQ ==========
KEYWORD_RESPONSES = {
"invest": "Aap ₹200 se start kar sakte hain. System daily 3–5% ka prediction match return deta hai. 😊",
"profit": "Daily 3% se 5% tak ka profit prediction matches ke through milta hai.",
"return": "Daily 3–5% return milta hai, jo prediction matches par depend karta hai.",
"daily": "Yahan daily 3% to 5% profit milta hai. Bas prediction follow karni hoti hai.",
"minimum invest": "Minimum deposit ₹200 hai. Isse aap system test bhi kar sakte hain.",
"company lifetime": "Chelsea Football ka goal long-term stable aur fast growth dena hai.",
"30 din profit": "Example: Daily 3% to 5% percentage ke hisaab se monthly achha compound profit ho sakta hai.",
"compounding": "Agar aap daily profit reinvest karte hain, to compounding se amount faster grow hota hai.",

# ===== REFERRAL & TEAM =====
"referral": "Referral system me har referral par 8% reward bonus milta hai[cite: 3].",
"team": "Team banane se aapko 6 levels tak team income milti hai[cite: 1], jo total 15% passive income ban sakti hai[cite: 1].",
"commission": "Level 1: 7%, Level 2: 3%, Level 3: 2%, Level 4: 1%, Level 5: 1%, Level 6: 1% commission milta hai[cite: 1].",
"level": "6 levels ka income system hai[cite: 1]: LV1 (7%), LV2 (3%), LV3 (2%), LV4 (1%), LV5 (1%), LV6 (1%)[cite: 1].",
"bonus referral": "Every referral par 8% reward bonus direct wallet me add hota hai[cite: 3].",

# ===== WITHDRAWAL & BALANCE =====
"withdraw": "Minimum withdrawal ₹500 hai[cite: 4]. Fast withdrawal options available hain[cite: 4, 5].",
"withdrawal": "Aap withdrawal request kar sakte hain[cite: 4]. Minimum withdrawal amount ₹500 hai[cite: 4].",
"minimum withdraw": "Minimum withdrawal ₹500 hai[cite: 4], jabki minimum deposit ₹200 se start hota hai[cite: 4].",
"recharge pending": "Kabhi-kabhi payment sync hone me 5–10 minute lagte hain. Fast transaction options available hain[cite: 4, 5].",
"balance nahi dikha": "Wallet update hone me thoda time lag sakta hai. 10 minute baad dobara check karein.",

# ===== BONUSES =====
"bonus": "Every deposit par 6% deposit bonus[cite: 2] aur referral par 8% reward bonus milta hai[cite: 3]. Total level income 15% hai[cite: 1].",
"welcome bonus": "Har deposit par 6% deposit bonus automatically add hota hai[cite: 2].",
"reward": "System me daily profit[cite: 5], 6% deposit bonus[cite: 2], 8% referral bonus[cite: 3] aur level income options available hain[cite: 1].",
"cashback": "Platform par different deposit bonuses (6%) aur referral rewards (8%) milte hain[cite: 2, 3].",

# ===== PREDICTIONS (IMPORTANT SECTION) =====
"prediction": "Daily live match predictions share hoti hain[cite: 2, 3, 5]. Aap bas unhe follow karke 3% to 5% daily profit le sakte hain[cite: 5].",
"prediction time": "Live matches predictions daily platform/group me share hoti hain[cite: 2, 3, 5].",
"football knowledge": "Aapko extra football knowledge ki zarurat nahi. Accurate predictions ko bas follow karna hota hai[cite: 2, 5].",
"predictions kaise": "System daily simple predictions deta hai[cite: 2, 5]. Unhe follow karne par 3–5% return milta hai[cite: 5].",

# ===== TRUST & SAFETY =====
"risk": "System prediction match model par kaam karta hai[cite: 2, 5]. Aap ₹200 se start karke khud test kar sakte hain[cite: 4].",
"safe": "Platform safe & secure transactions provide karta hai[cite: 1, 4, 5]. Aap pehle chhota amount (₹200) use karke check kar sakte hain[cite: 4].",
"scam": "Aap khud ₹200 minimum deposit se start karke system ko test kar sakte hain[cite: 4].",
"real": "Platform par multiple payment options (UPI, PhonePe, GPay, Paytm, USDT) transparently available hain[cite: 4].",
"legal": "Transactions safe, secure aur transparent hote hain[cite: 1, 4, 5].",

# ===== GETTING STARTED =====
"start": "Aap ₹200 deposit karke start kar sakte hain[cite: 4]. Process simple aur fast hai[cite: 4, 5].",
"kaise shuru kare": "Steps: 1) Join Now / Signup[cite: 1, 2, 3, 4, 5], 2) ₹200 deposit[cite: 4], 3) Daily match prediction follow karein[cite: 2, 5].",
"account banana": "Join now click karke ₹200 deposit karein[cite: 4]. Account turant active ho jata hai.",
"app": "Mobile app interface available hai for fast transactions and live betting predictions[cite: 4, 5].",

# ===== PDF & DOCUMENTS =====
"pdf": "Complete details Admin se mangaen.",
"document": "Saari documents aur details Admin dwara available ki jati hain.",
"info pdf": "Yeh complete guide PDF Admin se praapt karein.",
"details": "Full system details PDF me explain ki gayi hain.",

# ===== LINKS (ONLY ON REQUEST) =====
"link": "Signup link ke liye Join Now button click karein ya Admin se mangayein[cite: 1, 2, 3, 4, 5].",
"join link": "Signup link: Click Join Now button on website[cite: 1, 2, 3, 4, 5].",
"group": "Official Telegram group join karein.",
"telegram": "Aap official Telegram group join kar sakte hain.",
"signup": "Signup link ke zariye Join Now karein[cite: 1, 2, 3, 4, 5].",

# ===== GREETING & CHAT =====
"hello": "Namaste! Aap Chelsea Football platform ke baare me kya jaanna chahte hain? 😊",
"hi": "Hello! Main aapki help kar sakti hoon. Kya poochna hai?",
"namaste": "Namaste! Agar koi doubt ho to pooch sakte hain.",
"aapka naam": "Main Ishani hoon, Chelsea Football ki assistant.",
"koun ho": "Main Ishani hoon, yahan users ko guide karne ke liye.",

# ===== GENERAL =====
"how": "Simple process hai: signup karein, ₹200 deposit karein[cite: 4], aur daily prediction follow karein[cite: 2, 5].",
"kaise": "Bas ₹200 deposit karein[cite: 4] aur daily match prediction follow karein[cite: 2, 5]. System simple hai.",
"idea": "Chelsea Football ek prediction platform hai jahan daily 3% se 5% percentage profit milta hai[cite: 5].",
"timing": "Predictions live matches par hoti hain[cite: 2, 3, 5] aur instant/fast processing options available hain[cite: 4, 5].",
"money": "Deposit par 6% bonus[cite: 2] aur daily 3–5% match prediction return milta hai[cite: 5].",
"plan": "Deposit par 6% bonus[cite: 2], daily 3–5% profit[cite: 5], aur 6-level total 15% income structure hai[cite: 1].",
"membership": "Sabhi users ke liye same transparent system aur rewards hote hain[cite: 1, 4].",
"tax": "Multiple payment channels available hain (UPI, Bank Transfer, USDT)[cite: 4].",
"indian": "UPI, Paytm, PhonePe, GPay jaise Indian payment gateways supported hain[cite: 4].",

# Documents
"pdf": "Complete details PDF me mil jayengi. Admin se PDF mangaen.",
"document": "Saari documents PDF format me available hain.",
"details": "Full system details PDF me explain ki gayi hain.",

# ===== MISCELLANEOUS =====
"how": "Sirf 3 steps: Join Now[cite: 1, 2, 3, 4, 5] → ₹200 deposit karo[cite: 4] → Daily profit kamao! 🎯[cite: 5]",
"kaise": "Simple! Deposit karo[cite: 4], predictions follow karo[cite: 2, 5], profit nikalo! 💰[cite: 4]",
"idea": "Chelsea Football ek sports prediction platform hai jahan daily fixed percentage profit milta hai! 🌟[cite: 5]",
"timing": "Live match predictions daily aati hain[cite: 2, 3, 5], aur fast withdrawal possible hai! ⏰[cite: 4, 5]",
"money": "₹200 minimum invest[cite: 4] → 6% deposit bonus[cite: 2] → 3-5% daily profit! 🚀[cite: 5]",
"speed": "Fast transaction and instant processing platform! ⚡[cite: 4, 5]",
"plan": "Single plan: ₹200 min deposit[cite: 4], 3–5% daily profit[cite: 5], 8% per referral reward[cite: 3]! 🎯",
"membership": "Saare members ke liye 6-level referral income system available hai! 💪[cite: 1]",
"tax": "Transparent payment methods: UPI, GPay, PhonePe, Bank Transfer & USDT! ✅[cite: 4]",
"indian": "UPI & Indian bank transfers supported! 🇮🇳[cite: 4]",
"app": "Mobile app UI available hai fast deposit/withdrawal aur predictions ke liye! 📱[cite: 4, 5]",


}
KEYWORD_RESPONSES = {k: clean_reply_text(v) for k, v in KEYWORD_RESPONSES.items()}

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


def load_persona() -> Dict[str, Any]:
    try:
        with PERSONA_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("master_prompt"):
            return data
    except Exception as e:
        print(f"⚠️ persona.json load error: {e}")
    return {
        "name": "Ishani Sharma",
        "age": 23,
        "master_prompt": "You are Ishani Sharma, a 23-year-old Indian girl chatting in Hinglish.",
        "company": {},
    }


def company_brief(persona: Optional[Dict[str, Any]] = None) -> str:
    company = (persona or load_persona()).get("company") or {}
    facts = company.get("facts") or []
    steps = company.get("join_steps") or []
    lines = [
        f"Company: {company.get('name') or 'Chelsea Football'}",
        company.get("role") or "",
        "END GOAL (this is the destination of every chat, without sounding like an ad):",
        company.get("end_goal") or "Get them to join Chelsea Football, then start with ₹200 and follow predictions.",
        f"Join link: {company.get('join_link') or 'https://t.me/+Qv2p0w48dy81NDFl'}",
        "Join then what:",
        *[f"- {item}" for item in steps],
        "Facts:",
        *[f"- {item}" for item in facts],
        company.get("rule") or "",
    ]
    return "\n".join(part for part in lines if part)


def persona_system_prompt() -> str:
    persona = load_persona()
    return (persona.get("master_prompt") or "").strip()


FRIENDLY_SYSTEM_PROMPT = persona_system_prompt()
COMPANY_KNOWLEDGE = company_brief()


def chat_display_name(record: Dict[str, Any], first_name: str) -> str:
    mem = record.get("memory") or {}
    raw = (mem.get("preferred_name") or record.get("name") or first_name or "tum").strip()
    raw = re.sub(r"\s+(sir|ji)$", "", raw, flags=re.IGNORECASE).strip()
    return raw or "tum"


def build_personal_system(user_id: int, first_name: str, history: List[Dict[str, str]], compact: bool = False) -> str:
    persona = load_persona()
    record = dm.load_chat(user_id, first_name)
    mem = record.get("memory") or {}
    name = chat_display_name(record, first_name)
    memory_lines = [
        f"Talking to: {name}",
        f"About them: {mem.get('about') or 'Abhi intro collect ho raha hai. Telegram display name ignore karo if they told a first name.'}",
        f"Things they talked about: {', '.join(mem.get('topics') or []) or 'fresh chat'}",
        f"Right now they are on: {mem.get('last_focus') or '-'}",
    ]
    if compact:
        # Local models drop the long persona and then answer without the company facts.
        return "\n".join([
            "You are Ishani Sharma, 23, on Telegram. Talk in natural Hinglish, like a girl in the chat, not like an essay or a call-center script.",
            "Read the whole thread, understand the latest message, then send only the reply. Never write your reasoning.",
            "Never write lines such as 'The user says', 'They want to know', 'Probably ask', or 'The assistant should'.",
            "Hello or hi: one short greeting and one short question. No extra lines.",
            "If the message is unclear, ask one short Hinglish question. Do not list every possible meaning.",
            "When they ask about Chelsea Football, joining, earning, deposit, withdrawal, referral, or the app, answer only from the company facts below. Do not invent numbers, links, or steps.",
            "Teach one next step at a time, in simple lines, like to a beginner. Use a short numbered list and a few emojis only when they asked how to do something. Do not explain the whole company in one message.",
            *memory_lines,
            company_brief(persona),
        ])
    return "\n".join([
        (persona.get("master_prompt") or FRIENDLY_SYSTEM_PROMPT).strip(),
        company_brief(persona),
        *memory_lines,
        "Reply only to the latest user message, but with full thread memory, like ChatGPT.",
        "Feel like a real girl sitting on the other side of the phone.",
        "Length: 1 or 2 short lines. Add a third line only when the user asked for steps or a list. No filler, no headings, no repeat of their message.",
        "If the message is unclear, incomplete, or could mean two things, do not guess. Ask one short question to confirm what they mean.",
        "Soft end-goal: after trust/vibe, invite them to JOIN Chelsea Football, then ₹200 start, then follow predictions. One natural nudge is enough — not every message.",
    ])


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
        await query.edit_message_text("📁 Please send the PDF document to upload.")
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
    """Handle document upload from admin"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.user_data.get('awaiting_document'):
        return
    
    if update.message.document:
        file_id = update.message.document.file_id
        dm.set_pdf_file_id(file_id)
        await update.message.reply_text("✅ Document uploaded successfully!")
        context.user_data['awaiting_document'] = False
    else:
        await update.message.reply_text("❌ Please send a valid document.")

# ========== BROADCAST HANDLER ==========
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast from admin"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.user_data.get('awaiting_broadcast'):
        return
    
    broadcast_message = update.message.text
    stats = dm.get_stats()
    stats['total_broadcasts'] += 1
    dm.save()
    
    await update.message.reply_text(
        f"✅ Broadcast recorded: {broadcast_message}\n"
        f"(Note: Manual implementation of bulk message sending required)"
    )
    context.user_data['awaiting_broadcast'] = False

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
        "• /stop - Stop the bot\n\n"
        "<i>Just ask questions or send messages for instant replies!</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode="HTML")

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
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    history = dm.recent_chat(user_id, first_name, limit=24)
    dm.append_chat(user_id, first_name, "user", user_text)
    personal_system = build_personal_system(
        user_id,
        first_name,
        history,
        compact=dm.uses_openai_compatible(),
    )
    
    try:
        response = await call_ai_with_retry(
            prompt=user_text,
            system_instruction=personal_system,
            history=history,
        )
        
        if response is None:
            await update.message.reply_text("Server busy, try again soon ⏳")
            return
        
        reply = clean_reply_text(response.text) if response and response.text else ""
        if reply:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            await update.message.reply_text(reply)
            dm.append_chat(user_id, first_name, "bot", reply)
        else:
            await update.message.reply_text("Arre bhai, thoda confuse ho gaya! 😅")
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        
        if "503" in error_msg:
            print("⏳ 503 UNAVAILABLE — waiting 10 seconds before sending...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            await asyncio.sleep(10)
            try:
                retry_response = await call_gemini_with_retry(
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
            await update.message.reply_text("Server busy, try again soon ⏳")
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text("Server busy, try again soon ⏳")
        else:
            await update.message.reply_text("Technical issue, please try again 🙏")

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
            ai_text = random.choice(WELCOME_MESSAGES).format(name=user_name)
        
        # CASE 2: MEMBER LEFT/KICKED
        elif old_status == "member" and new_status in ["left", "kicked"]:
            ai_text = random.choice(LEFT_MESSAGES).format(name=user_name)
        
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
async def handle_pdf_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF, document, or details requests"""
    
    file_id = dm.get_pdf_file_id()
    
    if not file_id:
        await update.message.reply_text(
            "📄 Document not available yet. Please contact admin."
        )
        return
    
    try:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=file_id
        )
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
    <div class="note" id="note">Gemini uses GEMINI_API_KEY from your .env file</div>
    <label>AI Provider:</label>
    <select id="provider">
      <option value="gemini">Gemini (Google)</option>
      <option value="openai">OpenAI</option>
      <option value="custom">Custom Provider</option>
    </select>
    <label id="endpoint_label">API Endpoint:</label>
    <input id="endpoint" placeholder="https://generativelanguage.googleapis.com">
    <label>API Key:</label>
    <input id="api_key" type="password" placeholder="from .env">
    <label>Model Name:</label>
    <input id="model" placeholder="models/gemini-3.5-flash">
    <div class="hint" id="hint">Leave empty for provider default</div>
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
function applyProvider() {
  const p = document.getElementById('provider').value;
  const endpoint = document.getElementById('endpoint');
  const key = document.getElementById('api_key');
  const model = document.getElementById('model');
  const note = document.getElementById('note');
  const hint = document.getElementById('hint');
  if (p === 'gemini') {
    endpoint.value = 'https://generativelanguage.googleapis.com';
    endpoint.disabled = true;
    if (!key.value) key.value = '••••••';
    if (!model.value || model.value.includes('gpt')) model.value = 'models/gemini-3.5-flash';
    note.textContent = 'Gemini uses GEMINI_API_KEY from your .env file';
    hint.textContent = 'Test Connection reads the key from .env automatically';
  } else {
    endpoint.disabled = false;
    note.textContent = 'Free users must use their own API keys';
    hint.textContent = 'Leave empty for provider default';
    if (p === 'openai') {
      endpoint.value = 'https://api.openai.com/v1/chat/completions';
      if (!model.value || model.value.includes('gemini')) model.value = 'gpt-4o-mini';
    }
  }
}
document.getElementById('provider').onchange = applyProvider;
async function load() {
  const r = await fetch('/api/config'); const d = await r.json();
  document.getElementById('provider').value = d.provider || 'gemini';
  document.getElementById('endpoint').value = d.endpoint || '';
  document.getElementById('api_key').value = d.has_key ? '••••••' : '';
  document.getElementById('model').value = d.model || '';
  applyProvider();
}
function body() {
  return {
    provider: document.getElementById('provider').value,
    endpoint: document.getElementById('endpoint').value,
    api_key: document.getElementById('api_key').value,
    model: document.getElementById('model').value
  };
}
document.getElementById('test').onclick = async () => {
  msg('Testing...', true);
  const r = await fetch('/api/test', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body()) });
  const d = await r.json();
  msg(d.message || (d.ok ? 'Connected' : 'Failed'), !!d.ok);
};
document.getElementById('save').onclick = async () => {
  const r = await fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body()) });
  const d = await r.json();
  msg(d.message || (d.ok ? 'Saved' : 'Save failed'), !!d.ok);
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
            provider = (cfg.get("provider") or "gemini").lower()
            env_key = reload_gemini_key_from_env()
            has_key = bool(env_key) if provider == "gemini" else bool(cfg.get("api_key"))
            endpoint = GEMINI_ENDPOINT if provider == "gemini" else cfg.get("endpoint", "")
            model = cfg.get("model") or (GEMINI_DEFAULT_MODEL if provider == "gemini" else "")
            self._json(200, {
                "ok": True,
                "provider": provider,
                "endpoint": endpoint,
                "model": model,
                "has_key": has_key,
                "key_source": "env" if provider == "gemini" and env_key else "saved",
                "key_hint": _mask_key(env_key) if provider == "gemini" else "",
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
            provider = (data.get("provider") or "gemini").lower()
            dm.save_ai_config(
                endpoint=data.get("endpoint", ""),
                api_key=data.get("api_key", ""),
                model=data.get("model", ""),
                provider=provider,
            )
            if provider == "gemini":
                message = "Gemini saved. The bot will use GEMINI_API_KEY from .env."
            else:
                message = "Provider saved. The bot will use this OpenAI-compatible API."
            self._json(200, {"ok": True, "message": message})
            return
        if path == "/api/test":
            self._json(200, _test_ai_connection(data))
            return
        self._json(404, {"ok": False, "message": "Not found"})


def _test_ai_connection(data: dict) -> dict:
    cfg = dm.get_ai_config()
    provider = (data.get("provider") or cfg.get("provider") or "gemini").strip().lower()
    if provider == "gemini":
        return _test_gemini_connection(data)
    return _test_openai_connection(data)


def _test_gemini_connection(data: dict) -> dict:
    api_key = resolve_gemini_key(data.get("api_key", ""))
    if not api_key:
        return {"ok": False, "message": "GEMINI_API_KEY is missing in .env"}
    model = normalize_gemini_model(data.get("model") or dm.get_ai_config().get("model") or GEMINI_DEFAULT_MODEL)
    try:
        response = generate_gemini_content(
            prompt="Reply with the word pong only.",
            system_instruction="Reply with a single word.",
            api_key=api_key,
            model=model,
        )
        text = (getattr(response, "text", None) or "").strip()
        return {
            "ok": True,
            "message": f"Gemini connected using .env key {_mask_key(api_key)}. Model {model} responded: {text or 'ok'}",
        }
    except Exception as e:
        return {"ok": False, "message": f"Gemini connection failed: {e}"}


def _test_openai_connection(data: dict) -> dict:
    cfg = dm.get_ai_config()
    endpoint = (data.get("endpoint") or cfg.get("endpoint") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    if _is_masked_key(api_key):
        api_key = cfg.get("api_key") or ""
    model = (data.get("model") or cfg.get("model") or "").strip() or "gpt-4o-mini"
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
if __name__ == "__main__":
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()
    
    # ===== COMMAND HANDLERS =====
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("panel", admin_panel_command))
    app.add_handler(CommandHandler("pdf", handle_pdf_request))
    app.add_handler(CommandHandler("document", handle_pdf_request))
    app.add_handler(CommandHandler("details", handle_pdf_request))
    
    # ===== CALLBACK HANDLERS =====
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # ===== MESSAGE HANDLERS =====
    # Run moderation first, then still allow the chat handler unless a message was removed.
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
        moderate_group,
    ), group=-1)
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document_upload))
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










