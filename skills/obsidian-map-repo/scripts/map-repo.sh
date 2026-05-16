#!/usr/bin/env bash
# map-repo.sh <vault> <repo-path> [--force]
# Scans a coding repo and writes <vault>/projects/<repo-slug>/repo-map.md with
# stack detection, top-level layout, README excerpt, git activity, file
# extension histogram, and follow-up checklist. If projects/<slug>/ doesn't
# exist yet, bootstraps it (task_type=development) before mapping. Refuses to
# overwrite an existing map unless --force is given.
#
# Output: absolute path of the created repo-map.md on stdout.

set -euo pipefail

vault=${1:-}
repo=${2:-}
flag=${3:-}

usage() {
  printf "usage: %s <vault> <repo-path> [--force]\n" "$0" >&2
}

if [ -z "$vault" ] || [ -z "$repo" ]; then
  usage; exit 1
fi
if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2; exit 1
fi
if [ ! -e "$repo" ]; then
  printf "repo not found: %s\n" "$repo" >&2; exit 1
fi
if [ ! -d "$repo" ]; then
  printf "repo path is not a directory: %s\n" "$repo" >&2; exit 1
fi

force=0
if [ "$flag" = "--force" ]; then
  force=1
fi

# Resolve repo absolute path + slug.
repo_abs=$(cd "$repo" && pwd)
repo_name=$(basename "$repo_abs")
slug=$(printf '%s' "$repo_name" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')
if [ -z "$slug" ]; then
  printf "repo name produced empty slug: %s\n" "$repo_name" >&2; exit 1
fi

# Ensure project exists; bootstrap as development if absent.
script_dir=$(cd "$(dirname "$0")" && pwd)
bootstrap="$script_dir/../../obsidian-project-bootstrap/scripts/bootstrap-project.sh"
proj_dir="$vault/projects/$slug"
if [ ! -d "$proj_dir" ]; then
  if [ ! -x "$bootstrap" ]; then
    printf "bootstrap helper not found: %s\n" "$bootstrap" >&2; exit 1
  fi
  bash "$bootstrap" "$vault" "$slug" development "$repo_name" >/dev/null
fi

map_file="$proj_dir/repo-map.md"
if [ -f "$map_file" ] && [ "$force" -ne 1 ]; then
  printf "repo-map.md already exists: %s\n" "$map_file" >&2
  printf "  (pass --force to overwrite)\n" >&2
  exit 1
fi

today=$(date +%F)

# --- Stack detection ---
stack_lines=()
[ -f "$repo_abs/package.json" ]      && stack_lines+=("- Node/JavaScript/TypeScript (package.json)")
[ -f "$repo_abs/pyproject.toml" ]    && stack_lines+=("- Python (pyproject.toml)")
[ -f "$repo_abs/requirements.txt" ]  && stack_lines+=("- Python (requirements.txt)")
[ -f "$repo_abs/setup.py" ]          && stack_lines+=("- Python (setup.py)")
[ -f "$repo_abs/Cargo.toml" ]        && stack_lines+=("- Rust (Cargo.toml)")
[ -f "$repo_abs/go.mod" ]            && stack_lines+=("- Go (go.mod)")
[ -f "$repo_abs/Gemfile" ]           && stack_lines+=("- Ruby (Gemfile)")
[ -f "$repo_abs/pom.xml" ]           && stack_lines+=("- Java/JVM (pom.xml)")
{ [ -f "$repo_abs/build.gradle" ] || [ -f "$repo_abs/build.gradle.kts" ]; } && stack_lines+=("- JVM (build.gradle)")
[ -f "$repo_abs/composer.json" ]     && stack_lines+=("- PHP (composer.json)")
[ -f "$repo_abs/mix.exs" ]           && stack_lines+=("- Elixir (mix.exs)")
[ -f "$repo_abs/Dockerfile" ]        && stack_lines+=("- Docker (Dockerfile)")
[ -f "$repo_abs/Makefile" ]          && stack_lines+=("- Make (Makefile)")
[ -f "$repo_abs/flake.nix" ]         && stack_lines+=("- Nix (flake.nix)")
if [ ${#stack_lines[@]} -eq 0 ]; then
  stack_lines+=("- (no recognized manifests detected)")
fi

# --- Top-level layout (depth 2, excluding noise) ---
tree_output=$(find "$repo_abs" -maxdepth 2 -mindepth 1 \
  -not -path "*/.git" -not -path "*/.git/*" \
  -not -path "*/node_modules" -not -path "*/node_modules/*" \
  -not -path "*/__pycache__" -not -path "*/__pycache__/*" \
  -not -path "*/.venv" -not -path "*/.venv/*" \
  -not -path "*/venv" -not -path "*/venv/*" \
  -not -path "*/target" -not -path "*/target/*" \
  -not -path "*/dist" -not -path "*/dist/*" \
  -not -path "*/build" -not -path "*/build/*" \
  -not -path "*/.next" -not -path "*/.next/*" \
  -not -path "*/.cache" -not -path "*/.cache/*" \
  2>/dev/null \
  | sed "s|^${repo_abs}/||" \
  | sort | head -n 80)
[ -z "$tree_output" ] && tree_output="(empty)"

# --- README excerpt ---
readme_excerpt=""
readme_path=""
for f in README.md README.rst README.txt README; do
  if [ -f "$repo_abs/$f" ]; then
    readme_excerpt=$(head -n 30 "$repo_abs/$f")
    readme_path="$f"
    break
  fi
done

# --- Git activity ---
git_section=""
if [ -d "$repo_abs/.git" ] || ( cd "$repo_abs" && git rev-parse --git-dir >/dev/null 2>&1 ); then
  branch=$(cd "$repo_abs" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(detached)")
  commits=$(cd "$repo_abs" && git log --oneline -n 10 2>/dev/null || echo "(no commits)")
  git_section=$(printf 'Branch: `%s`\n\nRecent commits:\n\n```\n%s\n```' "$branch" "$commits")
else
  git_section="(not a git repository)"
fi

# --- File counts by extension (top 10) ---
ext_counts=$(find "$repo_abs" -type f \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.venv/*" \
  -not -path "*/venv/*" \
  -not -path "*/target/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*" \
  -not -path "*/.next/*" \
  -not -path "*/.cache/*" \
  2>/dev/null \
  | grep -oE '\.[a-zA-Z0-9]+$' \
  | sort | uniq -c | sort -rn | head -n 10 \
  | awk '{ printf "- `%s`: %d\n", $2, $1 }')
[ -z "$ext_counts" ] && ext_counts="(none)"

# --- Render map file ---
{
  printf -- '---\n'
  printf 'type: project\n'
  printf 'tags: [map, repo-scan]\n'
  printf 'project: %s\n' "$slug"
  printf 'status: active\n'
  printf 'created: %s\n' "$today"
  printf 'updated: %s\n' "$today"
  printf 'task_type: development\n'
  printf 'related: ["[[index]]"]\n'
  printf -- '---\n\n'

  printf '# Repo map — %s\n\n' "$repo_name"
  printf 'Generated by obsidian-map-repo on %s.\n\n' "$today"

  printf '## Location\n\n`%s`\n\n' "$repo_abs"

  printf '## Stack\n\n'
  printf '%s\n' "${stack_lines[@]}"
  printf '\n'

  printf '## Top-level layout\n\n'
  printf '```\n%s\n```\n\n' "$tree_output"

  printf '## README excerpt\n\n'
  if [ -n "$readme_excerpt" ]; then
    printf '*From `%s`:*\n\n' "$readme_path"
    printf '```markdown\n%s\n```\n\n' "$readme_excerpt"
  else
    printf '(no README detected)\n\n'
  fi

  printf '## Git activity\n\n%s\n\n' "$git_section"

  printf '## File counts (top 10 extensions)\n\n%s\n\n' "$ext_counts"

  printf '## Suggested follow-ups\n\n'
  printf -- '- [ ] Capture key architecture notes under `knowledge/architecture/` and link from the project index\n'
  printf -- '- [ ] Document external/internal API surfaces you touch under `knowledge/api/`\n'
  printf -- '- [ ] Capture gotchas to `agent-memory/gotchas/` with `project: %s` as they surface\n' "$slug"
  printf -- '- [ ] Re-run `/obsidian-map-repo --force` periodically to refresh this scan\n\n'

  printf '## Related\n\n- [[index]]\n'
} > "$map_file"

printf '%s\n' "$map_file"
