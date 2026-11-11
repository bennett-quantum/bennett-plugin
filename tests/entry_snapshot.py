#!/usr/bin/env python3
"""Automatic CC snapshots: observe payloads, faults, private writes and clean release.

Exit 124 means UNKNOWN: a hang guard expired. Test failures retain their exit status.
"""

import argparse, json, os, shutil, subprocess, hashlib, shlex, sys
from concurrent.futures import ThreadPoolExecutor
from production import REF as DEBUG_REF

REF = DEBUG_REF.parent.parent / "release/bennett-isa-ref"
from contextlib import suppress
from contracts import run as _run

# `python3 -B tests/entry_snapshot.py --major 18`, timed with the per-call
# limit lifted locally on this 12-core Intel i7-1365U host, 2026-11-08:
# slowest subprocess 850.375730 s (logical-stack reference run-program).
# The guard is 10x that measurement, rounded up to whole seconds.
ENTRY_SNAPSHOT_HANG_GUARD_S = 8504
UNKNOWN_EXIT_STATUS = 124
# Concurrency: scripts/gate runs both LLVM majors at once; each case is one opt then single-threaded reference runs.
MAJORS_AT_ONCE = 2
CPUS_PER_CASE = 2
CASE_PEAK_BYTES = 3 * 1024**3  # measured: reference run-program peaks at ~2.2 GB RSS per case (Spiral, 2026-11-11)
from contracts import ROOT as R

from production_environments import descriptor, DECL


def run(command):
    with suppress(subprocess.TimeoutExpired):
        return _run(command, timeout=ENTRY_SNAPSHOT_HANG_GUARD_S)
    print(
        f"UNKNOWN: hang guard {ENTRY_SNAPSHOT_HANG_GUARD_S} s exceeded by {shlex.join(map(str, command))}",
        file=sys.stderr, flush=True,
    )
    raise SystemExit(UNKNOWN_EXIT_STATUS)


def source(region, setup, argument="0", mutation="", result=7, second=None):
    fields = [
        (0, "i32", "2"),
        (4, "i32", "1"),
        (8, "i32", "0"),
        (12, "i32", "0"),
        (16, "ptr", "%q"),
        (24, "ptr", "%fault"),
        (32, "i32", "2"),
        (36, "i32", "0"),
        (40, "ptr", "null"),
        (48, "i64", argument),
        (56, "i64", "0"),
    ]
    measure = (
        lambda prefix: "\n".join(
            f"%{prefix}{i} = call i1 @__bennett_measure(ptr %q, i64 {i})\n%{prefix}z{i} = zext i1 %{prefix}{i} to i64\n%{prefix}s{i} = shl i64 %{prefix}z{i}, {i}"
            for i in range(8)
        )
        + "\n"
        + "\n".join(
            f"%{prefix}r{i} = or i64 "
            + (f"%{prefix}s0" if i == 1 else f"%{prefix}r{i-1}")
            + f", %{prefix}s{i}"
            for i in range(1, 8)
        )
    )
    call = "call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)"
    return (
        region
        + "\ndefine i64 @top(i64 %n) {\n%q = call ptr @__bennett_qalloc(i64 0, i64 8)\n%fault = call ptr @__bennett_qalloc(i64 0, i64 4)\n%desc = alloca [64 x i8], align 8\n"
        + setup
        + "\n"
        + descriptor(fields)
        + "\n"
        + call
        + "\n"
        + measure("a")
        + "\n"
        + call
        + "\n"
        + mutation
        + "\n"
        + call
        + "\n"
        + measure("b")
        + "\n"
        + call
        + "\ncall void @__bennett_qfree(ptr %fault)\ncall void @__bennett_qfree(ptr %q)\n%r = add i64 %ar7, %br7\nret i64 %r\n}\n"
        + DECL
        + "\ndeclare i1 @__bennett_measure(ptr, i64)\ndeclare ptr @__bennett_nz_alloc(i64)\ndeclare void @__bennett_nz_free(ptr)\n"
    )


def stack_witness(body, second, fault=0, first=7):
    # These deterministic witnesses clear the observed target/fault basis bits
    # with X, so each distinct metadata state needs only one expensive replay.
    # The global/heap witnesses separately exercise oracle involution pairs.
    call = "call void @__bennett_oracle(ptr @f, ptr null, ptr @record)"
    parts = body.split(call)
    assert len(parts) == 5
    clear = lambda q, n: "\n".join(
        f"call void @__bennett_gate(i32 1, ptr %{q}, i64 {i})"
        for i in range(8)
        if n >> i & 1
    )
    return (
        parts[0]
        + call
        + parts[1]
        + clear("q", first)
        + parts[2]
        + call
        + parts[3]
        + clear("q", second)
        + "\n"
        + clear("fault", fault)
        + parts[4]
    )


