# Thoth

Session memory for Claude Code. `/log` captures the current session as a structured Markdown log, updates a marker block in your `~/CLAUDE.md`, and stages a handoff. On the next `/clear`, a SessionStart hook auto-injects the handoff into the fresh session so you can pick up exactly where you left off.

Named for the Egyptian god of writing — the deity whose literal job is to record what happened.

## What you get

- **`/log [optional title]`** — slash command. Reads the current transcript, extracts user prompts, assistant text, thinking blocks, tool calls, and sources, and writes a structured log to `~/logs/Claude_logs/log_<date>_<time>_<title>.md`. Updates a marker block in `~/CLAUDE.md` to point at the newest log. Stages a handoff to `~/.claude/handoff_pending.md` with an embedded directive that tells Claude in the next session to acknowledge and ask before continuing.
- **`/handoff [current | <substring>]`** — companion slash command. Loads a handoff and engages with it on demand. Use it when the SessionStart hook didn't fire (e.g. you started a fresh Claude Code instance instead of `/clear`-ing) or when you want to re-surface a prior handoff later in a session. With no args it presents an interactive chooser of the most recent handoffs; `/handoff current` loads the newest (pending if one exists, else newest archive); `/handoff <substring>` matches against archive basenames.
- **SessionStart hook** — fires on `/clear` AND on fresh startup. If a pending handoff exists, injects it as `additionalContext` into the new session and archives it to `~/.claude/handoff_archive/<timestamp>.md`. (Hook is a no-op when no pending handoff exists.)

End result: `/log` → `/clear` (or close + reopen) → fresh session that already knows what the previous one was doing AND tells you what's open instead of waiting silently.

## Install

```bash
git clone https://github.com/Praxathea/thoth.git ~/thoth
cd ~/thoth
./install.sh
```

The installer:
- Symlinks `commands/log.md` → `~/.claude/commands/log.md`
- Symlinks `hooks/load-handoff.sh` → `~/.claude/hooks/load-handoff.sh` (and chmods it)
- Creates `~/logs/Claude_logs/` and `~/.claude/handoff_archive/`
- Backs up any existing files it would overwrite to `<file>.bak.<timestamp>`
- Prints the JSON snippet to merge into `~/.claude/settings.json` (it does not edit your settings — JSON merging is brittle and you should review it)

After install, restart Claude Code (slash commands are loaded at startup) and add the SessionStart hook block from `settings.snippet.json` to your `~/.claude/settings.json`.

## Usage

```
/log                          # auto-titled from session topic
/log build api routing layer  # explicit title
```

Then either `/clear` (same Claude Code instance) or close-and-reopen — the handoff loads automatically thanks to the `clear` and `startup` matchers.

To manually surface a handoff (e.g. mid-session, or to re-read a prior one):
```
/handoff
```

## Requirements

- Claude Code (slash commands and hooks)
- `jq` (for JSON manipulation in the hook and command)
- A `~/CLAUDE.md` containing the marker block — `/log` rewrites whatever is between these:
  ```
  <!-- LATEST_LOG_START -->
  <!-- LATEST_LOG_END -->
  ```
  If the markers don't exist, the command will skip the `CLAUDE.md` update step.

## Known issues

- **Parallel sessions narrow race**: when two Claude Code sessions are active and you run `/log`, the picker now scans transcripts modified in the last 2 minutes; if more than one matches, it picks newest mtime and prints a `NOTE:` to stderr with a `grep -l` command to verify. The wrong-session case is rare but possible — when in doubt, include a phrase unique to your current session in your last prompt before `/log`.
- **Thinking-block content is empty**: Claude Code does not persist reasoning text to the transcript; only block structure. The `## Thinking context` section will always be blank for past sessions.

## Files

```
thoth/
├── commands/
│   ├── log.md               # /log slash-command body
│   └── handoff.md           # /handoff slash-command body
├── hooks/load-handoff.sh    # SessionStart hook (matcher: clear + startup)
├── settings.snippet.json    # hook block to merge into ~/.claude/settings.json
├── install.sh               # symlink installer
├── LICENSE                  # MIT
└── README.md
```

## License

MIT — see `LICENSE`.
