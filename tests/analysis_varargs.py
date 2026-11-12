#!/usr/bin/env python3
"""PT9 through §14.3 N23 va blocks: a pointer passed through `...` and read with
va_arg must reach the callee's AV (PT9 binds the spilled va block; S2 models N23's
value effects). Regression for allocator installation through varargs, plus ABI records,
IR va_arg, va_copy in nonvariadic consumers and reversible closure selection."""

import argparse
import json
from pathlib import Path

from contracts import run
from contracts import ROOT as R

VA = """%va = type { i32, i32, ptr, ptr }
declare void @llvm.va_start(ptr)
declare void @llvm.va_end(ptr)
"""
# The memory path of the x86-64 inline va_arg: overflow_arg_area at offset 8.
READ = """ %ap = alloca %va
 call void @llvm.va_start(ptr %ap)
 %ovp = getelementptr inbounds %va, ptr %ap, i64 0, i32 2
 %ov = load ptr, ptr %ovp
 %p = load ptr, ptr %ov
 call void @llvm.va_end(ptr %ap)
"""
CASES = {
    "va-pointer": (
        VA + """@g = internal global i32 0
define internal ptr @pass(i32 %n, ...) {
""" + READ + """ ret ptr %p
}
define ptr @top() {
 %r = call ptr (i32, ...) @pass(i32 1, ptr @g)
 ret ptr %r
}""",
        [("pass", "%p", "PTR(@g,0,0)"), ("top", "%r", "PTR(@g,0,0)")],
        None,
    ),
    # sqlite3_config(SQLITE_CONFIG_MALLOC, &defaultMethods) installs the allocator.
    "va-installs-callee": (
        VA + """%methods = type { ptr }
@impl = internal global i8 0
@defaults = internal constant %methods { ptr @myMalloc }
@cfg = internal global %methods zeroinitializer
define internal ptr @myMalloc(i32 %n) { ret ptr @impl }
define internal void @config(i32 %op, ...) {
""" + READ + """ call void @llvm.memcpy.p0.p0.i64(ptr @cfg, ptr %p, i64 8, i1 false)
 ret void
}
declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1)
define ptr @top(i32 %n) {
 call void (i32, ...) @config(i32 1, ptr @defaults)
 %f = load ptr, ptr @cfg
 %r = call ptr %f(i32 %n)
 ret ptr %r
}""",
        [("top", "%f", "FN(@myMalloc,0,0)"), ("top", "%r", "PTR(@impl,0,0)")],
        ("top", "%r", "myMalloc"),
    ),
}


CASES["indirect-va-pointer"] = (
    CASES["va-pointer"][0].replace("define ptr @top() {", "define ptr @top() {\n %f = select i1 true, ptr @pass, ptr @pass").replace("@pass(i32 1, ptr @g)", "%f(i32 1, ptr @g)"),
    CASES["va-pointer"][1], None,
)
CASES["empty-block"] = (
    VA + """define internal ptr @pass(i32 %n, ...) {
 %ap = alloca %va
 call void @llvm.va_start(ptr %ap)
 %ovp = getelementptr %va, ptr %ap, i64 0, i32 2
 %p = load ptr, ptr %ovp
 ret ptr %p
}
define ptr @top() {
 %r = call ptr (i32, ...) @pass(i32 0)
 ret ptr %r
}
""", [("top", "%r", "INT(0)")], None,
)
CASES["composite-slots"] = (
    VA + """@g = internal global i32 0
@h = internal global i32 1
define internal ptr @pass(i32 %n, ...) {
 %ap = alloca %va
 call void @llvm.va_start(ptr %ap)
 %skip = va_arg ptr %ap, i64
 %v = va_arg ptr %ap, <2 x ptr>
 %a = va_arg ptr %ap, {ptr, ptr}
 %p = extractelement <2 x ptr> %v, i32 0
 %q = extractvalue {ptr, ptr} %a, 1
 ret ptr %q
}
define ptr @top() {
 %r = call ptr (i32, ...) @pass(i32 1, i64 7,
       <2 x ptr> <ptr @g, ptr @h>, {ptr, ptr} {ptr @g, ptr @h})
 ret ptr %r
}
""", [("pass", "%p", "PTR(@g,0,0)"), ("pass", "%q", "PTR(@h,0,0)"),
      ("top", "%r", "PTR(@h,0,0)")], None,
)


def analyse(major, plugin, source, directory, reversible):
    report = directory / "report.json"
    route = (["-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
              "-bennett-tier=reversible", "-bennett-entry=top"] if reversible
             else ["-bennett-dialect=0.2.13"])
    command = [f"/usr/lib/llvm-{major}/bin/opt", f"-load-pass-plugin={plugin}",
               "-passes=bennett", *route, "-bennett-analysis-only",
               f"-bennett-report={report}", "-disable-output", source]
    result = run(command)
    assert result.returncode == 0, result.stderr
    return json.loads(report.read_text())


