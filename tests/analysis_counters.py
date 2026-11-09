#!/usr/bin/env python3
"""S2 work receipts survive resource and unsupported-transfer exits."""

import argparse
import json
import os
from pathlib import Path

from contracts import ROOT, run


PREFIX = "bennett-analysis-work:"
COUNTERS = ("transfer_applications", "worklist_pops", "rounds_completed", "join_count")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", required=True, type=int)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path,
                        default=ROOT / ".tmp/analysis-counters")
    args = parser.parse_args(argv)
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    results = []

    def check(name, source, options=(), diagnostic=None, with_report=True,
              environment=None, cpu_clock_available=True):
        report = directory / f"{name}.json"
        report.unlink(missing_ok=True)
        result = run([
            f"/usr/lib/llvm-{args.major}/bin/opt",
            f"-load-pass-plugin={plugin}", "-passes=bennett",
            "-bennett-dialect=0.2.13", "-bennett-analysis-only",
            *([f"-bennett-report={report}"] if with_report else []),
            "-disable-output", source, *options,
        ], env=environment)
        if diagnostic:
            assert result.returncode != 0 and diagnostic in result.stderr, result.stderr
        else:
            assert result.returncode == 0, result.stderr
        lines = [line[len(PREFIX):].strip() for line in result.stderr.splitlines()
                 if line.startswith(PREFIX)]
        assert len(lines) == 1, (name, "expected exactly one work receipt", result.stderr)
        work = json.loads(lines[0])
        if with_report:
            assert report.exists(), (name, "missing JSON report on analysis exit")
            data = json.loads(report.read_text())
            assert data["analysis_work"] == work, name
            if not diagnostic:
                assert data["analysis_rounds"] == work["rounds_completed"], data
        else:
            assert not report.exists(), name
        assert all(type(work[key]) is int and work[key] >= 0 for key in COUNTERS), work
        joins = ("av_merges", "field_joins", "slot_joins")
        assert all(type(work[key]) is int and work[key] >= 0 for key in joins), work
        assert work["join_count"] == sum(work[key] for key in joins), work
        visits = work["function_visits"]
        assert type(visits["total"]) is int and visits["total"] >= 0, work
        assert all(type(value) is int and value > 0 for value in visits["top"].values()), work
        assert sum(visits["top"].values()) <= visits["total"], work
        assert type(visits["top_limit"]) is int and len(visits["top"]) <= visits["top_limit"], work
        functions = work["per_function"]
        assert sum(f["worklist_pops"] for f in functions.values()) == work["worklist_pops"], work
        assert sum(f["transfer_applications"] for f in functions.values()) == work["transfer_applications"], work
        assert sum(f["join_count"] for f in functions.values()) <= work["join_count"], work
        assert all(f["rounds_completed"] >= work["rounds_completed"]
                   for f in functions.values()), work
        assert work["worklist_pops"] >= work["transfer_applications"], work
        assert work["cpu_ms"]["deterministic"] is False, work
        if cpu_clock_available:
            assert isinstance(work["cpu_ms"]["value"], (int, float)), work
            assert work["cpu_ms"]["value"] >= 0, work
        else:
            assert work["cpu_ms"]["value"] is None, work
            assert work["cpu_ms"]["error"] == "S2 thread CPU clock unavailable", work
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
    check("success-without-report", simple, with_report=False)

    # The scalar add joins its computed constant and result once, then is
    # cached on round two. Each of the two return transfers joins once.
    cached = fixture("cached", """define i8 @top() {
 %v = add i8 1, 2
 ret i8 %v
}""")
    work = check("cached-transfer", cached)
    assert (work["rounds_completed"], work["worklist_pops"],
            work["transfer_applications"], work["join_count"]) == (2, 4, 3, 4), work
    assert work["function_visits"]["top"] == {"top": 2}, work
    many = fixture("many-functions", "\n".join(
        f"define void @f{index:02}() {{ ret void }}" for index in range(12)
    ))
    work = check("top-functions", many)
    assert work["function_visits"]["total"] == 12, work
    assert work["function_visits"]["top_limit"] == 10, work
    assert work["function_visits"]["top"] == {f"f{index:02}": 1 for index in range(10)}, work
    unnamed = fixture("unnamed-functions", """define void @0() { ret void }
define void @1() { ret void }""")
    work = check("unnamed-functions", unnamed)
    assert work["function_visits"]["total"] == 2, work
    assert work["function_visits"]["top"] == {"@0": 1, "@1": 1}, work

    aggregate = fixture("aggregate", """@cell = internal global {i8, i8} zeroinitializer
define i8 @top() {
 store {i8, i8} {i8 7, i8 9}, ptr @cell
 %a = load {i8, i8}, ptr @cell
 %v = extractvalue {i8, i8} %a, 1
 ret i8 %v
}""")
    work = check("field-and-slot-joins", aggregate)
    assert all(work[key] > 0 for key in ("av_merges", "field_joins", "slot_joins")), work

    # An absent ordinary import is conservatively analysed, as before; adding
    # observability must not introduce a new rejection for external calls.
    imported = fixture("external-import", """declare i8 @external(i8)
define i8 @top() {
 %v = call i8 @external(i8 7)
 ret i8 %v
}""")
    work = check("external-import", imported)
    assert work["transfer_applications"] > 0 and work["rounds_completed"] > 0, work

    vector = fixture("vector-vaarg", """define <2 x i32> @top(ptr %p) {
 %v = va_arg ptr %p, <2 x i32>
 ret <2 x i32> %v
}""")
    work = check("unimplemented-composite", vector, diagnostic="§5 PT10")
    assert work["transfer_applications"] == work["worklist_pops"] == 1, work
    assert work["rounds_completed"] == 0, work
    check("stop-without-report", vector, diagnostic="§5 PT10", with_report=False)
    scalable = fixture("scalable-gep", """define ptr @top(ptr %p, i64 %n) {
 %v = getelementptr <vscale x 2 x i8>, ptr %p, i64 %n
 ret ptr %v
}""")
    work = check("unimplemented-gep", scalable, diagnostic="§5 PT2 GEP offset")
    assert work["transfer_applications"] == work["worklist_pops"] == 1, work
    assert work["rounds_completed"] == 0, work

    # Normalisation fails in another translation unit while the S2 scope is
    # active; this must retain the same receipt as a direct transfer failure.
    incompatible = fixture("incompatible-import", """declare void @__bennett_sf_add_f32()
define float @top(float %x) {
 %v = fadd float %x, 1.0
 ret float %v
}""")
    work = check("helper-import-stop", incompatible,
                 diagnostic="§13.1 incompatible linked entry point")
    assert work["rounds_completed"] == 0 and work["transfer_applications"] == 1, work

    missing = fixture("missing-import", """declare void @__bennett_oracle(ptr, ptr, ptr)
define internal float @top(float %x) {
 %v = fadd float %x, 1.0
 ret float %v
}
define void @host() {
 call void @__bennett_oracle(ptr @top, ptr null, ptr null)
 ret void
}""")
    work = check("missing-import-stop", missing,
                 diagnostic="§13.1 BENNETT_ARITH_BITCODE could not be read",
                 environment=dict(os.environ, BENNETT_ARITH_BITCODE=str(
                     directory / "absent-arithmetic.bc")))
    assert work["rounds_completed"] > 0 and work["transfer_applications"] > 0, work

    # A controlled thread clock makes the interrupted position independent of
    # host speed and also exercises the real pass's clock-unavailable exit.
    clock = directory / "clock.so"
    built = run(["cc", "-shared", "-fPIC", "-x", "c", "-o", clock, "-"], input=r"""
#define _GNU_SOURCE
#include <stdlib.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
int clock_gettime(clockid_t clock, struct timespec *time) {
  if (clock != CLOCK_THREAD_CPUTIME_ID)
    return syscall(SYS_clock_gettime, clock, time);
  if (getenv("ANALYSIS_TEST_CLOCK_UNAVAILABLE")) return -1;
  static unsigned long long reads = 0;
  unsigned long long nanoseconds = ++reads * 100000;
  time->tv_sec = nanoseconds / 1000000000;
  time->tv_nsec = nanoseconds % 1000000000;
  return 0;
}
""")
    assert built.returncode == 0, built.stderr
    controlled = dict(os.environ, LD_PRELOAD=str(clock.absolute()))
    chain = fixture("transfer-chain", "define i64 @top() {\n" + "\n".join(
        f" %v{index} = add i64 " + (f"%v{index-1}" if index else "0") + ", 1"
        for index in range(32)
    ) + "\n ret i64 %v31\n}")
    interrupted = check("interrupted-transfer", chain,
                        ["-bennett-analysis-budget-ms=1"], diagnostic="§5.2",
                        environment=controlled)
    assert {key: interrupted[key] for key in COUNTERS} == {
        "transfer_applications": 9, "worklist_pops": 10,
        "rounds_completed": 0, "join_count": 18,
    }, interrupted
    again = check("interrupted-repeat", chain,
                  ["-bennett-analysis-budget-ms=1"], diagnostic="§5.2",
                  environment=controlled)
    assert {k: v for k, v in interrupted.items() if k != "cpu_ms"} == {
        k: v for k, v in again.items() if k != "cpu_ms"
    }, (interrupted, again)
    check("clock-unavailable", simple, diagnostic="S2 thread CPU clock unavailable",
          environment=dict(controlled, ANALYSIS_TEST_CLOCK_UNAVAILABLE="1"),
          cpu_clock_available=False)
    return {"major": args.major, "cases": len(results),
            "passed": len(results), "results": results}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
