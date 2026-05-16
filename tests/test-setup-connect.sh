#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

CONNECT=skills/obsidian-setup/scripts/connect-vault.sh
RESOLVE=skills/obsidian-setup/scripts/resolve-vault.sh
RESOLVE_BRAIN=skills/obsidian-setup/scripts/resolve-brain.sh

for s in "$CONNECT" "$RESOLVE" "$RESOLVE_BRAIN"; do
  if [ ! -x "$s" ]; then
    printf "script missing or not executable: %s\n" "$s" >&2
    exit 1
  fi
done

tmp=$(mktemp -d)
cfg_dir=$(mktemp -d)
trap 'rm -rf "$tmp" "$cfg_dir"' EXIT

# Isolate the persisted config file via env override so we don't clobber the
# real repo's .vault-path during tests.
export BRAIN_VAULT_CONFIG="$cfg_dir/vault-path"

# Case 1: empty path rejected.
if bash "$CONNECT" "" >/dev/null 2>&1; then
  printf "empty path accepted\n" >&2; exit 1
fi

# Case 2: nonexistent path rejected.
if bash "$CONNECT" "$tmp/does-not-exist" >/dev/null 2>&1; then
  printf "nonexistent path accepted\n" >&2; exit 1
fi

# Case 3: regular file (not dir) rejected.
touch "$tmp/afile"
if bash "$CONNECT" "$tmp/afile" >/dev/null 2>&1; then
  printf "file-not-dir accepted\n" >&2; exit 1
fi

# Case 4: empty dir — accepted, Agent-Brain/ scaffolded inside it, persisted.
mkdir -p "$tmp/empty-vault"
if ! bash "$CONNECT" "$tmp/empty-vault" >/dev/null; then
  printf "empty-dir connect failed\n" >&2; exit 1
fi
for f in Agent-Brain/_meta/AGENTS.md Agent-Brain/templates/decision.md Agent-Brain/templates/project-development.md; do
  if [ ! -f "$tmp/empty-vault/$f" ]; then
    printf "scaffold gap not filled: %s\n" "$f" >&2; exit 1
  fi
done
# Vault root must not get the scaffold sections.
for d in knowledge agent-memory projects daily _meta templates; do
  if [ -d "$tmp/empty-vault/$d" ]; then
    printf "scaffolded section leaked into vault root: %s\n" "$d" >&2; exit 1
  fi
done
got=$(cat "$BRAIN_VAULT_CONFIG")
if [ "$got" != "$tmp/empty-vault" ]; then
  printf "persisted path mismatch: %s vs %s\n" "$got" "$tmp/empty-vault" >&2; exit 1
fi

# Case 5: existing vault with .obsidian/ + user content — accepted, Agent-Brain/ created, user content preserved.
mkdir -p "$tmp/real-vault/.obsidian"
mkdir -p "$tmp/real-vault/Inbox" "$tmp/real-vault/Daily Notes"
echo "user note body" > "$tmp/real-vault/Inbox/note.md"
echo "daily entry" > "$tmp/real-vault/Daily Notes/2026-05-17.md"
if ! bash "$CONNECT" "$tmp/real-vault" >/dev/null; then
  printf "existing-vault connect failed\n" >&2; exit 1
fi
if ! grep -q "user note body" "$tmp/real-vault/Inbox/note.md"; then
  printf "connect overwrote user content (Inbox)\n" >&2; exit 1
fi
if ! grep -q "daily entry" "$tmp/real-vault/Daily Notes/2026-05-17.md"; then
  printf "connect overwrote user content (Daily Notes)\n" >&2; exit 1
fi
[ -f "$tmp/real-vault/Agent-Brain/_meta/AGENTS.md" ] || { printf "AGENTS.md not added\n" >&2; exit 1; }
[ -f "$tmp/real-vault/Agent-Brain/templates/project-research.md" ] || { printf "project template not added\n" >&2; exit 1; }
got=$(cat "$BRAIN_VAULT_CONFIG")
if [ "$got" != "$tmp/real-vault" ]; then
  printf "persisted path not updated\n" >&2; exit 1
fi

# Case 5b: resolve-brain returns vault + /Agent-Brain.
brain_resolved=$(bash "$RESOLVE_BRAIN")
if [ "$brain_resolved" != "$tmp/real-vault/Agent-Brain" ]; then
  printf "resolve-brain wrong: %s\n" "$brain_resolved" >&2; exit 1
fi

# Case 5c: BRAIN_SUBDIR override flows through resolve-brain.
brain_custom=$(BRAIN_SUBDIR="My-AI" bash "$RESOLVE_BRAIN")
if [ "$brain_custom" != "$tmp/real-vault/My-AI" ]; then
  printf "BRAIN_SUBDIR not honored by resolve-brain: %s\n" "$brain_custom" >&2; exit 1
fi

# Case 6: resolve-vault prefers the persisted config.
unset OBSIDIAN_VAULT
resolved=$(bash "$RESOLVE")
if [ "$resolved" != "$tmp/real-vault" ]; then
  printf "resolve did not return persisted path: %s\n" "$resolved" >&2; exit 1
fi

# Case 7: OBSIDIAN_VAULT env beats persisted config.
mkdir -p "$tmp/env-vault"
export OBSIDIAN_VAULT="$tmp/env-vault"
resolved=$(bash "$RESOLVE")
if [ "$resolved" != "$tmp/env-vault" ]; then
  printf "env override ignored: %s\n" "$resolved" >&2; exit 1
fi
unset OBSIDIAN_VAULT

# Case 8: resolve falls back to default when no env, no config.
rm -f "$BRAIN_VAULT_CONFIG"
resolved=$(bash "$RESOLVE")
expected="$HOME/Documents/ObsidianVault"
if [ "$resolved" != "$expected" ]; then
  printf "default fallback wrong: %s vs %s\n" "$resolved" "$expected" >&2; exit 1
fi

# Case 9: relative path stored as absolute.
mkdir -p "$tmp/rel-target"
cd "$tmp"
if ! bash "$OLDPWD/$CONNECT" "rel-target" >/dev/null; then
  printf "relative path connect failed\n" >&2
  cd "$OLDPWD"
  exit 1
fi
cd "$OLDPWD"
stored=$(cat "$BRAIN_VAULT_CONFIG")
case "$stored" in
  /*) ;;
  *) printf "stored path not absolute: %s\n" "$stored" >&2; exit 1 ;;
esac
if [ ! -d "$stored" ]; then
  printf "stored absolute path doesn't resolve: %s\n" "$stored" >&2; exit 1
fi

printf "connect ok\n"
