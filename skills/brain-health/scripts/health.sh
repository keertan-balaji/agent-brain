#!/usr/bin/env bash
# brain-health: thin wrapper to `brain health`.

set -euo pipefail

exec brain health "$@"
