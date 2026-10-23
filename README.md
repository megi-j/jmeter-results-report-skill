# jmeter-results-report — custom Agent Skill

Runs an Apache JMeter test plan headless, builds the HTML dashboard, and turns the raw `.jtl`
into a **Performance Results** report that checks every sampler against NFRs
(p90/p95/p99, error rate, throughput) — PASS / REVIEW / FAIL.

## Layout

```
jmeter-results-report/
├── SKILL.md
├── scripts/      run_jmeter.sh, analyze_jtl.py
├── references/   jmeter-cli.md, metrics.md
└── assets/       nfr-template.json, report-template.md
docs/
└── analysis-and-reflection.md
```

## Install

Copy the `jmeter-results-report/` folder into your agent's skills directory
(e.g. `~/.claude/skills/` or the project's `.claude/skills/`), or install the folder as a plugin
skill in Antigravity / Claude Code, then restart the session.

## Use

Ask the agent in plain words, e.g.:

- "run `booking.jmx` in non-GUI mode and check it against the NFRs"
- "analyze `results.jtl`, p95 must be under 1 s"
- "write the Performance Results report for my last JMeter run"

Or run the scripts directly:

```bash
bash jmeter-results-report/scripts/run_jmeter.sh plan.jmx -Jthreads=10 -Jduration=60
python3 jmeter-results-report/scripts/analyze_jtl.py results/<run-id>/results.jtl --nfr nfr.json
```

Requirements: JMeter 5.x on PATH (or `JMETER_HOME`) for running; Python 3.8+ for analysis
(standard library only).
