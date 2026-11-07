#!/usr/bin/env python3
"""M1 acceptance witnesses for §5 represented-address images.

These witnesses do not establish every symbolic/residue-class image; a green
regression gate does not close bp-3w4. Expectations follow accepted 0.2.10,
never the sibling worktree.
"""

import argparse
import json
import subprocess
from contracts import ROOT as R

CASES = {
    "PT3-address-space-copy": (
        "e-p:64:64-p270:32:32",
        """@g = internal global i8 0
define ptr addrspace(270) @top() {
 %v = addrspacecast ptr @g to ptr addrspace(270)
 ret ptr addrspace(270) %v
}""",
        {"PTR(@g,0,0)"},
        False,
    ),
    "PT4-object-roundtrip": (
        "e-p:64:64",
        """@g = internal global i8 0
define ptr @top() {
 %p = ptrtoint ptr @g to i64
 %v = inttoptr i64 %p to ptr
 ret ptr %v
}""",
        {"PTR(@g,0,0)"},
        False,
    ),
    "PT2-numerical-not-host-escape": (
        "e-p:64:64:64:8",
        """@g = internal global [32 x i8] zeroinitializer, align 16
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
define ptr @top() {
 %h = call ptr @__bennett_qalloc(i64 0,i64 1)
 %v = getelementptr i8, ptr @g, i8 16
 store ptr %h, ptr %v
 call void @__bennett_qfree(ptr %h)
 ret ptr %v
}""",
        {"PTR(@g,16,0)", "PTR(@g,-240,0)", "PTR(EXT,0,-1)"},
        True,
    ),
    # With I=8 and alignment 16, base low bits can be 240. Adding 16
    # preserves all pointer bits above I, so that case moves -240 bytes.
    "PT2-low-index-wrap": (
        "e-p:64:64:64:8",
        """@g = internal global [32 x i8] zeroinitializer, align 16
define ptr @top() {
 %v = getelementptr i8, ptr @g, i8 16
 ret ptr %v
}""",
        {"PTR(@g,16,0)", "PTR(@g,-240,0)", "PTR(EXT,0,-1)"},
        True,
    ),
    # High address bits are lost. The image cannot be represented as a single
    # displacement from @g for all possible base patterns.
    "PT4-narrow-address": (
        "e-p:64:64",
        """@g = internal global i8 0, align 16
define i8 @top() {
 %v = ptrtoint ptr @g to i8
 ret i8 %v
}""",
        {"PTR(@g,0,-1)", "PTR(EXT,0,-1)"},
        True,
    ),
    # Explicit fixed reference fallback in PT5 for widening pointer integers.
    "PT5-widen-address": (
        "e-p:64:64",
        """@g = internal global i8 0
define i128 @top() {
 %p = ptrtoint ptr @g to i64
 %v = zext i64 %p to i128
 ret i128 %v
}""",
        {"PTR(@g,0,-1)", "PTR(EXT,0,-1)"},
        True,
    ),
    "PT2-finite-index-wrap": (
        "e-p:64:64:64:8",
        """@g = internal global [32 x i8] zeroinitializer, align 16
define ptr @top(i1 %c) {
 %i = select i1 %c, i8 0, i8 16
 %v = getelementptr i8, ptr @g, i8 %i
 ret ptr %v
}""",
        {"PTR(@g,0,0)", "PTR(@g,16,0)", "PTR(@g,-240,0)", "PTR(EXT,0,-1)"},
        True,
    ),
    "PT2-finite-multi-index-accumulation": (
        "e-p:64:64:64:8",
        """@g = internal global [16 x i8] zeroinitializer, align 256
define ptr @top(i1 %c) {
 %i = select i1 %c, i8 1, i8 2
 %j = select i1 %c, i8 -16, i8 -32
 %v = getelementptr [16 x i8], ptr @g, i8 %i, i8 %j
 ret ptr %v
}""",
        {"PTR(@g,0,0)", "PTR(@g,16,0)", "PTR(@g,240,0)", "PTR(EXT,0,-1)"},
        True,
    ),
    "PT2-symbolic-small-index-image": (
        "e-p:64:64:64:8",
        """@g = internal global [32 x i8] zeroinitializer, align 256
define ptr @top(i8 %i) {
 %v = getelementptr i8, ptr @g, i8 %i
 ret ptr %v
}""",
        {f"PTR(@g,{i},0)" for i in range(256)} | {"PTR(EXT,0,-1)"},
        True,
    ),
    "PT5-full-width-outside-object": (
        "e-p:64:64",
        """@g = internal global i8 0
define i64 @top() {
 %p = ptrtoint ptr @g to i64
 %v = add i64 %p, 8
 ret i64 %v
}""",
        {"PTR(@g,8,0)", "PTR(EXT,0,-1)"},
        True,
    ),
    "PT5-commuted-add": (
        "e-p:64:64",
        """@g = internal global [16 x i8] zeroinitializer
define i64 @top() {
 %p = ptrtoint ptr @g to i64
 %v = add i64 8, %p
 ret i64 %v
}""",
        {"PTR(@g,8,0)"},
        False,
    ),
    "PT5-wide-unrepresentable-displacement": (
        "e-p:64:64",
        """@g = internal global i8 0
define i128 @top() {
 %p = ptrtoint ptr @g to i128
 %v = add i128 %p, 18446744073709551616
 ret i128 %v
}""",
        {"PTR(@g,0,-1)", "PTR(EXT,0,-1)"},
        True,
    ),
    "PT8-partial-copy-contained-destination": (
        "e-p:64:64",
        """@g = internal global i64 42
declare void @llvm.memcpy.p0.p0.i64(ptr,ptr,i64,i1)
define i32 @top() {
 %dst = alloca [8 x i8]
 call void @llvm.memcpy.p0.p0.i64(ptr %dst, ptr @g, i64 2, i1 false)
 %tail = getelementptr i8, ptr %dst, i64 4
 %v = load i32, ptr %tail
 ret i32 %v
}""",
        {"INT(0)"},
        False,
    ),
    "PT12-indirect-undefined-result": (
        "e-p:64:64",
        """declare i32 @external(ptr)
define i32 @top(i1 %c) {
 %fp = select i1 %c, ptr @external, ptr @external
 %dst = alloca i32
 %v = call i32 %fp(ptr %dst)
 ret i32 %v
}""",
        set(),
        True,
    ),
    "PT12-indirect-undefined-reachable-memory": (
        "e-p:64:64",
        """declare i32 @external(ptr)
define i32 @top(i1 %c) {
 %fp = select i1 %c, ptr @external, ptr @external
 %dst = alloca i32
 %r = call i32 %fp(ptr %dst)
 %v = load i32, ptr %dst
 ret i32 %v
}""",
        set(),
        True,
    ),
    "PT11-host-caller-constant-argument": (
        "e-p:64:64",
        """define internal i8 @leaf(i8 %x) {
 %v = add i8 %x, 0
 ret i8 %v
}
define i8 @top() {
 %r = call i8 @leaf(i8 7)
 ret i8 %r
}""",
        set(),
        True,
    ),
    "PT11-device-only-address-use": (
        "e-p:64:64",
        """@table = internal constant ptr @leaf
declare void @__bennett_oracle(ptr,ptr,ptr)
define internal i8 @leaf(i8 %x) {
 %v = add i8 %x, 0
 ret i8 %v
}
define internal i8 @region() {
 %fp = load ptr, ptr @table
 %r = call i8 %fp(i8 7)
 ret i8 %r
}
define void @top() {
 call void @__bennett_oracle(ptr @region,ptr null,ptr null)
 ret void
}""",
        {"INT(7)"},
        False,
    ),
    "N21-vp-reduction-select-unions": (
        "e-p:64:64",
        """declare i32 @llvm.vp.reduce.mul.v2i32(i32,<2 x i32>,<2 x i1>,i32)
define i32 @top() {
 %v = call i32 @llvm.vp.reduce.mul.v2i32(i32 3,<2 x i32> <i32 5,i32 7>,<2 x i1> <i1 true,i1 false>,i32 2)
 ret i32 %v
}""",
        {"INT(3)", "INT(15)", "INT(21)", "INT(105)"},
        False,
    ),
    "N21-vp-selector-zero-arm": (
        "e-p:64:64",
        """declare <2 x i32> @llvm.vp.select.v2i32(<2 x i1>,<2 x i32>,<2 x i32>,i32)
define i32 @top() {
 %x = call <2 x i32> @llvm.vp.select.v2i32(<2 x i1> <i1 true,i1 false>,<2 x i32> <i32 5,i32 6>,<2 x i32> <i32 7,i32 9>,i32 2)
 %v = extractelement <2 x i32> %x, i32 1
 ret i32 %v
}""",
        {"INT(0)", "INT(6)", "INT(9)"},
        False,
    ),
    "N27-extrema-select-union": (
        "e-p:64:64",
        """declare i32 @llvm.smax.i32(i32,i32)
define i32 @top() {
 %v = call i32 @llvm.smax.i32(i32 3,i32 7)
 ret i32 %v
}""",
        {"INT(3)", "INT(7)"},
        False,
    ),
    "N21-faulting-division-no-result": (
        "e-p:64:64",
        """define i8 @top() {
 %x = udiv <2 x i8> <i8 7,i8 8>, <i8 0,i8 1>
 %v = extractelement <2 x i8> %x, i32 0
 ret i8 %v
}""",
        set(),
        False,
    ),
    "PT12-uinc-wrap-select-union": (
        "e-p:64:64",
        """@g = internal global i8 0
define i8 @top() {
 %v = atomicrmw uinc_wrap ptr @g, i8 0 monotonic
 ret i8 %v
}""",
        {f"INT({i})" for i in range(256)},
        False,
    ),
    "PT12-udec-wrap-select-union": (
        "e-p:64:64",
        """@g = internal global i8 0
define i8 @top() {
 %v = atomicrmw udec_wrap ptr @g, i8 0 monotonic
 ret i8 %v
}""",
        {f"INT({i})" for i in range(256)},
        False,
    ),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True)
    major = parser.parse_args().major
    rows = []
    for name, (layout, body, atoms, top) in CASES.items():
        dest = R / f".tmp/reference-images/{major}/{name}"
        dest.mkdir(parents=True, exist_ok=True)
        source, report = dest / "in.ll", dest / "report.json"
        source.write_text(f'target datalayout = "{layout}"\n{body}\n')
        report.unlink(missing_ok=True)
        result = subprocess.run(
            [
                f"/usr/lib/llvm-{major}/bin/opt",
                "-load-pass-plugin=" + str(R / f"build/libbennett-plugin-{major}.so"),
                "-passes=bennett",
                "-bennett-dialect=0.2.13",
                "-bennett-analysis-only",
                "-bennett-report=" + str(report),
                "-disable-output",
                str(source),
            ],
            text=True,
            capture_output=True,
        )
        actual = (
            next(
                (
                    value
                    for value in json.loads(report.read_text())["values"]
                    if value["value"] == "%v"
                ),
                None,
            )
            if result.returncode == 0
            else None
        )
        rows.append(
            {
                "case": name,
                "ok": actual is not None
                and set(actual["atoms"]) == atoms
                and actual["top"] == top,
                "expected": {"atoms": sorted(atoms), "top": top},
                "actual": actual,
                "diagnostic": result.stderr if result.returncode else "",
            }
        )
    audit = {
        "major": major,
        "cases": len(rows),
        "passed": sum(row["ok"] for row in rows),
        "bead": "bp-3w4",
        "results": rows,
    }
    (R / f".tmp/reference-images-{major}.json").write_text(
        json.dumps(audit, indent=2) + "\n"
    )
    print(json.dumps(audit, indent=2))
    return audit["passed"] != audit["cases"]


if __name__ == "__main__":
    raise SystemExit(main())
