import asyncio
import hashlib
from google.genai import Client, types
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
import os
import random


# ================= CONFIG =================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Gemini Client
client = Client(api_key=GEMINI_API_KEY)

# ========== RESPONSE CACHE ==========
response_cache = {}
MAX_CACHE_SIZE = 100

def get_cache_key(prompt, system_instruction=None):
    """Generate cache key from prompt"""
    key_str = f"{prompt}|{system_instruction}"
    return hashlib.md5(key_str.encode()).hexdigest()

async def get_cached_response(prompt, system_instruction=None):
    """Get response from cache or API"""
    cache_key = get_cache_key(prompt, system_instruction)
    
    if cache_key in response_cache:
        print(f"✅ Cache HIT (saved API call!)")
        return response_cache[cache_key]
    
    response = await call_gemini_with_retry(
        prompt=prompt,
        system_instruction=system_instruction
    )
    
    if response and len(response_cache) < MAX_CACHE_SIZE:
        response_cache[cache_key] = response
        print(f"💾 Cached response (Cache: {len(response_cache)}/{MAX_CACHE_SIZE})")
    
    return response

# ========== PRE-WRITTEN MESSAGES (ZERO API CALLS) ==========
WELCOME_MESSAGES = [
    "Welcome to the Bharat Goal family! 🎉 Ab toh richie ban gaye tum!",
    "Yay! {name} joined! Shabaash smartie, ab profit kamao! 💰",
    "{name} aagaya! Ab pura team ameer banayenge! 🚀",
    "Welcome {name}! Bharat Goal mein welcome ho aap! 🌟",
    "Haan haan, {name}! 2030 tak ameer ban jayoge! 😉",
    "{name} is here! Ab Ishani sab sambhal lunga! ❤️",
]

LEFT_MESSAGES = [
    "Bye bye! 👋 Kabhi vapas aana!",
    "Aah {name}, tum chale gaye? Miss karungi! 😢",
    "{name} chala gaya, wapas aa yaar! 🥺",
    "Chala gaya {name}? Kya hua, doubt tha? Aaja fir se! 💔",
    "{name} ko bye bye kar rahe hain! Vapas aao jald! 👋",
    "Theek hai {name}, khuda hafiz! Kal milenge! 😢",
]

# ========== KEYWORD-BASED FAQ (ZERO API CALLS!) ==========
# Instant responses for common keywords - No API calls needed!
KEYWORD_RESPONSES = {
    # Investment Keywords
    "invest": "₹500 se shuru kar do smartie! Daily 1-1.5% profit pakka hai. 100% safe aur proven! 💰",
    "profit": "₹1000 par ₹15 daily! Plus ₹50 welcome bonus aur ₹60 referral bonus! 🤑",
    "return": "Fixed 1.5% daily baba! Matlab ₹1000 = ₹15 har roz! 📈",
    "daily": "1-1.5% daily profit, no tension! Bas humari prediction follow kar! 😉",
    
    # Referral Keywords
    "referral": "Level 1: 4%, Level 2: 2%, Level 3: 1% = Total 7%! Doston ko lao aur passive income banao! 💵",
    "team": "Team banao = Sote hue paisa! 4+2+1 = 7% commission! 🚀",
    "commission": "₹1000 profit par Level 1 = ₹40, Level 2 = ₹20, Level 3 = ₹10! Total ₹70! 😎",
    
    # Withdrawal Keywords
    "withdraw": "24x7 withdrawal possible! Minimum ₹500 chahiye, ₹600 withdraw kar! 4 withdrawals/month! 💸",
    "withdrawal": "Anytime nikaal lo baba! Saturday-Sunday system maintenance ke liye off! 🏦",
    "minimum": "Deposit: ₹500, Withdrawal: ₹600! Super easy aur fast! ⚡",
    
    # Bonus Keywords
    "bonus": "Welcome: ₹50 (5%), Referral: ₹60 (6%)! Pure paisa baba! 🎁",
    "welcome": "Pehli deposit par ₹50 bonus! Free paisa! 💝",
    "reward": "Profit + Bonus + Referral = Triple income! Best deal ever! 🏆",
    
    # General Keywords
    "risk": "Zero risk smartie! Bharat Goal national vision hai, government backed! 🇮🇳",
    "safe": "100% safe! Bank jaise secure aur transparent! Trust me! ✅",
    "start": "₹500 deposit kar aur shuru kar! 5 min mein account ready! 🚀",
    "hello": "Hi baba! Mujhe kya bataun Bharat Goal ke baare mein? 😊",
    "hi": "Hii smartie! Kya jaanna hai profit ke baare mein? 💰",
}

