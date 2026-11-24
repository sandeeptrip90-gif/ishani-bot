import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ISHANI_NO_DASHBOARD", "1")

import bot
import group_chat


def check(name, ok, extra=""):
    if not ok:
        raise AssertionError(f"{name}: {extra}")
    print("PASS ", name)


class FakeChat:
    id = 123
    type = "supergroup"


class FakeUser:
    id = 55
    is_bot = False
    first_name = "Tester"


class FakeMessage:
    message_id = 77
    text = "check this https://example.com/offer"
    caption = ""
    entities = []
    caption_entities = []
    reply_markup = None


class FakeBot:
    id = 999
    username = "IshaniBot"


async def run_moderation(settings, message=None):
    calls = {"delete": 0, "contain": 0}

    async def fake_admin(chat, user_id):
        return False

    async def fake_delete(msg):
        calls["delete"] += 1
        return True

    async def fake_contain(update, context, user, chat, label):
        calls["contain"] += 1

    original_admin = bot._is_group_admin
    original_delete = bot._delete_and_verify
    original_contain = group_chat._contain_group_message
    original_settings = bot.dm.moderation_settings
    try:
        bot._is_group_admin = fake_admin
        bot._delete_and_verify = fake_delete
        group_chat._contain_group_message = fake_contain
        bot.dm.moderation_settings = lambda group_id: {
            **{key: True for key in bot.GROUP_MODERATION_KEYS},
            **settings,
        }
        update = SimpleNamespace(
            effective_message=message or FakeMessage(),
            effective_chat=FakeChat(),
            effective_user=FakeUser(),
        )
        context = SimpleNamespace(bot=FakeBot())
        try:
            await group_chat.moderate_group(update, context)
        except Exception as exc:  # ApplicationHandlerStop is expected when action runs
            if exc.__class__.__name__ != "ApplicationHandlerStop":
                raise
        return calls
    finally:
        bot._is_group_admin = original_admin
        bot._delete_and_verify = original_delete
        group_chat._contain_group_message = original_contain
        bot.dm.moderation_settings = original_settings


def main():
    check("link removal defaults on", bot.group_setting_enabled({}, "link_removal") is True)
    check("explicit false disables", bot.group_setting_enabled({"link_removal": False}, "link_removal") is False)
    check("string false disables", bot.group_setting_enabled({"link_removal": "false"}, "link_removal") is False)

    calls = asyncio.run(run_moderation({}))
    check("unset link removal deletes link", calls["delete"] == 1, calls)

    calls = asyncio.run(run_moderation({"link_removal": False}))
    check("disabled link removal keeps link", calls["delete"] == 0, calls)

    abuse = FakeMessage()
    abuse.text = "kill you"
    calls = asyncio.run(run_moderation({"abuse_removal": False}, abuse))
    check("disabled abuse removal does not contain", calls["contain"] == 0, calls)
    calls = asyncio.run(run_moderation({"abuse_removal": True}, abuse))
    check("enabled abuse removal contains", calls["contain"] == 1, calls)

    fraud = FakeMessage()
    fraud.text = "ye scam hai, paisa doob gaya"
    calls = asyncio.run(run_moderation({"fraud_removal": False}, fraud))
    check("disabled fraud handling does not contain", calls["contain"] == 0, calls)

    check("moderation keys exposed", set(bot.GROUP_MODERATION_KEYS) == {
        "link_removal", "abuse_removal", "fraud_removal", "bot_removal",
    })

    original_data = bot.dm.data
    try:
        bot.dm.data = {
            "groups": {"123": {"group_id": 123, "settings": {"link_removal": False}}},
            "group_moderation": {"link_removal": True, "abuse_removal": False},
        }
        effective = bot.dm.moderation_settings(123)
        check("per-group override wins", effective["link_removal"] is False, effective)
        check("global default applies", bot.dm.moderation_settings(999)["abuse_removal"] is False)

        bot.dm.data["group_moderation"]["link_removal"] = False
        check("global disable applies without override", bot.dm.moderation_settings(999)["link_removal"] is False)
    finally:
        bot.dm.data = original_data

    print("ALL GROUP MODERATION TOGGLE CHECKS PASSED")


if __name__ == "__main__":
    main()
