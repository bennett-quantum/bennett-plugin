#!/usr/bin/env python3
"""Mutate the real numerical suites to prove their structural checks see residue."""

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import runpy
import sys

import contracts


CASES = {
    "integer-call": ("integer_intrinsics", "integer-intrinsics", "f8_cttz"),
    "integer-vector": ("integer_intrinsics", "integer-intrinsics", "vf16_ctpop"),
    "integer-helper": ("integer_intrinsics", "integer-intrinsics", None),
    "wide-memory": ("wide", "wide", "nonbyte"),
    "memory-call": ("memory_runtime", "memory-runtime", "memmove"),
}


def mutation(source, output, name):
    # Regexes select mutations only; the verifier parses the complete LLVM module.
    if name is None:
        changed, count = re.subn(
            r"(define i1 @__bennett_rt_ctpop_i1[^\n]*\{\nentry:\n)",
            r"\1  %residual.mutation = call i8 @llvm.cttz.i8(i8 1, i1 false)\n",
            output,
            count=1,
        )
    else:
        pattern = rf"define [^\n]*@{name}\([^}}]*}}"
        raw = re.search(pattern, source)
        assert raw is not None, name
        changed, count = re.subn(pattern, lambda match: raw.group(), output)
    assert count == 1 and changed != output, (name, count)
    return changed


def check_case(major, label):
    driver, directory, name = CASES[label]
    target = contracts.ROOT / f".tmp/{directory}/{major}/out.ll"
    original_run, original_args = contracts.run_checked, sys.argv
    snapshots = []

    def intercept(command, **kwargs):
        result = original_run(command, **kwargs)
        arguments = list(map(str, command))
        if "-bennett-normalise-only" in arguments and "-o" in arguments:
            output = Path(arguments[arguments.index("-o") + 1])
            if output == target:
                memory = "byte-memory" if driver == "wide" else "values"
                contracts.validate_normalisation(major, output, memory)
                text = output.read_text()
                snapshots.append(text)
                output.write_text(mutation((output.parent / "in.ll").read_text(), text, name))
        return result

    contracts.run_checked = intercept
    sys.argv = [driver, "--major", str(major)]
    try:
        with redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(contracts.ROOT / f"tests/{driver}.py"), run_name="__main__")
            except AssertionError as error:
                expected = name or "__bennett_rt_ctpop_i1"
                assert len(snapshots) == 1 and f"normalisation residue: {expected} " in str(error), str(error)
            else:
                assert snapshots, f"{label}: no output was mutated"
                raise AssertionError(f"{label}: suite accepted residue in its real output")
    finally:
        contracts.run_checked, sys.argv = original_run, original_args
        if snapshots:
            target.write_text(snapshots[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    cases = [args.case] if args.case else CASES
    for label in cases:
        check_case(args.major, label)
    print(f"LLVM {args.major}: rejected {len(cases)}/{len(cases)} real-module mutations")


if __name__ == "__main__":
    main()
