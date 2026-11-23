"""Group-side chat behaviour for Ishani.

Everything that is specific to a group conversation lives here: the reply gate,
moderation, containment and member join/leave. DM behaviour is in user_chat.py;
the shared answer pipeline is in chat_engine.py.

bot.py binds itself with ``bind(module)`` once all of its own definitions exist.
Every shared name is then read through that bound module at call time, which
keeps the single ``dm`` singleton, the handler order and test-time patching intact.
"""

import html
import random
import re
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

_APP = None


def bind(module) -> None:
    """Bind the fully built bot module (works for `import bot` and `python bot.py`)."""
    global _APP
    _APP = module


def _b():
    if _APP is None:
        raise RuntimeError("group_chat.bind(bot) must run before group handlers")
    return _APP


# -------------------------- group-only policy --------------------------
ACKNOWLEDGMENT_WORDS = {
    "ok", "okay", "k", "thanks", "thank you", "thankyou",
    "done", "theek hai", "shukriya", "samajh gaya",
    "samajh gaye", "accha", "achi baat hai", "bilkul",
    "understood", "got it", "yes", "haan",
    "thik hai", "thik h", "alright", "cool", "nice",
}

CHAT_ENDING_WORDS = {
    "bye", "goodbye", "bye bye", "khuda hafiz",
    "alvida", "see you", "tc", "take care",
    "later", "see ya", "cya", "exit", "quit",
    "stop", "band karo", "enough", "jaata hoon",
}

_LINK_ONLY_RE = re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE)

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

# Answer unsafe group messages right there. No "come to DM" pressure.
_GROUP_CONTAINMENT_LINE = "yahi bata deti hoon, kya confusion hai?"
_DM_CONTAINMENT_LINE = "group me tumhari baat delete hui, yahi baat karte hain."


# -------------------------- reply gate --------------------------
async def should_reply(update, context) -> bool:
    """One gate for every text message: DMs get answers, groups stay human-quiet."""
    b = _b()
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
    # Admins are participants too; mentions mode still applies to them.
    mode = b.GROUP_MODE
    override = str(b.dm.get_group_settings(chat.id).get("group_mode") or "").lower()
    if override in ("all", "mentions"):
        mode = override
    return mode == "all"


def group_system_addendum(chat, links_allowed) -> str:
    """Group-only rules appended to the shared system prompt."""
    b = _b()
    parts = [
        "GROUP CHAT: answer fully right here in the group. Never ask them to DM, "
        "never say 'bheed hai' or 'DM kar de', never move the conversation elsewhere.",
    ]
    if links_allowed is False:
        parts.append("Links are not permitted in this group. Explain without sharing any link.")
    controls = b.load_persona().get("admin_learning_controls") or {}
    blocked = {str(url).strip().casefold() for url in (controls.get("blocked_links") or []) if str(url).strip()}
    canonical = b._canonical_platform_link()
    if canonical and links_allowed is not False and not controls.get("block_all_links") and canonical.casefold() not in blocked:
        parts.append(
            "LINK RULE: send the configured platform link for any general, platform, signup, "
            f"registration, account or website link request ({canonical}). Use the Telegram "
            f"join link ({b._canonical_join_link()}) only when they explicitly ask for the "
            "group/Telegram/join link. Never swap them."
        )
    if b.dm.get_group_business(getattr(chat, "id", 0)).get("welcome_message"):
        parts.append("This group has its own welcome note; stay consistent with it.")
    return "\n".join(parts)


# -------------------------- moderation --------------------------
def _message_has_link(message) -> bool:
    b = _b()
    text = message.text or message.caption or ""
    if b.has_any_links(text):
        return True
    entities = list(message.entities or []) + list(message.caption_entities or [])
    return any(getattr(entity, "type", "") in ("url", "text_link") for entity in entities)


def _message_has_inline_buttons(message) -> bool:
    markup = message.reply_markup
    return bool(markup and getattr(markup, "inline_keyboard", None))


def _message_is_abuse_or_threat(message) -> bool:
    """Gaali or a threat aimed at a person or a company. A complaint is not abuse."""
    text = message.text or message.caption or ""
    return bool(_ABUSE_OR_THREAT.search(text))


def _message_has_fraud_claim(message) -> bool:
    b = _b()
    text = message.text or message.caption or ""
    return bool(b._FRAUD.search(text))


def _mention_text(user) -> str:
    """Username tag when available, tg:// link otherwise."""
    if getattr(user, "username", None):
        return f"@{user.username}"
    name = html.escape(str(getattr(user, "first_name", None) or "Friend"))
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _contain_group_message(update, context, user, chat, label: str) -> None:
    """Remove the unsafe post, then answer calmly in the same group."""
    b = _b()
    await b._delete_and_verify(update.effective_message)
    tag = _mention_text(user)
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"{tag} {_GROUP_CONTAINMENT_LINE}",
        parse_mode="HTML",
    )
    print(f"🧹 {label} contained from {user.id}", flush=True)
    try:
        b.update_lead_state(user.id, "", user.first_name or "User", flags={"contained": True})
    except Exception as e:
        print(f"⚠️ Could not flag contained lead {user.id}: {e}", flush=True)


async def _is_group_admin(chat, user_id: int) -> bool:
    try:
        member = await chat.get_member(user_id)
    except Exception as e:
        print(f"⚠️ Could not check member {user_id}: {e}", flush=True)
        return False
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def _delete_and_verify(message) -> bool:
    """Delete a group message, then delete again. 'not found' means it is gone."""
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


async def moderate_group(update, context) -> None:
    """Remove non-admin bots, links and button posts; admins stay in the chain."""
    b = _b()
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type not in ("group", "supergroup"):
        return
    if user.id == context.bot.id:
        return

    is_admin = await b._is_group_admin(chat, user.id)
    if user.is_bot and not is_admin:
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            print(f"🚫 Banned non-admin bot {user.id} from {chat.id}", flush=True)
        except Exception as e:
            print(f"⚠️ Could not ban bot {user.id}: {e}", flush=True)
        await b._delete_and_verify(message)
        raise ApplicationHandlerStop

    if is_admin:
        # Admins may post links/buttons and still reach the chat handlers below.
        return
    if b._message_has_fraud_claim(message):
        await _contain_group_message(update, context, user, chat, "Fraud claim")
        raise ApplicationHandlerStop
    if b._message_is_abuse_or_threat(message):
        await _contain_group_message(update, context, user, chat, "Abuse or threat")
        raise ApplicationHandlerStop
    if b._message_has_link(message) or b._message_has_inline_buttons(message):
        await b._delete_and_verify(message)
        raise ApplicationHandlerStop


# -------------------------- join / leave --------------------------
async def welcome_new_friend(update, context) -> None:
    """Handle member join/leave events in groups."""
    b = _b()
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
        if old_status in ["left", "kicked"] and new_status == "member":
            custom_welcome = ""
            if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                custom_welcome = b.dm.get_group_business(update.effective_chat.id).get("welcome_message") or ""
            if custom_welcome:
                ai_text = b._render_template(html.escape(custom_welcome), {"name": user_name})
            else:
                ai_text = b._render_template(random.choice(b.WELCOME_MESSAGES), {"name": user_name})
            username = getattr(context.bot, "username", None) or "IshaniBot"
            deep = f"https://t.me/{username}?start=join_{user_id}"
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("Ishani se baat karo", url=deep)
            ]])
        elif old_status == "member" and new_status in ["left", "kicked"]:
            ai_text = b._render_template(random.choice(b.LEFT_MESSAGES), {"name": user_name})
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
        print(f"❌ Welcome/Exit error: {e}", flush=True)
