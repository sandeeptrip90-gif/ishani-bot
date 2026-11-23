import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ISHANI_NO_DASHBOARD", "1")

import bot
import chat_engine


def check(name, ok, extra=""):
    if not ok:
        raise AssertionError(f"{name}: {extra}")
    print("PASS ", name)


def main():
    # Fixed regex tokenization for English and Devanagari.
    persona = {
        "learned_from_admin": ["Refunds are processed within 3 business days.", "Deposit minimum is Rs.200."],
        "global_lessons": ["Never promise guaranteed profit."],
    }
    relevant = bot.relevant_admin_lessons(persona, "refund status please")
    check("relevant lesson retrieved", "Refunds are processed within 3 business days." in relevant)
    check("global lesson available", "Never promise guaranteed profit." in relevant)
    check("unrelated lesson not injected", bot.relevant_admin_lessons(persona, "weather today") == ["Never promise guaranteed profit."])

    devanagari = bot.relevant_admin_lessons(persona, "रिफंड कब मिलेगा")
    check("devanagari retrieval does not crash", isinstance(devanagari, list))

    # FAQ word boundaries.
    check("faq scam match", bool(bot.faq_context_for("scam hai kya")))
    check("faq unrelated no match", bot.faq_context_for("weather today") == [])
    check("faq boundary no partial match", bot.faq_context_for("scammer") == [])

    # Training fallback: only sufficiently relevant approved examples.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bot.dm.file_path = tmp_path / "data.json"
        bot.dm.CHAT_DIR = tmp_path / "chats"
        bot.dm.data = bot.dm._default_data()
        bot.dm.save()
        bot.dm.capture_training_example(1, "Test", "refund status please", "Refunds take 3 business days.", approved=True)
        bot.dm.capture_training_example(1, "Test", "weather today", "It is sunny.", approved=True)
        relevant_examples = bot.dm.training_examples_for_prompt("refund status", 3)
        check("relevant training example", [e["user_text"] for e in relevant_examples] == ["refund status please"])
        check("unrelated training example excluded", bot.dm.training_examples_for_prompt("football match", 3) == [])
        check("empty query injects none", bot.dm.training_examples_for_prompt("", 3) == [])

    bot.dm.file_path = ROOT / "data.json"
    bot.dm.CHAT_DIR = ROOT / "chats"
    bot.dm.CHAT_DIR.mkdir(exist_ok=True)

    # Natural non-company conversation should not receive detailed company knowledge.
    system = bot.build_personal_system(1, "Tester", [], compact=False, include_company=False, user_text="how are you")
    check("non-company prompt has no company knowledge", "Complete Company Knowledge Base" not in system)
    check("company context still compact", "Company:" in system or "Chelsea Football" in system)

    # Financial-risk wording should not be treated as a canned FAQ bypass.
    check("financial risk not canned", bot.get_keyword_response("scam hai kya") is not None)
    context = bot.faq_context_for("scam hai kya")
    check("financial risk faq available as context", bool(context))

    # Long answers are not truncated to four chunks or 1000 characters.
    long_reply = " ".join(f"Sentence {i}." for i in range(1, 8))
    shaped = chat_engine._shape_reply(long_reply, False)
    check("more than four sentences delivered", len(shaped) >= 7, len(shaped))
    long_sentence = "word " * 900 + "."
    shaped_long = chat_engine._shape_reply(long_sentence, False)
    check("long sentence split within Telegram limit", all(len(chunk) <= 3900 for chunk in shaped_long) and len(shaped_long) > 1)

    # Global lessons remain available.
    persona = {"learned_from_admin": ["Refund policy details."], "global_lessons": ["Always be polite."]}
    lessons = bot.relevant_admin_lessons(persona, "weather today")
    check("global lesson retained", "Always be polite." in lessons)
    check("irrelevant specific lesson excluded", "Refund policy details." not in lessons)

    print("ALL AUDIT REGRESSION CHECKS PASSED")


if __name__ == "__main__":
    main()
