#!/usr/bin/env bash
# run_tests.sh - Run the framework test suite without changing system state.
#
# Usage:
#   bash tests/run_tests.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Syntax-checking shell sources..."
bash -n "$ROOT_DIR"/component_logging.sh "$ROOT_DIR"/component_menu.sh "$ROOT_DIR"/component_runtime.sh "$ROOT_DIR"/component_loader.sh "$ROOT_DIR"/installer_helpers.sh
bash -n "$ROOT_DIR"/install.sh "$ROOT_DIR"/lib/framework_install.sh "$ROOT_DIR"/installer/components.sh
echo "  OK"

fail=0
for t in "$SCRIPT_DIR"/test_*.py; do
  [ -f "$t" ] || continue
  echo "Running $(basename "$t")..."
  python3 "$t" || fail=$((fail + 1))
done

if [ "$fail" -eq 0 ]; then
  echo "All tests passed."
else
  echo "$fail test file(s) failed." >&2
fi
exit "$fail"
