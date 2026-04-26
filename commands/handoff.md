---
description: Surface the most recent handoff into the current chat and engage with it
argument-hint: (no arguments)
---

You are executing the `/handoff` command. Manually load the most recent handoff into the conversation and engage with it. This is the read-side companion to `/log` — use it when the SessionStart hook didn't fire (e.g. you started a fresh Claude Code instance instead of using `/clear`), or when you want to re-surface a prior handoff later in a session.

## 1. Locate the handoff

Prefer pending (not yet consumed by the hook), fall back to the newest archive:

```bash
if [[ -f "$HOME/.claude/handoff_pending.md" ]]; then
  HANDOFF="$HOME/.claude/handoff_pending.md"
  STATUS="pending (will be consumed by the next /clear)"
elif [[ -d "$HOME/.claude/handoff_archive" ]]; then
  HANDOFF=$(ls -t "$HOME/.claude/handoff_archive"/*.md 2>/dev/null | head -1)
  [[ -n "$HANDOFF" ]] && STATUS="archived ($(basename "$HANDOFF"))"
fi

if [[ -z "${HANDOFF:-}" ]]; then
  echo "No handoffs found. Run /log in a session first to create one."
  exit 0
fi

echo "Loading: $HANDOFF"
echo "Status: $STATUS"
```

## 2. Read the handoff

Use the Read tool to read `$HANDOFF` in full.

## 3. Engage with it

Write a short response to the user with this exact shape:

```
Loaded handoff: <basename> (<status>)

**Prior session was**: <one-sentence summary, paraphrased from the handoff's Summary section>

**Open tasks**:
<copy the Open tasks section verbatim, including the `- [ ]` checkboxes>

Which would you like to continue with?
```

Do not start executing any of the tasks autonomously. Wait for the user to pick one.

## 4. Do not modify the handoff file

This command is read-only. Do not delete, move, or edit `handoff_pending.md` — only the SessionStart hook (`load-handoff.sh`) should consume it. Do not modify archived handoffs either.

## Notes

- If `handoff_pending.md` exists, it means a `/log` ran but the SessionStart hook hasn't fired yet (you didn't `/clear` or restart). The hook will still consume it on the next eligible event — running `/handoff` does not interfere.
- Do not use emojis — plain text only.
