#!/usr/bin/env bash
# install-claude-code.sh
# Symlinks every skill in this repo into ~/.claude/skills/ so Claude Code
# loads them on the next session. Idempotent — existing correct symlinks
# are left alone, existing wrong symlinks are replaced (with a warning),
# regular files at the target paths abort the install.
#
# Output: one line per skill describing the action taken.

set -uo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
skills_src="$repo_root/skills"

if [ ! -d "$skills_src" ]; then
  printf "skills directory not found: %s\n" "$skills_src" >&2
  exit 1
fi

target_dir="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$target_dir"

installed=0
already=0
replaced=0
failed=0

for skill_path in "$skills_src"/*/; do
  [ -d "$skill_path" ] || continue
  skill_name=$(basename "$skill_path")
  src=$(cd "$skill_path" && pwd)
  dst="$target_dir/$skill_name"

  if [ -L "$dst" ]; then
    current=$(readlink "$dst")
    if [ "$current" = "$src" ]; then
      printf "ok    %-32s → %s\n" "$skill_name" "$current"
      already=$((already + 1))
      continue
    fi
    printf "warn  %-32s replacing symlink %s → %s\n" "$skill_name" "$current" "$src"
    rm "$dst"
    ln -s "$src" "$dst"
    replaced=$((replaced + 1))
    continue
  fi

  if [ -e "$dst" ]; then
    printf "skip  %-32s target exists and is not a symlink: %s\n" "$skill_name" "$dst"
    failed=$((failed + 1))
    continue
  fi

  ln -s "$src" "$dst"
  printf "new   %-32s → %s\n" "$skill_name" "$src"
  installed=$((installed + 1))
done

printf "\nsummary: %d new, %d already, %d replaced, %d skipped\n" \
  "$installed" "$already" "$replaced" "$failed"

if [ "$failed" -gt 0 ]; then
  printf "skipped entries may already be installed via another method — inspect %s\n" "$target_dir" >&2
  exit 2
fi

printf "Restart Claude Code (or run /skills reload if available) to pick up new skills.\n"
