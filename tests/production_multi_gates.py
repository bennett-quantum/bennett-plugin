#!/usr/bin/env python3
"""CC multiwire markers: exhaustive basis states, alias checks and exact phase."""

import argparse
import json
from itertools import product
from contracts import ROOT, dialect_blob, plugin_command, run, sibling


def source(arity, separate, phase=False):
    if separate == "selected":
        return '''#include "bennett_markers.h"
unsigned top(unsigned state, unsigned op, unsigned long long i,
             unsigned long long j, unsigned long long k) {
 void *a=__bennett_qalloc(0,3), *b=__bennett_qalloc(0,5);
 void *chosen=state ? a : b;
 __bennett_gate(1,a,0);
 __bennett_gate2(op,a,i,chosen,j);
 unsigned r=__bennett_measure(b,0);
 __bennett_gate2(op,a,i,chosen,j);
 __bennett_gate(1,a,0);
 __bennett_qfree(a); __bennett_qfree(b);
 return r;
}
'''
    handles = [f"q{j}" if separate else "q0" for j in range(arity)]
    count = arity if separate else 1
    allocate = "".join(f"void *q{j}=__bennett_qalloc(0,3);" for j in range(count))
    free = "".join(f"__bennett_qfree(q{j});" for j in range(count))
    wire = [f"{handles[j]},{0 if separate else j}" for j in range(arity)]
    # All dynamic indices and opcodes reach the actual marker dispatch.
    args = ",".join(f"{handles[j]},{'ijk'[j]}" for j in range(arity))
    marker = f"__bennett_gate{arity}(op,{args});"
    prepare = "".join(f"if (state & {1 << j}) __bennett_gate(1,{w});" for j, w in enumerate(wire))
    measure = "".join(f"r |= (unsigned)__bennett_measure({w}) << {j};" for j, w in enumerate(wire))
    if phase:
        # CCX fixes |+++> exactly; H-conjugation exposes relative phases.
        # Conjugating CZ on the first wire flips it when the second is |1>.
        if arity == 2:
            flip = f"__bennett_gate(1,{wire[1]});"
            hadamard = f"__bennett_gate(2,{wire[0]});"
            forward = flip + hadamard + marker + hadamard
            backward = hadamard + marker + hadamard + flip
        else:
            prepare = "".join(f"__bennett_gate(2,{w});" for w in wire)
            forward = backward = prepare + marker + prepare
    else:
        forward, backward = prepare + marker, marker + prepare
    return f'''#include "bennett_markers.h"
unsigned top(unsigned state, unsigned op, unsigned long long i,
             unsigned long long j, unsigned long long k) {{
 {allocate}
 {forward}
 unsigned r=0; {measure}
 {backward}
 {free}
 return r;
}}
'''


def expected(state, op, arity):
    if arity == 3:
        return state ^ (4 if state & 3 == 3 else 0)
    if op == 1:
        return state ^ (2 if state & 1 else 0)
    if op == 2:
        return state
    return ((state & 1) << 1) | ((state & 2) >> 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True)
    parser.add_argument("--profile", choices=("legacy", "r", "both"), default="both")
    args = parser.parse_args()
    root = ROOT / f".tmp/production-multi-gates/{args.major}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bennett_markers.h").write_text(dialect_blob("spec/bennett_markers.h"))
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    report = []
    profiles = ("legacy", "r") if args.profile == "both" else (args.profile,)
    for profile, (arity, separate, phase) in product(profiles, [(2, False, False), (2, True, False),
                                    (3, False, False), (3, True, False),
                                    (2, False, True), (3, False, True),
                                    (2, "selected", False)]):
        name = profile + f"-g{arity}-{'selected' if separate == 'selected' else 'split' if separate else 'same'}-{'phase' if phase else 'basis'}"
        directory = root / name
        directory.mkdir(exist_ok=True)
        src, ll = directory / "input.c", directory / "input.ll"
        src.write_text(source(arity, separate, phase).replace('"bennett_markers.h"', '"../bennett_markers.h"'))
        cc = run([f"/usr/lib/llvm-{args.major}/bin/clang", "-O1", "-S", "-emit-llvm", src, "-o", ll])
        assert cc.returncode == 0, cc.stderr
        command = plugin_command(args.major)
        if profile == "r":
            command = [v for v in command if not v.startswith("-bennett-dialect=")]
            command += ["-bennett-dialect=0.3-r1", "-bennett-isa=0.9"]
        lower = run([*command, "-bennett-out=" + str(directory / "out"), "-disable-output", ll])
        row = {"case": name, "lower_exit": lower.returncode, "diagnostic": lower.stderr, "runs": []}
        report.append(row)
        if lower.returncode:
            continue
        obj = directory / "out/top/launch.bennett"
        check = run([ref, "check", obj])
        row["check"] = check.returncode == 0
        row["check_output"] = check.stdout + check.stderr
        if check.returncode:
            continue
        ops = [2 if arity == 2 else 1] if phase else range(1, 4 if arity == 2 else 2)
        for op in ops:
            for state in [0] if phase else range(2 if separate == "selected" else 1 << arity):
                indices = ([0, 1 if state else 0, 0] if separate == "selected"
                           else [0, 0, 0] if separate else [0, 1, 2])
                invocation = [state, op, *indices]
                z = run([ref, "run-program", obj, "top", "--args", ",".join(map(str, invocation)), "--budget", "100000,0,0,0", "--draws", ",".join(["0.999999"] * arity)])
                value = json.loads(z.stdout) if z.returncode == 0 else {}
                want = ((0 if state or op == 2 else 1) if separate == "selected"
                        else (3 if arity == 2 else 0) if phase else expected(state, op, arity))
                row["runs"].append({"args": invocation, "exit": z.returncode, "diagnostic": z.stderr,
                                    "result": value, "ok": value.get("status") == "COMPLETED"
                                    and value.get("run_state") == "CLOSED"
                                    and value.get("results") == [{"type": "i32", "value": str(want)}]})
        # Each runtime check must fail rather than silently running a gate.
        if not phase:
            bads = [(0, 0, [0, 0, 0] if separate else [0, 1, 2]),
                    (0, 1, [3, 0, 0] if separate else [3, 1, 2])]
            if not separate:
                bads.append((0, 1, [0, 0, 2]))
                if arity == 3:
                    bads += [(0, 1, [0, 1, 0]), (0, 1, [0, 1, 1])]
            if separate == "selected":
                bads += [(1, 1, [0, 0, 0]), (0, 1, [0, 5, 0])]
            for state, op, indices in bads:
                invocation = [state, op, *indices]
                z = run([ref, "run-program", obj, "top", "--args", ",".join(map(str, invocation)), "--budget", "100000,0,0,0", "--draws", ",".join(["0.999999"] * arity)])
                value = json.loads(z.stdout) if z.returncode == 0 else {}
                row["runs"].append({"args": invocation, "exit": z.returncode, "result": value,
                                    "ok": value.get("status") == "FAILED" and any(int(f["code"]) == 4 for f in value.get("faults", []))})
        row["ok"] = row["check"] and all(r["ok"] for r in row["runs"])
    result = {"major": args.major, "profile": args.profile, "cases": report, "passed": sum(r.get("ok", False) for r in report)}
    (root / (args.profile + "-report.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result["passed"] != len(report)


if __name__ == "__main__":
    raise SystemExit(main())
