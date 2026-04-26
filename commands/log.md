---
description: Capture the current session as a structured log, update CLAUDE.md, and stage a handoff for /clear
argument-hint: [optional title]
---

You are executing the `/log` command. Your job: write a comprehensive log of the current session to disk, point CLAUDE.md at it, stage a handoff, and tell the user what to do next.

Do **everything** in this command — do not stop partway. Do not ask the user for input. At the end, the only message to the user is the final status block described at the bottom.

## 1. Determine the title

If `$ARGUMENTS` is non-empty, use it as the title. Otherwise, generate a 3–5 word title from the session's primary topic by reading recent user prompts.

Sanitize the title to a slug: lowercase, replace whitespace and punctuation with `_`, strip everything not `[a-z0-9_]`, collapse repeated `_`, trim leading/trailing `_`. Cap at 5 words / 50 characters.

Examples:
- `$ARGUMENTS = "Build /log slash command"` → `build_log_slash_command`
- empty, session about token reduction → `token_reduction_research`

## 2. Locate the current transcript

Claude Code does not expose `$CLAUDE_TRANSCRIPT_PATH` to slash-command bash (verified — only `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_EXECPATH` are visible). Locate by recently-modified mtime across all project transcript dirs, with disambiguation when multiple sessions are active.

```bash
PROJECTS_DIR="$HOME/.claude/projects"
RECENT=$(find "$PROJECTS_DIR" -maxdepth 2 -name '*.jsonl' -mmin -2 2>/dev/null)
RECENT_COUNT=$(printf '%s\n' "$RECENT" | grep -c . || true)

if [[ "$RECENT_COUNT" -eq 1 ]]; then
  TRANSCRIPT="$RECENT"
elif [[ "$RECENT_COUNT" -gt 1 ]]; then
  # Parallel sessions detected — pick newest mtime and warn.
  TRANSCRIPT=$(printf '%s\n' "$RECENT" | xargs ls -t 2>/dev/null | head -1)
  echo "NOTE: $RECENT_COUNT active transcripts; picked $TRANSCRIPT by mtime." >&2
  echo "If wrong session, grep recent transcripts for a unique phrase from your prompts:" >&2
  echo "  grep -l '<unique-phrase>' $(printf '%s ' $RECENT)" >&2
else
  # No activity in last 2 min — fall back to overall most recent.
  TRANSCRIPT=$(ls -t "$PROJECTS_DIR"/*/*.jsonl 2>/dev/null | head -1)
fi

SESSION_ID=$(jq -r 'select(.sessionId != null) | .sessionId' "$TRANSCRIPT" | head -1)
```

Capture `$TRANSCRIPT` once at this step and reuse the variable for all subsequent jq calls. Do not re-run `ls -t` later — a sibling `/log` run can change the result mid-execution.

## 3. Compute filename

```bash
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H-%M)
FILENAME="log_${DATE}_${TIME}_${TITLE_SLUG}.md"
LOG_PATH="$HOME/logs/Claude_logs/$FILENAME"
```

## 4. Extract content with jq

Run these to gather raw material (write outputs to temp files in `/tmp/log-build-$$/` if helpful):

- **User prompts** (filter out synthetic entries). User content is sometimes a plain string, sometimes an array of `{type:"text", text:"..."}` blocks (e.g. slash-command bodies). Handle both:
  ```bash
  jq -r 'select(.type=="user") | (.message.content | if type=="string" then . else (map(select(.type=="text")) | map(.text) | join("\n")) end)' "$TRANSCRIPT" \
    | grep -vE '^<(local-command-caveat|command-name|command-message|command-args|system-reminder|/system-reminder)' \
    | grep -v '^$'
  ```
- **Assistant text**:
  ```bash
  jq -c 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' "$TRANSCRIPT"
  ```
