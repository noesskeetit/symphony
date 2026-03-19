"""GitHub CLI wrappers."""

import json
import subprocess

from tg_bot.config import REPO


def _gh(*args):
    try:
        r = subprocess.run(
            ["gh"] + list(args), capture_output=True, text=True, timeout=30
        )
        return r.stdout.strip()
    except Exception as e:
        return "[error] %s" % e


def open_prs():
    raw = _gh(
        "pr", "list", "--repo", REPO, "--state", "open",
        "--json", "number,title,additions,deletions,changedFiles,headRefName",
    )
    try:
        return json.loads(raw) if raw and not raw.startswith("[error]") else []
    except json.JSONDecodeError:
        return []


def pr_ci_ok(n):
    raw = _gh("pr", "checks", str(n), "--repo", REPO)
    return bool(raw) and "fail" not in raw.lower()


def pr_detail(n):
    raw = _gh(
        "pr", "view", str(n), "--repo", REPO,
        "--json", "title,additions,deletions,files,body,url",
    )
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None


def do_merge(n):
    return _gh("pr", "merge", str(n), "--repo", REPO, "--merge", "--admin")


def do_close(n):
    return _gh("pr", "close", str(n), "--repo", REPO)
