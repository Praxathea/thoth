#!/usr/bin/env bash
# Thoth installer — symlinks the /log skill, /handoff command + SessionStart hook into ~/.claude/
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMDS_DIR="$HOME/.claude/commands"
SKILLS_DIR="$HOME/.claude/skills"
HOOKS_DIR="$HOME/.claude/hooks"
LOGS_DIR="$HOME/logs/Claude_logs"
WIKI_DIR="$HOME/logs/Claude_logs/wiki"
ARCHIVE_DIR="$HOME/.claude/handoff_archive"

TS=$(date +%Y-%m-%d_%H-%M-%S)

backup_if_exists() {
  local path="$1"
  if [[ -e "$path" && ! -L "$path" ]]; then
    mv "$path" "${path}.bak.${TS}"
    echo "  backed up existing → ${path}.bak.${TS}"
  elif [[ -L "$path" ]]; then
    rm "$path"
    echo "  removed existing symlink → $path"
  fi
}

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing required command: $1" >&2; exit 1; }
}

echo "Thoth installer"
echo "==============="
require jq

echo
echo "Creating directories..."
mkdir -p "$CMDS_DIR" "$SKILLS_DIR/log" "$HOOKS_DIR" "$LOGS_DIR" "$WIKI_DIR" "$ARCHIVE_DIR"
echo "  $CMDS_DIR"
echo "  $SKILLS_DIR/log"
echo "  $HOOKS_DIR"
echo "  $LOGS_DIR"
echo "  $WIKI_DIR"
echo "  $ARCHIVE_DIR"

echo
echo "Installing /log skill..."
backup_if_exists "$SKILLS_DIR/log/SKILL.md"
ln -s "$REPO_DIR/skills/log/SKILL.md" "$SKILLS_DIR/log/SKILL.md"
echo "  symlinked $SKILLS_DIR/log/SKILL.md → $REPO_DIR/skills/log/SKILL.md"
chmod +x "$REPO_DIR/scripts/log_wiki_update.py"
echo "  helper ready: $REPO_DIR/scripts/log_wiki_update.py (called by the skill, no symlink needed)"

echo
echo "Installing /handoff command..."
backup_if_exists "$CMDS_DIR/handoff.md"
ln -s "$REPO_DIR/commands/handoff.md" "$CMDS_DIR/handoff.md"
echo "  symlinked $CMDS_DIR/handoff.md → $REPO_DIR/commands/handoff.md"

echo
echo "Installing SessionStart hook..."
backup_if_exists "$HOOKS_DIR/load-handoff.sh"
chmod +x "$REPO_DIR/hooks/load-handoff.sh"
ln -s "$REPO_DIR/hooks/load-handoff.sh" "$HOOKS_DIR/load-handoff.sh"
echo "  symlinked $HOOKS_DIR/load-handoff.sh → $REPO_DIR/hooks/load-handoff.sh"

echo
echo "Files installed. One manual step remaining:"
echo
echo "  Add the following to ~/.claude/settings.json under .hooks.SessionStart"
echo "  (merge with any existing SessionStart entries):"
echo
sed 's/^/    /' "$REPO_DIR/settings.snippet.json"
echo
echo "Then restart Claude Code so the /log skill is loaded."
echo
echo "Test: in a Claude Code session, run /log — it should produce a log file in $LOGS_DIR,"
echo "update the CLAUDE.md pointer, and incrementally append to the wiki HTMLs in $WIKI_DIR."
