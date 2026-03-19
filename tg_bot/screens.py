"""UI screens — clean, informative, no broken tables."""

import os
import re

from tg_bot.config import REPO, LINEAR_KEY, PROXY
from tg_bot.telegram import panel, btn
from tg_bot.github import open_prs, pr_ci_ok, pr_detail
from tg_bot.linear import get_tickets

auto_merge = False

_PRIO = {0: "", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
_STATE = {
    "Todo": "⬜", "In Progress": "🔵", "In Review": "🟡",
    "Merging": "🟣", "Rework": "🔧", "Backlog": "📦", "Done": "✅",
}


def home():
    tickets = get_tickets()
    active = [t for t in tickets if t["state"]["name"] != "Done"]
    done = len(tickets) - len(active)
    prs = open_prs()

    text = (
        "🎛  <b>Symphony</b>\n"
        "\n"
        "Тикеты: <b>%d</b> в работе, <b>%d</b> готово\n"
        "PR: <b>%d</b> открыто\n"
        "Модель: <b>sonnet</b>  ·  Автомерж: <b>%s</b>"
    ) % (len(active), done, len(prs), "вкл" if auto_merge else "выкл")

    panel(text, kb=[
        [btn("📋 Тикеты", "go:tickets"), btn("🔀 Pull Requests", "go:prs")],
        [btn("📊 Логи", "go:logs"), btn("⚙ Настройки", "go:cfg")],
        [btn("🔄 Обновить", "go:home")],
    ])


def tickets():
    items = get_tickets()
    active = [t for t in items if t["state"]["name"] != "Done"]
    done_n = sum(1 for t in items if t["state"]["name"] == "Done")

    if not active:
        body = "📋  <b>Тикеты</b>\n\nВсе задачи выполнены ✅"
    else:
        lines = []
        for t in active:
            s = t["state"]["name"]
            icon = _STATE.get(s, "❓")
            prio = _PRIO.get(t.get("priority", 0), "")
            lines.append(
                "%s %s <b>%s</b>\n%s" % (icon, prio, t["identifier"], t["title"])
            )
        body = "📋  <b>Тикеты</b>\n\n" + "\n\n".join(lines)

    body += "\n\n✅ %d готово  ·  ⏳ %d в работе" % (done_n, len(active))
    panel(body, kb=[[btn("🔄 Обновить", "go:tickets"), btn("◀ Меню", "go:home")]])


def prs():
    items = open_prs()

    if not items:
        panel(
            "🔀  <b>Pull Requests</b>\n\nНет открытых PR",
            kb=[[btn("🔄 Обновить", "go:prs"), btn("◀ Меню", "go:home")]],
        )
        return

    lines = []
    btns = []
    for pr in items:
        n = pr["number"]
        ci = pr_ci_ok(n)
        a = pr.get("additions", 0)
        d = pr.get("deletions", 0)

        status = "✅" if ci else "⏳"
        lines.append(
            "%s  <b>#%d</b>  ·  +%d/−%d\n%s" % (status, n, a, d, pr["title"])
        )

        if ci:
            btns.append([
                btn("✅ Merge #%d" % n, "pr:m:%d" % n),
                btn("📄 Подробнее", "pr:v:%d" % n),
            ])
        else:
            btns.append([btn("📄 Подробнее #%d" % n, "pr:v:%d" % n)])

    btns.append([btn("🔄 Обновить", "go:prs"), btn("◀ Меню", "go:home")])
    panel("🔀  <b>Pull Requests</b>\n\n" + "\n\n".join(lines), kb=btns)


def pr_view(n):
    info = pr_detail(n)
    if not info:
        panel("PR #%d не найден" % n, kb=[[btn("◀ Назад", "go:prs")]])
        return

    ci = pr_ci_ok(n)
    ci_text = "✅ Все проверки пройдены" if ci else "❌ Есть ошибки в CI"

    file_list = info.get("files", [])
    files = "\n".join("  %s" % f["path"] for f in file_list[:12])
    if len(file_list) > 12:
        files += "\n  ... ещё %d" % (len(file_list) - 12)

    text = (
        "🔀  <b>PR #%d</b>\n"
        "%s\n\n"
        "%s\n"
        "+%d −%d  ·  %d файлов\n\n"
        "<pre>%s</pre>"
    ) % (n, info["title"], ci_text, info["additions"], info["deletions"], len(file_list), files)

    rows = []
    if ci:
        rows.append([btn("✅ Merge", "pr:m:%d" % n)])
    rows.append([btn("❌ Закрыть PR", "pr:c:%d" % n)])
    rows.append([btn("◀ К списку PR", "go:prs"), btn("◀ Меню", "go:home")])
    panel(text, kb=rows)


def logs():
    try:
        dirs = sorted(
            [f for f in os.listdir("/tmp") if f.startswith("symphony-logs")],
            reverse=True,
        )
        if not dirs:
            panel("📊 Логи не найдены", kb=[[btn("◀ Меню", "go:home")]])
            return
        path = "/tmp/%s/log/symphony.log.1" % dirs[0]
        with open(path) as f:
            raw_lines = f.readlines()[-10:]

        short = []
        for line in raw_lines:
            m = re.match(
                r"\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})\.\d+\+\d+:\d+ (\w+): (.+)",
                line,
            )
            if m:
                level = {"info": "ℹ", "warning": "⚠", "error": "❌", "debug": "🔍"}.get(m.group(2), "·")
                msg = m.group(3).replace("<", "&lt;").replace(">", "&gt;")
                short.append("%s <code>%s</code> %s" % (level, m.group(1), msg[:80]))
            elif line.strip():
                short.append(line.strip()[:80])

        text = "📊  <b>Логи</b>\n\n" + "\n".join(short[-10:])
        panel(text[-3500:], kb=[[btn("🔄 Обновить", "go:logs"), btn("◀ Меню", "go:home")]])
    except Exception as e:
        panel("❌ %s" % e, kb=[[btn("◀ Меню", "go:home")]])


def settings():
    am_label = "включён ✅" if auto_merge else "выключен"
    text = (
        "⚙  <b>Настройки</b>\n\n"
        "🤖  Автомерж — %s\n"
        "🧠  Модель — sonnet\n"
        "👥  Агентов — 1\n"
        "📦  Репо — %s\n"
        "🔑  Linear — %s\n"
        "🌐  Proxy — %s"
    ) % (
        am_label,
        REPO,
        "подключён" if LINEAR_KEY else "нет",
        "подключён" if PROXY else "нет",
    )

    toggle = "🔴 Выключить автомерж" if auto_merge else "🟢 Включить автомерж"
    panel(text, kb=[
        [btn(toggle, "cfg:am")],
        [btn("◀ Меню", "go:home")],
    ])