- **Thinking blocks** (often empty in non-thinking model runs — that's fine):
  ```bash
  jq -c 'select(.type=="assistant") | .message.content[]? | select(.type=="thinking") | .thinking' "$TRANSCRIPT" | grep -v '^""$'
  ```
- **Tool calls** (for sources + summary):
  ```bash
  jq -c 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | {name, input}' "$TRANSCRIPT"
  ```

Use the tool-calls output to derive:
- **Sources read**: every `url` from WebFetch/WebSearch inputs, every `file_path` from Read inputs, every `pattern` or `query` from Grep/WebSearch inputs. Deduplicate.
- **Tool calls summary table**: count per tool name.

## 5. Build and write the log file

Use Write to create `$LOG_PATH` with this exact structure:

```markdown
# <title in human-readable form> — <ISO8601 timestamp>

**Session ID**: `<SESSION_ID>`
**Transcript**: `<TRANSCRIPT path>`

## Inquiries
<numbered list of user prompts, chronological, verbatim, synthetic entries skipped>

## Outputs
<numbered list of assistant text responses, chronological, verbatim. Truncate any single response over 1500 chars to first 1500 + "\n\n...[truncated — see transcript for full]">

## Thinking context
<all non-empty thinking blocks, in order. If none, write: "(no thinking blocks recorded in this session)">

## Sources read
<bulleted, deduplicated. Format: `- <url-or-path>` per line. If empty: "(none)">

## Tool calls summary
| Tool | Count | Example input |
|------|-------|---------------|
<one row per distinct tool used, sorted by count desc>

## Lessons Learned
<3–7 bullets analyzing the session. Look for: token-wasting patterns (re-reading same file, redundant tool calls, over-broad searches), unverified assumptions that turned out wrong, places the user had to correct course, missing context that caused a wrong turn early. Be specific — name the moment ("at turn N, I assumed X without checking, then had to redo Y"). If the session was clean, write "(no notable issues — execution matched plan)" rather than padding.>

## TODO
<extracted open items, each prefixed `- [ ]`. Look for: tasks user asked for but not completed, follow-ups the user mentioned, deferred decisions, "Phase 2" / "later" items from any plan. If none: "(no open items)".>
```

## 6. Update ~/CLAUDE.md

Replace the block between `<!-- LATEST_LOG_START -->` and `<!-- LATEST_LOG_END -->` (markers already exist) with:

```markdown
<!-- LATEST_LOG_START -->
## Latest Session Log
- [<FILENAME>](logs/Claude_logs/<FILENAME>) — <one-line summary, ≤80 chars>
<!-- LATEST_LOG_END -->
```

Implementation: use Read on `~/CLAUDE.md`, then Edit to replace the marker block. The whole block (including both markers) gets rewritten so any leftover whitespace is cleaned.

## 7. Stage the handoff

Use Write to create `~/.claude/handoff_pending.md`:

```markdown
# Handoff from previous session — <ISO8601 timestamp>

## Summary of what was done
<2–5 sentences. The shape of what the previous session accomplished, in plain prose. Mention the log file path.>

## Open tasks
<copy the TODO section from the log, verbatim, including the `- [ ]` checkboxes>

## Relevant info to finish them
<key facts the next session will need: file paths touched, decisions made, gotchas discovered, what NOT to redo. Be specific and complete — lean toward over-including, this is what saves work post-/clear. Bullet list.>

## Full log
See: `~/logs/Claude_logs/<FILENAME>`
```

## 8. Final output to user

Print exactly (no preamble, no explanation):

```
DONE.
- Log: ~/logs/Claude_logs/<FILENAME>
- CLAUDE.md pointer: updated
- Handoff: ~/.claude/handoff_pending.md

Type /clear next — the SessionStart hook will auto-inject the handoff into the fresh session.
```

Then stop. Do not continue with other work.

## Notes

- Do not use emojis anywhere — the user prefers plain text.
- If any extraction step fails (transcript malformed, jq error), still produce the log with whatever sections you have. Mark missing sections explicitly: `(extraction failed: <reason>)`. Never abort silently.
- Keep all outputs in the log verbatim — do not paraphrase user prompts or your own outputs. Lessons Learned and Summary are the only places where you synthesize.
