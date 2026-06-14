---
name: log
description: Capture the current session as a structured log, update CLAUDE.md, refresh the three session-log wiki HTMLs incrementally, and stage a handoff for /clear. Use when the user runs /log or asks to log/checkpoint the session.
argument-hint: [optional title]
---

You are executing the `/log` command. Your job: write a comprehensive log of the current session to disk, point CLAUDE.md at it, incrementally update the three wiki HTMLs, stage a handoff, and tell the user what to do next.

Do **everything** in this command — do not stop partway. Do not ask the user for input. At the end, the only message to the user is the final status block described at the bottom.

## 1. Determine the title

If `$ARGUMENTS` is non-empty, use it as the title. Otherwise, generate a 3–5 word title from the session's primary topic by reading recent user prompts.

Sanitize the title to a slug: lowercase, replace whitespace and punctuation with `_`, strip everything not `[a-z0-9_]`, collapse repeated `_`, trim leading/trailing `_`. Cap at 5 words / 50 characters.

Examples:
- `$ARGUMENTS = "Build /log slash command"` → `build_log_slash_command`
- empty, session about token reduction → `token_reduction_research`

## 2. Locate the current transcript

Prefer `${CLAUDE_SESSION_ID}` when the skill runtime exposes it — it names this exact session and sidesteps the parallel-session race. Fall back to recently-modified mtime otherwise.

