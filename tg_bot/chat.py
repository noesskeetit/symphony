"""Chat with Claude — relay user messages to Claude API and return answers."""

import json
import os
import sys
import urllib.request


ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PROXY = os.environ.get("HTTPS_PROXY", "")

SYSTEM_PROMPT = """You are a Telegram assistant for the Symphony project — an AI agent orchestration system.
You help the user manage their PerekupHelper project (car listing aggregator).
You can answer questions about the project, explain code, suggest improvements, and help debug issues.
Keep answers concise — this is Telegram, not a terminal. Use Russian.
Do not use markdown headers (#). Use <b>bold</b> for emphasis (HTML parse mode)."""


def ask_claude(user_message):
    """Send message to Claude API and return the response text."""
    if not ANTHROPIC_KEY:
        return "⚠ ANTHROPIC_API_KEY не задан в .env. Добавь его чтобы общаться со мной."

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )

    try:
        handlers = []
        if PROXY:
            handlers.append(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(req, timeout=30) as resp:
            data = json.loads(resp.read())

        # Extract text from response
        content = data.get("content", [])
        texts = [block["text"] for block in content if block.get("type") == "text"]
        return "\n".join(texts) if texts else "Пустой ответ от Claude"

    except Exception as e:
        print("Claude API error: %s" % e, file=sys.stderr)
        return "❌ Ошибка Claude API: %s" % str(e)[:200]
