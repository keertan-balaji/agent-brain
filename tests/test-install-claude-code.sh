#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

INSTALLER=clients/install-claude-code.sh
if [ ! -x "$INSTALLER" ]; then
  printf "installer missing: %s\n" "$INSTALLER" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export CLAUDE_SKILLS_DIR="$tmp/skills"

# Case 1: fresh install creates a symlink for every skill.
if ! bash "$INSTALLER" >/dev/null; then
  printf "fresh install failed\n" >&2; exit 1
fi
expected_skills=$(ls -1 skills/ | sort)
got_skills=$(ls -1 "$CLAUDE_SKILLS_DIR" | sort)
if [ "$expected_skills" != "$got_skills" ]; then
  printf "skill set mismatch:\nexpected:\n%s\ngot:\n%s\n" "$expected_skills" "$got_skills" >&2
  exit 1
fi
for s in $expected_skills; do
  if [ ! -L "$CLAUDE_SKILLS_DIR/$s" ]; then
    printf "not a symlink: %s\n" "$CLAUDE_SKILLS_DIR/$s" >&2; exit 1
  fi
  target=$(readlink "$CLAUDE_SKILLS_DIR/$s")
  case "$target" in
    /*) ;;
    *) printf "symlink target not absolute: %s -> %s\n" "$s" "$target" >&2; exit 1 ;;
  esac
  if [ ! -d "$target" ]; then
    printf "symlink target not a dir: %s -> %s\n" "$s" "$target" >&2; exit 1
  fi
  if [ ! -f "$target/SKILL.md" ]; then
    printf "skill missing SKILL.md: %s\n" "$target" >&2; exit 1
  fi
done

# Case 2: re-running is a no-op (all entries marked "ok").
out=$(bash "$INSTALLER")
if printf '%s\n' "$out" | grep -q '^new'; then
  printf "second run reported new installs:\n%s\n" "$out" >&2; exit 1
fi
if ! printf '%s\n' "$out" | grep -q '^ok'; then
  printf "second run didn't report 'ok' entries:\n%s\n" "$out" >&2; exit 1
fi

# Case 3: stale symlink gets replaced.
sk="obsidian-recall"
rm "$CLAUDE_SKILLS_DIR/$sk"
mkdir -p "$tmp/stale-target"
ln -s "$tmp/stale-target" "$CLAUDE_SKILLS_DIR/$sk"
out=$(bash "$INSTALLER")
if ! printf '%s\n' "$out" | grep -q "^warn  $sk"; then
  printf "stale symlink not replaced:\n%s\n" "$out" >&2; exit 1
fi
target=$(readlink "$CLAUDE_SKILLS_DIR/$sk")
case "$target" in
  */skills/$sk) ;;
  *) printf "replaced symlink wrong target: %s\n" "$target" >&2; exit 1 ;;
esac

# Case 4: regular file at target path → skip with non-zero exit.
sk2="obsidian-capture"
rm "$CLAUDE_SKILLS_DIR/$sk2"
echo "user file" > "$CLAUDE_SKILLS_DIR/$sk2"
if bash "$INSTALLER" >/dev/null 2>&1; then
  printf "installer didn't error on existing non-symlink\n" >&2; exit 1
fi

printf "install-claude-code ok\n"
