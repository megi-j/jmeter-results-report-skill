#!/usr/bin/env python3
"""Summarise a JMeter CSV result file (.jtl) and check it against NFR thresholds.

Usage:
    python3 analyze_jtl.py results.jtl [--nfr nfr.json] [--out DIR]
                           [--skip-first-seconds N] [--exclude REGEX] [--title TEXT]

Writes DIR/summary.json and DIR/performance-report.md (DIR defaults to the .jtl's folder).
Only the standard library is used, so it runs wherever Python 3.8+ does.

Exit code: 0 all NFRs pass, 1 at least one FAIL, 2 bad input. REVIEW (borderline) does not fail.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("timeStamp", "elapsed", "label", "success")
BORDERLINE = 0.10  # within 10 % of a threshold on the passing side -> REVIEW

# metric key in nfr.json -> (summary field, comparison, unit)
NFR_METRICS = {
    "avg_ms": ("avg", "max", "ms"),
    "p90_ms": ("p90", "max", "ms"),
    "p95_ms": ("p95", "max", "ms"),
    "p99_ms": ("p99", "max", "ms"),
    "max_ms": ("max", "max", "ms"),
    "error_rate_pct": ("error_pct", "max", "%"),
    "throughput_rps_min": ("throughput", "min", "req/s"),
}


# ------------------------------------------------------------------------------------ statistics
def percentile(sorted_vals: list[int], p: float) -> float:
    """Apache Commons Math 'legacy' estimator - the one JMeter's HTML dashboard uses."""
    n = len(sorted_vals)
    if n == 0:
        return float("nan")
    if n == 1:
        return float(sorted_vals[0])
    pos = p / 100.0 * (n + 1)
    if pos < 1:
        return float(sorted_vals[0])
    if pos >= n:
        return float(sorted_vals[-1])
    lower = math.floor(pos)
    d = pos - lower
    lo, hi = sorted_vals[lower - 1], sorted_vals[lower]
    return lo + d * (hi - lo)


def summarise(rows: list[dict]) -> dict:
    elapsed = sorted(int(r["elapsed"]) for r in rows)
    n = len(elapsed)
    errors = [r for r in rows if r["success"].strip().lower() != "true"]
    start = min(int(r["timeStamp"]) for r in rows)
    end = max(int(r["timeStamp"]) + int(r["elapsed"]) for r in rows)
    duration_s = max((end - start) / 1000.0, 0.001)

    msgs = Counter()
    for r in errors:
        code = (r.get("responseCode") or "").strip()
        msg = (r.get("failureMessage") or r.get("responseMessage") or "").strip()
        msgs[f"{code} {msg}".strip() or "(no message)"] += 1

    return OrderedDict(
        samples=n,
        errors=len(errors),
        error_pct=round(100.0 * len(errors) / n, 2),
        avg=round(sum(elapsed) / n, 1),
        min=elapsed[0],
        max=elapsed[-1],
        p90=round(percentile(elapsed, 90), 1),
        p95=round(percentile(elapsed, 95), 1),
        p99=round(percentile(elapsed, 99), 1),
        throughput=round(n / duration_s, 2),
        duration_s=round(duration_s, 1),
        top_errors=msgs.most_common(5),
    )


# -------------------------------------------------------------------------------------- loading
def load(path: Path, skip_first: float, exclude: str | None) -> list[dict]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(
                f"error: {path} has no column(s) {missing}. The file must be CSV with a header row "
                "(jmeter.save.saveservice.output_format=csv, print_field_names=true). "
                "XML .jtl files are not supported - re-run with run_jmeter.sh."
            )
        rows = [r for r in reader if r.get("timeStamp", "").strip().isdigit()]

    if not rows:
        sys.exit(f"error: {path} contains no samples")

    if skip_first > 0:
        t0 = min(int(r["timeStamp"]) for r in rows)
        rows = [r for r in rows if int(r["timeStamp"]) - t0 >= skip_first * 1000]
    if exclude:
        rx = re.compile(exclude)
        rows = [r for r in rows if not rx.search(r["label"])]
    if not rows:
        sys.exit("error: no samples left after --skip-first-seconds / --exclude")
    return rows


# ------------------------------------------------------------------------------------- NFR check
def thresholds_for(nfr: dict, label: str) -> dict:
    if label == "TOTAL":
        return dict(nfr.get("total", {}))
    merged = dict(nfr.get("defaults", {}))
    merged.update(nfr.get("samplers", {}).get(label, {}))
    return merged


def check(stats: dict, limits: dict) -> list[dict]:
    results = []
    for key, limit in limits.items():
        if key not in NFR_METRICS or limit is None:
            continue
        field, direction, unit = NFR_METRICS[key]
        actual = stats[field]
        if direction == "max":
            ok = actual <= limit
            near = ok and limit > 0 and actual >= limit * (1 - BORDERLINE)
        else:
            ok = actual >= limit
            near = ok and actual <= limit * (1 + BORDERLINE)
        status = "FAIL" if not ok else ("REVIEW" if near else "PASS")
        results.append(dict(metric=key, limit=limit, actual=actual, unit=unit,
                            direction=direction, status=status))
    return results


