#!/usr/bin/env sh
set -eu
exec python3 -B "$(dirname "$0")/UNINSTALL.py" "$@"