def cases():
    yield "global", source(
        "@g = global i8 1\ndefine i8 @f(i64 %unused) { %v = load i8, ptr @g\n store i8 99, ptr @g\n ret i8 %v }",
        "store i8 7, ptr @g",
        mutation="store i8 11, ptr @g",
    ), [(0, 18)]
    handles = source(
        "@g = global i8 1\ndefine i8 @f(i64 %input) { %v = load i8, ptr @g\n%x = trunc i64 %input to i8\n%r = xor i8 %v, %x\nret i8 %r }",
        "%input = call ptr @__bennett_qalloc(i64 0, i64 8)\ncall void @__bennett_gate(i32 1, ptr %input, i64 0)\ncall void @__bennett_gate(i32 1, ptr %input, i64 1)\nstore i8 7, ptr @g",
        mutation="store i8 11, ptr @g\ncall void @__bennett_gate(i32 1, ptr %input, i64 0)",
    )
    handles = handles.replace("store i32 2, ptr %p6", "store i32 1, ptr %p6").replace(
        "store ptr null, ptr %p8", "store ptr %input, ptr %p8"
    )
    handles = handles.replace(
        "call void @__bennett_qfree(ptr %q)",
        "call void @__bennett_gate(i32 1, ptr %input, i64 1)\ncall void @__bennett_qfree(ptr %input)\ncall void @__bennett_qfree(ptr %q)",
    )
    yield "handle-input", handles, [(0, 13)]
    first = source(
        "@g = global i8 1\ndefine i8 @f(i64 %unused) { %v = load i8, ptr @g\nret i8 %v }",
        "store i8 7, ptr @g",
        mutation="store i8 11, ptr @g",
    )
    second = source("", "store i8 13, ptr @g", mutation="store i8 17, ptr @g")
    begin = second.index("define i64 @top")
    end = second.index("\n}\n", begin) + 3
    many = first.replace("define i64 @top", "define i64 @first") + second[
        begin:end
    ].replace("define i64 @top", "define i64 @second")
    yield "several-entries", many, [(0, {"first": 18, "second": 30})]
    yield "heap-history", source(
        "define i8 @f(ptr %p) { %v = load i8, ptr %p\n store i8 99, ptr %p\n ret i8 %v }",
        "%dead = call ptr @__bennett_nz_alloc(i64 3)\ncall void @__bennett_nz_free(ptr %dead)\n%zero = call ptr @__bennett_nz_alloc(i64 0)\n%p = call ptr @__bennett_nz_alloc(i64 %n)\nstore i8 7, ptr %p\n%addr = ptrtoint ptr %p to i64",
        "%addr",
        "store i8 11, ptr %p",
    ), [(1, 18), (5, 18)]
    address = source(
        "define i8 @f(ptr %p) { %bits = ptrtoint ptr %p to i64\n%v = trunc i64 %bits to i8\nret i8 %v }",
        "%dead = call ptr @__bennett_nz_alloc(i64 3)\ncall void @__bennett_nz_free(ptr %dead)\n%p = call ptr @__bennett_nz_alloc(i64 0)\n%addr = ptrtoint ptr %p to i64",
        "%addr",
    )
    yield "address-observation", address, [(0, 6)]
    yield "allocator-only", source(
        "define i8 @f(i64 %unused) { %p = call ptr @__bennett_nz_alloc(i64 0)\n %addr = ptrtoint ptr %p to i64\n %v = trunc i64 %addr to i8\n ret i8 %v }",
        "%p = call ptr @__bennett_nz_alloc(i64 %n)\ncall void @__bennett_nz_free(ptr %p)\n%z = call ptr @__bennett_nz_alloc(i64 0)",
        mutation="%later = call ptr @__bennett_nz_alloc(i64 2)",
    ), [(0, 6), (3, 10)]

    # Logical table, dynamic allocation, save/restore and stack adoption all cross
    # the same automatic stream as ordinary heap bytes.
    stack = source(
        "define i8 @f(ptr %p) { %v = load i8, ptr %p\n ret i8 %v }",
        "%frame = call ptr @__bennett_rt_ss_push(i64 1, i64 1)\n%p = call ptr @__bennett_rt_ss_alloca(i64 %n, i64 1)\nstore i8 7, ptr %p\n%addr = ptrtoint ptr %p to i64",
        "%addr",
        "%save = call ptr @__bennett_rt_ss_save()\n%temp = call ptr @__bennett_rt_ss_alloca(i64 1, i64 1)\ncall void @__bennett_rt_ss_restore(ptr %save)\nstore i8 11, ptr %p",
    )
    stack = "@record = global [64 x i8] zeroinitializer, align 8\n" + stack.replace(
        "%desc = alloca [64 x i8], align 8\n", ""
    ).replace("%desc", "@record")
    stack += "\ndeclare ptr @__bennett_rt_ss_push(i64, i64)\ndeclare ptr @__bennett_rt_ss_alloca(i64, i64)\ndeclare ptr @__bennett_rt_ss_save()\ndeclare void @__bennett_rt_ss_restore(ptr)\n"
    yield "logical-stack", stack_witness(stack, 11), [(3, 18)]
    popped = stack.replace(
        "%save = call ptr @__bennett_rt_ss_save()",
        "call void @__bennett_rt_ss_pop(ptr %frame)\n%save = call ptr @__bennett_rt_ss_save()",
    )
    # Keep the pop witness free of subsequent invalid stack operations. The
    # second pair must return fault 7, while the first pair observed the live 7.
    a = popped.index("call void @__bennett_rt_ss_pop(ptr %frame)")
    b = popped.index("call void @__bennett_oracle", a)
    popped = popped[:a] + "call void @__bennett_rt_ss_pop(ptr %frame)\n" + popped[b:]
    observation = "\n".join(
        f"%fc{i} = call i1 @__bennett_measure(ptr %fault, i64 {i})\n%fz{i} = zext i1 %fc{i} to i64\n%fs{i} = shl i64 %fz{i}, {8+i}"
        for i in range(4)
    )
    observation += "\n%f01 = or i64 %fs0, %fs1\n%f23 = or i64 %fs2, %fs3\n%code = or i64 %f01, %f23\n"
    p = popped.index("%br7 =")
    e = popped.index("\n", p)
    popped = popped[:e] + "\n" + observation + popped[e:]
    popped = (
        popped.replace(
            "%r = add i64 %ar7, %br7",
            "%partial = add i64 %ar7, %br7\n%r = add i64 %partial, %code",
        )
        + "\ndeclare void @__bennett_rt_ss_pop(ptr)\n"
    )
    yield "popped-frame", stack_witness(popped, 0, 7), [(1, 1799)]
    restored = popped.replace(
        "call void @__bennett_rt_ss_pop(ptr %frame)",
        "call void @__bennett_rt_ss_restore(ptr %saved)",
    )
    restored = restored.replace(
        "%p = call ptr @__bennett_rt_ss_alloca(i64 %n",
        "%saved = call ptr @__bennett_rt_ss_save()\n%p = call ptr @__bennett_rt_ss_alloca(i64 %n",
    )
    yield "restored-allocation", stack_witness(restored, 0, 7), [(1, 1799)]
    dead = source(
        "define i8 @f(ptr %p) { call void @__bennett_nz_free(ptr %p)\nret i8 7 }",
        "%p = call ptr @__bennett_nz_alloc(i64 1)\ncall void @__bennett_nz_free(ptr %p)\n%addr = ptrtoint ptr %p to i64",
        "%addr",
    )
    at = dead.index("%br7 =")
    end = dead.index("\n", at)
    dead = dead[:end] + "\n" + observation + dead[end:]
    dead = dead.replace(
        "%r = add i64 %ar7, %br7",
        "%partial = add i64 %ar7, %br7\n%r = add i64 %partial, %code",
    )
    yield "dead-entry", dead, [(0, 1792)]
    saved = source(
        "define i8 @f(i64 %expected) { %point = inttoptr i64 %expected to ptr\ncall void @__bennett_rt_ss_restore(ptr %point)\n%p = call ptr @__bennett_rt_ss_save()\n%x = ptrtoint ptr %p to i64\n%eq = icmp eq i64 %x, %expected\n%v = zext i1 %eq to i8\nret i8 %v }",
        "%frame = call ptr @__bennett_rt_ss_push(i64 1, i64 1)\n%saved = call ptr @__bennett_rt_ss_save()\n%addr = ptrtoint ptr %saved to i64",
        "%addr",
    )
    saved = "@record = global [64 x i8] zeroinitializer, align 8\n" + saved.replace(
        "%desc = alloca [64 x i8], align 8\n", ""
    ).replace("%desc", "@record")
    saved += "\ndeclare ptr @__bennett_rt_ss_push(i64, i64)\ndeclare ptr @__bennett_rt_ss_save()\ndeclare void @__bennett_rt_ss_restore(ptr)\n"
    yield "save-state", stack_witness(saved, 1, first=1), [(0, 2)]


