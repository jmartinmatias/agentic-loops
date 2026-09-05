#!/usr/bin/env bash
set -u
fail=0
for f in labs/ch*_lab.py; do
  python3 "$f" > /dev/null 2>&1 && echo "PASS  $f" || { echo "FAIL  $f"; fail=1; }
done
python3 meridian_runtime.py > /dev/null 2>&1 && echo "PASS  meridian_runtime.py" \
  || { echo "FAIL  meridian_runtime.py"; fail=1; }
exit $fail
