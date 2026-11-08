#!/usr/bin/env python3
"""Pointer orbits checked against an enumerating finite-width set oracle."""

import argparse
import json
import subprocess
from pathlib import Path
import re

from analysis_convergence import frozen_clock
from contracts import ROOT, run


def least_fixpoint(width, seeds, edges):
    """Simultaneous set union, independent of the plugin's subgroup solver."""
    modulus = 1 << width
    result = {node: set(values) for node, values in seeds.items()}
    while True:
        next_result = {node: set(values) for node, values in result.items()}
        for destination, source, displacement in edges:
            next_result[destination].update(
                (value + displacement) % modulus for value in result[source])
        if next_result == result:
            return result
        result = next_result


def represented_offsets(atoms, object_name, width):
    modulus = 1 << width
    result = set()
    for text in atoms:
        match = re.fullmatch(r"PTR\((.*),(-?\d+),(-?\d+)\)", text)
        if not match or match[1] != object_name:
            continue
        offset, stride = int(match[2]), int(match[3])
        if stride == -1:
            result.update(range(modulus))
        elif stride:
            result.update(value % modulus for value in range(
                -(modulus // 2), modulus // 2) if (value - offset) % stride == 0)
        else:
            result.add(offset % modulus)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path, default=ROOT / ".tmp/analysis-pointer-closure")
    args = parser.parse_args(argv)
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    environment = frozen_clock(directory)
    results = []

    def check(name, body, layout="e-p:64:64", diagnostic=None):
        source = directory / f"{name}.ll"
        source.write_text(f'target datalayout = "{layout}"\n' + body)
        report = directory / f"{name}.json"
        result = run([
            f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
            "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
            "-bennett-analysis-max-rounds=64", f"-bennett-report={report}",
            "-disable-output", source,
        ], env=environment)
        (directory / f"{name}.stderr").write_text(result.stderr)
        data = json.loads(report.read_text())
        if diagnostic:
            assert result.returncode and diagnostic in result.stderr, result.stderr
        else:
            assert result.returncode == 0, result.stderr
            assert data["analysis_work"]["rounds_completed"] <= 64, data
        results.append({"case": name, "exit": result.returncode,
                        "rounds": data["analysis_work"]["rounds_completed"]})
        return {row["value"]: row for row in data.get("values", [])}

    nested = check("nested", """
@a = internal global i8 0
define ptr @top(i1 %condition) {
entry: br label %outer
outer:
 %p = phi ptr [ @a, %entry ], [ %s, %exit ]
 br label %inner
inner:
 %q = phi ptr [ %p, %outer ], [ %r, %inner ]
 %r = getelementptr i8, ptr %q, i8 1
 br i1 %condition, label %inner, label %exit
exit:
 %s = getelementptr i8, ptr %q, i8 2
 br i1 %condition, label %outer, label %done
done: ret ptr %s
}
""", layout="e-p:8:8")
    oracle = least_fixpoint(8, {"p": {0}, "q": set(), "r": set(), "s": set()},
                           [("p", "s", 0), ("q", "p", 0), ("q", "r", 0),
                            ("r", "q", 1), ("s", "q", 2)])
    for name, expected in oracle.items():
        row = nested[f"%{name}"]
        assert represented_offsets(row["atoms"], "@a", 8) == expected, row
        assert row["top"] and "PTR(EXT,0,-1)" in row["atoms"], row

    fields = check("field-families", """
define i64 @top(i1 %condition) {
entry:
 %cell = alloca [2 x {i64, i64}], align 16
 br label %loop
loop:
 %p = phi ptr [ %cell, %entry ], [ %next, %loop ]
 %next = getelementptr i8, ptr %p, i64 16
 %field = getelementptr i8, ptr %p, i64 8
 store i64 7, ptr %p
 store i64 9, ptr %field
 %second = getelementptr i8, ptr %cell, i64 8
 %left = load i64, ptr %cell
 %right = load i64, ptr %second
 %partial = load i8, ptr %cell
 %spanning = load i128, ptr %cell
 br i1 %condition, label %loop, label %done
done: ret i64 %left
}
""")
    assert fields["%left"]["top"] is False, fields["%left"]
    assert set(fields["%left"]["atoms"]) == {"INT(0)", "INT(7)"}, fields["%left"]
    assert fields["%right"]["top"] is False, fields["%right"]
    assert set(fields["%right"]["atoms"]) == {"INT(0)", "INT(9)"}, fields["%right"]
    assert fields["%partial"]["top"] and fields["%spanning"]["top"], fields
    assert "PTR(%cell,0,16)" in fields["%p"]["atoms"], fields["%p"]
    assert "PTR(%cell,8,16)" in fields["%field"]["atoms"], fields["%field"]

    writes = check("narrow-write-and-copy", """
declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1)
define internal void @target() { ret void }
define ptr @top(i1 %condition) {
entry:
 %src = alloca [2 x {ptr, ptr}], align 16
 %dst = alloca {ptr, ptr}, align 16
 br label %loop
loop:
 %p = phi ptr [ %src, %entry ], [ %next, %loop ]
 %next = getelementptr i8, ptr %p, i64 16
 store ptr @target, ptr %p
 br i1 %condition, label %loop, label %done
done:
 store ptr null, ptr %src
 call void @llvm.memcpy.p0.p0.i64(ptr %dst, ptr %src, i64 16, i1 false)
 %copied = load ptr, ptr %dst
 %second = getelementptr i8, ptr %src, i64 16
 %unmodified = load ptr, ptr %second
 ret ptr %copied
}
""")
    assert "FN(@target,0,0)" in writes["%copied"]["atoms"], writes["%copied"]
    assert not writes["%copied"]["top"], writes["%copied"]
    assert set(writes["%unmodified"]["atoms"]) == {"INT(0)", "FN(@target,0,0)"}, writes
    assert not writes["%unmodified"]["top"], writes["%unmodified"]

    overlap = check("overlapping-family-members", """
define internal void @target() { ret void }
define ptr @top(i1 %condition) {
entry:
 %cell = alloca [4 x ptr], align 16
 br label %loop
loop:
 %p = phi ptr [ %cell, %entry ], [ %next, %loop ]
 %next = getelementptr i8, ptr %p, i64 4
 store ptr @target, ptr %p
 %address = getelementptr i8, ptr %cell, i64 4
 %value = load ptr, ptr %address
 br i1 %condition, label %loop, label %done
done: ret ptr %value
}
""")
    assert "FN(@target,0,0)" in overlap["%value"]["atoms"], overlap["%value"]
    assert overlap["%value"]["top"], overlap["%value"]

    identities = check("identities-and-growing-increments", """
@a = internal global i8 0
@b = internal global i8 0
define internal void @target() { ret void }
define ptr @top(i1 %condition) {
entry:
 %objects = select i1 %condition, ptr @a, ptr @b
 %seed = select i1 %condition, ptr %objects, ptr @target
 br label %loop
loop:
 %d = phi i8 [ 16, %entry ], [ %late, %loop ]
 %p = phi ptr [ %seed, %entry ], [ %copy, %loop ]
 %next = getelementptr i8, ptr %p, i8 %d
 %copy = freeze ptr %next
 %late = select i1 %condition, i8 8, i8 16
 br i1 %condition, label %loop, label %done
done: ret ptr %p
}
""", layout="e-p:8:8")
    expected = least_fixpoint(8, {"p": {0}}, [("p", "p", 16), ("p", "p", 8)])["p"]
    for object_name in ("@a", "@b"):
        assert represented_offsets(identities["%p"]["atoms"], object_name, 8) == expected, identities
    assert "FN(@target,0,0)" in identities["%p"]["atoms"], identities
    assert sum(text.startswith("PTR(@a,") for text in identities["%p"]["atoms"]) == 1, identities

    finite = check("zero-net-cycle", """
@a = internal global [4 x i8] zeroinitializer
define ptr @top(i1 %condition) {
entry: br label %loop
loop:
 %p = phi ptr [ @a, %entry ], [ %back, %loop ]
 %next = getelementptr i8, ptr %p, i64 1
 %back = getelementptr i8, ptr %next, i64 -1
 br i1 %condition, label %loop, label %done
done: ret ptr %p
}
""")
    assert finite["%p"]["atoms"] == ["PTR(@a,0,0)"] and not finite["%p"]["top"], finite
    assert finite["%next"]["atoms"] == ["PTR(@a,1,0)"], finite

    partial = check("partial-index-width", """
@a = internal global [128 x i8] zeroinitializer, align 256
define ptr @top() {
 %p = getelementptr i8, ptr @a, i64 250
 %wrapped = getelementptr i8, ptr %p, i64 10
 ret ptr %wrapped
}
""", layout="e-p:64:64:64:8")
    assert set(partial["%p"]["atoms"]) == {"PTR(@a,250,0)", "PTR(EXT,0,-1)"}, partial
    assert set(partial["%wrapped"]["atoms"]) == {"PTR(@a,4,0)", "PTR(EXT,0,-1)"}, partial

    check("root-provenance", """
declare ptr @__bennett_qalloc(i64, i64)
define void @top(i1 %condition) {
entry:
 %h0 = call ptr @__bennett_qalloc(i64 1, i64 0)
 %h1 = call ptr @__bennett_qalloc(i64 1, i64 0)
 %seed = select i1 %condition, ptr %h0, ptr %h1
 br label %loop
loop:
 %p = phi ptr [ %seed, %entry ], [ %next, %loop ]
 %next = getelementptr i8, ptr %p, i64 16
 br i1 %condition, label %loop, label %done
done: ret void
}
""", diagnostic="BD-E-HANDLE")
    receipt = {"major": args.major, "cases": len(results), "passed": len(results),
               "results": results}
    (directory / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    try:
        print(json.dumps(main(), indent=2))
    except subprocess.TimeoutExpired as error:
        print(f"UNKNOWN/TIMEOUT: {error.cmd}")
        raise SystemExit(124)
