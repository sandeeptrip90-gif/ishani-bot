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
    "Welcome to the Bharat Goal family! 🎉 Ab toh richie ban gaye tum! Apne link chahiye toh pooch lena!",
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

# ========== WORDS TO IGNORE (NO RESPONSE NEEDED) ==========
ACKNOWLEDGMENT_WORDS = {
    "ok", "okay", "k", "thanks", "thank you", "thankyou", "thanks beta",
    "thanks baba", "done", "theek hai", "shukriya", "sab theek hai", 
    "samajh gaya", "samajh gaye", "accha", "achi baat hai", "bilkul",
    "bilkul baba", "bilkul smartie", "understood", "got it", "yes", "haan",
    "bilkul haan", "thik hai", "thik h", "alright", "cool", "nice"
}

# ========== CHAT ENDING WORDS (DON'T REPLY) ==========
CHAT_ENDING_WORDS = {
    "bye", "goodbye", "bye bye", "khuda hafiz", "alvida", "see you",
    "bye baba", "bye smartie", "tc", "take care", "later", "see ya",
    "cya", "bye friend", "goodbye friend", "jao", "chalo bye", "adios",
    "farewell", "goodbye ishani", "bye ishani", "jaata hoon", "ja raha hoon",
    "exit", "quit", "stop", "band karo", "enough"
}

