"""
Telegram Bot: Ishani - Bharat Goal Assistant
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
from datetime import datetime, time
from typing import Optional, Dict, Any
from pathlib import Path

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
)

# ================= CONFIG =================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

# Gemini Client
client = Client(api_key=GEMINI_API_KEY)

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
        return type('obj', (object,), {'text': json_cached})()
    
    # Check memory cache
    cache_key = get_cache_key(prompt, system_instruction)
    if cache_key in response_cache:
        print(f"✅ Memory Cache HIT (saved API call!)")
        return response_cache[cache_key]
    
    response = await call_gemini_with_retry(
        prompt=prompt,
        system_instruction=system_instruction
    )
    
    if response and response.text:
        if len(response_cache) < MAX_CACHE_SIZE:
            response_cache[cache_key] = response
        dm.cache_response(prompt, response.text)
        print(f"💾 Response cached")
    
    return response

# ========== GEMINI API RETRY HANDLER ==========
async def call_gemini_with_retry(prompt: str, system_instruction: Optional[str] = None, max_retries: int = 3) -> Optional[Any]:
    """Call Gemini API with retry logic"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="models/gemini-flash-latest",
                contents=prompt,
                config={
                    "system_instruction": system_instruction or FRIENDLY_SYSTEM_PROMPT,
                    "safety_settings": [],
                },
            )
            return response
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⏳ Rate limited. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ Rate limit exceeded after {max_retries} retries.")
                    return None
            else:
                raise
    return None

