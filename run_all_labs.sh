#!/usr/bin/env bash
# Runs every lab and the program. Needs Python 3.10 or newer.
set -u
PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "This needs Python 3.10 or newer; $("$PY" --version 2>&1) found. Set PYTHON=/path/to/python3.10+." >&2
  exit 2
fi
fail=0
ERR=$(mktemp)
for f in labs/*.py; do
  if "$PY" "$f" > /dev/null 2> "$ERR"; then echo "PASS  $f"
  else echo "FAIL  $f"; sed 's/^/      /' "$ERR" | tail -3; fail=1; fi
done
if "$PY" meridian_runtime.py > /dev/null 2> "$ERR"; then echo "PASS  meridian_runtime.py"
else echo "FAIL  meridian_runtime.py"; sed 's/^/      /' "$ERR" | tail -3; fail=1; fi
rm -f "$ERR"
exit $fail
