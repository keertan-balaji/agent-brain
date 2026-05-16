#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v rg >/dev/null 2>&1; then
  printf "ripgrep required for end-to-end test\n" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
vault="$tmp/vault"

if ! bash skills/obsidian-setup/scripts/scaffold-vault.sh "$vault" >/dev/null; then
  printf "scaffold failed\n" >&2; exit 1
fi

path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$vault" decision "Pick redis for JWT store" "auth,redis" "brain")
if [ ! -f "$path" ]; then printf "decision not captured\n" >&2; exit 1; fi

if ! bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$path" >/dev/null 2>&1; then
  printf "captured note fails validation\n" >&2
  cat "$path" >&2; exit 1
fi

hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$vault" "JWT")
if ! printf '%s\n' "$hits" | grep -q "pick-redis-for-jwt-store.md"; then
  printf "recall did not find the captured decision\n" >&2
  printf "hits were:\n%s\n" "$hits" >&2
  exit 1
fi

glossary_path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$vault" glossary "JWT" "auth" "")
if [ ! -f "$glossary_path" ]; then printf "glossary not captured\n" >&2; exit 1; fi

hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$vault" "JWT")
first=$(printf '%s\n' "$hits" | head -n1)
if ! printf '%s' "$first" | grep -q 'knowledge/glossary/jwt.md'; then
  printf "recall ranking broken — expected glossary first, got: %s\n" "$first" >&2
  exit 1
fi

echo "user content" > "$vault/_meta/AGENTS.md"
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$vault" >/dev/null
if ! grep -q "user content" "$vault/_meta/AGENTS.md"; then
  printf "re-scaffold overwrote user file\n" >&2; exit 1
fi

printf "end-to-end ok\n"
