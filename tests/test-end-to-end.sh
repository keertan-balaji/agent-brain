#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v rg >/dev/null 2>&1; then
  printf "ripgrep required for end-to-end test\n" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
vault="$tmp/vault"

# Simulate the user's existing vault content — must be preserved end-to-end.
mkdir -p "$vault/Inbox"
echo "user's daily note" > "$vault/Inbox/scratch.md"

if ! bash skills/obsidian-setup/scripts/scaffold-brain.sh "$vault" >/dev/null; then
  printf "scaffold failed\n" >&2; exit 1
fi

brain="$vault/Agent-Brain"
[ -d "$brain" ] || { printf "Agent-Brain/ not created\n" >&2; exit 1; }

path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$brain" decision "Pick redis for JWT store" "auth,redis" "brain")
if [ ! -f "$path" ]; then printf "decision not captured\n" >&2; exit 1; fi
case "$path" in
  "$brain"/*) ;;
  *) printf "decision written outside Agent-Brain/: %s\n" "$path" >&2; exit 1 ;;
esac

if ! bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$path" >/dev/null 2>&1; then
  printf "captured note fails validation\n" >&2
  cat "$path" >&2; exit 1
fi

hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$brain" "JWT")
if ! printf '%s\n' "$hits" | grep -q "pick-redis-for-jwt-store.md"; then
  printf "recall did not find the captured decision\n" >&2
  printf "hits were:\n%s\n" "$hits" >&2
  exit 1
fi

glossary_path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$brain" glossary "JWT" "auth" "")
if [ ! -f "$glossary_path" ]; then printf "glossary not captured\n" >&2; exit 1; fi

hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$brain" "JWT")
first=$(printf '%s\n' "$hits" | head -n1)
if ! printf '%s' "$first" | grep -q 'knowledge/glossary/jwt.md'; then
  printf "recall ranking broken — expected glossary first, got: %s\n" "$first" >&2
  exit 1
fi

# Recall is bounded to the brain — must not surface user vault content.
if printf '%s\n' "$hits" | grep -q "/Inbox/"; then
  printf "recall leaked into user vault content\n" >&2
  exit 1
fi

# User content untouched throughout.
if ! grep -q "user's daily note" "$vault/Inbox/scratch.md"; then
  printf "user content modified by end-to-end run\n" >&2; exit 1
fi

# Re-scaffold preserves agent-edited brain content.
echo "user-edited agent doc" > "$brain/_meta/AGENTS.md"
bash skills/obsidian-setup/scripts/scaffold-brain.sh "$vault" >/dev/null
if ! grep -q "user-edited agent doc" "$brain/_meta/AGENTS.md"; then
  printf "re-scaffold overwrote brain file\n" >&2; exit 1
fi

printf "end-to-end ok\n"
