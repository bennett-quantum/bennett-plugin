#!/usr/bin/env python3
"""N21 scalar graphs, lane facts, immutable H IR, and selected-oracle results."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import time
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
    "fneg-formats": (1, ()),
    "vector-extrema": (3, ()),
    "vector-reduce-extrema": (9, ()),
    "vector-phi": (1, (1,)),
    "vector-abi": (3, ()),
    "vector-abi-device": (3, ()),
    "vector-loop-phi": (3, ()),
    "vector-forward-block": (7, ()),
    "vector-abi-indirect": (3, ()),
    "vector-abi-recursive": (3, ()),
    "vector-abi-nested": (3, ()),
    "gep-address-space": (4294967295, ()),
    "gep-constant-expression": (8, ()),
    "vector-scalable": (3, ()),
    "vector-scalable-fixed": (9, ()),
    "vector-scalable-option": (10, ()),
    "vector-scalable-minimum": (9, ()),
    "vector-scalable-fixed-override": (9, ()),
    "vector-scalable-abi": (7, ()),
    "vector-scalable-module-order": (22, ()),
    "vector-scalable-module-order-reversed": (22, ()),
    "vector-reduce-smax": (9, ()),
    "vector-reduce-smin": (2147483648, ()),
    "vector-reduce-umax": (4294967295, ()),
    "vector-reduce-umin": (1, ()),
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
    # PT11 seeds the internal callee of the H-only top with non-handle top.
    "vector-abi": {"%r": []},
    "vector-abi-device": {"%r": ["INT(3)"]},
    "vector-scalable-fixed": {"%r": ["INT(9)"]},
    "vector-scalable-minimum": {"%r": ["INT(9)"]},
    "vector-scalable-option": {"%r": ["INT(10)"]},
    "vector-scalable-fixed-override": {"%r": ["INT(9)"]},
    "vector-scalable-abi": {"%r": []},
    "vector-scalable-module-order": {"%r": ["INT(22)"]},
    "vector-scalable-module-order-reversed": {"%r": ["INT(22)"]},
}
TOP_FACTS = {"vector-abi", "vector-scalable-abi"}


def command(args):
    override = [f"-bennett-vscale={args.vscale}"] if getattr(args, "vscale", None) else []
    return [f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={args.plugin}",
            "-passes=bennett", "-bennett-dialect=0.2.13", *override]


def checked(argv, args, **kwargs):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    state = "COMPLETE"
    try:
        result = run(argv, timeout=args.guard_seconds, **kwargs)
        state = "COMPLETE" if result.returncode == 0 else "FAILED"
    except subprocess.TimeoutExpired:
        state = "UNKNOWN/TIMEOUT"
        raise SystemExit(124)
    finally:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        args.output.mkdir(parents=True, exist_ok=True)
        receipt = dict(argv=list(map(str, argv)), wall_seconds=time.monotonic() - started,
                       cpu_seconds=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
                       state=state, exit=124 if state == "UNKNOWN/TIMEOUT" else result.returncode)
        with (args.output / f"commands-{args.major}.jsonl").open("a") as file:
            file.write(json.dumps(receipt) + "\n")
    assert result.returncode == 0, (list(map(str, argv)), result.returncode, result.stderr)
    return result


def canonical(args, source):
    return checked([f"/usr/lib/llvm-{args.major}/bin/opt", "-S", source, "-o", "-"], args).stdout


def functions(text):
    return dict(re.findall(r"^define [^@\n]*@([^ (]+)[^{]*\{(.*?)^}", text, re.M | re.S))


def normalise(args, name, dest):
    args.vscale = 3 if name in ("vector-scalable-option", "vector-scalable-fixed-override") else None
    source, output = FIXTURES / (name + ".ll"), dest / "scalar.ll"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    checked([*command(args), "-bennett-normalise-only", "-S", source, "-o", output], args)
    device = output
    if name == "vector-abi-indirect":
        # The address-taken source function retains its host vector ABI. Validate
        # the device graph independently with that H wrapper declared only.
        device = dest / "device.ll"
        text, count = re.subn(r"define internal <2 x i32> @identity\(<2 x i32> %v\)[^{]*\{.*?^}",
                              "declare <2 x i32> @identity(<2 x i32>)", output.read_text(), flags=re.S | re.M)
        assert count == 1 and "@identity.nz(" in text, text
        device.write_text(text)
    if name == "vector-abi-device":
        device = dest / "device.ll"
        text, count = re.subn(r"define void @launch\(\)[^{]*\{.*?^}",
                              "declare void @launch()", output.read_text(), flags=re.S | re.M)
        assert count == 1, text
        device.write_text(text)
    checked([*command(args), "-bennett-validate-only", "-disable-output", device], args)
    assert before == hashlib.sha256(source.read_bytes()).hexdigest(), "source fixture changed"
    body = "\n".join(functions(device.read_text()).values())
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
             "-bennett-scalar-stack=256", "-bennett-out=" + str(output), "-S", source, "-o", h], args)
    # Compare actual in-memory H functions emitted after production with plain LLVM.
    assert h.read_text() == canonical(args, source), "production mutated H module"
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/debug/bennett-isa-ref"
    for values, want in [(inputs, expected), *((((0,), 5),) if name == "vector-phi" else ())]:
        result = checked([ref, "run-oracle", output / "ref.bennett", "ref", "--input",
                          ",".join(map(str, values)), "--budget", "1000000,0,256,64"], args)
        data = json.loads(result.stdout)
        assert (data["code"], int(data["payload"])) == (0, want), (name, values, want, data)
    if name.startswith("vector-scalable-module-order"):
        library = dest / "native.so"
        checked([f"/usr/lib/llvm-{args.major}/bin/clang", "-O0", "-shared", "-fPIC", source, "-o", library], args)
        native = ctypes.CDLL(str(library.absolute()))
        native.top.restype = ctypes.c_uint32
        assert native.top() == expected, "link vscale changed with function order"
    checked([ref, "step-check", output / "ref.bennett", "ref", "--exhaustive", "--max-bits", "1",
             "--budget", "1000000,0,256,64"], args)
    if name.startswith("fneg-"):
        ir = checked([f"/usr/lib/llvm-{args.major}/bin/llvm-dis", output / "materialised.bc", "-o", "-"], args).stdout
        assert "fneg " not in ir, ir
    return dict(expected=expected, inputs=inputs)


def facts(args, source, dest, label):
    path = dest / (label + ".json")
    h = dest / (label + ".ll")
    checked([*command(args), "-bennett-analysis-only", "-bennett-report=" + str(path),
             "-S", source, "-o", h], args)
    assert h.read_text() == canonical(args, source), "S2 mutated H module"
    return {v["value"]: (v["top"], set(v["atoms"])) for v in json.loads(path.read_text())["values"] if v["function"] == "top"}


def scalar_fact_name(value, explicit, scalar):
    if value in explicit:
        return value
    if value in ("%p0", "%p1"):
        return "%nz.l" + value[-1] + ".p"
    returned = re.search(r"ret i\d+ (%[-.\w]+)", functions(scalar.read_text())["top"])
    assert returned, ("missing scalar return", scalar.read_text())
    return returned[1]


def check_case(args, name):
    dest = args.output / str(args.major) / name
    dest.mkdir(parents=True, exist_ok=True)
    source, scalar = normalise(args, name, dest)
    if args.mode == "oracle":
        return oracle(args, scalar, name, dest)
    if args.mode == "production":
        return oracle(args, source, name, dest)
    if args.mode in ("analysis", "scalar-analysis"):
        explicit = facts(args, scalar, dest, "explicit")
        virtual = facts(args, source, dest, "virtual") if args.mode == "analysis" else None
        for value, want in FACTS.get(name, {}).items():
            scalar_value = scalar_fact_name(value, explicit, scalar)
            assert scalar_value in explicit, (name, value, scalar_value, explicit)
            expected = (name in TOP_FACTS, set(want))
            assert explicit[scalar_value] == expected, (name, value, expected, explicit[scalar_value])
        if args.mode == "analysis":
            for value, want in FACTS.get(name, {}).items():
                assert value in virtual, (name, value, virtual)
                expected = (name in TOP_FACTS, set(want))
                assert virtual[value] == expected, (name, value, expected, virtual[value])
                assert explicit[scalar_fact_name(value, explicit, scalar)] == virtual[value]
        return {"checked_scalar_facts": sorted(FACTS.get(name, {}))}
    return {"scalarised": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--mode", choices=("normalise", "oracle", "analysis", "scalar-analysis", "production"), default="normalise")
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
