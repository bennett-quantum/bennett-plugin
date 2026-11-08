#!/usr/bin/env python3
"""N21 keeps native symbols behind explicit scalar device adapters."""

import argparse
import ctypes
import json
from pathlib import Path
import re
import tomllib

from contracts import ROOT
from sqlite_vector_normalise import checked, command, functions, oracle


def check_case(args, name):
    source = ROOT / "tests/fixtures/sqlite_vector" / (name + ".ll")
    dest = args.output / str(args.major) / name
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / "scalar.ll"
    checked([*command(args), "-bennett-normalise-only", "-S", source, "-o", output], args)
    text = output.read_text()
    symbol = "external" if name == "vector-external" else "identity"
    assert re.search(r"(?:define|declare) <2 x i32> @" + symbol + r"\(<2 x i32>", text), text
    assert re.search(r"define internal \{ i32, i32 \} @" + symbol + r"\.nz\(i32", text), text
    assert "bennett.n21.boundary" in text, text
    assert not re.search(r"<\d+ x ", functions(text)["top"]), text
    if name == "vector-callback":
        assert "@check(ptr @identity)" in functions(text)["top"], text
    else:
        assert "@" + symbol + ".nz(" in functions(text)["top"], text
    # Applying the existing module-ABI entry point again must not build adapters
    # for its own host boundary or change recursive device candidate identities.
    second = dest / "twice.ll"
    checked([*command(args), "-bennett-normalise-only", "-S", output, "-o", second], args)
    assert functions(second.read_text()) == functions(text), second.read_text()
    library = dest / "native.so"
    additional = [] if name == "vector-boundary" else [ROOT / "tests/fixtures/sqlite_vector" / (name + "-body.ll")]
    checked([f"/usr/lib/llvm-{args.major}/bin/clang", "-shared", "-fPIC", output, *additional, "-o", library], args)
    native = ctypes.CDLL(str(library.absolute()))
    native.top.restype = ctypes.c_uint32
    assert native.top() == 3, "native boundary changed lane order"
    if name == "vector-boundary":
        # Raw selected production also checks source H IR remains immutable.
        from sqlite_vector_normalise import CASES
        CASES[name] = (3, ())
        oracle(args, source, name, dest)
    return {"symbol": symbol, "native_result": 3, "idempotent": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--major", type=int, required=True, choices=(18, 23))
    p.add_argument("--plugin", type=Path, required=True)
    p.add_argument("--guard-table", type=Path, required=True)
    p.add_argument("--output", type=Path, default=ROOT / ".tmp/sqlite-vector-boundary")
    a = p.parse_args()
    table = tomllib.loads(a.guard_table.read_text())
    a.guard_seconds = table["classes"]["moderate"]["seconds"] * table["machine_config_factor"]
    rows = []
    for name in ("vector-boundary", "vector-external", "vector-callback"):
        try:
            result = check_case(a, name)
        except AssertionError as error:
            rows.append(dict(case=name, ok=False, error=str(error)))
        else:
            rows.append(dict(case=name, ok=True, result=result))
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / f"boundary-{a.major}.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    return int(any(not r["ok"] for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
