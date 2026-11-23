"""Shared answer pipeline used by both group chats and DMs.

Gate -> debounce -> keyword fast path -> persona prompt -> cached AI call ->
shaped reply. bot.py binds itself once it is fully defined; shared state and
patchable helpers are always read through that module so there is still exactly
one dm singleton, one buffer and one task table.
"""

import re
from typing import List

_APP = None


def bind(module) -> None:
    """Bind the fully built bot module (works for `import bot` and `python bot.py`)."""
    global _APP
    _APP = module


def _b():
    if _APP is None:
        raise RuntimeError("chat_engine.bind(bot) must run before chat handlers")
    return _APP


# -------------------------- delivery --------------------------
async def _send_paced(msg, text: str) -> None:
    """Keep a gap between sends so a fast lead cannot trip Telegram's flood limit."""
    b = _b()
    wait = b._last_send + 1.2 - b._time.monotonic()
    if wait > 0:
        await b.asyncio.sleep(wait)
    await msg.reply_text(text)
    b._last_send = b._time.monotonic()


def _shape_reply(reply: str, is_group: bool, max_lines: int = 2) -> List[str]:
    """Keep the answer readable in both places; groups are no longer truncated.

    A group reply used to be sliced to its first line, which silently dropped the
    explanation. Now both scopes get the same short, complete answer.
    """
    lines = [line.strip() for line in (reply or "").splitlines() if line.strip()]
    limit = max_lines if not is_group else max(2, max_lines)
    return [line[:1000] for line in lines[:limit]]


async def _deliver_reply(user_text: str, user_id: int, first_name: str, update, context,
                         reply: str, chat_scope: str, is_group: bool, fraud_dm: bool = False) -> str:
    """One delivery path for normal chat AND tool-backed answers.

    Returns the exact text that was delivered so it can be logged for analysis.
    """
    b = _b()
    reply = b.apply_admin_link_controls(b.clean_reply_text(reply or ""))
    if not reply and ((b.load_persona().get("admin_learning_controls") or {}).get("block_all_links")
                      or (b.load_persona().get("admin_learning_controls") or {}).get("blocked_links")):
        reply = b.user_language_notice(
            user_text, "I can explain it here without sharing a link.",
            "Link ke bina yahin samjha deti hoon 🙂",
            "लिंक के बिना मैं यहीं समझा देती हूँ 🙂",
        )
    if not reply:
        reply = b.user_language_notice(
            user_text, "Sorry, I didn't quite catch that. Could you say it another way?",
            "Sorry yaar, main samajh nahi paayi 😅 Ek baar aur bataoge?",
            "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई 😅 एक बार फिर बताएँगे?",
        )
    # Answer where the question was asked. No DM nudge is bolted on in groups.
    bubbles = b._shape_reply(reply, is_group, max_lines=3 if fraud_dm else 2)
    target = update.effective_message if getattr(update, "effective_message", None) else update.message
    for bubble in bubbles:
        await b._send_paced(target, bubble)
    delivered = " | ".join(bubbles)
    b.dm.append_chat(user_id, first_name, "bot", delivered, scope=chat_scope)
    return delivered


