#!/usr/bin/env bash
# Runs every test-*.sh script in this directory. Exits non-zero on any failure.
set -u
cd "$(dirname "$0")"
failed=0
shopt -s nullglob
for t in test-*.sh; do
  printf "=== %s ===\n" "$t"
  if bash "$t"; then
    printf "PASS: %s\n\n" "$t"
  else
    printf "FAIL: %s\n\n" "$t"
    failed=$((failed + 1))
  fi
done
if [ "$failed" -gt 0 ]; then
  printf "%d test file(s) failed\n" "$failed" >&2
  exit 1
fi
printf "all tests passed\n"
