#!/usr/bin/env python3
"""PT5 numerical/provenance unions and conditional standalone AV reports."""

import argparse
import json
from pathlib import Path

from analysis_monotone import LAYOUT, value_domains
from contracts import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    failures, receipts = [], []

    def check(name, passed, detail):
        if not passed:
            failures.append({"case": name, "detail": detail})
            print(f"FAIL {name}: {detail}", flush=True)

    def analyse(name, body):
        source, report = directory / (name + ".ll"), directory / (name + ".json")
        source.write_text(LAYOUT + body)
        command = [f"/usr/lib/llvm-{args.major}/bin/opt",
                   f"-load-pass-plugin={args.plugin.absolute()}", "-passes=bennett",
                   "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                   f"-bennett-report={report}", "-disable-output", source]
        result = run(command)
        (directory / (name + ".stderr")).write_text(result.stderr)
        assert result.returncode == 0, (name, result.stderr)
        receipts.append({"case": name, "argv": list(map(str, command))})
        return json.loads(report.read_text()), result.stderr

    # The fixed reference fallback for a pointer arithmetic operand is the
    # union TOP + originating object(*) + EXT(*), independently of numeric TOP.
    pointer_image = (True, ["PTR(@cell,0,-1)", "PTR(EXT,0,-1)"])
    for opcode in ("and", "urem", "mul", "add", "sub", "icmp eq"):
        for side in ("left", "right"):
            stages = {}
            for stage, alternative in (("pointer", "%address"), ("mixed", "%unknown")):
                left, right = ("%input", "15") if side == "left" else ("15", "%input")
                data, _ = analyse(f"{opcode.replace(' ', '-')}-{side}-{stage}", f"""
@cell = global i8 0
declare i64 @external()
define i64 @top() {{
 %address = ptrtoint ptr @cell to i64
 %unknown = call i64 @external()
 %input = select i1 true, i64 %address, i64 {alternative}
 %result = {opcode} i64 {left}, {right}
 ret i64 0
}}
""")
                stages[stage] = value_domains(data)["top", "%result"]
                # Add/sub by finite INT use modular displacement instead of
                # the conservative fallback; growth must still preserve them.
                if opcode not in ("add", "sub") or (opcode == "sub" and side == "right"):
                    check(f"{opcode}-{side}-{stage}", stages[stage] == pointer_image,
                          {"expected": pointer_image, "actual": stages[stage]})
            # Adding numeric alternatives to the pointer input cannot erase
            # its exact displacement by the still-finite opposing operand.
            expected = pointer_image
            if opcode == "add" or (opcode == "sub" and side == "left"):
                displacement = -15 if opcode == "sub" else 15
                expected = (True, [f"PTR(@cell,{displacement},0)", "PTR(EXT,0,-1)"])
            check(f"growth-{opcode}-{side}", stages["mixed"] == expected, stages)

    # Reordering a backedge must preserve the complete AV map, including the
    # pointer contribution to an ICmp with a TOP-only opposing operand.
    blocks = {
        "entry": "%x = ptrtoint ptr @cell to i64\n br label %loop",
        "loop": "%y = phi i64 [0, %entry], [%z, %back]\n %c = icmp eq i64 %x, %y\n br label %back",
        "back": "%z = call i64 @external()\n br label %loop",
    }
    orders = []
    for name, order in (("forward", ("entry", "loop", "back")),
                        ("back-first", ("entry", "back", "loop"))):
        body = "\n".join(b + ":\n " + blocks[b] for b in order)
        data, _ = analyse(name, "@cell = global i8 0\ndeclare i64 @external()\n"
                          + "define void @top() {\n" + body + "\n}\n")
        orders.append(value_domains(data))
    check("icmp-block-order", orders[0] == orders[1],
          [r["top", "%c"] for r in orders])
    for domains in orders:
        check("icmp-top-pointer", domains["top", "%c"] == pointer_image,
              domains["top", "%c"])

    # Numeric TOP masks/remainders stay exact; no coarsening to repair provenance.
    data, _ = analyse("numeric", """
declare i64 @external()
define i64 @top() {
 %x = call i64 @external()
 %mask = and i64 %x, 5
 %rem = urem i64 %x, 3
 ret i64 %mask
}
""")
    for name, numbers in (("%mask", [0, 1, 4, 5]), ("%rem", [0, 1, 2])):
        expected = (False, [f"INT({n})" for n in numbers])
        check("numeric-" + name, value_domains(data)["top", name] == expected,
              value_domains(data)["top", name])

    # A later null store is the only modeled source in an incomplete unit.
    # A valid linked entry state can still make the comparison false. The
    # report must carry the unresolved premise, never claim unreachability.
    external = """@environment = external global ptr
define i1 @clear() {
 %p = load ptr, ptr @environment
 %isnull = icmp eq ptr %p, null
 store ptr null, ptr @environment
 ret i1 %isnull
}
"""
    data, stderr = analyse("external-state", external)
    check("conditional-value", value_domains(data)["clear", "%isnull"] == (False, ["INT(1)"]),
          value_domains(data)["clear", "%isnull"])
    premise = data.get("value_premise", {})
    check("external-state-premise",
          premise.get("status") == "conditional"
          and premise.get("concrete_unreachability") == "not-established"
          and premise.get("external_globals") == ["@environment"]
          and premise.get("applies_to") == "all values"
          and bool(premise.get("requires")), premise)
    check("audible-premise", "conditional AVs" in stderr, stderr)
    support = directory / "external-support.ll"
    support.write_text(LAYOUT + """
@storage = global i8 7
@environment = global ptr @storage
declare i1 @clear()
define i32 @main() {
 %observed = call i1 @clear()
 %status = zext i1 %observed to i32
 ret i32 %status
}
""")
    executable = directory / "external-state"
    compiled = run([f"/usr/lib/llvm-{args.major}/bin/clang", "-O0",
                    directory / "external-state.ll", support, "-o", executable])
    assert compiled.returncode == 0, compiled.stderr
    executed = run([executable])
    check("excluded-value-executes", executed.returncode == 0, executed.stderr)

    data, _ = analyse("callback", """
define i32 @invoke(ptr %callback) {
 %r = call i32 %callback()
 ret i32 %r
}
""")
    premise = data.get("value_premise", {})
    check("callback-premise", premise.get("indirect_calls") == [
        {"function": "invoke", "value": "%r", "candidates": []}], premise)
    (directory / "results.json").write_text(json.dumps(
        {"receipts": receipts, "failures": failures}, indent=2) + "\n")
    assert not failures, failures
    print(json.dumps({"major": args.major, "runs": len(receipts), "passed": True}))


if __name__ == "__main__":
    main()
