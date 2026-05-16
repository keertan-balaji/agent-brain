#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$VALIDATOR" ]; then
  printf "validator not executable: %s\n" "$VALIDATOR" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Case 1: valid note passes
cat > "$tmp/good.md" <<'EOF'
---
type: decision
tags: [auth]
project: brain
status: active
created: 2026-05-17
updated: 2026-05-17
related: []
---
# Body
EOF
if ! bash "$VALIDATOR" "$tmp/good.md" >/dev/null 2>&1; then
  printf "valid note rejected\n" >&2; exit 1
fi

# Case 2: missing required field
cat > "$tmp/missing-status.md" <<'EOF'
---
type: decision
tags: [auth]
created: 2026-05-17
updated: 2026-05-17
---
# Body
EOF
if bash "$VALIDATOR" "$tmp/missing-status.md" >/dev/null 2>&1; then
  printf "missing-status not detected\n" >&2; exit 1
fi

# Case 3: invalid type
cat > "$tmp/bad-type.md" <<'EOF'
---
type: notathing
tags: []
status: active
created: 2026-05-17
updated: 2026-05-17
---
# Body
EOF
if bash "$VALIDATOR" "$tmp/bad-type.md" >/dev/null 2>&1; then
  printf "invalid type not detected\n" >&2; exit 1
fi

# Case 4: no frontmatter at all
printf '# just a body\n' > "$tmp/none.md"
if bash "$VALIDATOR" "$tmp/none.md" >/dev/null 2>&1; then
  printf "no-frontmatter not detected\n" >&2; exit 1
fi

printf "frontmatter validator ok\n"
