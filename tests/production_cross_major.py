#!/usr/bin/env python3
"""Compare complete production object bytes, including rejected-pair references."""

import hashlib, json
from contracts import ROOT as R

pairs = []
for family in [
    "production-dispatch",
    "production-environments",
    "entry-snapshot",
    "softfloat",
    "wide",
    "integer-intrinsics",
    "memory-runtime",
    "aggregate-rows",
    "cc-calls",
    "cc-switch",
    "reversible",
]:
    left = R / f".tmp/{family}/18"
    right = R / f".tmp/{family}/23"
    files = {
        p.relative_to(left)
        for p in left.rglob("*.bennett")
        if family != "reversible" or "r-hello" not in p.relative_to(left).parts
    }
    assert files and files == {
        p.relative_to(right)
        for p in right.rglob("*.bennett")
        if family != "reversible" or "r-hello" not in p.relative_to(right).parts
    }, family
    for name in sorted(files):
        a = (left / name).read_bytes()
        b = (right / name).read_bytes()
        assert a == b, f"{family}/{name}: LLVM18/23 object bytes differ"
        pairs.append(
            {"object": f"{family}/{name}", "sha256": hashlib.sha256(a).hexdigest()}
        )
report = {"pairs": len(pairs), "byte_identical": True, "objects": pairs}
(R / ".tmp/production-cross-major.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
