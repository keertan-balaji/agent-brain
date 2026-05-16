#!/usr/bin/env bash
# validate-frontmatter.sh <path-to-note.md>
# Exits 0 if frontmatter is present and contains all required fields with valid type. Exits 1 otherwise.
# Prints diagnostics to stderr.

set -uo pipefail

file=${1:-}
if [ -z "$file" ] || [ ! -f "$file" ]; then
  printf "usage: %s <note.md>\n" "$0" >&2
  exit 1
fi

if ! head -n1 "$file" | grep -q '^---$'; then
  printf "no opening frontmatter delimiter in %s\n" "$file" >&2
  exit 1
fi

fm=$(awk '
  BEGIN { in_fm = 0; count = 0 }
  /^---$/ { count++; if (count == 1) { in_fm = 1; next } else if (count == 2) { in_fm = 0; exit } }
  in_fm { print }
' "$file")

if [ -z "$fm" ]; then
  printf "empty frontmatter in %s\n" "$file" >&2
  exit 1
fi

for key in type status created updated; do
  if ! printf '%s\n' "$fm" | grep -qE "^${key}:"; then
    printf "missing required key '%s' in %s\n" "$key" "$file" >&2
    exit 1
  fi
done

type_value=$(printf '%s\n' "$fm" | grep -E '^type:' | head -n1 | sed -E 's/^type:[[:space:]]*//; s/[[:space:]]+$//')
case "$type_value" in
  decision|session|gotcha|api|architecture|process|glossary|pattern|project|task|meta) ;;
  *)
    printf "invalid type '%s' in %s\n" "$type_value" "$file" >&2
    exit 1
    ;;
esac

status_value=$(printf '%s\n' "$fm" | grep -E '^status:' | head -n1 | sed -E 's/^status:[[:space:]]*//; s/[[:space:]]+$//')
case "$status_value" in
  draft|active|archived|promoted) ;;
  *)
    printf "invalid status '%s' in %s\n" "$status_value" "$file" >&2
    exit 1
    ;;
esac

for key in created updated; do
  v=$(printf '%s\n' "$fm" | grep -E "^${key}:" | head -n1 | sed -E "s/^${key}:[[:space:]]*//; s/[[:space:]]+$//")
  if ! printf '%s' "$v" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    printf "invalid %s date '%s' in %s\n" "$key" "$v" "$file" >&2
    exit 1
  fi
done

exit 0