def check_values(data, wants, call):
    values = {(v["function"], v["value"]): v for v in data["values"]}
    for fn, val, atom in wants:
        value = values[(fn, val)]
        assert atom in value["atoms"], (fn, val, atom, value)
    if call:
        sites = data["value_premise"]["indirect_calls"]
        assert any(s["function"] == call[0] and s["value"] == call[1]
                   and call[2] in s["candidates"] for s in sites), sites


def abi_case(target):
    # IR va_arg advances the same cursor as inline va_arg. The consumer is
    # deliberately nonvariadic, and va_copy aliases its source in the second call.
    body = VA + """declare void @llvm.va_copy(ptr, ptr)
@g = internal global i32 0
@h = internal global i32 1
define internal ptr @consume(ptr %source) {
 %copy = alloca [32 x i8], align 8
 call void @llvm.va_copy(ptr %copy, ptr %source)
 %p = va_arg ptr %copy, ptr
 call void @llvm.va_copy(ptr %copy, ptr %copy)
 call void @llvm.va_end(ptr %copy)
 ret ptr %p
}
define internal ptr @pass(i32 %n, ...) {
 %ap = alloca [32 x i8], align 8
 call void @llvm.va_start(ptr %ap)
 %p = call ptr @consume(ptr %ap)
 call void @llvm.va_end(ptr %ap)
 ret ptr %p
}
define ptr @top() {
 %one = call ptr (i32, ...) @pass(i32 1, ptr @g)
 %two = call ptr (i32, ...) @pass(i32 1, ptr @h)
 ret ptr %two
}
"""
    return target, body, [("consume", "%p", f"PTR(@{g},0,0)") for g in ("g", "h")]



def differential(major, plugin, source, directory, data, wants, reversible):
    normalised = directory / "normalised.ll"
    result = run([f"/usr/lib/llvm-{major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-normalise-only", "-S", source,
                  "-o", normalised])
    assert result.returncode == 0, result.stderr
    target = directory / "normalised-analysis"
    target.mkdir(exist_ok=True)
    reference = analyse(major, plugin, normalised, target, reversible)
    observed = {(v["function"], v["value"]): (v["top"], sorted(v["atoms"]))
                for v in data["values"]}
    expected = {(v["function"], v["value"]): (v["top"], sorted(v["atoms"]))
                for v in reference["values"]}
    # N21 can erase source extracts; compare surviving call results as well.
    compared = {(fn, value) for fn, value, _ in wants} & expected.keys()
    assert compared
    for key in compared:
        assert observed[key] == expected[key], (key, observed[key], expected[key])


def diagnostic(major, plugin, directory):
    # This target has no §14.3 record. An unsupported operation must not leave
    # its pointer result at bottom and then appear to succeed.
    source = directory / "unsupported.ll"
    source.write_text('target triple = "powerpc64le-unknown-linux-gnu"\n' +
                      CASES["va-pointer"][0])
    result = run([f"/usr/lib/llvm-{major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only", "-disable-output", source])
    assert result.returncode != 0 and "§14.3" in result.stderr, result.stderr

def production(major, plugin, directory):
    body = CASES["va-installs-callee"][0] + """
define i32 @main() {
 %p = call ptr @top(i32 8)
 ret i32 0
}
"""
    source = directory / "production.ll"
    source.write_text('target datalayout = "e-p:64:64"\n' + body)
    out = directory / "production"
    result = run([f"/usr/lib/llvm-{major}/bin/opt", f"-load-pass-plugin={plugin}",
                  "-passes=bennett", "-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
                  "-bennett-tier=reversible", "-bennett-entry=main",
                  "-bennett-budget-default=10000000,1048576,65536,256,65536",
                  f"-bennett-out={out}", "-disable-output", source])
    assert result.returncode == 0, result.stderr
    launch = out / "main/launch.bennett"
    # Reversible.inc assigns R ordinals in module order. myMalloc is the
    # first defined source function and the only target of this signature.
    emitted = launch.read_text()
    assert "fn r @R0 (a0:i32) (result:ptr)" in emitted, launch
    assert "= call @R0 " in emitted, launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, choices=(18, 23), required=True)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path, default=R / ".tmp/analysis-varargs")
    args = parser.parse_args()
    plugin = (args.plugin or R / f"build/libbennett-plugin-{args.major}.so").resolve()
    cases = [(name, "x86_64", *case) for name, case in CASES.items()]
    cases += [("copy-" + target, target, body, wants, None)
              for target, body, wants in map(abi_case, ("x86_64", "aarch64", "riscv64"))]
    for name, target, body, wants, call in cases:
        for reversible in (False, True):
            directory = args.artifacts / str(args.major) / (name + str(reversible))
            directory.mkdir(parents=True, exist_ok=True)
            source = directory / "in.ll"
            source.write_text('target datalayout = "e-p:64:64"\n' +
                              f'target triple = "{target}-unknown-linux-gnu"\n' + body)
            data = analyse(args.major, plugin, source, directory, reversible)
            check_values(data, wants, call)
            differential(args.major, plugin, source, directory, data, wants, reversible)
    production(args.major, plugin, directory)
    diagnostic(args.major, plugin, directory)
    print(json.dumps(dict(major=args.major, cases=len(cases) * 2 + 1, passed=True)))


if __name__ == "__main__":
    main()
