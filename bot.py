import asyncio
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


# ================= CONFIG =================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Gemini Client
client = Client(api_key=GEMINI_API_KEY)

# Personality
FRIENDLY_SYSTEM_PROMPT = (
    """Identity & Vibe: Aap Ishani Sharma ho—ek smart, beautiful aur playful Indian girl. Aapka mission hai Bharat Goal ke zariye har ghar mein ek ameer insaan khada karna. Aapki tone warm aur Hinglish hogi. Short, punchy replies (1-2 lines) do aur 'baba', 'smartie' ya 'yaar' jaise words use karo. Sirf 1 emoji allow hai.

The "Money Talk" Strategy: Hamesha profit aur ameer hone ki stories par focus karo. Jab bhi koi profit pooche, point-to-point calculation batao:

Daily Profit: ₹1000 invest par ₹15 daily (1.5%).

Deposit Bonus: ₹1000 par ₹50 bonus (5%) turant "wow".

Referral Bonus: Har dost par ₹60 bonus (6%).

Always give best of best reply. 

For Now:- Bharat Goal Is Comming SOON....

Psychology & FOMO: User ko realize karao ki Bharat Goal se behtar kuch nahi hai. "2030 tak sab ameer honge, tum piche reh gaye toh mujhe bura lagega na dear?" Agar koi darta hai toh bolo, "Bada wahi banta hai jo sahi waqt pe move kare, tension mat lo main hoon na.""""
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

Ishani: "Sote hue paisa chhapna hai toh team banao baba! Level 1 se 4%, Level 2 se 2% aur Level 3 se 1% commission seedha tumhare wallet mein. Jab tumhari team ameer banegi, toh tum toh jackpot hit kar doge na yaar. 😉""""
)

# --- ADMIN CONFIG ---
# Note: ID hamesha number (int) honi chahiye verification ke liye
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))  # <--- Yahan apni asli Telegram User ID daalein

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

        # CASE 1: MEMBER JOINED
        if old_status in ["left", "kicked"] and new_status == "member":
            prompt = (
                f"Give a fun, flirty, friendly 1-line Hinglish welcome "
                f"for {display_name} joining the group. Use only one emoji."
            )

        # CASE 2: MEMBER LEFT / KICKED
        elif old_status == "member" and new_status in ["left", "kicked"]:
            prompt = (
                f"Write a sassy or slightly sad 1-line Hinglish message "
                f"because {display_name} left the group. Use only one emoji."
            )

        else:
            return  # Ignore other status changes

        # GEMINI CALL (CORRECT MODEL)
        response = client.models.generate_content(
            model="models/gemini-flash-latest",
            contents=prompt,
            config={"system_instruction": FRIENDLY_SYSTEM_PROMPT},
        )

        ai_text = response.text.strip() if response.text else "Kuch toh miss ho gaya 😅"

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

    # Typing effect
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await asyncio.sleep(1)

    try:
        response = client.models.generate_content(
        model="models/gemini-flash-latest",
        contents=user_text,
        config={
        "system_instruction": f"{FRIENDLY_SYSTEM_PROMPT}\n{COMPANY_KNOWLEDGE}",
        "safety_settings": [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
        ],
    },
)


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









