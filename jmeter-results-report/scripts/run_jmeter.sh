#!/usr/bin/env bash
# Run a JMeter test plan headless and build the HTML dashboard into a fresh, timestamped folder.
#
# Usage:  bash run_jmeter.sh <plan.jmx> [extra jmeter args, e.g. -Jthreads=10 -Jduration=60]
# Env:    JMETER_HOME  (optional) - used when `jmeter` is not on PATH
#         RESULTS_DIR  (optional) - parent folder for runs, default ./results
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <plan.jmx> [jmeter args...]" >&2
  exit 2
fi

PLAN="$1"; shift
if [[ ! -f "$PLAN" ]]; then
  echo "error: test plan not found: $PLAN" >&2
  exit 2
fi

# --- locate jmeter -----------------------------------------------------------------------------
if command -v jmeter >/dev/null 2>&1; then
  JMETER=jmeter
elif [[ -n "${JMETER_HOME:-}" && -x "$JMETER_HOME/bin/jmeter" ]]; then
  JMETER="$JMETER_HOME/bin/jmeter"
else
  echo "error: jmeter not found. Put it on PATH or set JMETER_HOME." >&2
  echo "       Command to run yourself once installed:" >&2
  echo "       jmeter -n -t \"$PLAN\" -l results/results.jtl -e -o results/html" >&2
  exit 3
fi

# --- a new folder per run: the dashboard refuses a non-empty output dir --------------------------
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${RESULTS_DIR:-results}/$RUN_ID"
mkdir -p "$RUN_DIR"

# Force CSV with the columns analyze_jtl.py and the dashboard need, whatever user.properties says.
CSV_PROPS=(
  -Jjmeter.save.saveservice.output_format=csv
  -Jjmeter.save.saveservice.print_field_names=true
  -Jjmeter.save.saveservice.timestamp_format=ms
  -Jjmeter.save.saveservice.label=true
  -Jjmeter.save.saveservice.time=true
  -Jjmeter.save.saveservice.successful=true
  -Jjmeter.save.saveservice.response_code=true
  -Jjmeter.save.saveservice.response_message=true
  -Jjmeter.save.saveservice.thread_counts=true
  -Jjmeter.save.saveservice.latency=true
  -Jjmeter.save.saveservice.connect_time=true
  -Jjmeter.save.saveservice.bytes=true
  -Jjmeter.save.saveservice.assertion_results_failure_message=true
)

echo "== JMeter non-GUI run"
echo "   plan : $PLAN"
echo "   out  : $RUN_DIR"
echo "   args : $*"

set +e
"$JMETER" -n \
  -t "$PLAN" \
  -l "$RUN_DIR/results.jtl" \
  -j "$RUN_DIR/jmeter.log" \
  -e -o "$RUN_DIR/html" \
  "${CSV_PROPS[@]}" \
  "$@"
STATUS=$?
set -e

# Keep a copy of exactly what ran, so the report can be traced back to the plan.
cp "$PLAN" "$RUN_DIR/"
printf '%s\n' "$*" > "$RUN_DIR/jmeter-args.txt"

if [[ $STATUS -ne 0 ]]; then
  echo "error: jmeter exited with $STATUS - see $RUN_DIR/jmeter.log" >&2
  exit $STATUS
fi

if [[ ! -s "$RUN_DIR/results.jtl" ]]; then
  echo "error: results.jtl is empty - no sampler ran. Check $RUN_DIR/jmeter.log" >&2
  exit 4
fi

echo "== done"
echo "RUN_DIR=$RUN_DIR"
