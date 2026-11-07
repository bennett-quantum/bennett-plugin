#!/usr/bin/env python3
"""An allowlisted unavailable check cannot hide a new property failure."""

import runpy
import unittest
from contracts import ROOT
from corpus_gate import classify, summarize


def row(name, props, **kw):
    return dict(
        case=name,
        major=18,
        properties=props,
        agree=all(v is True for v in props.values()),
        **kw
    )


base = {"L1": False, "L2": True, "L3": True, "L4": True, "L5": False, "L6": True}
b = row(
    "spec-sem2-adj",
    base,
    native_exits={"pre_O0": 87, "pre_O3": 87, "post_O0": 87, "post_O3": 87},
)
assert classify(b) == "blocked-upstream: bp-c2i (upstream b-dialect-spec-566)"
assert (
    classify(
        row("spec-sem2-compute", dict(base, L3=False), native_exits=b["native_exits"])
    )
    == "diverge"
)
assert (
    classify(
        row("spec-sem2-adj", base, native_exits=dict(b["native_exits"], post_O3=1))
    )
    == "diverge"
)
missing = dict(
    missing_entry_point="__bennett_sf_sitofp_f64",
    softfloat_error="unavailable: §13.1 missing entry point __bennett_sf_sitofp_f64; supply BENNETT_ARITH_BITCODE",
)
assert (
    classify(row("fp-rot-fastmath-reassoc", dict(base, L1=True), **missing))
    == "diverge"
)
assert classify(row("fp-rot-fastmath-reassoc", dict(base, L1=True))) == "diverge"
assert (
    classify(
        row(
            "fp-rot-fastmath-reassoc",
            dict(base, L1=True),
            missing_entry_point="__bennett_sf_unrelated_f64",
            softfloat_error=missing["softfloat_error"],
        )
    )
    == "diverge"
)
assert (
    classify(row("fp-rot-fastmath-reassoc", dict(base, L1=True, L4=False))) == "diverge"
)
assert classify(row("ordinary", {"L5": False})) == "diverge"
s = summarize([b, row("ordinary", {"L1": True})])
assert s["cases_blocked"] == 1 and s["cases_agree"] == 1 and s["cases_diverge"] == 0
print("gate policy: 9 assertions passed")

# Explicit receipt revisions bind both byte versions and retain every prior name.
revise = runpy.run_path(str(ROOT / "scripts/record-verification.py"))["revised_rows"]
previous = [{"object": "launch", "sha256": "old"}]
current = {"launch": {"object": "launch", "sha256": "new"}}
changes = [{"object": "launch", "previous_sha256": "old", "sha256": "new"}]
assert revise(previous, current, changes) == [current["launch"]]
assert revise(previous, {"launch": previous[0]}, []) == previous
check = unittest.TestCase()
with check.assertRaises(AssertionError):
    revise(previous, current, [])
with check.assertRaises(AssertionError):
    revise(previous, {}, changes)
with check.assertRaises(AssertionError):
    revise(previous, current, [dict(changes[0], previous_sha256="stale")])
with check.assertRaises(AssertionError):
    revise(previous, current, [dict(changes[0], sha256="wrong")])
with check.assertRaises(AssertionError):
    revise(previous, current, changes * 2)
with check.assertRaises(AssertionError):
    revise(previous, {"launch": previous[0]}, changes)
print("receipt revisions: exact hashes, complete retention, stale/unused approvals refused")
