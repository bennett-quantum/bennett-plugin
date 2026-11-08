#!/usr/bin/env python3
"""PT5 bottom/operand-growth and serial function-order regression receipts.

The value oracle is elementwise bit-vector evaluation, not another scheduler.
Function-order checks compare complete named value domains; report array order,
work counters and rounds are observable separately and are retained unchanged.
"""

import argparse
import json
from pathlib import Path

from analysis_convergence import frozen_clock
from contracts import ROOT, run


LAYOUT = 'target datalayout = "e-p:64:64-i64:64-n8:16:32:64"\n'
SOURCES = {
    "bottom": "define internal i32 @source() { unreachable }",
    "one": "define internal i32 @source() { ret i32 1 }",
    "pair": """define internal i32 @source() {
 %v = select i1 true, i32 1, i32 0
 ret i32 %v
}""",
    "top": """declare i32 @external()
define internal i32 @source() {
 %v = call i32 @external()
 ret i32 %v
}""",
}


def value_domains(report):
    return {(v["function"], v["value"]): (v["top"], sorted(v["atoms"]))
            for v in report["values"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path, default=ROOT / ".tmp/analysis-monotone")
    args = parser.parse_args(argv)
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    plugin = (args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so").absolute()
    environment = frozen_clock(directory)
    receipts, failures = [], []

    def analyse(name, body):
        source, report = directory / f"{name}.ll", directory / f"{name}.json"
        source.write_text(LAYOUT + body + "\n")
        report.unlink(missing_ok=True)
        command = [f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
                   "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
                   "-bennett-analysis-max-rounds=64", f"-bennett-report={report}",
                   "-disable-output", source]
        result = run(command, env=environment)
        (directory / f"{name}.stderr").write_text(result.stderr)
        assert result.returncode == 0, (name, result.stderr)
        data = json.loads(report.read_text())
        work = data["analysis_work"]
        assert data["analysis_rounds"] == work["rounds_completed"] <= 64, data
        assert work["worklist_pops"] >= work["transfer_applications"] > 0, work
        assert work["cpu_ms"]["value"] == 0, work
        receipts.append({"case": name, "argv": list(map(str, command)), "work": work})
        return data

    def check(name, predicate, detail):
        if not predicate:
            failures.append({"case": name, "detail": repr(detail)})
            print(f"FAIL {name}: {detail}", flush=True)

    # Original three-instruction parallel-design witness, independent oracle 1 == 0.
    witness = analyse("bottom-compare", """define i1 @top() {
 %a = add i32 0, 1
 %comparison = icmp eq i32 %a, 0
 ret i1 %comparison
}""")
    check("bottom-compare", value_domains(witness)["top", "%comparison"] == (False, ["INT(0)"]),
          value_domains(witness))
    expected = [[], ["INT(0)"], ["INT(0)", "INT(1)"], ["INT(0)", "INT(1)"]]
    for side in ("left", "right"):
        previous = set()
        for index, (stage, source) in enumerate(SOURCES.items()):
            operands = "%a, 0" if side == "left" else "0, %a"
            data = analyse(f"growth-{side}-{stage}", source + f"""
define i1 @top() {{
 %a = call i32 @source()
 %comparison = icmp eq i32 {operands}
 ret i1 %comparison
}}""")
            top, atoms = value_domains(data)["top", "%comparison"]
            check(f"growth-{side}-{stage}", not top and atoms == expected[index],
                  {"expected": expected[index], "actual": [top, atoms]})
            check(f"monotone-{side}-{stage}", previous <= set(atoms),
                  {"previous": sorted(previous), "actual": atoms})
            previous = set(atoms)

    # The parallel witness delayed by a defined call exposes exactly the same
    # missing-operand state in an ordinary serial scan. Only definitions move.
    producer = "define internal i32 @one() { %a = add i32 0, 1\n ret i32 %a }\n"
    consumer = """define i1 @top() {
 %a = call i32 @one()
 %comparison = icmp eq i32 %a, 0
 ret i1 %comparison
}
"""
    reports = [analyse("order-producer-first", producer + consumer),
               analyse("order-consumer-first", consumer + producer)]
    check("function-order", value_domains(reports[0]) == value_domains(reports[1]),
          [value_domains(r)["top", "%comparison"] for r in reports])

    data = analyse("bottom-with-top", SOURCES["bottom"] + """
declare i32 @unknown()
define i1 @top() {
 %a = call i32 @source()
 %b = call i32 @unknown()
 %left = icmp eq i32 %a, %b
 %right = icmp ne i32 %b, %a
 ret i1 %left
}
""")
    for name in ("%left", "%right"):
        check("bottom-with-top-" + name, value_domains(data)["top", name] == (False, []),
              value_domains(data)["top", name])

    # With no seed, the least solution of x = (x == 0) is bottom.
    # Inflationary outer joins cannot oscillate, even with the old default.
    data = analyse("unseeded-cycle", """define internal i1 @cycle() {
entry:
 %seed = call i1 @empty()
 br label %loop
loop:
 %x = phi i1 [ %seed, %entry ], [ %comparison, %loop ]
 %comparison = icmp eq i1 %x, false
 br label %loop
}
define internal i1 @empty() { unreachable }
""")
    for name in ("%x", "%comparison"):
        check("unseeded-cycle-" + name, value_domains(data)["cycle", name] == (False, []),
              value_domains(data)["cycle", name])

    # Audit companions: PT3 unions value operands even with a bottom condition;
    # casts and integer Cartesian products have no empty-product Boolean default.
    data = analyse("copies-and-binops", SOURCES["bottom"] + """
define i32 @top() {
 %a = call i32 @source()
 %condition = trunc i32 %a to i1
 %choice = select i1 %condition, i32 7, i32 9
 %cast = zext i32 %a to i64
 %sum = add i32 %a, 1
 %product = mul i32 %a, 2
 ret i32 %choice
}
""")
    domains = value_domains(data)
    for name in ("%condition", "%cast", "%sum", "%product"):
        check("copy-" + name, domains["top", name] == (False, []), domains["top", name])
    check("select-bottom-condition", domains["top", "%choice"] == (False, ["INT(7)", "INT(9)"]), domains)

    # Missing allocation extents must not seed the entire possible address space.
    # Byte 0 of a one-byte object is zero; byte 8 has no initial-image fact.
    size = "define internal i64 @size() { %n = add i64 0, 1\n ret i64 %n }\n"
    for allocator, declaration, call in (
        ("malloc", "declare ptr @malloc(i64)", "call ptr @malloc(i64 %n)"),
        ("calloc-size", "declare ptr @calloc(i64,i64)", "call ptr @calloc(i64 1,i64 %n)"),
        ("calloc-count", "declare ptr @calloc(i64,i64)", "call ptr @calloc(i64 %n,i64 1)"),
    ):
        use = f"""define i8 @top() {{
 %n = call i64 @size()
 %p = {call}
 %inside = load i8, ptr %p
 %q = getelementptr i8, ptr %p, i64 8
 %outside = load i8, ptr %q
 ret i8 %inside
}}
"""
        pair = [analyse(f"extent-{allocator}-{order}", declaration + "\n" + body)
                for order, body in (("first", size + use), ("last", use + size))]
        for data in pair:
            domains = value_domains(data)
            check(f"extent-{allocator}", domains["top", "%inside"] == (False, ["INT(0)"])
                  and domains["top", "%outside"] == (False, []), domains)
        check(f"extent-order-{allocator}", value_domains(pair[0]) == value_domains(pair[1]),
              [value_domains(r)["top", "%outside"] for r in pair])

    data = analyse("calloc-bottom-count-top-size", """declare ptr @calloc(i64,i64)
declare i64 @unknown()
define internal i64 @empty() { unreachable }
define i8 @top() {
 %count = call i64 @empty()
 %size = call i64 @unknown()
 %p = call ptr @calloc(i64 %count, i64 %size)
 %v = load i8, ptr %p
 ret i8 %v
}
""")
    check("calloc-bottom-count-top-size", value_domains(data)["top", "%v"] == (False, []),
          value_domains(data)["top", "%v"])

    (directory / "results.json").write_text(json.dumps({"receipts": receipts, "failures": failures}, indent=2) + "\n")
    assert not failures, failures
    print(json.dumps({"major": args.major, "runs": len(receipts), "passed": True}))


if __name__ == "__main__":
    main()