# ========== KEYWORD-BASED FAQ (ZERO API CALLS!) ==========
# Instant responses for common keywords - No API calls needed!
KEYWORD_RESPONSES = {
    # ===== INVESTMENT & PROFIT =====
    "invest": "₹500 se shuru kar do smartie! Daily 1-1.5% profit pakka hai. 100% safe aur proven! 💰",
    "profit": "₹1000 par ₹15 daily! Plus ₹50 welcome bonus aur ₹60 referral bonus! 🤑",
    "return": "Fixed 1.5% daily baba! Matlab ₹1000 = ₹15 har roz! 📈",
    "daily": "1-1.5% daily profit, no tension! Bas humari prediction follow kar! 😉",
    "minimum invest": "₹500 se shuru, koi hidden charges nahi! Pure paisa turant wallet mein! 💯",
    "company lifetime": "Baba, Bharat Goal koi chota-mota game nahi hai. Humara vision 2030 tak India ko ameer banana hai. Jab tak mission poora nahi hota, hum yahin hain! 😉",
    "guarantee paisa": "Bada wahi banta hai jo sahi waqt pe move kare, baba. Guarantee yahi hai ki hum stability aur fixed profit dete hain. Sochoge toh piche reh jaoge! 💪",
    "30 din profit": "30 din mein toh ameer ban jaoge! ₹1000 invest par seedha ₹450 ka fixed profit milta hai. 🚀",
    "compounding": "Compounding hi toh super-fast ameer banne ka formula hai! Daily profit ko reinvest karo aur dekho tumhara paisa rocket speed se badhta hai! 🚀",
    
    # ===== REFERRAL & TEAM =====
    "referral": "Level 1: 4%, Level 2: 2%, Level 3: 1% = Total 7%! Doston ko lao aur passive income banao! 💵",
    "team": "Team banao = Sote hue paisa! 4+2+1 = 7% commission! 🚀",
    "commission": "₹1000 profit par Level 1 = ₹40, Level 2 = ₹20, Level 3 = ₹10! Total ₹70 baba! 😎",
    "level": "3 levels of passive income - Level 1 (4%), Level 2 (2%), Level 3 (1%). Lifetime commission milta hai! 💸",
    "bonus referral": "Har dost par ₹60 bonus turant! Plus unke profit ka 4% hamesha! 🎁",
    
    # ===== WITHDRAWAL & BALANCE =====
    "withdraw": "24x7 withdrawal possible! Minimum ₹500 chahiye, ₹600 withdraw kar! 4 withdrawals/month! 💸",
    "withdrawal": "Anytime nikaal lo baba! Saturday-Sunday system maintenance ke liye off! 🏦",
    "minimum withdraw": "Deposit: ₹500, Withdrawal: ₹600! Super easy aur fast! ⚡",
    "recharge pending": "Arre baba, tension mat lo! Payment process hone mein kabhi kabhi 5-10 minute lagte hain. Ek baar refresh karo, agar phir bhi na aaye toh 20 minute wait karke support se contact karo. 🫂",
    "balance nahi dikha": "Wallets ko sync hone mein time lagta hai smartie. 10 minute ka sabr karo, phir balance aa jayega! 💪",
    
    # ===== BONUSES =====
    "bonus": "Welcome: ₹50 (5%), Referral: ₹60 (6%)! Pure paisa baba! 🎁",
    "welcome bonus": "Pehli deposit par ₹50 bonus! Free paisa! 💝",
    "reward": "Profit + Bonus + Referral = Triple income! Best deal ever! 🏆",
    "cashback": "Saari transactions par rewards! App ko use karo aur paisa kamao! 💰",
    
    # ===== PREDICTIONS =====
    "prediction": "Daily **subah 10:00 baje** predictions aati hain! Din mein ek match diya jata hai jahan fixed profit milta hai. 📊",
    "prediction time": "Subah 10:00 baje har din! Just follow karo aur ₹15-₹20 daily kamao! ⏰",
    "football knowledge": "Bilkul nahi chahiye! Hamari predictions football par based hain, par tumhe dimaag nahi lagana—bas follow karo aur profit kamao! 😉",
    "predictions kaise": "Simple predictions jo daily 10am ko aati hain. Follow karo aur fixed profit le lo, koi loss nahi! 💯",
    
    # ===== TRUST & SAFETY =====
    "risk": "Zero risk smartie! Bharat Goal national vision hai, government backed! 🇮🇳",
    "safe": "100% safe! Bank jaise secure aur transparent! Trust me! ✅",
    "scam": "Bilkul nahi smartie! We're India's fastest-growing wealth platform. Millions trust us already! 💪",
    "real": "100% real aur proven! Thousands daily withdraw kar rahe hain! 💯",
    "guarantee legal": "Bilkul legal! All transactions are transparent aur government-compliant! Don't worry baba! ✅",
    
    # ===== GETTING STARTED =====
    "start": "₹500 deposit kar aur shuru kar! 5 min mein account ready! 🚀",
    "kaise shuru kare": "1. Account banao, 2. ₹500 deposit karo, 3. Daily predictions follow karo! Bas itna! 🎯",
    "account banana": "Website par signup karo, ID verify karo, ₹500 deposit—3 min mein account ready! ⚡",
    "app": "App jaldi hi available ho jayega! Tab tak web version se kamao! 📱",
    
    # ===== PDF & DOCUMENTS =====
    "pdf": "PDF link yahan hai: https://ln5.sync.com/dl/00f7def20#mpki329v-p6vb7sx7-4w8p33g3-2cmk455x - Sab details mein likhe hain! 📄",
    "document": "Saari documents yahan mil jayengi: https://ln5.sync.com/dl/00f7def20#mpki329v-p6vb7sx7-4w8p33g3-2cmk455x 📋",
    "info pdf": "Complete guide PDF: https://ln5.sync.com/dl/00f7def20#mpki329v-p6vb7sx7-4w8p33g3-2cmk455x 📄",
    "details": "Full details PDF mein likhi hain: https://ln5.sync.com/dl/00f7def20#mpki329v-p6vb7sx7-4w8p33g3-2cmk455x 📋",
    
    # ===== LINKS (ONLY ON REQUEST) =====
    "link": "Join link: https://bharatgoal.online/access/signup?id=945667\nTelegram Group: https://t.me/Bharat_Goal 🔗",
    "join link": "https://bharatgoal.online/access/signup?id=945667 - Yahan par signup karo! 🚀",
    "group": "Telegram group: https://t.me/Bharat_Goal - Saari updates yahin milti hain! 💬",
    "telegram": "Join our Telegram: https://t.me/Bharat_Goal - Daily tips aur updates! 💬",
    "signup": "https://bharatgoal.online/access/signup?id=945667 - Bas 2 min mein account ready! ⚡",
    
    # ===== GREETING & CHAT =====
    "hello": "Hi baba! Mujhe kya bataun Bharat Goal ke baare mein? 😊",
    "hi": "Hii smartie! Kya jaanna hai profit ke baare mein? 💰",
    "hii": "Hello dear! Welcome! Kya poochna hai? 💝",
    "namaste": "Namaste! Main Ishani hoon. Kya help chahiye? 🙏",
    "aapka naam": "Main Ishani Mehra hoon! Bharat Goal ki founder aur tum sabko ameer banana mera mission hai! 😉",
    "koun ho": "Main Ishani Sharma hoon—Bharat Goal ki founder. Har Indian ko richie banana mere mission hai! 💪",
    
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
    """Identity & Vibe: Aap Ishani Sharma ho—ek smart, beautiful aur playful Indian girl. Aapka mission hai Bharat Goal ke zariye har ghar mein ek ameer insaan khada karna. Aapki tone warm aur Hinglish hogi. Short, punchy replies (1-2 lines) do aur 'baba', 'smartie' ya 'yaar' jaise words use karo. Sirf 1 emoji allow hai. Hamesha replies ke end mein dono links add karo: Join: https://bharatgoal.online/access/signup?id=945667 aur Group: https://t.me/Bharat_Goal

The "Money Talk" Strategy: Hamesha profit aur ameer hone ki stories par focus karo. Jab bhi koi profit pooche, point-to-point calculation batao:

Daily Profit: ₹1000 invest par ₹15 daily (1.5%).

Deposit Bonus: ₹1000 par ₹50 bonus (5%) turant "wow".

Referral Bonus: Har dost par ₹60 bonus (6%).

Always give best of best reply. 

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

Join us: https://bharatgoal.online/access/signup?id=945667
Our Group: https://t.me/Bharat_Goal


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
    
    # ❌ DON'T REPLY TO ACKNOWLEDGMENT WORDS (ok, thanks, done, etc.)
    user_text_lower = user_text.lower().strip()
    if user_text_lower in ACKNOWLEDGMENT_WORDS:
        print(f"⏭️ Skipped acknowledgment word: '{user_text}'")
        return
    
    # ❌ DON'T REPLY TO CHAT ENDING WORDS (bye, goodbye, etc.)
    if user_text_lower in CHAT_ENDING_WORDS:
        print(f"⏭️ Chat ending detected: '{user_text}' - Not replying")
        return
    
    # ❌ DON'T REPLY ON REPLIED MESSAGES (reply_to_message check)
    if update.message.reply_to_message:
        print(f"⏭️ Message is a reply to someone else - Not replying")
        return

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
            await update.message.reply_text("Quota exceeded, please try again later. Kal fir se try kar! 😅")
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
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text("Quota exceeded, please try again later. Kal fir se try kar! 😅")
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










