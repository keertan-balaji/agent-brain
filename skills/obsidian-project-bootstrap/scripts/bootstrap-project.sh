#!/usr/bin/env bash
# bootstrap-project.sh <vault> <project-name> <task-type> [title]
# Creates projects/<project-name>/ with task-type-specific index.md and subdirs.
# Task types: research, development, repo-analysis, generic.
# Refuses to overwrite an existing project (idempotency = no-clobber).
# Prints the absolute path of the created index.md.

set -euo pipefail

vault=${1:-}
project=${2:-}
task_type=${3:-}
title=${4:-}

usage() {
  printf "usage: %s <vault> <project-name> <task-type> [title]\n" "$0" >&2
  printf "  task-type: research | development | repo-analysis | generic\n" >&2
}

if [ -z "$vault" ] || [ -z "$project" ] || [ -z "$task_type" ]; then
  usage; exit 1
fi
if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2; exit 1
fi

case "$task_type" in
  research|development|repo-analysis|generic) ;;
  *) printf "invalid task type: %s\n" "$task_type" >&2; usage; exit 1 ;;
esac

# Project name sanity — kebab-case-ish; reject path separators and dots.
case "$project" in
  */*|*..*|*.) printf "invalid project name: %s\n" "$project" >&2; exit 1 ;;
esac
slug=$(printf '%s' "$project" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')
if [ -z "$slug" ]; then
  printf "project name produced empty slug: %s\n" "$project" >&2; exit 1
fi

proj_dir="$vault/projects/$slug"
if [ -e "$proj_dir" ]; then
  printf "project already exists: %s\n" "$proj_dir" >&2
  printf "  (refusing to overwrite — pick a new name or extend existing index)\n" >&2
  exit 1
fi

# Subdirs per task-type.
mkdir -p "$proj_dir/tasks"
case "$task_type" in
  development) mkdir -p "$proj_dir/modules" ;;
esac

# Pick template.
case "$task_type" in
  research)      tpl_name="project-research.md" ;;
  development)   tpl_name="project-development.md" ;;
  repo-analysis) tpl_name="project-repo-analysis.md" ;;
  generic)       tpl_name="project-generic.md" ;;
esac
tpl="$vault/templates/$tpl_name"
if [ ! -f "$tpl" ]; then
  printf "template not found: %s\n" "$tpl" >&2
  rmdir "$proj_dir/tasks" "$proj_dir/modules" 2>/dev/null || true
  rmdir "$proj_dir" 2>/dev/null || true
  exit 1
fi

today=$(date +%F)
effective_title=${title:-$project}

content=$(cat "$tpl")
content=${content//\{\{date\}\}/$today}
content=${content//\{\{title\}\}/$effective_title}
content=${content//\{\{project\}\}/$slug}

dst="$proj_dir/index.md"
printf '%s\n' "$content" > "$dst"
printf '%s\n' "$dst"
