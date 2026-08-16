#!/usr/bin/env sh
set -eu
exec python3 -B "$(dirname "$0")/INSTALL.py" --probe-dsh auto "$@"
