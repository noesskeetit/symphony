"""Single-process bot: panel + bridge to Claude Code terminal."""

import json
import os
import re
import sys
import time
import urllib.request

from tg_bot.config import BOT_TOKEN, OWNER_ID, REPO
from tg_bot.github import open_prs, pr_ci_ok, pr_detail, do_merge, do_close
from tg_bot.linear import get_tickets, move_to_done
from tg_bot import screens

INBOX = "/tmp/symphony-tg-inbox.jsonl"
OUTBOX = "/tmp/symphony-tg-outbox.jsonl"

last_update_id = 0
known_prs = set()
panel_id = None


# ── Telegram ──────────────────────────────────────────────────────────────────

def tg(method, payload=None):
    url = "https://api.telegram.org/bot%s/%s" % (BOT_TOKEN, method)
    if payload:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print("tg/%s: %s" % (method, e), file=sys.stderr)
        return {"ok": False}


def panel(text, kb=None):
    global panel_id
    body = {"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if kb:
        body["reply_markup"] = {"inline_keyboard": kb}
    if panel_id:
        body["message_id"] = panel_id
        r = tg("editMessageText", body)
        if r.get("ok"):
            return
        if "message is not modified" in json.dumps(r):
            return
    body.pop("message_id", None)
    r = tg("sendMessage", body)
    if r.get("ok"):
        panel_id = r["result"]["message_id"]


def send_msg(text):
    tg("sendMessage", {"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"})


def toast(cb_id, text=""):
    tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text[:200]})


def delete_msg(msg_id):
    tg("deleteMessage", {"chat_id": OWNER_ID, "message_id": msg_id})


def btn(label, data):
    return {"text": label, "callback_data": data}


# ── Monkey-patch screens to use our panel ─────────────────────────────────────

import tg_bot.telegram as _tmod
_tmod.panel = panel
_tmod.btn = btn


# ── Bridge: write to inbox for Claude Code ────────────────────────────────────

def bridge_to_claude(text):
    with open(INBOX, "a") as f:
        f.write(json.dumps({"text": text, "ts": time.time()}) + "\n")
    print("[TG] %s" % text, file=sys.stderr)


def check_outbox():
    if not os.path.exists(OUTBOX):
        return
    try:
        with open(OUTBOX, "r") as f:
            lines = f.readlines()
        if not lines:
            return
        with open(OUTBOX, "w") as f:
            pass
        for line in lines:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            send_msg(data.get("text", ""))
    except Exception as e:
        print("outbox err: %s" % e, file=sys.stderr)


# ── PR helpers ────────────────────────────────────────────────────────────────

def ticket_num_from_pr(n):
    info = pr_detail(n)
    if not info:
        return None
    m = re.search(r"ALE-(\d+)", info.get("title", ""), re.IGNORECASE)
    return int(m.group(1)) if m else None


# ── Callback router ──────────────────────────────────────────────────────────

def route_cb(cb):
    d = cb.get("data", "")
    cid = cb["id"]

    if d == "go:home":
        toast(cid); screens.home()
    elif d == "go:tickets":
        toast(cid, "..."); screens.tickets()
    elif d == "go:prs":
        toast(cid, "..."); screens.prs()
    elif d == "go:logs":
        toast(cid, "..."); screens.logs()
    elif d == "go:cfg":
        toast(cid); screens.settings()
    elif d == "cfg:am":
        screens.auto_merge = not screens.auto_merge
        toast(cid, "Автомерж %s" % ("вкл" if screens.auto_merge else "выкл"))
        screens.settings()
    elif d.startswith("pr:v:"):
        toast(cid, "..."); screens.pr_view(int(d.split(":")[2]))
    elif d.startswith("pr:m:"):
        n = int(d.split(":")[2])
        toast(cid, "Мержу...")
        res = do_merge(n)
        ok = res is not None and "error" not in (res or "").lower()
        if ok:
            panel("✅ PR #%d смержен" % n, kb=[[btn("◀ PR-ы", "go:prs"), btn("◀ Меню", "go:home")]])
            tn = ticket_num_from_pr(n)
            if tn:
                move_to_done(tn)
        else:
            panel("❌ Ошибка: %s" % (res or "")[:200], kb=[[btn("◀ PR-ы", "go:prs")]])
    elif d.startswith("pr:c:"):
        n = int(d.split(":")[2])
        toast(cid, "Закрываю...")
        do_close(n)
        panel("PR #%d закрыт" % n, kb=[[btn("◀ PR-ы", "go:prs"), btn("◀ Меню", "go:home")]])
    else:
        toast(cid)