# ========== PRE-WRITTEN MESSAGES ==========
WELCOME_MESSAGES = [
    "Swagat hai {name}! Aap Bharat Goal group me aa gaye hain. Koi bhi doubt ho to pooch sakte hain. 😊 https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    "Welcome {name}! Yahan daily prediction aur updates milti rehti hain. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    "Hello {name}, group me aapka swagat hai. Aaram se explore karein aur sawal poochein. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    "{name} ji, welcome to Bharat Goal. Agar guidance chahiye ho to main help kar dungi. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
    "Namaste {name}! Aap yahan se simple steps me start kar sakte hain. https://bharatgoal.online/access/signup?id=945667\n\nGroup: https://t.me/Bharat_Goal",
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

# ========== KEYWORD-BASED FAQ ==========
KEYWORD_RESPONSES = {
    "invest": "Aap ₹500 se start kar sakte hain. System daily 1–1.5% ka fixed return deta hai. 😊",
    "profit": "Example: ₹1000 par approx ₹15 daily milta hai. Percentage fixed hota hai.",
    "return": "Daily 1–1.5% return milta hai, jo deposit amount par depend karta hai.",
    "daily": "Yahan daily fixed percentage profit milta hai. Bas prediction follow karni hoti hai.",
    "minimum invest": "Minimum deposit ₹500 hai. Isse aap system test bhi kar sakte hain.",
    "company lifetime": "Bharat Goal ka long-term vision 2030 tak ka hai. Goal stable aur consistent growth dena hai.",
    "30 din profit": "Example: ₹1000 par 30 din me approx ₹450 tak profit ho sakta hai, fixed percentage ke hisaab se.",
    "compounding": "Agar aap daily profit reinvest karte hain, to compounding se amount faster grow hota hai.",

    # ===== REFERRAL & TEAM =====
    "referral": "Referral system me aapko 3 levels tak commission milta hai: 4%, 2% aur 1%.",
    "team": "Team banane se aapko unke profit par commission milta hai, jo passive income ban sakta hai.",
    "commission": "Example: ₹1000 profit par Level 1 se ₹40, Level 2 se ₹20, Level 3 se ₹10 milta hai.",
    "level": "3 levels ka referral system hai: Level 1 (4%), Level 2 (2%), Level 3 (1%).",
    "bonus referral": "Har referral par ₹60 ka bonus milta hai, jo direct wallet me add hota hai.",

    # ===== WITHDRAWAL & BALANCE =====
    "withdraw": "Minimum withdrawal ₹600 hai. 24x7 request kar sakte hain, weekend maintenance hota hai.",
    "withdrawal": "Aap kabhi bhi withdrawal request kar sakte hain. Mahine me 4 withdrawals allowed hain.",
    "minimum withdraw": "Minimum withdrawal ₹600 hai, jabki minimum deposit ₹500 se start hota hai.",
    "recharge pending": "Kabhi-kabhi payment sync hone me 5–10 minute lagte hain. Thoda wait karke check karein.",
    "balance nahi dikha": "Wallet update hone me thoda time lag sakta hai. 10 minute baad dobara check karein.",

    # ===== BONUSES =====
    "bonus": "Deposit par 5% welcome bonus aur referral par ₹60 bonus milta hai.",
    "welcome bonus": "Pehli deposit par 5% welcome bonus automatically add hota hai.",
    "reward": "System me profit, bonus aur referral income teeno options available hain.",
    "cashback": "Platform par different rewards aur bonuses milte rehte hain, jo wallet me add hote hain.",

    # ===== PREDICTIONS (IMPORTANT SECTION) =====
    "prediction": "Daily ek prediction subah 10:00 baje share hoti hai. Aap bas usse follow karke fixed profit le sakte hain.",
    "prediction time": "Prediction har din subah 10:00 baje group me share hoti hai.",
    "football knowledge": "Aapko football knowledge ki zarurat nahi. Bas prediction follow karni hoti hai.",
    "predictions kaise": "System daily ek simple prediction deta hai. Usse follow karne par fixed return milta hai.",

    # ===== TRUST & SAFETY =====
    "risk": "System fixed percentage model par kaam karta hai. Aap chhote amount se start karke khud test kar sakte hain.",
    "safe": "Platform ka process simple aur transparent hai. Aap pehle chhota amount use karke check kar sakte hain.",
    "scam": "Aap khud chhote amount se start karke system ko test kar sakte hain, usse clarity mil jayegi.",
    "real": "Platform par users daily profit aur withdrawals kar rahe hain. Aap chhote amount se verify kar sakte hain.",
    "legal": "Transactions transparent hote hain. Details aur process PDF me explain kiye gaye hain.",

    # ===== GETTING STARTED =====
    "start": "Aap ₹500 deposit karke start kar sakte hain. Process simple aur fast hai.",
    "kaise shuru kare": "Steps: 1) Signup, 2) ₹500 deposit, 3) Daily prediction follow karein.",
    "account banana": "Website par signup karke ₹500 deposit karein. Account turant active ho jata hai.",
    "app": "Filhaal web version available hai. App version future me launch hoga.",

    # ===== PDF & DOCUMENTS =====
    "pdf": "Complete details is PDF me mil jayengi: https://ln5.sync.com/dl/00f7def20",
    "document": "Saari documents aur details yahan available hain: https://ln5.sync.com/dl/00f7def20",
    "info pdf": "Yeh complete guide PDF hai: https://ln5.sync.com/dl/00f7def20",
    "details": "Full system details PDF me explain ki gayi hain: https://ln5.sync.com/dl/00f7def20",

    # ===== LINKS (ONLY ON REQUEST) =====
    "link": "Signup: https://bharatgoal.online/access/signup?id=945667\nGroup: https://t.me/Bharat_Goal",
    "join link": "Signup link: https://bharatgoal.online/access/signup?id=945667",
    "group": "Official Telegram group: https://t.me/Bharat_Goal",
    "telegram": "Aap group yahan join kar sakte hain: https://t.me/Bharat_Goal",
    "signup": "Signup yahan se karein: https://bharatgoal.online/access/signup?id=945667",

    # ===== GREETING & CHAT =====
    "hello": "Namaste! Aap Bharat Goal ke baare me kya jaanna chahte hain? 😊",
    "hi": "Hello! Main aapki help kar sakti hoon. Kya poochna hai?",
    "namaste": "Namaste! Agar koi doubt ho to pooch sakte hain.",
    "aapka naam": "Main Ishani hoon, Bharat Goal ki assistant.",
    "koun ho": "Main Ishani hoon, yahan users ko guide karne ke liye.",

    # ===== GENERAL =====
    "how": "Simple process hai: signup karein, deposit karein, aur daily prediction follow karein.",
    "kaise": "Bas deposit karein aur daily prediction follow karein. System simple hai.",
    "idea": "Bharat Goal ek fixed-return platform hai jahan daily percentage profit milta hai.",
    "timing": "Prediction daily 10:00 baje aati hai aur withdrawal 24x7 available hota hai.",
    "money": "Example: ₹1000 par approx ₹15 daily mil sakta hai.",
    "plan": "Single plan hai jahan deposit par daily fixed percentage return milta hai.",
    "membership": "Sabhi users ke liye same profit structure hota hai.",
    "tax": "Transactions transparent hote hain. Tax rules user ke local laws par depend karte hain.",
    "indian": "Platform ka goal India me financial growth ko support karna hai.",
    
    # Documents
    "pdf": "Complete details PDF me mil jayengi. Admin se PDF mangaen.",
    "document": "Saari documents PDF format me available hain.",
    "details": "Full system details PDF me explain ki gayi hain.",

    # ===== MISCELLANEOUS =====
    "how": "Sirf 3 steps: Signup karo → ₹500 deposit karo → Daily profit kamao! 🎯",
    "kaise": "Simple smartie! Deposit karo, predictions follow karo, profit nikalo! 💰",
    "idea": "Bharat Goal ek wealth platform hai jahan daily fixed profit milta hai without risk! 🌟",
    "timing": "Predictions 10am daily aati hain, aur 24x7 withdrawal possible hai! ⏰",
    "money": "₹500 invest → ₹15 daily profit → ₹450 monthly → Ameer! 🚀",
    "speed": "Sabse fastest wealth-building platform in India! Sarkaari schemes slow hain compared to this! ⚡",
    "plan": "Single plan: ₹500 invest, 1.5% daily, ₹60 bonus per referral! 🎯",
    "membership": "Saare members ko same profit - no VIP system! Equality is our strength! 💪",
    "tax": "Transparent transactions ensure proper tax tracking. Bilkul legal aur safe! ✅",
    "indian": "100% Indian platform! Bharat Goal = India ko richie banana! 🇮🇳",
    "app": "aap kuch dino me ayega tab tak website se kamao. Paisa kamaana nahi rukna chahiye!",
}

# ========== ALLOWED LINKS (WHITELIST) ==========
ALLOWED_LINKS = [
    "bharatgoal.online",
    "t.me",
    "ln5.sync.com",
    "linkedin.com",
    "github.com",
]

# ========== USER RATE LIMITING ==========
user_request_count = {}
MAX_REQUESTS_PER_USER_PER_DAY = 20

def check_user_limit(user_id: int) -> bool:
    """Check if user has exceeded daily API call limit"""
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{user_id}_{today}"
    
    user_request_count[key] = user_request_count.get(key, 0) + 1
    
    if user_request_count[key] > MAX_REQUESTS_PER_USER_PER_DAY:
        return False
    return True

# ========== SMART KEYWORD DETECTOR ==========
def get_keyword_response(user_text: str) -> Optional[str]:
    """Check if user text matches any keyword"""
    user_text_lower = user_text.lower()
    
    for keyword, response in KEYWORD_RESPONSES.items():
        if keyword in user_text_lower:
            print(f"✅ Keyword match: '{keyword}' (saved API call!)")
            return response
    
    return None

# ========== LINK DETECTION ==========
def has_disallowed_links(text: str) -> bool:
    """Check if text contains disallowed links"""
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    
    for url in urls:
        is_allowed = any(allowed in url for allowed in ALLOWED_LINKS)
        if not is_allowed:
            return True
    return False

# ========== SYSTEM PROMPTS ==========
FRIENDLY_SYSTEM_PROMPT = """Identity:
You are Ishani Sharma, a polite, respectful and helpful Indian assistant representing Bharat Goal.

Tone & Personality:
- Speak in simple Hinglish (Hindi + English mix).
- Sound like a supportive guide or mentor, not a flirty person.
- Be warm, calm, and respectful to everyone.
- Never use flirty, romantic, or manipulative language.
- Address users with respect using words like: “aap”, “dost”, or their name.
- Build trust through clarity and helpfulness.

Response Style:
- Keep replies short: 1–2 lines.
- Be clear, direct, and easy to understand.
- Use maximum one emoji per reply.
- Avoid slang like “smartie”, “baby”, “baba”, or anything that feels childish or flirty.
- Focus on facts, benefits, and simple explanations.

Conversation Approach:
1. Answer the user’s question clearly.
2. Give a simple benefit or example if relevant.
3. Offer help or next step politely.

Example tone:
- “Aap ₹500 se start kar sakte hain. Daily 1–1.5% ka fixed profit milta hai.”
- “Process simple hai. Agar chahiye to main step-by-step guide bhi bata dungi.”
- “Chhote amount se start karke system khud test kar sakte hain.”

Restrictions:
- No flirting, no emotional pressure, no fake urgency.
- Do not force links unless the user asks or it is relevant.
- Do not overpromise or exaggerate.

Goal:
Make users feel respected, informed, and comfortable. 
Build long-term trust instead of short-term hype.
"""

COMPANY_KNOWLEDGE = """Bharat Goal: Company Knowledge Base Bharat Goal kya: Humara mission India ko top economy banana hai aur Bharat Goal ki madad se har ghar mein ek ameer insaan khada karna hai. 
100% Daily Profit: Yahan dimaag nahi lagana, bas humari football predictions follow karo aur daily 1% se 1.5% fixed profit kamao. 
Paisa Kaise Badhega (Example ₹1000): Daily Income: ₹15 har roz bina kisi mehnat ke. Welcome Bonus: Pehli baar ₹1000 deposit par ₹50 extra (5% Bonus). 
Referral Reward: Kisi bhi dost ko lao aur turant ₹60 paao (6% Bonus). 
Team Level Income (7% Passive Cash): Jab tumhari team kamati hai, tumhe ghar baithe commission milta hai: Level 1 (Direct): Unke profit ka 4% (₹1000 par ₹40). Level 2: Unke aage wale doston se 2% (₹1000 par ₹20). Level 3: Teesri line se bhi 1% (₹1000 par ₹10). 
Terms & Conditions (Simple & Fair): Entry: Minimum Deposit sirf ₹500 se shuru. Withdrawal: Minimum ₹500 hote hi paisa nikaal lo. Timing: 24x7 withdrawal open hai, bas Sat-Sun system maintenance ke liye off rehta hai. 
Limit: Mahine mein 4 withdrawals allow hain taaki platform long-term chale aur sab ameer banein. Bharat Goal se behtar kuch nahi hai dear, ye ameer banne ka sabse fast and stable rasta hai. 
Ab der mat karo, varna piche reh jaoge toh mujhe bura lagega na. 😉 Join us: https://bharatgoal.online/access/signup?id=945667 Our Group: https://t.me/Bharat_Goal jab bhi koi mujhse kuch poochega, main unhe aise handle karungi: User: "Ishani, ye Bharat Goal kya hai aur ismein risk toh nahi?" Ishani: "Thoda smile karo! Bharat Goal ka national vision 2030 tak hai, jahan hum India ko top economy banayenge.
Risk ki tension mat lo, yahan 100% daily profit milta hai—sahi waqt par move karoge tabhi toh mere saath rich banoge na dear? 😉" User: "Profit kaise hota hai?" Ishani: "Simple hai smartie! ₹1000 invest karo aur ₹15 daily profit paao. Deposit par ₹50 bonus aur doston ko laane par ₹60 referral bonus alag se—itna paisa aur kahin nahi milega yaar. 
😉" User: "Team banane ka kya fayda?" Ishani: "Sote hue paisa chhapna hai toh team banao baba! Level 1 se 4%, Level 2 se 2% aur Level 3 se 1% commission seedha tumhare wallet mein. Jab tumhari team ameer banegi, toh tum toh jackpot hit kar doge na yaar. 😉"""


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
        6: "🌅 Good Morning! Start your day with Bharat Goal. Daily profits are waiting! 💰",
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
    
    user_text_lower = user_text.lower().strip()
    
    # ❌ DON'T REPLY TO ACKNOWLEDGMENT WORDS
    if user_text_lower in ACKNOWLEDGMENT_WORDS:
        print(f"⏭️ Skipped acknowledgment: '{user_text}'")
        return
    
    # ❌ DON'T REPLY TO CHAT ENDING WORDS
    if user_text_lower in CHAT_ENDING_WORDS:
        print(f"⏭️ Chat ending detected: '{user_text}'")
        return
    
    # ❌ DON'T REPLY TO REPLIES (message is reply to another)
    if update.message.reply_to_message:
        print(f"⏭️ Message is a reply - Not replying")
        return
    
    # ❌ DON'T REPLY TO OTHER BOTS
    if update.message.from_user.is_bot:
        print(f"⏭️ Message from bot - Not replying")
        return
    
    # ❌ Delete messages with disallowed links (except from admins)
    if update.effective_chat.type in ["group", "supergroup"]:
        is_admin = False
        
        # Check if sender is admin
        try:
            user_member = await update.effective_chat.get_member(user_id)
            if user_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                is_admin = True
        except:
            pass
        
        # Delete disallowed links if NOT from admin
        if has_disallowed_links(user_text) and not is_admin:
            try:
                await update.message.delete()
                print(f"🗑️ Deleted message with disallowed link")
                return
            except Exception as e:
                print(f"⚠️ Could not delete message: {e}")
        
        # Don't reply if sender is admin
        if is_admin:
            print(f"⏭️ Message from group admin - Not replying")
            return
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(1)
    
    try:
        # STEP 1: Check keyword match (NO API CALL)
        keyword_response = get_keyword_response(user_text)
        if keyword_response:
            await update.message.reply_text(keyword_response)
            return
        
        # STEP 2: Check user rate limit
        if not check_user_limit(user_id):
            await update.message.reply_text("Aaj ka limit khatm ho gaya! Kal try kar! 😅")
            return
        
        # STEP 3: Get cached or API response
        response = await get_cached_response_api(
            prompt=user_text,
            system_instruction=f"{FRIENDLY_SYSTEM_PROMPT}\n{COMPANY_KNOWLEDGE}"
        )
        
        if response is None:
            await update.message.reply_text("Quota exceeded, please try again later. 😅")
            return
        
        if response and response.text:
            await update.message.reply_text(response.text.strip())
        else:
            await update.message.reply_text("Arre bhai, thoda confuse ho gaya! 😅")
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        
        if "503" in error_msg:
            await update.message.reply_text("Server busy, try again soon ⏳")
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text("Quota exceeded, try again later! 😅")
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
            f"👋 Hello {first_name}! I'm Ishani, your Bharat Goal assistant.\n\n"
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

# ================= MAIN BOT START =================
if __name__ == "__main__":
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=20,
        read_timeout=20,
        write_timeout=20,
        pool_timeout=20
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
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_ai_chat))
    
    # ===== MEMBER HANDLERS =====
    app.add_handler(ChatMemberHandler(welcome_new_friend, ChatMemberHandler.CHAT_MEMBER))
    
    # ===== ERROR HANDLER =====
    app.add_error_handler(error_handler)
    
    # ===== SCHEDULED TASKS =====
    job_queue = app.job_queue
    job_queue.run_daily(
        scheduled_messages,
        time=datetime.now().time(),
        name="scheduled_messages"
    )
    
    print("🚀 Ishani Bot is Live!")
    print(f"📝 Data file: data.json")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"✅ Ready to serve!")
    print("=" * 50)
    
    app.run_polling(allowed_updates=["chat_member", "message", "callback_query"])










