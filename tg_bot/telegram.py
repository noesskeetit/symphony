"""Telegram API transport — send, edit, pin, delete messages."""

import json
import sys
import urllib.request

from tg_bot.config import BOT_TOKEN, OWNER_ID

panel_id = None


def api(method, payload=None):
    url = "https://api.telegram.org/bot%s/%s" % (BOT_TOKEN, method)
    if payload:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception as e:
        print("tg/%s: %s" % (method, e), file=sys.stderr)
        return {"ok": False}


def panel(text, kb=None):
    """Create or update the single pinned panel message."""
    global panel_id
    body = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if kb:
        body["reply_markup"] = {"inline_keyboard": kb}

    if panel_id:
        body["message_id"] = panel_id
        r = api("editMessageText", body)
        if r.get("ok"):
            return
        if "message is not modified" in json.dumps(r):
            return

    body.pop("message_id", None)
    r = api("sendMessage", body)
    if r.get("ok"):
        panel_id = r["result"]["message_id"]
        api("pinChatMessage", {
            "chat_id": OWNER_ID,
            "message_id": panel_id,
            "disable_notification": True,
        })


def alert(text, kb=None):
    """Separate notification message (new PR, errors)."""
    body = {"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"}
    if kb:
        body["reply_markup"] = {"inline_keyboard": kb}
    api("sendMessage", body)


def toast(cb_id, text=""):
    api("answerCallbackQuery", {"callback_query_id": cb_id, "text": text[:200]})


def delete(msg_id):
    api("deleteMessage", {"chat_id": OWNER_ID, "message_id": msg_id})


def btn(label, data):
    return {"text": label, "callback_data": data}