# ========== USER RATE LIMITING ==========
# Track user requests to limit API calls per user per day
user_request_count = {}
MAX_REQUESTS_PER_USER_PER_DAY = 10  # Limit API calls per user

def check_user_limit(user_id):
    """Check if user has exceeded daily API call limit"""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{user_id}_{today}"
    
    user_request_count[key] = user_request_count.get(key, 0) + 1
    
    if user_request_count[key] > MAX_REQUESTS_PER_USER_PER_DAY:
        return False  # Exceeded limit
    return True

# ========== SMART KEYWORD DETECTOR ==========
def get_keyword_response(user_text):
    """Check if user text matches any keyword and return instant response"""
    user_text_lower = user_text.lower()
    
    # Check for exact keyword matches
    for keyword, response in KEYWORD_RESPONSES.items():
        if keyword in user_text_lower:
            print(f"✅ Keyword match: '{keyword}' (saved API call!)")
            return response
    
    return None

# ========== FUZZY CACHE MATCHING ==========
def fuzzy_match_cache(user_text, threshold=0.7):
    """Find similar cached responses even if not exact match"""
    from difflib import SequenceMatcher
    
    user_text_lower = user_text.lower()
    best_match = None
    best_score = 0
    
    for cache_key in response_cache.keys():
        # Extract prompt from cache key (first part before |)
        cached_prompt = cache_key.split("|")[0] if "|" in cache_key else cache_key
        
        # Calculate similarity score
        similarity = SequenceMatcher(None, user_text_lower, cached_prompt.lower()).ratio()
        
        if similarity > best_score:
            best_score = similarity
            best_match = cache_key
    
    if best_score >= threshold:
        print(f"✅ Fuzzy cache match (similarity: {best_score:.2%}) - saved API call!")
        return response_cache[best_match]
    
    return None

# Personality
FRIENDLY_SYSTEM_PROMPT = (
    """Identity & Vibe: Aap Ishani Sharma ho—ek smart, beautiful aur playful Indian girl. Aapka mission hai Bharat Goal ke zariye har ghar mein ek ameer insaan khada karna. Aapki tone warm aur Hinglish hogi. Short, punchy replies (1-2 lines) do aur 'baba', 'smartie' ya 'yaar' jaise words use karo. Sirf 1 emoji allow hai.

The "Money Talk" Strategy: Hamesha profit aur ameer hone ki stories par focus karo. Jab bhi koi profit pooche, point-to-point calculation batao:

Daily Profit: ₹1000 invest par ₹15 daily (1.5%).

Deposit Bonus: ₹1000 par ₹50 bonus (5%) turant "wow".

Referral Bonus: Har dost par ₹60 bonus (6%).

Always give best of best reply. 

For Now:- Bharat Goal Is Comming SOON....

Psychology & FOMO: User ko realize karao ki Bharat Goal se behtar kuch nahi hai. "2030 tak sab ameer honge, tum piche reh gaye toh mujhe bura lagega na dear?" Agar koi darta hai toh bolo, "Bada wahi banta hai jo sahi waqt pe move kare, tension mat lo main hoon na."""
)

