#!/usr/bin/env python3
"""S2 work receipts survive resource and unsupported-transfer exits."""

import argparse
import json
from pathlib import Path

from contracts import ROOT, run


PREFIX = "bennett-analysis-work:"
COUNTERS = ("transfer_applications", "worklist_pops", "rounds_completed", "join_count")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", required=True, type=int)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path,
                        default=ROOT / ".tmp/analysis-counters")
    args = parser.parse_args()
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    results = []

    def check(name, source, options=(), diagnostic=None):
        report = directory / f"{name}.json"
        report.unlink(missing_ok=True)
        result = run([
            f"/usr/lib/llvm-{args.major}/bin/opt",
            f"-load-pass-plugin={plugin}", "-passes=bennett",
            "-bennett-dialect=0.2.13", "-bennett-analysis-only",
            f"-bennett-report={report}", "-disable-output", source, *options,
        ])
        if diagnostic:
            assert result.returncode != 0 and diagnostic in result.stderr, result.stderr
        else:
            assert result.returncode == 0, result.stderr
        lines = [line[len(PREFIX):].strip() for line in result.stderr.splitlines()
                 if line.startswith(PREFIX)]
        assert len(lines) == 1, (name, "expected exactly one work receipt", result.stderr)
        work = json.loads(lines[0])
        assert report.exists(), (name, "missing JSON report on analysis exit")
        assert json.loads(report.read_text())["analysis_work"] == work, name
        assert all(type(work[key]) is int and work[key] >= 0 for key in COUNTERS), work
        visits = work["function_visits"]
        assert type(visits["total"]) is int and visits["total"] >= 0, work
        assert all(type(value) is int and value > 0 for value in visits["top"].values()), work
        assert sum(visits["top"].values()) <= visits["total"], work
        assert type(visits["top_limit"]) is int and len(visits["top"]) <= visits["top_limit"], work
        assert work["worklist_pops"] >= work["transfer_applications"], work
        assert work["cpu_ms"]["deterministic"] is False, work
        assert isinstance(work["cpu_ms"]["value"], (int, float)), work
        assert work["cpu_ms"]["value"] >= 0, work
        results.append({"case": name, "work": work})
        return work

    hashtable = ROOT / f"tests/probes/hashtable-postlink-{args.major}.ll"
    allowance = check("allowance", hashtable, ["-bennett-analysis-budget-ms=1"],
                      "budget exhausted at AV(")
    assert allowance["cpu_ms"]["value"] >= 1, allowance
    # A complete module scan precedes the explicit one-round stop.
    limited = check("round-limit", hashtable, ["-bennett-analysis-max-rounds=1"],
                    "budget exhausted")
    assert limited["rounds_completed"] == 1, limited
    assert limited["transfer_applications"] > 0 and limited["join_count"] > 0, limited
    assert limited["function_visits"]["total"] > 0, limited

    def fixture(name, body):
        path = directory / f"{name}.ll"
        path.write_text('target datalayout = "e-p:64:64"\n' + body + "\n")
        return path

    simple = fixture("simple", "define i8 @top() { ret i8 7 }")
    first = check("success", simple)
    assert {key: first[key] for key in COUNTERS} == {
        "transfer_applications": 1, "worklist_pops": 1,
        "rounds_completed": 1, "join_count": 1,
    }, first
    assert first["function_visits"]["total"] == 1, first
    assert first["function_visits"]["top"] == {"top": 1}, first
    repeat = check("repeat", simple)
    assert {k: v for k, v in first.items() if k != "cpu_ms"} == {
        k: v for k, v in repeat.items() if k != "cpu_ms"
    }, (first, repeat)

    vector = fixture("vector-gep", """define <2 x ptr> @top(ptr %p) {
 %v = getelementptr i8, ptr %p, <2 x i64> <i64 0, i64 1>
 ret <2 x ptr> %v
}""")
    work = check("unimplemented-composite", vector, diagnostic="§5 PT10")
    assert work["transfer_applications"] == work["worklist_pops"] == 1, work
    assert work["rounds_completed"] == 0, work
    scalable = fixture("scalable-gep", """define ptr @top(ptr %p, i64 %n) {
 %v = getelementptr <vscale x 2 x i8>, ptr %p, i64 %n
 ret ptr %v
}""")
    work = check("unimplemented-gep", scalable, diagnostic="§5 PT2 GEP offset")
    assert work["transfer_applications"] == work["worklist_pops"] == 1, work
    assert work["rounds_completed"] == 0, work
    print(json.dumps({"major": args.major, "cases": len(results),
                      "passed": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
