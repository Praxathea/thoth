#!/usr/bin/env bash
# SessionStart hook — fires on /clear (matcher="clear" in settings.json).
# If a pending handoff exists from a prior /log run, inject it as additionalContext
# into the fresh session, then archive so it doesn't replay on later /clears.
set -euo pipefail

HANDOFF="$HOME/.claude/handoff_pending.md"
ARCHIVE_DIR="$HOME/.claude/handoff_archive"

[[ -f "$HANDOFF" ]] || exit 0

mkdir -p "$ARCHIVE_DIR"
jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: .}}' < "$HANDOFF"
mv "$HANDOFF" "$ARCHIVE_DIR/$(date +%Y-%m-%d_%H-%M-%S).md"
