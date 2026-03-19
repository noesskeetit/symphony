"""Bridge — poll Telegram for new messages and write them to a file.

Main Claude Code session reads the file and responds.
Response is written to another file, bridge sends it to Telegram.
"""

import json
import os
import sys
import time
import urllib.request

BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
OWNER_ID = int(os.environ["TG_CHAT_ID"])

INBOX = "/tmp/symphony-tg-inbox.jsonl"    # Claude reads from here
OUTBOX = "/tmp/symphony-tg-outbox.jsonl"  # Claude writes here

last_update_id = 0


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
        print("tg err: %s" % e, file=sys.stderr)
        return {"ok": False}


def send(text):
    tg("sendMessage", {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML",
    })


def poll_telegram():
    global last_update_id
    resp = tg("getUpdates", {"offset": last_update_id + 1, "timeout": 0})
    if not resp.get("ok"):
        return

    for u in resp.get("result", []):
        last_update_id = u["update_id"]
        msg = u.get("message", {})
        uid = msg.get("from", {}).get("id")
        if uid != OWNER_ID:
            continue
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        # Write to inbox for Claude to read
        with open(INBOX, "a") as f:
            f.write(json.dumps({"text": text, "ts": time.time()}) + "\n")
        print("[TG->Claude] %s" % text, file=sys.stderr)


def poll_outbox():
    if not os.path.exists(OUTBOX):
        return
    try:
        with open(OUTBOX, "r") as f:
            lines = f.readlines()
        if not lines:
            return
        # Clear outbox
        with open(OUTBOX, "w") as f:
            pass
        for line in lines:
            data = json.loads(line.strip())
            send(data.get("text", ""))
            print("[Claude->TG] sent", file=sys.stderr)
    except Exception as e:
        print("outbox err: %s" % e, file=sys.stderr)


def main():
    # Clear files
    for path in (INBOX, OUTBOX):
        with open(path, "w") as f:
            pass

    send("🟢 Symphony bridge online. Пиши сюда — отвечу из терминала.")
    print("TG bridge running. Inbox: %s  Outbox: %s" % (INBOX, OUTBOX), file=sys.stderr)

    while True:
        try:
            poll_telegram()
            poll_outbox()
            time.sleep(2)
        except KeyboardInterrupt:
            send("🔴 Bridge offline")
            break
        except Exception as e:
            print("bridge err: %s" % e, file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    main()
