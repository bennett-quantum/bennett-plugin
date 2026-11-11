#!/usr/bin/env python3
"""PT3/PT4/PT5 pointer-bearing integer orbits have bounded exact closure work."""

import argparse
import json
from pathlib import Path

from analysis_convergence import frozen_clock
from analysis_monotone import value_domains
from analysis_pointer_closure import least_fixpoint, represented_offsets, small_pointer_module
from contracts import ROOT, run


# A translation by eight in Z/(2^64) generates exactly the multiples of eight.
# Full-width ptrtoint/add/inttoptr preserves that originating-object coset.
MAX_ROUNDS = 8
BLOCKS = {
    "entry": "%seed = ptrtoint ptr @data to i64\n br label %loop",
    "loop": "%bits = phi i64 [ %seed, %entry ], [ %next, %back ]\n br label %back",
    "back": "%next = add i64 %bits, -8\n %p = inttoptr i64 %next to ptr\n br i1 %condition, label %loop, label %done",
    "done": "ret ptr %p",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path, default=ROOT / ".tmp/integer-pointer-closure")
    args = parser.parse_args(argv)
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    environment = frozen_clock(directory)
    reports = []
    for name, order in (("original", ("entry", "loop", "back", "done")),
                        ("blocks", ("entry", "done", "back", "loop"))):
        source = directory / f"{name}.ll"
        source.write_text('target datalayout = "e-p:64:64"\n'
                          + "@data = internal global [8 x i8] zeroinitializer\n"
                          + "define ptr @top(i1 %condition) {\n"
                          + "\n".join(label + ":\n " + BLOCKS[label] for label in order)
                          + "\n}\n")
        report = directory / f"{name}.json"
        result = run([f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
                      "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                      f"-bennett-analysis-max-rounds={MAX_ROUNDS}", f"-bennett-report={report}",
                      "-disable-output", source], env=environment)
        (directory / f"{name}.stderr").write_text(result.stderr)
        data = json.loads(report.read_text())
        assert result.returncode == 0, (name, data["analysis_work"], result.stderr)
        work = data["analysis_work"]
        # Eight instructions per scan; cached dispatches still count.
        assert work["rounds_completed"] <= MAX_ROUNDS, work
        assert work["worklist_pops"] <= 8 * MAX_ROUNDS, work
        for value in ("%bits", "%next", "%p"):
            row = value_domains(data)["top", value]
            assert row == (True, ["PTR(@data,0,8)", "PTR(EXT,0,-1)"]), (value, row)
        reports.append(value_domains(data))
    assert reports[0] == reports[1], reports
    # Repeated reads of one unchanged interval family should reuse its PT6
    # image. 128 exact slots and 32 equivalent reads have a linear work bound;
    # a fresh 128-way join for every read exceeds it independently of CPU time.
    source = directory / "repeated-loads.ll"
    source.write_text('target datalayout = "e-p:64:64"\n'
                      + "@cells = internal global [128 x i64] ["
                      + ", ".join("i64 7" for _ in range(128)) + "]\n"
                      + "define i64 @top(i1 %condition) {\nentry: br label %loop\nloop:\n"
                      + " %p = phi ptr [ @cells, %entry ], [ %next, %loop ]\n"
                      + " %next = getelementptr i8, ptr %p, i64 8\n"
                      + "\n".join(f" %read{n} = load i64, ptr %p" for n in range(32))
                      + "\n br i1 %condition, label %loop, label %done\ndone: ret i64 %read31\n}\n")
    report = directory / "repeated-loads.json"
    result = run([f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                  f"-bennett-report={report}", "-disable-output", source], env=environment)
    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text())
    assert data["analysis_work"]["join_count"] <= 2048, data["analysis_work"]
    for n in range(32):
        assert value_domains(data)["top", f"%read{n}"] == (True, []), data
    # Independently enumerate a complete small bit-vector orbit through both
    # PT4 casts. This checks the subgroup's members, not just its printed stride.
    source = directory / "small-orbit.ll"
    source.write_text(small_pointer_module("@data = internal global [4 x i8] zeroinitializer\n"
                      + "define ptr @top(i1 %condition) {\nentry:\n"
                      + " %seed = getelementptr i8, ptr @data, i8 3\n br label %loop\nloop:\n"
                      + " %p = phi ptr [ %seed, %entry ], [ %back, %loop ]\n"
                      + " %bits = ptrtoint ptr %p to i8\n %next = sub i8 %bits, 16\n"
                      + " %back = inttoptr i8 %next to ptr\n"
                      + " br i1 %condition, label %loop, label %done\ndone: ret ptr %p\n}\n"))
    report = directory / "small-orbit.json"
    result = run([f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                  f"-bennett-report={report}", "-disable-output", source], env=environment)
    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text())
    expected = least_fixpoint(8, {"p": {3}}, [("p", "p", -16)])["p"]
    for name in ("%p", "%bits", "%next", "%back"):
        row = value_domains(data)["top", name]
        assert represented_offsets(row[1], "@data", 8) == expected, (name, row)

    # A cached bottom or finite image must be invalidated by a new slot, an
    # existing slot's new value.
    source = directory / "memory-growth.ll"
    source.write_text('target datalayout = "e-p:64:64"\n'
                      + "@cell = internal global i8 7\n@empty = external global i8\n"
                      + "define i8 @top() {\n %before = load i8, ptr @cell\n"
                      + " %missing = load i8, ptr @empty\n store i8 9, ptr @cell\n"
                      + " store i8 11, ptr @empty\n %after = load i8, ptr @cell\n"
                      + " %added = load i8, ptr @empty\n ret i8 %after\n}\n")
    report = directory / "memory-growth.json"
    result = run([f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                  f"-bennett-report={report}", "-disable-output", source], env=environment)
    assert result.returncode == 0, result.stderr
    domains = value_domains(json.loads(report.read_text()))
    for name in ("%before", "%after"):
        assert domains["top", name] == (False, ["INT(7)", "INT(9)"]), domains
    for name in ("%missing", "%added"):
        assert domains["top", name] == (False, ["INT(11)"]), domains
    receipt = {"major": args.major, "orders": len(reports), "passed": True}
    print(json.dumps(receipt))
    return receipt


if __name__ == "__main__":
    main()
