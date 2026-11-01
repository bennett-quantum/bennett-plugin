# Handoff

Rewritten at session end with `date -u`: **2026-11-01T10:21:57Z**.

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. M1 remains complete; M2 and the North Star ladder remain in progress.
**bp-bux remains open**: this attempted pass was rolled back under the task's red-gate stop rule.
**bp-eof** records the measured consumer execution/admission failures. **bp-7ni unchanged**. No push.

Implementation attempt: **9adc557486b2aa739111f4daa7312e0c836b768c**.
Revert: **5081c8d9fc11cc684a719b9a0f414acf2989352f**. Source, probes and gate/recorder changes from the attempt are all reverted.
The active code is the pre-attempt bp-9fo implementation and again stops at CC switch.
Both plugins were rebuilt after the revert; an archived dense probe reproduced the original
§17.4 switch refusal (exit 1) on both majors. Diagnostics and plugin hashes are recorded in
`docs/rung2-analysis.json` `bp-bux_rollback_reproduction`.
No hashtable forward/native equality or byte-exact reversal is claimed.

## Attempted switch lowering and verification

§14.8 uses §16.4's unsigned sorted compare tree: midpoint ult split for more than three keys,
eq chains at leaves, unconditional default for no keys, generated blocks in creation order.
§17.4/ISA §3.4 carry original-predecessor phi values as parallel block-argument tuples,
including duplicate destinations, shared defaults and loop-carried swaps.
Five probes in the implementation commit cover dense/sparse sets, default-only, a loop and
loaded conditions. Each major passed 41 independent-native/full-state reversal vectors, including
memory/allocator/handle equality. Objects were independently checked/hashed and byte-identical
across majors; recognised/materialised digests and bitcode verification are retained.

One complete **scripts/gate exit 0** on the attempt: **66 run / 66 agree / 0 deferred /
0 blocked / 0 diverge** each major; cells **924/924** (18), **792/792** (23).
All **299** prior hashes preserved; **304** equal object pairs, **45** published matches.
Log: `.tmp/bp-bux-gate.log`. Recorded with scripts/record-verification.py --pass bp-bux.
`docs/verification.json` retains that exact receipt as `rolled_back_attempt`, with disposition
and revert SHA; `latest_pass` keeps the active bp-9fo baseline, avoiding impossible prior-object
requirements for probes removed by the mandated rollback.

## Linked hashtable and unchanged rung-2 gate

With the attempt, fresh marked C -> clang -O2 -flto -> llvm-link --only-needed with published
major-matched runtimes and SHA-pinned arith -> lto<O3> -> S1–S5 analysis -> S1–S9 production
all passed on both majors (production 6.31s LLVM18 / 7.85s LLVM23, concurrent with plugin gate).
Full commands, timings and hashes: `docs/rung2-analysis.json` `bp-bux_after`.

The requested unchanged rung-2 gate ran **once**, exit **1**, against frozen implementation
9adc557 and the gate's frozen VM/reference executables. Fixtures, plugin/VM builds, native
reference, front end, link, LTO, production and launch artifacts all passed on both majors.

| Stage | LLVM 18 | LLVM 23 |
|---|---|---|
| Reference admission | PASS | PASS |
| VM admission | FAIL | FAIL |
| Reference forward = native | FAIL (300s timeout, basic 0) | FAIL (300s timeout, basic 0) |
| VM forward = native | BLOCKED | BLOCKED |
| Reference byte-exact reverse | BLOCKED | BLOCKED |
| VM byte-exact reverse | BLOCKED | BLOCKED |

VM check reports `§3.3: arithmetic needs integer operands`; the emitted object contains pointer
icmp/null comparisons outside the switch trees (e.g. LLVM18 `%192 = icmp eq ptr %191, null`,
ISA `v535 = icmp.eq v532 v533`, both operands ptr). The diagnostic has no instruction location;
ownership/causality remains unproven. Accepted reference check/hash accepts both objects, but
its forward `ht_demo_basic --args 0` commands each time out at 300s, without an instruction
diagnostic. No nontermination or spec ambiguity is inferred. Do not conflate these two failures.

Raw evidence: `../bennett-conformance/.tmp/rung-2/20261101T094524.766276Z/`.
Report, manifest, table and hashes are copied into `docs/rung2-analysis.json` `bp-bux_rung2_gate`.
Raw tables say UNFILED; **bp-eof**, labels consumer,m2,rung2, now accounts for those observed failures.
No further lowering pass was attempted after production completed and the consumer gate went red.
No dialect-ruling bead was needed; no conformance/runtime/VM/arith/spec source was edited.

Run headless: unset DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER;
TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp. Never LLVM -view-*.
Export beads before committing .beads; commit explicit paths. Never push from this task.
The orchestrator owns the session worklog and any later push. Investigate bp-eof against the
frozen emitted artifacts; restore/close bp-bux only in a subsequent authorized green pass.
