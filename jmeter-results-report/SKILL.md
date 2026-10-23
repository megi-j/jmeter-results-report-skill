---
name: jmeter-results-report
description: >-
  Run an Apache JMeter test plan (.jmx) in non-GUI mode, build the HTML dashboard, and turn the raw
  .jtl results into a Performance Results report that checks every sampler against the project's
  NFRs (response-time percentiles, error rate, throughput). Use when someone asks to run a .jmx
  from the command line, "run jmeter non-gui", generate the JMeter HTML report, analyze or
  summarize a .jtl / results.csv, compare load-test results to NFRs or SLAs, write a performance
  results document, or explain why a JMeter run passed or failed. Also when the HTML report
  generation fails ("results folder not empty", "no sample results") or numbers in the dashboard
  look wrong.
---

# JMeter results report

A load test is not finished when JMeter stops. It is finished when someone can say, per request,
**"p95 was 840 ms against a 1000 ms NFR — pass"** and back it up with the dashboard. That last
step — run headless, build the dashboard, read the numbers, compare to NFRs, write it up — is the
same every time and is what this skill automates.

The agent runs and measures. **The human owns the thresholds and the verdict on borderline
results.** Never invent an NFR value; never quietly relax one to make a run pass.

## What goes in, what comes out

| Input | Required | Where it usually is |
|---|---|---|
| test plan `*.jmx` | yes | repo root or `tests/` |
| NFR thresholds | yes — ask if missing | `nfr.json`, an NFR doc, or the assignment text |
| JMeter install | yes for running | `jmeter` on PATH or `$JMETER_HOME/bin` |
| existing `*.jtl` / `results.csv` | instead of running | when the user already ran it |

| Output | Path |
|---|---|
| raw results | `results/<run-id>/results.jtl` |
| JMeter HTML dashboard | `results/<run-id>/html/index.html` |
| JMeter log | `results/<run-id>/jmeter.log` |
| machine summary | `results/<run-id>/summary.json` |
| **Performance Results report** | `results/<run-id>/performance-report.md` |

`<run-id>` is a timestamp (`20261024-1530`) so runs never overwrite each other.

## Workflow

### 1. Detect before asking

```bash
ls *.jmx **/*.jmx 2>/dev/null
ls nfr*.json **/nfr*.json *.jtl **/*.jtl results*.csv 2>/dev/null
command -v jmeter || ls "$JMETER_HOME/bin/jmeter" 2>/dev/null
grep -o 'testname="[^"]*"' <plan>.jmx | sort -u | head -40     # sampler / thread group names
grep -o '\${__P([^)]*)}' <plan>.jmx | sort -u                   # properties the plan accepts (-J)
```

From the plan learn: the sampler labels (these become report rows), the thread groups, and
whether threads/ramp-up/duration are parameterised with `${__P(...)}`. If they are hard-coded,
say so — the load profile cannot be changed from the command line without editing the plan.

### 2. Settle the NFRs (human decision)

Look for an existing `nfr.json` (format in `assets/nfr-template.json`). If there is none, ask for
the thresholds — offer the likely shape instead of a blank question:

- *p95 ≤ 1000 ms, error rate ≤ 1 %, all samplers* (recommended starting point)
- *the values in the assignment / NFR document* — the user pastes or points to them
- *per-sampler values* — e.g. login p95 ≤ 500 ms, search p90 ≤ 2 s

Write what was agreed to `nfr.json` next to the plan, so the next run reuses it. Record **where
each number came from** in its `source` field. If the user says "just pick something", use the
recommended defaults and state in the report that they are placeholders, not agreed NFRs.

Also confirm the **load profile** (threads, ramp-up, duration/loops) when the plan takes it as
properties. Running a 500-user test against someone else's public demo site is not the agent's
call — public targets (reqres.in, restful-booker, demowebshop, jsonplaceholder) get the profile
the assignment states, or a small one (≤ 10 threads) if it states none.

### 3. Run headless

```bash
bash scripts/run_jmeter.sh <plan>.jmx [-Jthreads=10 -Jrampup=10 -Jduration=60 ...]
```

The script creates `results/<run-id>/`, runs `jmeter -n -t … -l results.jtl -j jmeter.log
-e -o html`, forces CSV output with the fields the analyzer needs, and prints the run folder. See
`references/jmeter-cli.md` for every flag and the common failures (non-empty output folder,
missing plugins, `-J` properties not picked up).

If JMeter is not installed or the target is unreachable from here, **do not fake a run**. Say so,
give the exact command, and continue from step 4 once the user supplies the `.jtl`.

### 4. Analyze

```bash
python3 scripts/analyze_jtl.py results/<run-id>/results.jtl --nfr nfr.json \
        --out results/<run-id>
```

Produces `summary.json` and `performance-report.md`: one row per sampler label plus a TOTAL row
with samples, avg, min, max, p90, p95, p99, error %, throughput, and a PASS/FAIL per NFR. It also
lists the top error messages per label, because "4 % errors" is useless without knowing they were
all `429 Too Many Requests`.

Numbers are computed the same way the JMeter dashboard computes them; see
`references/metrics.md` for definitions and the one known difference (percentile interpolation,
at most a few ms on small samples).

### 5. Read the result — then hand the judgement back

Check before writing anything:

- **Sample count is plausible** for threads × loops. A label with 3 samples in a 10-minute test
  usually means a controller skipped it or an earlier step failed.
- **Errors are real errors.** Look at `top_errors`. Assertion failures, 4xx from a rate limit and
  connection resets mean different things.
- **Transaction Controllers vs. their children.** If the plan has both, the parent rows duplicate
  their children in TOTAL. Report them, but flag it.
- **Warm-up.** The first seconds of a ramp-up inflate max and p99. Mention it; do not silently
  trim data. Trimming (`--skip-first-seconds N`) is the user's call.

Then fill the **Conclusions** section of the report with what you observed, and mark anything
borderline (within 10 % of a threshold) as **needs review** rather than pass/fail. Whether a
borderline or noisy result is acceptable, and whether to re-run, is the user's decision.

### 6. Hand over

Tell the user, in a few lines: overall verdict, which NFRs failed and by how much, where the
dashboard and report are. If they need a `.docx` (some assignments ask for "Performance Results
docx"), convert the markdown report rather than re-writing it.

Do not commit `results/` unless asked — `.jtl` files get large. Suggest adding `results/` to
`.gitignore` and attaching the dashboard screenshots / report instead.

## Reference files

- `references/jmeter-cli.md` — non-GUI flags, properties, report generation from an existing
  `.jtl`, and the failure-mode table.
- `references/metrics.md` — what each column means, how it is computed, and how to phrase a
  verdict.
- `assets/nfr-template.json` — the NFR file format the analyzer reads.
- `assets/report-template.md` — the report layout `analyze_jtl.py` fills.
