#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-capture/scripts/make-note.sh
VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$SCRIPT" ]; then
  printf "make-note script missing\n" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/agent-memory/decisions" "$tmp/agent-memory/gotchas" "$tmp/templates"
cat > "$tmp/templates/decision.md" <<'EOF'
---
type: decision
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
---
# {{title}}
EOF

out=$(bash "$SCRIPT" "$tmp" decision "Use redis for jwt store" "auth,security" "brain")
if [ -z "$out" ]; then printf "no output\n" >&2; exit 1; fi
path=$(printf '%s' "$out" | tr -d '\n')
if [ ! -f "$path" ]; then printf "note not created at %s\n" "$path" >&2; exit 1; fi
case "$path" in
  *agent-memory/decisions/*-use-redis-for-jwt-store.md) ;;
  *) printf "unexpected path: %s\n" "$path" >&2; exit 1 ;;
esac

if ! bash "$VALIDATOR" "$path" >/dev/null 2>&1; then
  printf "generated note failed validation\n" >&2
  cat "$path" >&2
  exit 1
fi

grep -q "tags: \[auth, security\]" "$path" || { printf "tags missing\n" >&2; cat "$path" >&2; exit 1; }
grep -q "Use redis for jwt store" "$path" || { printf "title missing\n" >&2; cat "$path" >&2; exit 1; }
grep -q "project: brain" "$path" || { printf "project missing\n" >&2; cat "$path" >&2; exit 1; }

if bash "$SCRIPT" "$tmp" notathing "x" "" "" >/dev/null 2>&1; then
  printf "invalid type accepted\n" >&2; exit 1
fi

if bash "$SCRIPT" "$tmp" decision "" "" "" >/dev/null 2>&1; then
  printf "empty title accepted\n" >&2; exit 1
fi

printf "capture make-note ok\n"
