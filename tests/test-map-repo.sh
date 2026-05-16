#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-map-repo/scripts/map-repo.sh
VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$SCRIPT" ]; then
  printf "map-repo script missing: %s\n" "$SCRIPT" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

vault="$tmp/vault"
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$vault" >/dev/null

# Build a synthetic repo: Python project, with README and git history.
repo="$tmp/myrepo"
mkdir -p "$repo/src" "$repo/tests" "$repo/docs"
cat > "$repo/pyproject.toml" <<'EOF'
[project]
name = "myrepo"
version = "0.1.0"
EOF
cat > "$repo/README.md" <<'EOF'
# myrepo

A demo project used by the obsidian-map-repo test.

## Install

`pip install -e .`
EOF
echo "print('hi')" > "$repo/src/main.py"
echo "def test_x(): pass" > "$repo/tests/test_x.py"
echo "node_modules/" > "$repo/.gitignore"
( cd "$repo" && git init -q && \
  git -c user.email=t@t -c user.name=t add -A && \
  git -c user.email=t@t -c user.name=t commit -q -m "feat: initial commit" && \
  echo "" >> README.md && \
  git -c user.email=t@t -c user.name=t add -A && \
  git -c user.email=t@t -c user.name=t commit -q -m "docs: README tweak" ) || {
  printf "git setup failed\n" >&2; exit 1
}

# Case 1: missing args.
if bash "$SCRIPT" >/dev/null 2>&1; then
  printf "no-args accepted\n" >&2; exit 1
fi
if bash "$SCRIPT" "$vault" >/dev/null 2>&1; then
  printf "missing repo arg accepted\n" >&2; exit 1
fi

# Case 2: nonexistent repo.
if bash "$SCRIPT" "$vault" "$tmp/nope" >/dev/null 2>&1; then
  printf "nonexistent repo accepted\n" >&2; exit 1
fi

# Case 3: file-not-dir rejected.
touch "$tmp/afile"
if bash "$SCRIPT" "$vault" "$tmp/afile" >/dev/null 2>&1; then
  printf "file-not-dir accepted\n" >&2; exit 1
fi

# Case 4: fresh repo with no existing project — bootstraps then maps.
out=$(bash "$SCRIPT" "$vault" "$repo")
if [ -z "$out" ] || [ ! -f "$out" ]; then
  printf "map file not created\n" >&2; exit 1
fi
case "$out" in
  */projects/myrepo/repo-map.md) ;;
  *) printf "unexpected map path: %s\n" "$out" >&2; exit 1 ;;
esac
[ -f "$vault/projects/myrepo/index.md" ] || { printf "project index missing\n" >&2; exit 1; }

# Frontmatter valid.
if ! bash "$VALIDATOR" "$out" >/dev/null 2>&1; then
  printf "map file fails frontmatter validation\n" >&2
  head -20 "$out" >&2; exit 1
fi

# Contains expected sections.
for needle in \
  "Repo map" \
  "Location" \
  "Stack" \
  "Python (pyproject.toml)" \
  "Top-level layout" \
  "src" \
  "tests" \
  "README excerpt" \
  "demo project used by the obsidian-map-repo test" \
  "Git activity" \
  "feat: initial commit" \
  "File counts" \
  "Suggested follow-ups"; do
  if ! grep -q -- "$needle" "$out"; then
    printf "map missing expected content: %s\n" "$needle" >&2
    exit 1
  fi
done

# Case 5: re-running without --force fails.
if bash "$SCRIPT" "$vault" "$repo" >/dev/null 2>&1; then
  printf "re-map without --force accepted\n" >&2; exit 1
fi

# Case 6: --force overwrites.
sleep 1
echo "modified content" >> "$repo/README.md"
( cd "$repo" && git -c user.email=t@t -c user.name=t commit -aq -m "docs: another line" )
out2=$(bash "$SCRIPT" "$vault" "$repo" --force)
[ -f "$out2" ] || { printf "force map not created\n" >&2; exit 1; }
grep -q "docs: another line" "$out2" || { printf "force re-map didn't refresh git activity\n" >&2; exit 1; }

# Case 7: non-git repo handled.
plain="$tmp/plainrepo"
mkdir -p "$plain"
cat > "$plain/package.json" <<'EOF'
{ "name": "plain", "version": "0.0.0" }
EOF
out3=$(bash "$SCRIPT" "$vault" "$plain")
grep -q "Node" "$out3" || { printf "Node stack not detected\n" >&2; exit 1; }
grep -q "not a git repository" "$out3" || { printf "non-git not flagged\n" >&2; exit 1; }

# Case 8: repo with no README, no manifests.
bare="$tmp/barerepo"
mkdir -p "$bare/random"
touch "$bare/random/x.txt"
out4=$(bash "$SCRIPT" "$vault" "$bare")
grep -q "no README detected" "$out4" || { printf "missing README not flagged\n" >&2; exit 1; }
grep -q "no recognized manifests detected" "$out4" || { printf "missing manifests not flagged\n" >&2; exit 1; }

printf "map-repo ok\n"
