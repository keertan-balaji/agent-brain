#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-recall/scripts/recall-search.sh
if [ ! -x "$SCRIPT" ]; then
  printf "recall script missing: %s\n" "$SCRIPT" >&2
  exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
  printf "ripgrep not installed — install with: sudo pacman -S ripgrep\n" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/knowledge/architecture" "$tmp/agent-memory/decisions" "$tmp/projects/foo" "$tmp/daily"
cat > "$tmp/knowledge/architecture/auth.md" <<'EOF'
---
type: architecture
status: active
created: 2026-05-01
updated: 2026-05-01
---
# Auth subsystem
Uses JWT rotation every 15 minutes.
EOF
cat > "$tmp/agent-memory/decisions/2026-05-10-jwt-store.md" <<'EOF'
---
type: decision
status: active
created: 2026-05-10
updated: 2026-05-10
---
# Decided to store JWT keys in redis
EOF
cat > "$tmp/projects/foo/index.md" <<'EOF'
---
type: project
status: active
created: 2026-05-15
updated: 2026-05-15
---
# foo project
EOF

out=$(bash "$SCRIPT" "$tmp" "JWT")
if [ -z "$out" ]; then
  printf "no output from recall\n" >&2; exit 1
fi

first=$(printf '%s\n' "$out" | head -n1)
if ! printf '%s' "$first" | grep -q 'knowledge/architecture/auth.md'; then
  printf "expected knowledge/ first, got: %s\n" "$first" >&2
  exit 1
fi

if ! printf '%s\n' "$out" | grep -q 'agent-memory/decisions/2026-05-10-jwt-store.md'; then
  printf "missing agent-memory hit\n" >&2; exit 1
fi

if printf '%s\n' "$out" | grep -q 'projects/foo/index.md'; then
  printf "unexpected projects hit for JWT query\n" >&2; exit 1
fi

many=$(printf '%s\n' "$out" | wc -l)
if [ "$many" -gt 5 ]; then
  printf "too many hits (%d > 5)\n" "$many" >&2; exit 1
fi

printf "recall search ok\n"
