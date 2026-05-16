#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-project-bootstrap/scripts/bootstrap-project.sh
VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$SCRIPT" ]; then
  printf "bootstrap script missing: %s\n" "$SCRIPT" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Build a minimal vault (just templates).
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$tmp" >/dev/null

# Case 1: bootstrap a development project
path=$(bash "$SCRIPT" "$tmp" "myrepo" development "Build a CLI tool")
if [ -z "$path" ] || [ ! -f "$path" ]; then printf "no index created\n" >&2; exit 1; fi
case "$path" in
  */projects/myrepo/index.md) ;;
  *) printf "unexpected path: %s\n" "$path" >&2; exit 1 ;;
esac

# Folder structure
for sub in tasks modules; do
  if [ ! -d "$tmp/projects/myrepo/$sub" ]; then
    printf "missing subdir: %s\n" "$sub" >&2; exit 1
  fi
done

# Frontmatter health
if ! bash "$VALIDATOR" "$path" >/dev/null 2>&1; then
  printf "bootstrap index fails validation\n" >&2
  cat "$path" >&2; exit 1
fi
grep -q "^task_type: development$" "$path" || { printf "task_type missing\n" >&2; cat "$path" >&2; exit 1; }
grep -q "^project: myrepo$" "$path" || { printf "project key missing\n" >&2; exit 1; }
grep -q "Build a CLI tool" "$path" || { printf "title missing\n" >&2; exit 1; }

# Case 2: bootstrap a research project (no modules/ dir, has tasks/)
path2=$(bash "$SCRIPT" "$tmp" "perf-investigation" research "Diagnose p99 spike")
if [ ! -f "$path2" ]; then printf "research index not created\n" >&2; exit 1; fi
[ -d "$tmp/projects/perf-investigation/tasks" ] || { printf "tasks dir missing for research\n" >&2; exit 1; }
[ -d "$tmp/projects/perf-investigation/modules" ] && { printf "modules dir should not exist for research\n" >&2; exit 1; }
grep -q "^task_type: research$" "$path2" || { printf "research task_type missing\n" >&2; exit 1; }

# Case 3: bootstrap a repo-analysis project
path3=$(bash "$SCRIPT" "$tmp" "legacy-svc-audit" repo-analysis "Audit legacy service")
if [ ! -f "$path3" ]; then printf "repo-analysis index not created\n" >&2; exit 1; fi
grep -q "^task_type: repo-analysis$" "$path3" || { printf "repo-analysis task_type missing\n" >&2; exit 1; }

# Case 4: re-bootstrapping existing project must fail (no overwrite).
if bash "$SCRIPT" "$tmp" "myrepo" development "Rebuild" >/dev/null 2>&1; then
  printf "re-bootstrap should have failed\n" >&2; exit 1
fi

# Case 5: invalid task type rejected.
if bash "$SCRIPT" "$tmp" "x" notathing "x" >/dev/null 2>&1; then
  printf "invalid task type accepted\n" >&2; exit 1
fi

# Case 6: missing project name rejected.
if bash "$SCRIPT" "$tmp" "" development "x" >/dev/null 2>&1; then
  printf "empty project name accepted\n" >&2; exit 1
fi

# Case 7: generic fallback
path7=$(bash "$SCRIPT" "$tmp" "misc-thing" generic "Generic project")
[ -f "$path7" ] || { printf "generic project not created\n" >&2; exit 1; }
grep -q "^task_type: generic$" "$path7" || { printf "generic task_type missing\n" >&2; exit 1; }

printf "project bootstrap ok\n"