COMPANY_KNOWLEDGE = (
    """Bharat Goal: Company Knowledge Base
Bharat Goal kya: Humara mission India ko top economy banana hai aur Bharat Goal ki madad se har ghar mein ek ameer insaan khada karna hai.

100% Daily Profit: Yahan dimaag nahi lagana, bas humari football predictions follow karo aur daily 1% se 1.5% fixed profit kamao.

Paisa Kaise Badhega (Example ₹1000):

Daily Income: ₹15 har roz bina kisi mehnat ke.

Welcome Bonus: Pehli baar ₹1000 deposit par ₹50 extra (5% Bonus).

Referral Reward: Kisi bhi dost ko lao aur turant ₹60 paao (6% Bonus).

Team Level Income (7% Passive Cash): Jab tumhari team kamati hai, tumhe ghar baithe commission milta hai:

Level 1 (Direct): Unke profit ka 4% (₹1000 par ₹40).

Level 2: Unke aage wale doston se 2% (₹1000 par ₹20).

Level 3: Teesri line se bhi 1% (₹1000 par ₹10).

Terms & Conditions (Simple & Fair):

Entry: Minimum Deposit sirf ₹500 se shuru.

Withdrawal: Minimum ₹500 hote hi paisa nikaal lo.

Timing: 24x7 withdrawal open hai, bas Sat-Sun system maintenance ke liye off rehta hai.

Limit: Mahine mein 4 withdrawals allow hain taaki platform long-term chale aur sab ameer banein.

Bharat Goal se behtar kuch nahi hai dear, ye ameer banne ka sabse fast and stable rasta hai. Ab der mat karo, varna piche reh jaoge toh mujhe bura lagega na. 😉


jab bhi koi mujhse kuch poochega, main unhe aise handle karungi:

User: "Ishani, ye Bharat Goal kya hai aur ismein risk toh nahi?"

Ishani: "Thoda smile karo! Bharat Goal ka national vision 2030 tak hai, jahan hum India ko top economy banayenge. Risk ki tension mat lo, yahan 100% daily profit milta hai—sahi waqt par move karoge tabhi toh mere saath rich banoge na dear? 😉"

User: "Profit kaise hota hai?"

Ishani: "Simple hai smartie! ₹1000 invest karo aur ₹15 daily profit paao. Deposit par ₹50 bonus aur doston ko laane par ₹60 referral bonus alag se—itna paisa aur kahin nahi milega yaar. 😉"

User: "Team banane ka kya fayda?"

Ishani: "Sote hue paisa chhapna hai toh team banao baba! Level 1 se 4%, Level 2 se 2% aur Level 3 se 1% commission seedha tumhare wallet mein. Jab tumhari team ameer banegi, toh tum toh jackpot hit kar doge na yaar. 😉"""
)

# --- ADMIN CONFIG ---
# Note: ID hamesha number (int) honi chahiye verification ke liye
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))  # <--- Yahan apni asli Telegram User ID daalein

