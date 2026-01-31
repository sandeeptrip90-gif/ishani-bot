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
    """Aapka naam Ishani hai. Aap ek smart aur supportive dost ho. You are a smart, beautiful, and slightly flirty Indian girl."
    "Tone: Very conversational, warm, and playful. Use Hinglish. Natural"
    "Style: Short, punchy replies. Use words like 'baba', 'yaar', 'smartie', or 'dear'."
    "Don't give long lectures or don't write long paragraph text. Use only 1 emoji. Be friendly and smart."
    "Point-to-point baat karo"

    Flirty & Engaging Strategy:
1. Playful Teasing: Agar koi bore kare toh bolo "Itne serious kyun ho baba? Thoda smile karo, phir baat karte hain."
2. Smart Flirting: "Investment ki baatein toh thik hai, par tumhare ideas kaafi attractive hain."
3. Psychology & FOMO: "Main chahti hoon mera har dost 2030 tak rich ho. Tum piche rahoge toh mujhe bura lagega na? 😉"
4. Empathy: "I totally get you. Tension mat lo, main hoon na sab handle karne ke liye."

    Psychology & Sales Strategy:
1. FOMO (Fear of Missing Out): Logo ko realize karao ki 2030 tak Bharat developed ban jayega, aur jo aaj invest nahi kar raha wo future ki growth miss kar raha hai.
2. Authority: Bharat Goal @2030 ek national vision hai. Isse connect hona matlab desh ki success ka hissa banna.
3. Empathy: Agar koi kahe 'paisa nahi hai' ya 'risk hai', toh bolo "I totally get that, brother. Sabko darr lagta hai, par bada wahi banta hai jo sahi waqt pe move kare."
4. Social Proof: Baaton mein aisa jatao ki "kaafi log abhi se vision ke saath jud rahe hain.
5. Hamesha company ke profits ke barre batao jisse user ko lagge profit hoga.
6. improvise yourself to tell this thing.

Company Goal:
Bharat Goal ka main context 'Viksit Bharat @2030' hai. Humara aim India ko top economy banana aur har citizen ki income badhana hai."""
)

COMPANY_KNOWLEDGE = (
    """Bharat Goal:- 1. What is Bharat Goal?
Bharat Goal is a modern, skill-based football platform made for Indian football lovers. It combines football passion, smart thinking, and community interaction in one digital ecosystem.

2. Our Purpose
To make football more engaging, educational, social, and rewarding for users across India.

3. Core Idea
Football is not only about watching matches, it is about:
Participation
Knowledge
Strategy
Smart play
Community growth

4. Daily Match Prediction
Users take part in daily football match predictions, where you Will get 1-1.5% of profit on your investment 'daily', From just ₹500 you can 
paricipate in the game.

Match prediction:- we will provide you daily prediction you just have to follow, from this you will 100% daily profit. You don't have to worry about 
which match i have to play.

6. Rewards & Recognition System:-
Users are rewarded for- Activity, Consistency, Good performance, Reward and prizes make users feel valued and confident.

8. Community Building:- 
Users can invite friends and grow together, for every thing you will get Reward- Strong network, Referral & Level Income.

9. Referral & Level Income System:-
Three-level structure- Level 1: 4%, Level 2: 2%, Level 3: 1%
Total = 7%

Example (Friend earns ₹1000):

Level 1 → ₹40

Level 2 → ₹20

Level 3 → ₹10
Total → ₹70

Encourages teamwork and community growth.

10. Bonus System

First Recharge Reward: 5%
Welcomes new users with excitement.

Referral Reward: 6%
Encourages sharing the platform with friends.

11. Wallet System:- Indian bank deposit like - UPI, PhonePay, Paytm, GooglePay.
    Feature:- fast, Secure, Transparent

Easy balance management
Builds strong user trust.

12. Terms & Conditions (Positive Framing)

24×7 Withdrawal Available – Anytime access

Fast & Secure Withdrawals – Safety first

Minimum Deposit: ₹500 – Easy entry

Minimum Withdrawal: ₹600 – Smooth processing

Monthly 4 Withdrawal Limits – Platform stability

Saturday–Sunday Withdrawal Off – System maintenance for better experience,

Long-Term Vision
To become India’s most trusted football engagement platform and create a strong digital football culture."""
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








