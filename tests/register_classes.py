#!/usr/bin/env python3
"""Execute configured-class allocations against independent target class tables."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path

from contracts import ROOT, sibling, plugin_command, run_checked as run


@dataclass(frozen=True)
class AllocationCase:
    name: str
    operand: str
    inputs: tuple[int, ...]
    targets: tuple[str, ...]
    references: frozenset[str]
    invalid: tuple[int, ...] = ()


CASES = (
    AllocationCase("any", "0", (0,), ("alpha",), frozenset({"any"})),
    AllocationCase("alpha", "1", (1,), ("alpha",), frozenset({"any", "alpha"})),
    AllocationCase("beta", "2", (2,), ("beta",), frozenset({"any", "beta"})),
    AllocationCase(
        "dynamic",
        "%class",
        (0, 1, 2),
        ("alpha", "beta"),
        frozenset({"any", "alpha", "beta"}),
        (3, (1 << 64) - 1),
    ),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument(
        "--promised-target-bp-ace",
        dest="promised_target",
        action="store_true",
        help="Target-aware native execution pending in the pinned executor",
    )
    args = parser.parse_args()
    work = ROOT / f".tmp/register-classes/{args.major}"
    work.mkdir(parents=True, exist_ok=True)
    command = plugin_command(args.major)
    if args.plugin:
        command[1] = "-load-pass-plugin=" + str(args.plugin)
    reference = (
        sibling("bennett-isa-spec")
        / "reference-interpreter/target/debug/bennett-isa-ref"
    )
    target_template = json.loads(
        (sibling("bennett-targets") / "targets/ideal-all-to-all.json").read_text()
    )
    body = """target datalayout = "e-p:64:64"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
declare i1 @__bennett_measure(ptr, i64)
define i1 @top(i64 %class) {
 %q = call ptr @__bennett_qalloc(i64 CLASS, i64 1)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 %bit = call i1 @__bennett_measure(ptr %q, i64 0)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_qfree(ptr %q)
 ret i1 %bit
}
!llvm.module.flags = !{!0}
!0 = !{i32 6, !"bennett.classes", !1}
!1 = !{!"alpha", !"beta"}
"""

    for case in CASES:
        directory = work / case.name
        directory.mkdir(exist_ok=True)
        source = directory / "input.ll"
        source.write_text(body.replace("CLASS", case.operand))
        run([*command, "-bennett-out=" + str(directory), "-disable-output", source])
        obj = directory / "top/launch.bennett"
        run([reference, "check", obj])
        # ISA §3.3 references are names from the 1-based link table. Measurement
        # introduces a separate class-any temporary. These expectations follow
        # the source table, independently of the compiler's output.
        allocations = [
            line.split()[3]
            for line in obj.read_text().splitlines()
            if len(line.split()) == 5 and line.split()[2] == "qreg.new"
        ]
        assert set(allocations) == case.references, (allocations, case.references)
        harness = directory / "main.c"
        harness.write_text(
            "#include <stdbool.h>\n#include <stdlib.h>\n"
            "extern bool top(unsigned long long);\n"
            "int main(int argc, char **argv) { return top(strtoull(argv[1],0,10)) ? 0 : 1; }\n"
        )
        library = sibling("bennett-vm") / "target/debug"
        executable = directory / "classes"
        run(
            [
                f"/usr/lib/llvm-{args.major}/bin/clang",
                directory / "host.bc",
                harness,
                "-L" + str(library),
                "-Wl,-rpath," + str(library),
                "-lbennett_vm",
                "-o",
                executable,
            ]
        )
        target = dict(
            target_template,
            classes={name: target_template["classes"]["data"] for name in case.targets},
        )
        for index in case.inputs:
            if args.promised_target:
                run(
                    [executable, str(index)],
                    env=dict(os.environ, BENNETT_TARGET=json.dumps(target)),
                )
            result = json.loads(
                run(
                    [
                        reference,
                        "run-program",
                        obj,
                        "top",
                        "--args",
                        str(index),
                        "--budget",
                        "1000,0,0,0",
                    ]
                ).stdout
            )
            assert result["status"] == "COMPLETED", result
            assert result["results"] == [{"type": "i1", "value": "1"}], result
        for index in case.invalid:
            invalid = json.loads(
                run(
                    [
                        reference,
                        "run-program",
                        obj,
                        "top",
                        "--args",
                        str(index),
                        "--budget",
                        "1000,0,0,0",
                    ]
                ).stdout
            )
            assert invalid["status"] == "FAILED", invalid
    print(f"LLVM {args.major}: configured constant and runtime classes passed")


if __name__ == "__main__":
    main()