# ------------------------------------------------------------------------------------- rendering
def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}" if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def render(template: str, data: dict) -> str:
    for k, v in data.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def build_report(jtl: Path, per_label: dict, total: dict, checks: dict, nfr: dict,
                 nfr_path: str | None, opts, template: str) -> str:
    cols = ["samples", "avg", "min", "max", "p90", "p95", "p99", "error_pct", "throughput"]
    head = "| Sampler | Samples | Avg ms | Min ms | Max ms | p90 ms | p95 ms | p99 ms | Error % | Req/s |"
    rows = [head, "|" + "---|" * (len(cols) + 1)]
    for label, s in list(per_label.items()) + [("**TOTAL**", total)]:
        rows.append("| " + label + " | " + " | ".join(fmt(s[c]) for c in cols) + " |")

    icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "REVIEW": "⚠️ REVIEW"}
    nfr_rows = ["| Sampler | NFR | Limit | Actual | Result |", "|---|---|---|---|---|"]
    counts = Counter()
    for label, res in checks.items():
        for c in res:
            counts[c["status"]] += 1
            sign = "≤" if c["direction"] == "max" else "≥"
            nfr_rows.append(f"| {label} | {c['metric']} | {sign} {fmt(c['limit'])} {c['unit']} "
                            f"| {fmt(c['actual'])} {c['unit']} | {icon[c['status']]} |")
    if not counts:
        nfr_rows = ["_No NFR file supplied — results were not checked against thresholds._"]

    if counts["FAIL"]:
        verdict = f"**❌ FAILED** — {counts['FAIL']} NFR check(s) failed"
    elif counts["REVIEW"]:
        verdict = f"**⚠️ NEEDS REVIEW** — all checks pass, {counts['REVIEW']} within 10 % of the limit"
    elif counts["PASS"]:
        verdict = f"**✅ PASSED** — all {counts['PASS']} NFR checks pass"
    else:
        verdict = "**— NOT EVALUATED** — no NFRs supplied"

    err_lines = []
    for label, s in list(per_label.items()) + [("TOTAL", total)]:
        if s["top_errors"] and label != "TOTAL":
            err_lines.append(f"- **{label}** — " + "; ".join(f"`{m}` ×{c}" for m, c in s["top_errors"]))
    errors = "\n".join(err_lines) or "_No failed samples._"

    meta = [
        f"| Results file | `{jtl}` |",
        f"| Generated | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |",
        f"| Test duration | {fmt(total['duration_s'])} s |",
        f"| Total samples | {fmt(total['samples'])} |",
        f"| NFR source | {nfr.get('source', nfr_path or '—')} |",
    ]
    if opts.skip_first_seconds:
        meta.append(f"| Warm-up excluded | first {opts.skip_first_seconds:g} s |")
    if opts.exclude:
        meta.append(f"| Labels excluded | `{opts.exclude}` |")
    if nfr.get("placeholder"):
        meta.append("| ⚠️ NFRs | placeholder values — not agreed with stakeholders |")

    return render(template, {
        "TITLE": opts.title or f"Performance Results — {jtl.parent.name}",
        "META": "| | |\n|---|---|\n" + "\n".join(meta),
        "VERDICT": verdict,
        "TABLE": "\n".join(rows),
        "NFR_TABLE": "\n".join(nfr_rows),
        "ERRORS": errors,
    })


# ------------------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jtl", type=Path)
    ap.add_argument("--nfr", help="NFR thresholds JSON (see assets/nfr-template.json)")
    ap.add_argument("--out", type=Path, help="output folder (default: folder of the .jtl)")
    ap.add_argument("--skip-first-seconds", type=float, default=0, help="drop warm-up samples")
    ap.add_argument("--exclude", help="regex of sampler labels to leave out")
    ap.add_argument("--title")
    ap.add_argument("--template", type=Path,
                    default=Path(__file__).resolve().parent.parent / "assets" / "report-template.md")
    opts = ap.parse_args()

    if not opts.jtl.is_file():
        print(f"error: {opts.jtl} not found", file=sys.stderr)
        return 2
    out = opts.out or opts.jtl.parent
    out.mkdir(parents=True, exist_ok=True)

    nfr = {}
    if opts.nfr:
        try:
            nfr = json.loads(Path(opts.nfr).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: cannot read NFR file {opts.nfr}: {e}", file=sys.stderr)
            return 2
        unknown = {k for sec in ("defaults", "total") for k in nfr.get(sec, {})} | \
                  {k for v in nfr.get("samplers", {}).values() for k in v}
        unknown -= set(NFR_METRICS)
        if unknown:
            print(f"warning: ignoring unknown NFR metric(s): {sorted(unknown)}", file=sys.stderr)

    rows = load(opts.jtl, opts.skip_first_seconds, opts.exclude)

    groups: dict[str, list] = OrderedDict()
    for r in rows:
        groups.setdefault(r["label"], []).append(r)
    per_label = OrderedDict((lbl, summarise(rs)) for lbl, rs in groups.items())
    total = summarise(rows)

    checks = OrderedDict()
    if nfr:
        for lbl, s in per_label.items():
            res = check(s, thresholds_for(nfr, lbl))
            if res:
                checks[lbl] = res
        res = check(total, thresholds_for(nfr, "TOTAL"))
        if res:
            checks["TOTAL"] = res

    labels_in_nfr = set(nfr.get("samplers", {}))
    unmatched = sorted(labels_in_nfr - set(per_label))

    summary = OrderedDict(
        source=str(opts.jtl), per_label=per_label, total=total, nfr_checks=checks,
        nfr_labels_not_found=unmatched,
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    template = opts.template.read_text(encoding="utf-8")
    report = build_report(opts.jtl, per_label, total, checks, nfr, opts.nfr, opts, template)
    (out / "performance-report.md").write_text(report, encoding="utf-8")

    fails = sum(c["status"] == "FAIL" for res in checks.values() for c in res)
    print(f"samples={total['samples']} labels={len(per_label)} errors={total['error_pct']}% "
          f"p95={total['p95']}ms throughput={total['throughput']}/s  NFR fails={fails}")
    if unmatched:
        print(f"warning: NFR names samplers that are not in the results: {unmatched}", file=sys.stderr)
    print(f"wrote {out / 'summary.json'}")
    print(f"wrote {out / 'performance-report.md'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
