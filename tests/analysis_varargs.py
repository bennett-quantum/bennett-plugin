#!/usr/bin/env python3
"""PT9 through §14.3 N23 va blocks: a pointer passed through `...` and read with
va_arg must reach the callee's AV (PT9 binds the spilled va block; S2 models N23's
value effects). Candidate regression for the SQLite allocator installed through
sqlite3_config(SQLITE_CONFIG_MALLOC, ...); expected to FAIL on b120196."""

import argparse, json, subprocess
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
@defaults = internal constant %methods { ptr @alloc }
@cfg = internal global %methods zeroinitializer
define internal ptr @alloc(i32 %n) { ret ptr @impl }
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
        [("top", "%f", "FN(@alloc,0,0)"), ("top", "%r", "PTR(@impl,0,0)")],
        ("top", "%r", "alloc"),
    ),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--major", type=int, required=True)
    a = p.parse_args()
    results = []
    for name, (body, wants, call) in CASES.items():
        dest = R / f".tmp/analysis-varargs/{a.major}/{name}"
        dest.mkdir(parents=True, exist_ok=True)
        src = dest / "in.ll"
        src.write_text('target datalayout = "e-p:64:64"\ntarget triple = "x86_64-unknown-linux-musl"\n' + body + "\n")
        report = dest / "report.json"
        x = subprocess.run(
            [
                f"/usr/lib/llvm-{a.major}/bin/opt",
                "-load-pass-plugin=" + str(R / f"build/libbennett-plugin-{a.major}.so"),
                "-passes=bennett",
                "-bennett-dialect=0.2.13",
                "-bennett-analysis-only",
                "-bennett-report=" + str(report),
                "-disable-output",
                str(src),
            ],
            capture_output=True,
            text=True,
        )
        ok = x.returncode == 0
        data = json.loads(report.read_text()) if ok else {}
        values = {(v["function"], v["value"]): v for v in data.get("values", [])}
        missing = []
        for fn, val, atom in wants:
            v = values.get((fn, val))
            # A superset is sound; only the native value's absence is a failure.
            if not v or not (v["top"] or atom in v["atoms"]):
                missing.append(f"{fn} {val} lacks {atom}")
        if call:
            sites = data.get("value_premise", {}).get("indirect_calls", [])
            if not any(s["function"] == call[0] and s["value"] == call[1] and call[2] in s["candidates"] for s in sites):
                missing.append(f"{call[0]} {call[1]} candidates lack {call[2]}")
        ok = ok and not missing
        results.append({"case": name, "ok": ok, "missing": missing, "stderr": x.stderr[-400:] if x.returncode else ""})
    print(json.dumps(results, indent=1))
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
