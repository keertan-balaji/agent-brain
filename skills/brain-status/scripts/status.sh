#!/usr/bin/env bash
# brain-status: thin wrapper around `brain status`. No args.

set -euo pipefail

exec brain status "$@"