# ── New PR watcher ────────────────────────────────────────────────────────────

def watch_prs():
    global known_prs
    prs = open_prs()
    cur = set(p["number"] for p in prs)
    fresh = cur - known_prs

    for p in prs:
        if p["number"] not in fresh:
            continue
        n = p["number"]
        ci = pr_ci_ok(n)
        a = p.get("additions", "?")
        d = p.get("deletions", "?")

        if screens.auto_merge and ci:
            do_merge(n)
            send_msg("🤖 Автомерж <b>#%d</b>\n%s\n+%s/−%s" % (n, p["title"], a, d))
            tn = ticket_num_from_pr(n)
            if tn:
                move_to_done(tn)
        else:
            st = "✅" if ci else "⏳"
            kb = []
            if ci:
                kb.append([btn("✅ Merge", "pr:m:%d" % n), btn("📄 Info", "pr:v:%d" % n)])
            else:
                kb.append([btn("📄 Info", "pr:v:%d" % n)])
            tg("sendMessage", {
                "chat_id": OWNER_ID,
                "text": "🆕 <b>PR #%d</b> %s\n%s\n+%s/−%s" % (n, st, p["title"], a, d),
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": kb},
            })

    known_prs = cur


# ── Commands ──────────────────────────────────────────────────────────────────

CMDS = {"/menu", "/start", "/help", "/status", "/tickets", "/prs", "/logs", "/settings", "/cfg"}


def handle_text(text, msg_id):
    cmd = text.lower().split()[0] if text.startswith("/") else None

    if cmd in CMDS:
        delete_msg(msg_id)
        if cmd in ("/menu", "/start"):
            screens.home()
        elif cmd in ("/status", "/tickets"):
            screens.tickets()
        elif cmd == "/prs":
            screens.prs()
        elif cmd == "/logs":
            screens.logs()
        elif cmd in ("/settings", "/cfg"):
            screens.settings()
        elif cmd == "/help":
            panel(
                "📖 <b>Команды</b>\n\n"
                "/menu — главный экран\n"
                "/tickets — тикеты\n"
                "/prs — pull requests\n"
                "/logs — логи\n"
                "/settings — настройки\n\n"
                "Любой текст → пробрасывается в Claude Code",
                kb=[[btn("◀ Меню", "go:home")]],
            )
    else:
        # Not a command → bridge to Claude Code terminal
        bridge_to_claude(text)
        send_msg("📨 Передано в Claude Code. Жди ответ.")


# ── Poll ──────────────────────────────────────────────────────────────────────

poll_backoff = 0

def poll():
    global last_update_id, poll_backoff
    resp = tg("getUpdates", {"offset": last_update_id + 1, "timeout": 0})
    if not resp.get("ok"):
        # Backoff on errors (409 etc)
        poll_backoff = min(poll_backoff + 5, 30)
        time.sleep(poll_backoff)
        return
    poll_backoff = 0

    for u in resp.get("result", []):
        last_update_id = u["update_id"]

        uid = None
        if "callback_query" in u:
            uid = u["callback_query"].get("from", {}).get("id")
        elif "message" in u:
            uid = u["message"].get("from", {}).get("id")
        if uid != OWNER_ID:
            continue

        if "callback_query" in u:
            route_cb(u["callback_query"])
            continue

        msg = u.get("message", {})
        txt = (msg.get("text") or "").strip()
        mid = msg.get("message_id")
        if txt and mid:
            handle_text(txt, mid)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global known_prs

    # Init files
    for p in (INBOX, OUTBOX):
        open(p, "w").close()

    try:
        known_prs = set(p["number"] for p in open_prs())
    except Exception:
        pass
    try:
        screens.home()
    except Exception:
        send_msg("🟢 Symphony bot started")
    print("Symphony TG bot running (single process)", file=sys.stderr)

    t = 0.0
    while True:
        try:
            poll()
            check_outbox()
            time.sleep(2)
            if time.time() - t > 30:
                watch_prs()
                t = time.time()
        except KeyboardInterrupt:
            panel("🛑 Bot остановлен")
            break
        except Exception as e:
            print("err: %s" % e, file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    main()
