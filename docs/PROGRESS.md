# Progress — 2026-10-30

Contract: dialect 0.2.6, ff249d597f767f8034176bbb6c0f86dea3b90270; ISA 0.8.
M1 remains in progress. No whole-program conformance claim, no push.

## Verified

- `scripts/build`: both major-specific plugins build offline with llvm-config/g++.
  CMake is absent; superbuild configure/build is an outstanding validation task bp-ahz.
- `tests/scalars.py --major 18` and `--major 23`: **9/9** generated reference objects
  pass the ISA binary's `check` and equal the published fixtures byte for byte:
  oracle-empty-output, oracle-empty-fault, oracle-discard-return, pointer-as270,
  gep-index-obj, gep-index-const, inc8, add2, switch5. Hashes match by exact object
  equality and the black-box hash command. Execution/budget vectors are also checked;
  extended ARG and exhaustive step-check runs are being added to this verification.
- Initial DA/DB/DC expansion: **54/61** published examples on each major. The failures
  revealed exported QREG-result handling, indirect handle calls, producer-vs-linked
  reserved-name scope and slow additive fixpoints. Fixes are under retest; do not
  read these counts as final acceptance.

## Gate and evidence

The independent driver uses every case/control and 14 opt pipelines on 18, 12 on 23.
The published harness has no plugin parameter; it is executed only in a scratch copy
as a black box to supply runtime binaries and baseline metadata. Its own baseline
reports all 69 entries cross-major-agree but exits nonzero: ABI 0.2 adj/compute
baselines fail with exit 87 on both majors (bp-c2i).

Legacy spike ABI support is a test-only audit option, requiring analysis-only.
Production recognition remains exact ABI 0.2. `control-region-twin` is a positive
content-identity witness under §7.3, despite its old negative label (bp-tye).
The three attribute/dereference negative controls must fail with the stated code.

The full corpus gate is running. Its JSON reports each divergence with its §21.1
property and never waives an unimplemented check. L1's present scope compares the
optimised module before/after the plugin; cross-stock-pipeline L4 equivalence and
full materialisation are not yet established. All remaining mechanics remain in
PLAN; unavailable production lowering fails explicitly.

## Dependencies and next work

bp-a41 owns M1. Plan/pin task bp-a41.1 is closed; the other tasks remain open until
verified. ISA dependencies: bp-2tw (BLK-1), bp-2bi (BLK-2), bp-ckk (BLK-4), bp-is0
(BLK-5). Blocked compilation is not claimed: status 3 requires actual blocker-trap
objects, which are M3 mechanics. Until then the diagnostic says unimplemented and
names the dependency.

Finish M1's reference analysis/gate gaps and CMake validation before declaring M1
done. M2 then adds the complete normaliser, logical memory, calls and scalarisation.
