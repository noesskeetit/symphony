# Symphony (Custom Fork)

Fork of [openai/symphony](https://github.com/openai/symphony), adapted to use
**Claude Code CLI** instead of Codex as the agent backend.

> [!WARNING]
> Symphony is a low-key engineering preview for testing in trusted environments.

## What changed from upstream

| Area | Upstream | This fork |
|------|----------|-----------|
| Agent backend | Codex app-server | Claude Code CLI (`claude`) |
| Model | GPT | Claude Opus |
| Permissions | Codex sandbox policies | `dangerously-skip-permissions` |
| Telegram | — | Claude Code Telegram channel plugin |

## Telegram Integration

This fork integrates with Telegram via the
[Claude Code Telegram plugin](https://github.com/anthropics/claude-code-plugins).
Once configured, the agent session can receive messages and respond directly in
Telegram — useful for monitoring task progress and interacting with the agent
remotely.

### Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and save the
   token.
2. Run `/telegram:configure` in Claude Code to save the bot token.
3. Send any message to your bot in Telegram — it will prompt a pairing code.
4. Run `/telegram:access pair <code>` in Claude Code to approve access.
5. Optionally set policy to `allowlist` via `/telegram:access policy allowlist`.

After that, messages sent to the bot are forwarded to the active Claude Code
session and replies are sent back to Telegram.

## Running Symphony

### Requirements

Symphony works best in codebases that have adopted
[harness engineering](https://openai.com/index/harness-engineering/). Symphony
is the next step — moving from managing coding agents to managing work that
needs to get done.

### Quick start

Check out [elixir/README.md](elixir/README.md) for instructions on how to set
up your environment and run the Elixir-based Symphony orchestrator.

### WORKFLOW.md

The `elixir/WORKFLOW.md` file defines the orchestration contract: which Linear
project to poll, how to bootstrap workspaces, and the full agent prompt
template. See [elixir/README.md](elixir/README.md) for configuration details.

Current configuration points to the **PerekupHelper** project on Linear and
clones the repo into isolated workspaces for each issue.

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