# -------------------------- the answer --------------------------
async def _answer(user_text: str, user_id: int, first_name: str, update, context) -> None:
    b = _b()
    started = b._time.monotonic()
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ("group", "supergroup"))
    chat_scope = f"group:{chat.id}" if is_group else "private"
    fraud_dm = bool(not is_group and b._FRAUD.search(user_text))

    # Snapshot first: the document must show the context the model actually saw,
    # not the user message we are about to append.
    history = b.dm.recent_chat(user_id, first_name, limit=40, scope=chat_scope)
    b.dm.append_chat(user_id, first_name, "user", user_text, scope=chat_scope)

    def _log_turn(*, reply: str, raw_reply: str = "", response_kind: str = "ai",
                  status: str = "ok", keyword_match: str = "", error: str = "",
                  system_instruction: str = "") -> None:
        """Queue one analysis document without touching the delivery path."""
        b.mongo_log_chat(
            user_id=user_id,
            first_name=first_name,
            user_text=user_text,
            model_reply=reply,
            history=history,
            raw_model_reply=raw_reply or reply,
            system_instruction=system_instruction,
            scope=chat_scope,
            source="telegram",
            response_kind=response_kind,
            status=status,
            keyword_match=keyword_match,
            latency_ms=int((b._time.monotonic() - started) * 1000),
            error=error,
        )

    has_media_type = bool(re.search(
        r"\b(pdf|document|file|brochure|guide|details?|photo|picture|image|poster|form|attachment)\b|"
        r"(pdf|brochure|tasveer|chitra)", user_text, re.IGNORECASE
    ))
    media_request = has_media_type and bool(re.search(
        r"\b(send|share|show|give|get|need|want|upload|forward|provide|bhejo|bhej|dikhao|chahiye|please|plz)\b",
        user_text, re.IGNORECASE
    ))
    if media_request:
        asset = b.find_media_asset(user_text)
        if asset:
            await b.send_media_asset(context.bot, chat.id, asset)
            media_note = f"Sent file: {asset.get('name') or asset.get('kind', 'file')}"
            b.dm.append_chat(user_id, first_name, "bot", media_note, scope=chat_scope)
            _log_turn(reply=media_note, response_kind="media", status="sent")
            return

    # The learned/canonical link rule is authoritative and must be resolved before
    # the static FAQ cache, which still contains the older Telegram join link.
    learned_link_reply = b.resolve_link_request_reply(user_text)
    keyword_reply = None if fraud_dm else (learned_link_reply or b.get_keyword_response(user_text))
    if keyword_reply:
        keyword_kind = "learned_link" if learned_link_reply else "keyword_faq"
        reply = b.apply_admin_link_controls(b.clean_reply_text(keyword_reply))
        if reply:
            bubbles = b._shape_reply(reply, is_group)
            for bubble in bubbles:
                await b._send_paced(update.message, bubble)
            delivered = " | ".join(bubbles)
            b.dm.append_chat(user_id, first_name, "bot", delivered, scope=chat_scope)
            _log_turn(reply=delivered, response_kind="keyword", status="ok",
                      keyword_match=keyword_kind)
            return
        _log_turn(reply="", response_kind="keyword", status="blocked",
                  keyword_match=keyword_kind, error="reply removed by link controls")
        return

    group_business = {}
    group_settings = {}
    if is_group:
        group_business = b.dm.get_group_business(chat.id)
        group_settings = b.dm.get_group_settings(chat.id)

    await context.bot.send_chat_action(chat_id=chat.id, action=b.ChatAction.TYPING)
    personal_system = b.build_personal_system(
        user_id,
        first_name,
        history,
        compact=False,
        group_business=group_business,
        include_company=bool(re.search(
            r"\b(chelsea|company|join|signup|sign up|link|earning|profit|deposit|withdraw|prediction|app)\b",
            user_text, re.I,
        )),
    )
    if is_group:
        personal_system += "\n" + b.group_system_addendum(chat, group_settings.get("links_allowed"))
    else:
        personal_system += "\n" + b.dm_system_addendum(fraud_dm, has_media_type)

    try:
        response = await b.get_cached_response_api(
            prompt=user_text,
            system_instruction=personal_system,
            history=history,
        )
        if response is None:
            reply = b.user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            )
            await b._send_paced(update.message, reply)
            _log_turn(reply=reply, status="no_response",
                      error="AI returned no response", system_instruction=personal_system)
            return

        raw_reply = response.text if response and response.text else ""
        delivered = await b._deliver_reply(
            user_text, user_id, first_name, update, context,
            raw_reply, chat_scope, is_group, fraud_dm,
        )
        _log_turn(reply=delivered, raw_reply=raw_reply,
                  system_instruction=personal_system)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        fallback = b.user_language_notice(
            user_text, "I hit a small technical issue. Please try again in a moment 🙏",
            "Chhota sa technical issue aa gaya yaar, ek minute baad try karna 🙏",
            "तकनीकी दिक्कत आ गई है, एक मिनट बाद फिर कोशिश कीजिए 🙏",
        )
        if "503" in error_msg:
            print("⏳ 503 UNAVAILABLE — waiting 10 seconds before sending...")
            await context.bot.send_chat_action(chat_id=chat.id, action=b.ChatAction.TYPING)
            await b.asyncio.sleep(10)
            try:
                retry_response = await b.call_ai_with_retry(
                    prompt=user_text,
                    system_instruction=personal_system,
                    history=history,
                )
                retry_reply = b.apply_admin_link_controls(
                    b.clean_reply_text(retry_response.text) if retry_response and retry_response.text else ""
                )
                if retry_reply:
                    bubbles = b._shape_reply(retry_reply, is_group,
                                             max_lines=3 if fraud_dm else 2)
                    for bubble in bubbles:
                        await b._send_paced(update.message, bubble)
                    delivered = " | ".join(bubbles)
                    b.dm.append_chat(user_id, first_name, "bot", delivered, scope=chat_scope)
                    _log_turn(reply=delivered,
                              raw_reply=retry_response.text if retry_response else retry_reply,
                              response_kind="ai_retry", status="ok_after_retry",
                              system_instruction=personal_system)
                    return
            except Exception as retry_error:
                print(f"❌ ERROR after 10s wait: {retry_error}")
            fallback = b.user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            )
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            fallback = b.user_language_notice(
                user_text, "The server's a little busy right now. Please try again soon ⏳",
                "Server thoda busy hai yaar, thodi der baad try karna ⏳",
                "सर्वर अभी व्यस्त है, थोड़ी देर बाद फिर कोशिश कीजिए ⏳",
            )
        await b._send_paced(update.message, fallback)
        _log_turn(reply=fallback, status="error", error=error_msg,
                  system_instruction=personal_system)