```bash
PROJECTS_DIR="$HOME/.claude/projects"
TRANSCRIPT=""
if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
  TRANSCRIPT=$(find "$PROJECTS_DIR" -maxdepth 2 -name "${CLAUDE_SESSION_ID}.jsonl" 2>/dev/null | head -1)
fi
if [[ -z "$TRANSCRIPT" ]]; then
  RECENT=$(find "$PROJECTS_DIR" -maxdepth 2 -name '*.jsonl' -mmin -2 2>/dev/null)
  RECENT_COUNT=$(printf '%s\n' "$RECENT" | grep -c . || true)
  if [[ "$RECENT_COUNT" -eq 1 ]]; then
    TRANSCRIPT="$RECENT"
  elif [[ "$RECENT_COUNT" -gt 1 ]]; then
    TRANSCRIPT=$(printf '%s\n' "$RECENT" | xargs ls -t 2>/dev/null | head -1)
    echo "NOTE: $RECENT_COUNT active transcripts; picked $TRANSCRIPT by mtime." >&2
    echo "If wrong session, grep recent transcripts for a unique phrase from your prompts:" >&2
    echo "  grep -l '<unique-phrase>' $(printf '%s ' $RECENT)" >&2
  else
    TRANSCRIPT=$(ls -t "$PROJECTS_DIR"/*/*.jsonl 2>/dev/null | head -1)
  fi
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

Replace the block between `<!-- LATEST_LOG_START -->` and `<!-- LATEST_LOG_END -->` (markers already exist) with the new pointer. Do the read-modify-write atomically under an exclusive `flock` so concurrent `/log` runs can't race. Substitute `<FILENAME>` and `<SUMMARY>` (≤80 chars) before running:

```bash
mkdir -p "$HOME/.claude"
(
  flock -x 9
  python3 - "<FILENAME>" "<SUMMARY>" <<'PY'
import re, sys, pathlib
fname, summary = sys.argv[1], sys.argv[2]
p = pathlib.Path.home() / "CLAUDE.md"
new_block = (
    "<!-- LATEST_LOG_START -->\n"
    "## Latest Session Log\n"
    f"- [{fname}](logs/Claude_logs/{fname}) — {summary}\n"
    "<!-- LATEST_LOG_END -->"
)
text = p.read_text()
out, n = re.subn(
    r"<!-- LATEST_LOG_START -->.*?<!-- LATEST_LOG_END -->",
    new_block, text, count=1, flags=re.DOTALL,
)
if n == 0:
    print("MARKER_BLOCK_MISSING — skipping CLAUDE.md update", file=sys.stderr)
    sys.exit(0)
p.write_text(out)
print(f"Updated CLAUDE.md marker -> {fname}")
PY
) 9>"$HOME/.claude/claude-md.lock"
```

## 7. Update the three session-log wiki HTMLs (incremental, append-only)

These live in `~/logs/Claude_logs/wiki/` (`open-tasks.html`, `completed-by-subject.html`, `lessons-learned.html`). **Never resummarize them.** You only contribute *this session's* deltas; the helper splices them in under each file's "Session Updates" region. Build a `delta.json` from material you already synthesized in step 5, then run the helper.

Field mapping — be conservative, quality over volume:
- `todos_new` — open items that are **genuinely new this session** (not carried over from the loaded handoff / not already present in `open-tasks.html`). Each is `{title, meta, body}`; `meta` may contain `<code>…</code>` markup (paths), `title`/`body` are plain text (auto-escaped).
- `todos_done` — short, **uniquely-identifying substrings** of tasks that existed *before* this session (from the prior handoff's Open Tasks or `open-tasks.html`) and were **completed** this session. The helper prepends `DONE <date>:` to the matching `<h3>` in place. Pick substrings distinctive enough to match exactly one card; the helper warns on a miss.
- `completed_new` — 1–3 plain-text sentences summarizing notable work finished or decisions/clarifications made this session. Rendered as `Edit:`-prefixed dated entries.
- `lessons_new` — the durable bullets from your Lessons Learned section (drop the "(no notable issues)" filler). Plain text.

Omit any field that has nothing for it (don't emit empty placeholders). If a whole session produced no wiki-worthy deltas, skip this step entirely.

```bash
mkdir -p /tmp/log-build-$$
cat > /tmp/log-build-$$/delta.json <<'JSON'
{
  "date": "<YYYY-MM-DD>",
  "todos_new":    [ { "title": "...", "meta": "<code>path</code>", "body": "..." } ],
  "todos_done":   [ "unique substring of a prior open task" ],
  "completed_new":[ "what got done / clarified this session" ],
  "lessons_new":  [ "durable lesson" ]
}
JSON
# Resolve the helper relative to this skill's repo (survives any clone location),
# with the canonical path as fallback.
SKILL_REAL="$(readlink -f "$HOME/.claude/skills/log/SKILL.md")"
WIKI_HELPER="$(cd "$(dirname "$SKILL_REAL")/../../scripts" 2>/dev/null && pwd)/log_wiki_update.py"
[[ -f "$WIKI_HELPER" ]] || WIKI_HELPER="$HOME/projects/thoth/scripts/log_wiki_update.py"
python3 "$WIKI_HELPER" --delta /tmp/log-build-$$/delta.json
```

The helper is idempotent for `DONE` marking (won't double-prefix) and auto-creates each file's append region if missing. If a wiki file is absent it prints `MISSING:` and continues — non-fatal. Capture its stdout; include a one-line summary of what it changed in the final status block.

## 8. Stage the handoff

Use Write to create `~/.claude/handoff_pending.md`. The first paragraph is a directive aimed at Claude in the new session — without it, Claude has the context but doesn't surface it spontaneously.

```markdown
**INSTRUCTION TO CLAUDE**: This is a handoff from a prior session, auto-injected as context (or manually loaded via `/handoff`). On your first response, briefly acknowledge the prior work in 1–2 sentences, list the Open Tasks, and ask the user which to continue. Do not start executing tasks autonomously.

---

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

## 9. Final output to user

Print exactly (no preamble, no explanation):

```
DONE.
- Log: ~/logs/Claude_logs/<FILENAME>
- CLAUDE.md pointer: updated
- Wiki HTMLs: <one-line summary of helper output, or "no deltas this session">
- Handoff: ~/.claude/handoff_pending.md

Type /clear next — the SessionStart hook will auto-inject the handoff into the fresh session.
```

Then stop. Do not continue with other work.

## Notes

- Do not use emojis anywhere — the user prefers plain text.
- If any extraction step fails (transcript malformed, jq error), still produce the log with whatever sections you have. Mark missing sections explicitly: `(extraction failed: <reason>)`. Never abort silently.
- Keep all outputs in the log verbatim — do not paraphrase user prompts or your own outputs. Lessons Learned, Summary, and the wiki deltas are the only places where you synthesize.
- The wiki update (step 7) is additive only. If you are tempted to "clean up" or rewrite an existing wiki entry, don't — that is a separate, explicit `/wiki-build`-style task, not `/log`.
