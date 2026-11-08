#!/usr/bin/env python3
"""Vector FP binaries retain lane bindings in the scalar published N32 graph."""

import argparse
import ctypes
import json
from pathlib import Path
import re
import tomllib

from contracts import ROOT, arith_path
from sqlite_vector_normalise import checked, command, functions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--major", type=int, required=True, choices=(18, 23))
    p.add_argument("--plugin", type=Path, required=True)
    p.add_argument("--guard-table", type=Path, required=True)
    p.add_argument("--output", type=Path, default=ROOT / ".tmp/sqlite-vector-fp")
    a = p.parse_args()
    table = tomllib.loads(a.guard_table.read_text())
    a.guard_seconds = table["classes"]["moderate"]["seconds"] * table["machine_config_factor"]
    a.output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/fixtures/sqlite_vector" / f"vector-fadd-layout-{a.major}.ll"
    output = a.output / f"fadd-{a.major}.ll"
    checked([*command(a), "-bennett-normalise-only", "-S", source, "-o", output], a)
    body = functions(output.read_text())["top"]
    assert "fadd " not in body and not re.search(r"<\d+ x ", body), body
    calls = re.findall(r"call i32 @__bennett_sf_add_f32\(i32 (%[-.\w]+), i32 (%[-.\w]+)\)", body)
    bitcasts = dict(re.findall(r"(%[-.\w]+) = bitcast float ([^ ]+) to i32", body))
    lanes = [(bitcasts[left], bitcasts[right]) for left, right in calls]
    # Exact source lanes (1+2, 2+4), without host FP evaluation of the operation.
    assert lanes == [("1.000000e+00", "2.000000e+00"), ("2.000000e+00", "4.000000e+00")], body
    published = a.output / f"arith-{a.major}.ll"
    checked([f"/usr/lib/llvm-{a.major}/bin/llvm-dis", arith_path(a.major), "-o", published], a)
    assert re.search(r"define[^\n]* i32 @__bennett_sf_add_f32\(i32[^\n]*i32", published.read_text()), "missing pinned arithmetic definition"
    linked = a.output / f"linked-{a.major}.ll"
    checked([f"/usr/lib/llvm-{a.major}/bin/llvm-link", output, arith_path(a.major), ROOT / "tests/fixtures/sqlite_vector/fp-environment.ll", "-S", "-o", linked], a)
    assert re.search(r"define[^\n]* i32 @__bennett_sf_add_f32\(", linked.read_text()), "N32 helper did not link"
    library = a.output / f"fadd-{a.major}.so"
    checked([f"/usr/lib/llvm-{a.major}/bin/clang", "-shared", "-fPIC", linked, "-o", library], a)
    native = ctypes.CDLL(str(library.absolute()))
    native.top.restype = ctypes.c_uint64
    assert native.top() == 4665729215033769984, "linked scalar arithmetic changed the packed result"
    result = dict(major=a.major, scalar_lane_inputs=lanes, published_helper_linked=True,
                  expected_concrete_carriers=[1077936128, 1086324736], concrete_packed=4665729215033769984)
    # Concrete expected values describe 3.0 and 6.0, not a demand that the
    # prescribed flow-insensitive linked graph has singleton abstract facts.
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
