# Setup Guide for Ishani Bot

## Step-by-Step Installation

### 1. Install Python Dependencies

```bash
cd d:\Tele_bot
pip install -r requirements.txt
```

**Required Packages**:
- `python-telegram-bot==21.0` - Telegram API wrapper
- `google-genai` - Google Gemini API
- `httpx` - HTTP client
- `anyio` - Async I/O

### 2. Get Required API Keys

#### A. Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot`
3. Follow prompts to create a new bot
4. BotFather will give you a token like: `123456789:ABCDEFghijklmnop_qrs`
5. Save this as `TELEGRAM_TOKEN`

#### B. Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com)
2. Click "Get API Key"
3. Create a new API key
4. Copy the key
5. Save this as `GEMINI_API_KEY`

#### C. Your Admin Telegram ID
1. Run this temporary Python script:
   ```python
   from telegram import Update
   from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
   
   async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
       print(f"Your User ID: {update.effective_user.id}")
   
   app = ApplicationBuilder().token("YOUR_TELEGRAM_TOKEN").build()
   app.add_handler(MessageHandler(filters.TEXT, get_user_id))
   ```
2. Or use [@userinfobot](https://t.me/userinfobot) on Telegram
3. Send any message, it will show your ID
4. Save this as `ADMIN_ID`

### 3. Set Environment Variables (Windows)

**Option A - Using Command Prompt**:
```cmd
set TELEGRAM_TOKEN=your_token_here
set GEMINI_API_KEY=your_key_here
set ADMIN_ID=your_user_id_here
```

**Option B - Using PowerShell**:
```powershell
$env:TELEGRAM_TOKEN = "your_token_here"
$env:GEMINI_API_KEY = "your_key_here"
$env:ADMIN_ID = "your_user_id_here"
```

**Option C - Create a .env file** (Manual):
1. Create file: `d:\Tele_bot\.env`
2. Add content:
```
TELEGRAM_TOKEN=your_token_here
GEMINI_API_KEY=your_key_here
ADMIN_ID=your_user_id_here
```

### 4. BotFather Settings

1. Open [@BotFather](https://t.me/botfather)
2. Send `/mybots`
3. Select your bot
4. Select `Bot Settings`
5. Go to `Group Privacy`
6. Set to `Disabled` (so bot can see messages in groups)

### 5. Run the Bot

```bash
cd d:\Tele_bot
python bot.py
```

You should see:
```
🚀 Ishani Bot is Live!
📝 Data file: data.json
👤 Admin ID: 123456789
✅ Ready to serve!
```

### 6. Test the Bot

Open Telegram and:
1. Start a private chat with your bot (search by username)
2. Send `/start` - Bot should greet you
3. Send `/help` - Shows available commands
4. Ask a normal question - Bot should respond
5. As admin, send `/panel` - Shows admin control panel

## Folder Structure

```
d:\Tele_bot\
├── bot.py              # Main bot code
├── data.json          # Persistent memory (auto-created)
├── requirements.txt   # Python dependencies
├── README.md          # Full documentation
└── SETUP.md           # This file
```

## Verifying Installation

### Check 1: Python Version
```bash
python --version
# Should show 3.8 or higher
```

### Check 2: Dependencies Installed
```bash
pip list | findstr "telegram genai"
# Should show installed packages
```

### Check 3: Bot Starting
```bash
python bot.py
# Should not show errors
```

### Check 4: Bot Responding
- Send `/start` to your bot
- Should get a welcome message

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'telegram'"
**Solution**:
```bash
pip install python-telegram-bot==21.0
```

### Issue: "API key not valid"
**Solution**:
1. Check GEMINI_API_KEY is correct
2. Ensure no extra spaces or quotes
3. Get a fresh key from [Google AI Studio](https://aistudio.google.com)

### Issue: "Bot not responding in groups"
**Solution**:
1. Go to [@BotFather](https://t.me/botfather)
2. Select your bot → Bot Settings → Group Privacy
3. Disable privacy mode (set to "Disabled")
4. Add bot to group as admin
5. Ensure messages don't have commands (text only)

### Issue: Bot starts but stops immediately
**Solution**:
1. Check for errors in console
2. Verify TELEGRAM_TOKEN is correct
3. Ensure bot token belongs to your bot
4. Check internet connection

### Issue: "Environment variable not found"
**Solution**:
1. On Windows, use: `set VARIABLE=value`
2. Then run: `python bot.py` in same command window
3. Or create `.env` file (but manual setup easier)

## Features After Setup

### 1. Admin Panel
- Command: `/panel`
- Upload documents
- Broadcast messages
- Mute/unmute bot
- View statistics

### 2. Auto Link Deletion
- Automatically deletes non-whitelisted links in groups
- Exceptions: Group admins, bot itself, whitelisted domains

### 3. Scheduled Messages
- Auto messages at: 6 AM, 12 PM, 6 PM, 10 PM
- Can be customized in `bot.py`

### 4. Auto Response Caching
- Saves API calls automatically
- Responds faster on repeat questions
- Reduces costs dramatically

### 5. User Tracking
- Every user interaction is logged
- Available in `/panel` → Stats

## Customization Guide

### Add Custom Keywords
Edit `KEYWORD_RESPONSES` in `bot.py`:
```python
KEYWORD_RESPONSES = {
    "your_keyword": "Your instant response",
}
```

### Whitelist More Links
Edit `ALLOWED_LINKS` in `bot.py`:
```python
ALLOWED_LINKS = [
    "yourdomain.com",
    "partner.com",
]
```

### Change Scheduled Times
Edit `scheduled_messages()` function:
```python
messages = {
    7: "7 AM message",  # Changed from 6
    12: "Noon message",
}
```

## Performance Tips

1. **Reduce API Calls**:
   - Add more keywords for common questions
   - Cache important responses

2. **Faster Responses**:
   - Use shorter prompts
   - Enable caching

3. **Lower Memory**:
   - Limit cache size (change MAX_CACHE_SIZE)
   - Archive old user data

## Security Tips

1. **Never share tokens/keys** in code or logs
2. **Use environment variables** for secrets
3. **Keep bot token private** - treat like password
4. **Rotate API keys occasionally**
5. **Monitor admin panel** for unauthorized uploads

## Advanced Configuration

### Custom System Prompt
Edit `FRIENDLY_SYSTEM_PROMPT` in `bot.py`:
```python
FRIENDLY_SYSTEM_PROMPT = """Your custom instructions here"""
```

### Custom Error Messages
Edit `handle_ai_chat()` function:
```python
await update.message.reply_text("Your custom message")
```

### Custom Response Format
Edit `get_cached_response_api()` function to modify response handling.

## Monitoring

Check `data.json` to see:
- Cached responses: `"responses"`
- User data: `"users"`
- Upload status: `"pdf_file_id"`
- Bot status: `"bot_muted"`
- Statistics: `"stats"`

## Backup

Important files to backup:
- `data.json` - Contains all cached data and user info
- `bot.py` - Your bot configuration

## Getting Help

If you encounter issues:
1. Check console output for errors
2. Review error messages in Telegram
3. Check `data.json` structure
4. Verify all environment variables
5. Ensure internet connection
6. Check BotFather settings

## Next Steps

After setup:
1. Add bot to your group
2. Set group admin permissions
3. Upload initial PDF document
4. Test all commands
5. Customize keywords for your use case
6. Monitor user interactions

---

**Bot Setup Complete!** 🎉

Your Ishani Bot is now ready to serve. Enjoy!
