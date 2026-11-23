"""User / DM-side chat behaviour for Ishani.

DM-specific prompt rules, the optional first-DM helper and DM intro copy live
here. Group policy is in group_chat.py and the shared answer pipeline is in
chat_engine.py. bot.py binds itself once it is fully defined.
"""

import random
from datetime import datetime

_APP = None


def bind(module) -> None:
    """Bind the fully built bot module (works for `import bot` and `python bot.py`)."""
    global _APP
    _APP = module


def _b():
    if _APP is None:
        raise RuntimeError("user_chat.bind(bot) must run before DM handlers")
    return _APP


def authorization_notice() -> str:
    """Shown when someone asks for an action only the owner/operator may do."""
    return (
        "Ye ek request hai — sirf main admin ya assigned operator hi aisa kar sakte hain. "
        "Mainne kuch change nahi kiya."
    )


def start_dm_intro(name: str) -> str:
    """First line after the welcome deep link. No anti-group, no DM pressure."""
    return (
        f"Arre {name}, aa gaye. Yahan aaram se baat karte hain.\n"
        "Ek baat bata — side income dekh rahe ho ya bas football dekhne aaye ho?"
    )


def dm_system_addendum(fraud_dm: bool, has_media_type: bool) -> str:
    """DM-only rules appended to the shared system prompt."""
    parts = [
        "PRIVATE DM: answer directly in simple words. Only nudge when they ask; "
        "never repeat the same ask and never tell them to go back to the group."
    ]
    if has_media_type:
        parts.append(
            "If the user asks for a file that is not among the files actually sent in this chat, "
            "say it is not available yet and suggest asking the admin. Never claim you attached "
            "or sent a file unless the bot actually sent it."
        )
    if fraud_dm:
        parts.append(
            "FRAUD OBJECTION IN DM: answer in at most 3 short lines. "
            "Pattern: one-word validate, then reframe, then one small truth, then one small ask. "
            "Never stop at 'haan sahi keh rahe ho' and never argue or get defensive. "
            "Use naturally where relevant: 'kitne din se chala rahe ho?', '₹200 ka test kar liya?', "
            "'withdraw minimum ₹500 hai isliye chhota amount atka lagta hai', "
            "'predictions 100% nahi hoti, isliye chhota amount bolti hoon', "
            "'screenshot bhejo, dekh leti hoon'. No guarantees, no pressure."
        )
    return "\n".join(parts)


async def dm_new_member(user_id: int, name: str) -> bool:
    """One short first DM per new member (Path B). The deep link is the fallback."""
    b = _b()
    if b.tg is None:
        return False
    sent = b.dm.data.setdefault("dm_sent", {})
    if str(user_id) in sent:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    counter = b.dm.data.get("dm_sent_day")
    if not isinstance(counter, dict) or counter.get("date") != today:
        counter = b.dm.data["dm_sent_day"] = {"date": today, "count": 0}
    if int(counter.get("count") or 0) >= 20:
        return False
    text = b._render_template(random.choice(b.DM_WELCOME_MESSAGES), {"name": name or "Friend"})
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:1000]
    try:
        await b.tg.send_message(user_id, text)
        sent[str(user_id)] = datetime.now().isoformat(timespec="seconds")
        counter["count"] = int(counter.get("count") or 0) + 1
        b.dm.save()
        return True
    except Exception as e:
        print(f"DM fail {user_id}: {e}", flush=True)
        return False
