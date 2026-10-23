# What the numbers mean

Every value in `summary.json` and the report is computed from the raw `.jtl`, one row per
sample. A sample is one execution of one sampler (or one Transaction Controller) by one thread.

## Columns

| Column | Definition | Notes |
|---|---|---|
| Samples | rows with that label | sanity-check against threads × loops |
| Avg | mean of `elapsed` (ms) | hides outliers — never judge an NFR on avg alone |
| Min / Max | extremes of `elapsed` | max is usually a warm-up or GC spike; one value, little meaning |
| p90 / p95 / p99 | the value below which 90/95/99 % of samples fall | the numbers NFRs are normally written in |
| Error % | samples with `success=false` / samples | includes assertion failures, not only HTTP errors |
| Req/s (throughput) | samples / (last end − first start) in seconds | per label: how often that request ran, not server capacity |
| Duration | last sample end − first sample start | |

`elapsed` in JMeter is the full time from just before the request is sent to after the last
byte of the response is received. `Latency` (time to first byte) and `Connect` are also in the
file but are not used for the NFR check unless the NFR explicitly says so.

## Percentiles

`analyze_jtl.py` uses the Apache Commons Math "legacy" estimator — the same one JMeter's HTML
dashboard uses — so p90/p95/p99 match the dashboard's Statistics table:

```
pos = p/100 × (n + 1)
pos < 1   → smallest value
pos ≥ n   → largest value
otherwise → interpolate between the values at floor(pos) and floor(pos)+1 (1-based)
```

The **Aggregate Report listener** in the GUI uses a different method (nearest rank, no
interpolation), so its "90% Line" can differ from the dashboard by a few ms on small samples.
When a user compares numbers between the two and they disagree slightly, this is why — it is not
a bug in either.

With fewer than ~100 samples, p99 is essentially the maximum. Say so rather than presenting it as
a meaningful statistic.

## Transaction Controllers

A Transaction Controller writes its own sample (the sum of its children) **in addition** to the
children's samples. If a plan has both, the TOTAL row counts the work twice: its sample count is
inflated and its throughput overstated. Options, in order of preference:

1. report the controllers and children, and state the double counting in the conclusions;
2. `--exclude` the children (or the controllers) to get a TOTAL that counts each request once —
   only when the user agrees which level the NFRs are written for.

## Phrasing a verdict

- **PASS** — the measured value is inside the limit by more than 10 %.
- **REVIEW** — inside the limit but within 10 % of it. A second run could fail. Do not call this a
  pass in prose; say "passes, with little margin".
- **FAIL** — outside the limit. State by how much: "p95 1 340 ms vs ≤ 1 000 ms (+34 %)".

Good conclusion sentences name the request, the metric, the limit and the number:

> *Create Token* meets every NFR (p95 412 ms ≤ 500 ms). *Get Users* fails p90 (918 ms vs ≤ 700 ms,
> +31 %); all of its 37 errors are `429 Too Many Requests`, which points at the demo API's rate
> limit rather than its response time — recommend re-running at 5 threads before drawing a
> conclusion.

Avoid "the system performed well" — it carries no number, so nobody can check it.

## What the agent must not decide alone

- changing a threshold, or calling a FAIL acceptable;
- trimming warm-up data or excluding labels from the TOTAL;
- the load profile against a target the user does not own.

All three change what the report claims. Propose them, explain the effect, let the user choose.
