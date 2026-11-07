#!/usr/bin/env python3
"""Unabridged rung-2 first-run inputs; resource failures must diagnose S2."""

import argparse, json, subprocess, time
from contracts import ROOT as R


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--major", type=int, required=True)
    a = p.parse_args()
    d = R / f".tmp/analysis-performance/{a.major}"
    d.mkdir(parents=True, exist_ok=True)
    cmd = [
        f"/usr/lib/llvm-{a.major}/bin/opt",
        "-load-pass-plugin=" + str(R / f"build/libbennett-plugin-{a.major}.so"),
        "-passes=bennett",
        "-bennett-dialect=0.2.13",
        "-bennett-analysis-only",
        "-disable-output",
        str(R / f"tests/probes/hashtable-postlink-{a.major}.ll"),
    ]
    start = time.monotonic()
    try:
        z = subprocess.run(
            [*cmd, "-bennett-report=" + str(d / "report.json")],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "S2 hashtable exceeded 20 seconds without completing; internal budget must fail loudly"
        )
    elapsed = time.monotonic() - start
    assert z.returncode == 0, z.stderr
    data = json.loads((d / "report.json").read_text())
    assert data["analysis_rounds"] < 100, data["analysis_rounds"]
    # Force exhaustion on the same real input; no silent timeout or bare cap.
    z = subprocess.run(
        [*cmd, "-bennett-analysis-max-rounds=1"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert (
        z.returncode
        and "<badref>" not in z.stderr
        and all(
            s in z.stderr for s in ("§5.2", "PT", "budget exhausted", "AV(", "ht_demo_")
        )
    ), z.stderr
    diagnostic = z.stderr
    z = subprocess.run(
        [*cmd, "-bennett-analysis-budget-ms=1"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert z.returncode and "budget exhausted at AV(" in z.stderr, z.stderr
    result = dict(
        major=a.major,
        cases=3,
        passed=3,
        seconds=elapsed,
        rounds=data["analysis_rounds"],
        budget_diagnostic=diagnostic,
    )
    (R / f".tmp/analysis-performance-{a.major}.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
