#!/usr/bin/env bash
# make-note.sh <vault> <type> <title> [tags-csv] [project]
# Creates a new note from the matching template in <vault>/templates/, fills frontmatter,
# writes to the correct folder under the vault. Prints the absolute path of the created note.

set -euo pipefail

vault=${1:-}
ntype=${2:-}
title=${3:-}
tags_csv=${4:-}
project=${5:-}

usage() {
  printf "usage: %s <vault> <type> <title> [tags-csv] [project]\n" "$0" >&2
  printf "  type: decision|session|gotcha|api|architecture|process|glossary|pattern|task\n" >&2
}

if [ -z "$vault" ] || [ -z "$ntype" ] || [ -z "$title" ]; then
  usage; exit 1
fi
if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2; exit 1
fi

case "$ntype" in
  decision)     folder="agent-memory/decisions"; dated=1 ;;
  session)      folder="agent-memory/sessions";  dated=1 ;;
  gotcha)       folder="agent-memory/gotchas";   dated=1 ;;
  api)          folder="knowledge/api";          dated=0 ;;
  architecture) folder="knowledge/architecture"; dated=0 ;;
  process)      folder="knowledge/process";      dated=0 ;;
  glossary)     folder="knowledge/glossary";     dated=0 ;;
  pattern)      folder="knowledge/patterns";     dated=0 ;;
  task)
    if [ -z "$project" ]; then
      printf "task type requires project arg\n" >&2; exit 1
    fi
    folder="projects/$project/tasks"; dated=1 ;;
  *) printf "invalid type: %s\n" "$ntype" >&2; usage; exit 1 ;;
esac

mkdir -p "$vault/$folder"

case "$ntype" in
  api) tpl_name="api-note.md" ;;
  *)   tpl_name="${ntype}.md" ;;
esac
tpl="$vault/templates/$tpl_name"
if [ ! -f "$tpl" ]; then
  printf "template not found: %s\n" "$tpl" >&2; exit 1
fi

slug=$(printf '%s' "$title" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
if [ -z "$slug" ]; then
  printf "title produced empty slug: %s\n" "$title" >&2; exit 1
fi

today=$(date +%F)
if [ "$dated" = "1" ]; then
  fname="${today}-${slug}.md"
else
  fname="${slug}.md"
fi
dst="$vault/$folder/$fname"

if [ -e "$dst" ]; then
  printf "note already exists: %s\n" "$dst" >&2; exit 1
fi

if [ -n "$tags_csv" ]; then
  tags_yaml="[$(printf '%s' "$tags_csv" | sed -E 's/[[:space:]]*,[[:space:]]*/, /g')]"
else
  tags_yaml="[]"
fi

content=$(cat "$tpl")
content=${content//\{\{date\}\}/$today}
content=${content//\{\{title\}\}/$title}

content=$(printf '%s\n' "$content" | awk -v t="$tags_yaml" '
  BEGIN { in_fm=0; count=0; done=0 }
  /^---$/ { count++; print; if (count==2) in_fm=0; else in_fm=1; next }
  in_fm && /^tags:/ && !done { print "tags: " t; done=1; next }
  { print }
')

if [ -n "$project" ]; then
  content=$(printf '%s\n' "$content" | awk -v p="$project" '
    BEGIN { in_fm=0; count=0; done=0 }
    /^---$/ { count++; print; if (count==2) in_fm=0; else in_fm=1; next }
    in_fm && /^project:/ && !done { print "project: " p; done=1; next }
    { print }
  ')
fi

printf '%s\n' "$content" > "$dst"
printf '%s\n' "$dst"
