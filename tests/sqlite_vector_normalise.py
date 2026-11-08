#!/usr/bin/env python3
"""N21 scalar graphs, lane facts, immutable H IR, and selected-oracle results."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from contracts import ROOT, run, sibling

FIXTURES = ROOT / "tests/fixtures/sqlite_vector"
# Results follow integer pointer strides, IEEE sign masks, or signed max by hand.
CASES = {
    "gep-scalar-base-vector-index": (8, ()),
    "gep-vector-base-scalar-index": (8, ()),
    "gep-vector-base-vector-index": (16, ()),
    "gep-index-wrap-high-bits": (8589934591, ()),
    "fneg-carriers": (2147483648, ()),
    "fneg-nan-payload": (9205677896870470469, ()),
    "vector-extrema": (3, ()),
    "vector-reduce-extrema": (9, ()),
    "vector-phi": (1, (1,)),
    "vector-abi": (3, ()),
}
FACTS = {
    "gep-scalar-base-vector-index": {"%p0": ["PTR(@buf,4,0)"], "%p1": ["PTR(@buf,12,0)"]},
    "gep-vector-base-scalar-index": {"%p0": ["PTR(@buf,4,0)"], "%p1": ["PTR(@buf,12,0)"]},
    "gep-vector-base-vector-index": {"%p0": ["PTR(@buf,4,0)"], "%p1": ["PTR(@buf,20,0)"]},
    "fneg-carriers": {"%r": ["INT(2147483648)"]},
    "fneg-nan-payload": {"%r": ["INT(9205677896870470469)"]},
    "vector-extrema": {"%r": ["INT(1)", "INT(3)"]},
    "vector-reduce-extrema": {"%r": ["INT(1)", "INT(9)"]},
    "vector-phi": {"%r": ["INT(1)", "INT(5)"]},
    "vector-abi": {"%r": ["INT(3)"]},
}


def command(args):
    return [f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={args.plugin}",
            "-passes=bennett", "-bennett-dialect=0.2.13"]


def checked(argv, args, **kwargs):
    result = run(argv, timeout=args.guard_seconds, **kwargs)
    assert result.returncode == 0, (list(map(str, argv)), result.returncode, result.stderr)
    return result


def canonical(args, source):
    return checked([f"/usr/lib/llvm-{args.major}/bin/opt", "-S", source, "-o", "-"], args).stdout


def functions(text):
    return dict(re.findall(r"^define [^@\n]*@([^ (]+)[^{]*\{(.*?)^}", text, re.M | re.S))


def normalise(args, name, dest):
    source, output = FIXTURES / (name + ".ll"), dest / "scalar.ll"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    checked([*command(args), "-bennett-normalise-only", "-S", source, "-o", output], args)
    checked([*command(args), "-bennett-validate-only", "-disable-output", output], args)
    assert before == hashlib.sha256(source.read_bytes()).hexdigest(), "source fixture changed"
    body = "\n".join(functions(output.read_text()).values())
    assert not re.search(r"<(?:vscale x )?\d+ x ", body), body
    if name.startswith("gep-"):
        assert len(re.findall(r" = getelementptr ", body)) >= 2, body
    if name.startswith("fneg-"):
        assert len(re.findall(r" = fneg float ", body)) == 2, body
    if name == "vector-phi":
        assert len(re.findall(r" = phi i32 ", body)) == 2, body
    if name == "vector-reduce-extrema":
        assert "icmp sgt i32 1, 9" in body and "select i1" in body, body
    if name == "vector-abi":
        assert re.search(r"define internal \{ i32, i32 \} @identity\(i32 .*i32 ", output.read_text()), output.read_text()
    return source, output


def oracle(args, source, name, dest):
    expected, inputs = CASES[name]
    output = dest / "oracle"
    output.mkdir(exist_ok=True)
    h = dest / "host.ll"
    width = 64 if name.startswith(("gep-", "fneg-")) else 32
    shape = ",".join("IN(1,zext)" for _ in inputs) + f";tgt={width}"
    checked([*command(args), "-bennett-oracle=top", "-bennett-scalar-shape=" + shape,
             "-bennett-out=" + str(output), "-S", source, "-o", h], args)
    # Compare actual in-memory H functions emitted after production with plain LLVM.
    assert functions(h.read_text()) == functions(canonical(args, source)), "production mutated H IR"
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/debug/bennett-isa-ref"
    for values, want in [(inputs, expected), *((((0,), 5),) if name == "vector-phi" else ())]:
        result = checked([ref, "run-oracle", output / "ref.bennett", "ref", "--input",
                          ",".join(map(str, values)), "--budget", "1000000,0,65536,64"], args)
        data = json.loads(result.stdout)
        assert (data["code"], data["payload"]) == (0, want), (name, values, want, data)
    if name.startswith("fneg-"):
        ir = checked([f"/usr/lib/llvm-{args.major}/bin/llvm-dis", output / "materialised.bc", "-o", "-"], args).stdout
        assert "fneg " not in ir, ir
    return dict(expected=expected, inputs=inputs)


def facts(args, source, dest, label):
    path = dest / (label + ".json")
    h = dest / (label + ".ll")
    checked([*command(args), "-bennett-analysis-only", "-bennett-report=" + str(path),
             "-S", source, "-o", h], args)
    assert functions(h.read_text()) == functions(canonical(args, source)), "S2 mutated H IR"
    return {v["value"]: (v["top"], set(v["atoms"])) for v in json.loads(path.read_text())["values"] if v["function"] == "top"}


def check_case(args, name):
    dest = args.output / str(args.major) / name
    dest.mkdir(parents=True, exist_ok=True)
    source, scalar = normalise(args, name, dest)
    if args.mode == "oracle":
        return oracle(args, scalar, name, dest)
    if args.mode == "production":
        return oracle(args, source, name, dest)
    if args.mode == "analysis":
        virtual, explicit = facts(args, source, dest, "virtual"), facts(args, scalar, dest, "explicit")
        for value, want in FACTS.get(name, {}).items():
            assert value in virtual, (name, value, virtual)
            assert virtual[value] == (False, set(want)), (name, value, want, virtual[value])
            # Extraction is lane renaming; its named scalar producer may be absent.
            if value in explicit:
                assert explicit[value] == virtual[value], (name, value, virtual[value], explicit[value])
        return {"equivalent_named_facts": sorted(FACTS.get(name, {}))}
    return {"scalarised": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--mode", choices=("normalise", "oracle", "analysis", "production"), default="normalise")
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp/sqlite-vector")
    parser.add_argument("--guard-table", type=Path, required=True)
    args = parser.parse_args()
    import tomllib
    table = tomllib.loads(args.guard_table.read_text())
    args.guard_seconds = table["classes"]["moderate"]["seconds"] * table["machine_config_factor"]
    args.plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    rows = []
    for name in args.case or CASES:
        try:
            result = check_case(args, name)
        except AssertionError as error:
            rows.append(dict(case=name, ok=False, error=str(error)))
        else:
            rows.append(dict(case=name, ok=True, result=result))
    dest = args.output / str(args.major)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / (args.mode + ".json")).write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    return int(any(not row["ok"] for row in rows))


if __name__ == "__main__":
    sys.exit(main())
