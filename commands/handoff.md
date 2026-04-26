---
description: Load a handoff into the current chat — pick from recent ones, or pass `current` for the newest
argument-hint: [current | <basename-or-substring>]
---

You are executing the `/handoff` command. Manually load a handoff into the conversation and engage with it. This is the read-side companion to `/log` — use it when the SessionStart hook didn't fire (e.g. you started a fresh Claude Code instance instead of `/clear`-ing) or when you want to re-surface a prior handoff later in a session.

`$ARGUMENTS` controls which handoff loads:
- **empty** (just `/handoff`) → list recent handoffs and let the user pick
- **`current`** (case-insensitive) → load the most recent (pending if one exists, else newest archive)
- **anything else** → treat as a basename or substring; match against pending + archive entries

## 1. Build the candidate list

```bash
{ [[ -f "$HOME/.claude/handoff_pending.md" ]] && \
    printf 'pending\t%s\thandoff_pending.md\n' "$HOME/.claude/handoff_pending.md"; \
  [[ -d "$HOME/.claude/handoff_archive" ]] && \
    ls -t "$HOME/.claude/handoff_archive"/*.md 2>/dev/null | while read -r p; do
      printf 'archived\t%s\t%s\n' "$p" "$(basename "$p")"
    done; } | head -20
```

Each row is `<status>\t<path>\t<basename>`. Rows are ordered newest-first (pending always wins if present).

If the list is empty, print:

```
No handoffs found. Run /log in a session first to create one.
```

…and stop.

## 2. Resolve the target from `$ARGUMENTS`

Trim whitespace from `$ARGUMENTS`, then:

- **empty** → go to step 3 (chooser).
- **equals `current`** (case-insensitive) → use the first row of the candidate list.
- **otherwise** → case-insensitively grep the basename column for `$ARGUMENTS`. If exactly one row matches, use it. If zero or 2+ match, go to step 3 with a one-line note explaining why (e.g. `No match for "foo" — pick from below:` or `"18-22" matched 3 candidates — pick one:`).

## 3. Chooser (interactive)

Use the `AskUserQuestion` tool with one question:

- `header`: short label like `Pick a handoff`
- `question`: `Which handoff would you like to load?`
- `multiSelect`: false
- `options`: up to **4** newest candidates. For each row, set:
  - `label` = the basename (or `handoff_pending.md` for the pending entry)
  - `description` = an 8–14 word teaser. Get it by reading the first paragraph under `## Summary of what was done` in that file and condensing.

After the user picks, set the target to the path corresponding to the chosen label.

If the candidate list has more than 4 entries, also include an `Other` option so the user can re-invoke `/handoff <substring>` themselves; in the description, list the remaining basenames.

## 4. Read the handoff

Use the Read tool on the resolved path, in full.

## 5. Engage with it

Write a short response to the user with this exact shape:

```
Loaded handoff: <basename> (<status>)

**Prior session was**: <one-sentence paraphrase of the Summary section>

**Open tasks**:
<copy the Open tasks section verbatim, including the `- [ ]` checkboxes>

Which would you like to continue with?
```

Do not start executing any of the tasks autonomously. Wait for the user to pick one.

## 6. Do not modify the handoff file

This command is read-only. Do not delete, move, or edit `handoff_pending.md` — only the SessionStart hook (`load-handoff.sh`) should consume it. Do not modify archived handoffs either.

## Notes

- `/handoff` (no args) → interactive chooser
- `/handoff current` → newest pending or archive
- `/handoff 18-22` → substring match against basenames (so `2026-04-26_18-22-38.md` would match)
- `/handoff pending` → matches the pending file via substring
- If `handoff_pending.md` exists, it means a `/log` ran but the SessionStart hook hasn't fired yet (you didn't `/clear` or restart). The hook will still consume it on the next eligible event — running `/handoff` does not interfere.
- Do not use emojis — plain text only.
