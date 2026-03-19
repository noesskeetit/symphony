"""Configuration — all secrets from env."""

import os

BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
OWNER_ID = int(os.environ["TG_CHAT_ID"])
LINEAR_KEY = os.environ["LINEAR_API_KEY"]
PROXY = os.environ.get("HTTPS_PROXY", "")
REPO = os.environ.get("GITHUB_REPO", "noesskeetit/perekup_helper")
LIN_PROJECT = os.environ.get("LINEAR_PROJECT_ID", "")
LIN_DONE = os.environ.get("LINEAR_DONE_STATE_ID", "")
LIN_TEAM = os.environ.get("LINEAR_TEAM_KEY", "ALE")