def run_case(major, name, body, vectors):
    """One case: plugin build of its IR, then reference runs per vector. Cases share nothing on disk."""
    d = R / f".tmp/entry-snapshot/{major}/{name}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    ll = d / "input.ll"
    ll.write_text(body)
    out = d / "out"
    heap, sstack = (
        (48, 24)
        if name
        in ("logical-stack", "popped-frame", "restored-allocation", "save-state")
        else (
            (0, 0)
            if name in ("global", "handle-input", "several-entries")
            else (16, 0)
        )
    )
    z = run(
        [
            f"/usr/lib/llvm-{major}/bin/opt",
            "-load-pass-plugin=" + str(R / f"build/libbennett-plugin-{major}.so"),
            "-passes=bennett",
            "-bennett-dialect=0.2.13",
            f"-bennett-budget-default=1000000,{heap},4096,16,{sstack}",
            "-bennett-out=" + str(out),
            "-disable-output",
            ll,
        ]
    )
    row = {"name": name, "exit": z.returncode, "diagnostic": z.stderr}
    if z.returncode:
        return row
    row["check"] = True
    row["runs"] = []
    for entry in (("first", "second") if name == "several-entries" else ("top",)):
        obj = out / entry / "launch.bennett"
        c = run([DEBUG_REF, "check", obj])
        row["check"] &= c.returncode == 0
        row.setdefault("checks", {})[entry] = c.stdout + c.stderr
        tokens = json.loads((out / entry / "build.json").read_text())["budgets"]
        for n, expected in vectors:
            if isinstance(expected, dict):
                expected = expected[entry]
            z = run(
                [
                    REF,
                    "run-program",
                    obj,
                    entry,
                    "--args",
                    ",".join([str(n)] + [str(t["steps"]) for t in tokens]),
                    "--budget",
                    f"10000000,{heap},4096,16",
                ]
            )
            v = json.loads(z.stdout) if z.returncode == 0 else {}
            row["runs"].append(
                {
                    "entry": entry,
                    "n": n,
                    "result": v,
                    "error": z.stderr,
                    "ok": v.get("status") == "COMPLETED"
                    and v.get("results")
                    == [{"type": "i64", "value": str(expected)}],
                }
            )
    if name == "address-observation":
        # §8.5 expressly makes allocation-derived address observations an
        # allocator-state dependency, even when the closure has no load or alloc.
        reference = (out / "top/oracle-0/ref.bennett").read_text()
        row["complete_history_interface"] = (
            "s0:region[" in reference
            and "lift.alloc" in reference
            and "lift.free" in reference
        )
        row["check"] &= row["complete_history_interface"]
    row["ok"] = row["check"] and all(r["ok"] for r in row["runs"])
    print(name, row["ok"], flush=True)
    return row


def width(selected):
    """Cases run concurrently; both majors run at once, each reference run is single-threaded."""
    cpus = len(os.sched_getaffinity(0))
    with open("/proc/meminfo") as meminfo:
        available = next(int(l.split()[1]) * 1024 for l in meminfo if l.startswith("MemAvailable:"))
    return max(1, min(len(selected), cpus // CPUS_PER_CASE, available // (MAJORS_AT_ONCE * CASE_PEAK_BYTES)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--major", type=int, required=True)
    p.add_argument("--case", action="append")
    a = p.parse_args()
    selected = [c for c in cases() if not a.case or c[0] in a.case]
    # map() keeps the report in case order whatever order the cases finish in; a hang-guard SystemExit propagates.
    with ThreadPoolExecutor(max_workers=width(selected)) as pool:
        rows = list(pool.map(lambda c: run_case(a.major, *c), selected))
    report = {
        "major": a.major,
        "isa_ref": str(REF),
        "isa_ref_sha256": hashlib.sha256(REF.read_bytes()).hexdigest(),
        "cases": rows,
    }
    (R / f".tmp/entry-snapshot-{a.major}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
    return not all(r.get("ok") for r in rows)


if __name__ == "__main__":
    raise SystemExit(main())