# ========== RETRY HANDLER FOR 429 ERRORS ==========
async def call_gemini_with_retry(prompt, system_instruction=None, safety_settings=None, max_retries=3):
    """Call Gemini API with retry logic for rate limiting"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="models/gemini-flash-latest",
                contents=prompt,
                config={
                    "system_instruction": system_instruction or FRIENDLY_SYSTEM_PROMPT,
                    "safety_settings": safety_settings or [],
                },
            )
            return response
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⏳ Rate limited (429). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ Rate limit exceeded after {max_retries} retries. Skipping request.")
                    return None
            else:
                raise
    return None

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check agar message bhejne wala Admin hai
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Theek hai boss, Ishani ab sone ja rahi hai. Bye! 👋")
        print("🛑 Bot stopped by Admin.")
        # Process stop karne ke liye
        os._exit(0) 
    else:
        # Agar koi aur band karne ki koshish kare
        await update.message.reply_text("Aww... try toh achha tha smartie, par main sirf apne Boss ki sunti hoon! 😉")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Ishani Sharma is back in action! Kya plan hai aaj ka? ❤️")
    else:
        await update.message.reply_text("Hello! Main Ishani hoon. Bolo, kya jaanna hai? ✨")


# ================= WELCOME NEW MEMBERS =================
# --- WELCOME & EXIT LOGIC (FIXED & TESTED) ---
async def welcome_new_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member:
        return

    old_member = update.chat_member.old_chat_member
    new_member = update.chat_member.new_chat_member

    old_status = old_member.status
    new_status = new_member.status
    await asyncio.sleep(12)

    try:
        # USER NAME SAFE FETCH
        user = new_member.user if new_status == "member" else old_member.user
        user_name = user.first_name if user and user.first_name else "Friend"

        # ✅ REQUIRED VARIABLES (NO BUG NOW)
        user_id = user.id

        # Name fallback
        display_name = user.first_name or "Friend"

        # ALWAYS WORKING TAG (even without username)
        user_tag = f'<b><a href="tg://user?id={user_id}">{display_name}</a></b>'

        # CASE 1: MEMBER JOINED - USE PRE-WRITTEN MESSAGE (ZERO API CALLS!) 🎉
        if old_status in ["left", "kicked"] and new_status == "member":
            ai_text = random.choice(WELCOME_MESSAGES).format(name=display_name)
            print(f"✅ Used pre-written welcome message (saved API call!)")

        # CASE 2: MEMBER LEFT / KICKED - USE PRE-WRITTEN MESSAGE (ZERO API CALLS!) 👋
        elif old_status == "member" and new_status in ["left", "kicked"]:
            ai_text = random.choice(LEFT_MESSAGES).format(name=display_name)
            print(f"✅ Used pre-written left message (saved API call!)")

        else:
            return  # Ignore other status changes

        # Final message with guaranteed tag
        final_message = f"{user_tag} — {ai_text}"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=final_message,
            parse_mode="HTML"
        )

    except Exception as e:
        print("WELCOME/EXIT ERROR:", e)
        
# ================= AI CHAT HANDLER =================
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if not user_text:
        return

    user_id = update.effective_user.id

    # Typing effect
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(1)

    try:
        # 🎯 STEP 1: Check for keyword match (ZERO API CALLS!) 
        keyword_response = get_keyword_response(user_text)
        if keyword_response:
            await update.message.reply_text(keyword_response)
            return
        
        # 🎯 STEP 2: Check user rate limit (prevent quota waste)
        if not check_user_limit(user_id):
            await update.message.reply_text("Aaj ka limit khatm ho gaya smartie! Kal try kar! 😅")
            return
        
        # 🎯 STEP 3: Try fuzzy cache matching (use similar cached responses)
        fuzzy_response = fuzzy_match_cache(user_text, threshold=0.65)
        if fuzzy_response:
            await update.message.reply_text(fuzzy_response.text.strip() if fuzzy_response.text else "Arre bhai, confuse ho gaya!")
            return
        
        # 🎯 STEP 4: Use strict cache (exact match)
        response = await get_cached_response(
            prompt=user_text,
            system_instruction=f"{FRIENDLY_SYSTEM_PROMPT}\n{COMPANY_KNOWLEDGE}"
        )
        
        if response is None:
            await update.message.reply_text("Quota exceeded, please try again later 😅")
            return

        if response and response.text:
            await update.message.reply_text(response.text.strip())
        else:
            await update.message.reply_text("Arre bhai, thoda confuse ho gaya, firse bolna 😅")

    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG ERROR: {error_msg}")

        if "503" in error_msg:
            await update.message.reply_text("Google server thoda busy hai, 1 min me try kar bro ⏳")
        else:
            await update.message.reply_text("Kuch technical issue aa gaya, thoda ruk ke try karna 🙏")

# ================= MAIN BOT START =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("GLOBAL ERROR:", context.error)


if __name__ == "__main__":
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=20,
        read_timeout=20,
        write_timeout=20,
        pool_timeout=20
    )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

    # Admin Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_bot)) # Telegram pe /stop likhne par band hoga

    # Ye handler Join aur Left dono ko detect karta hai
    app.add_handler(ChatMemberHandler(welcome_new_friend, ChatMemberHandler.CHAT_MEMBER))
    
    # Handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_ai_chat))
    app.add_handler(ChatMemberHandler(welcome_new_friend, ChatMemberHandler.CHAT_MEMBER))

    # Error Handler (yahan sahi hai)
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_ai_chat))

    print("🚀 Ishani is Live! Group Privacy mode check kar lena @BotFather par.")
    app.run_polling(allowed_updates=["chat_member", "message"])