# -------------------------- debounce + entry --------------------------
async def _flush(user_id: int, first_name: str, update, context) -> None:
    b = _b()
    try:
        await b.asyncio.sleep(b.DEBOUNCE_SEC)
        merged = " | ".join(b._buf.pop(user_id, [])).strip()
        if merged:
            await b._answer(merged, user_id, first_name, update, context)
    except b.asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"❌ Debounced reply error: {e}", flush=True)
    finally:
        b._tasks.pop(user_id, None)


async def handle_ai_chat(update, context) -> None:
    """Gate, buffer, then answer once per lead."""
    b = _b()
    if b.dm.is_bot_muted():
        return

    user_text = update.message.text
    if not user_text:
        return
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "User"
    chat = update.effective_chat
    chat_scope = f"group:{chat.id}" if chat and chat.type in ("group", "supergroup") else "private"

    if not await b.should_reply(update, context):
        return

    b.update_lead_state(user_id, user_text, first_name)
    b.dm.update_user(user_id, first_name)

    if b.request_needs_authorization(user_text) and not b.actor_may_authorize(user_id, chat):
        b.dm.audit("blocked_unauthorized_request", user_id, str(chat.id), user_text[:160])
        await b._send_paced(update.message, b.authorization_notice())
        return

    if await b.handle_agent_request(update, context, user_text, user_id, first_name, chat_scope):
        return

    b._buf.setdefault(user_id, []).append(user_text)
    await context.bot.send_chat_action(chat_id=chat.id, action=b.ChatAction.TYPING)
    task = b._tasks.get(user_id)
    if task is not None and not task.done():
        return
    b._tasks[user_id] = b.asyncio.create_task(
        b._flush(user_id, first_name, update, context)
    )
