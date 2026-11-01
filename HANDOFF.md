# Handoff

Rewritten at session end with `date -u`: **2026-11-01T12:36:24Z**.

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8**.
SHA-pinned major-matched arith bitcode remains unchanged (SPEC_VERSIONS.toml).
M1 remains complete. **bp-7ni remains BLOCKED on bp-xms**, not closed; no capability waived.
The missing published exports include `__bennett_sf_add_ppcf128` and `__bennett_sf_sin_f128`
on both majors; PPCDoubleDouble, own-format libm/non-i32 powi, arbitrary-format schema and
signaling ABI obligations remain on bp-xms (r3d/0he/38c/chn). No sibling repository edited.

## Where the closure stopped and what changed

The exact LLVM23 red stop was the plugin's active-set inlining guard at `bennett_sf_eval`,
encountering `call void @bennett_sf_eval(ptr %19, i32 %1, i32 3, ptr %18, i32 0, i32 %5)`.
§13.1 requires the entry points defined by bennett-arith in linked bitcode; §14.1 requires
CC/R calls and says recursion is unrestricted; §17.4 supplies integer/memory, phi block
parameters and aggregate multi-result transport. ISA §16.2 requires parenthesized multi-LHS.
The text is clear: no dialect-ruling bead was filed.

Recursive numerical closures now retain real CC call frames, materialise N22/N27/N24 helpers
and initialise their logical stack. Helpers remain callees with H bodies, not host launch stubs.
Aggregate parameters/results/insert/extract/phi/select/load/store flatten into scalar tuples;
new numerical pointer comparisons use integer addresses. Private S2 transfer graphs release
source operand uses before production rewrites (otherwise final verification exposed corruption).
Native M>128 comparison slots now link the existing logical-stack runtime and idempotent init;
linked allocation definitions win over native calloc backing. No arithmetic definition is fabricated.

Probes in tests/probes: cc-softfloat.ll, cc-softfloat-recursive.ll, cc-softfloat-oracle.ll,
softfloat-native-wide.ll. Real f64 zero/subnormal/negative-zero/finite/infinity/NaN direct CC
vectors completely reverse state and memory on both majors. Recursive tuple/phi/select transport
reverses at 0/1/3/7. Native i192 round-trips ±2^190/0/−1 at O0/O3, preserving a live parent slot.
Recognised/source/materialised/object hashes and LLVM verification are in docs/verification.json.

## Final verification

**scripts/gate exit 0**, LLVM18/23 each **66 run / 66 agree / 0 deferred / 0 blocked / 0 diverge**;
924/924 and 792/792 cells. fp-rot-fastmath-reassoc agrees on both majors.
Softfloat checks **112/112 (18), 116/116 (23)**.
305 equal object pairs, 45 published matches; all 299 previous hashes preserved.
Recorded by scripts/record-verification.py --pass bp-7ni; raw final log .tmp/bp-7ni-gate.log.

Unchanged 64-wire/two-oracle CC launch, frozen release ISA CLI: **464.356708s (18),
276.140375s (23)**, **9 CC steps each**, no faults, memory equal. Arguments
1000000,1000000; budget 1000000,65536,65536,128. Matching zero-input L runs return code 0/payload 0
in 44892 / 70119 materialised steps, below each 1000000-step token; CC's reported 9 steps exclude
nested oracle work. CLI hashes, commands, budgets and results are recorded. The case was not shrunk.

Earlier attempts are not green receipts: .tmp/bp-7ni-gate-incomplete.log (stopped for native-wide
repair), .tmp/bp-7ni-gate-prior-red.log (four legacy stack-snapshot hashes changed). e126501
scoped pointer comparison changes to the new numerical closure, restoring all prior hashes;
new numerical CC objects stayed byte-identical to the executed ones. Final run uses fixed source/plugins.

## Commits and next work

- 78b006075c69f7249e2b82ec2924b58035ee4720 — recursive closure, aggregate ABI, graph lifetime and probes.
- 1bc3f3610eee9a9c267333fea45619f800087c75 — native wide slot linkage/initialisation and probe.
- e126501ee07ce89913e2d0301b3a949f776395f4 — scope correction preserving prior CC objects; final gated code head.

Consume remaining published arith exports/ABI under bp-xms before claiming full seven-format
§13 closure or closing bp-7ni. No force-close or implicit waiver was used.
**bp-eof remains open**; the rung-2 gate was not run by this task (downstream work remains pending).
Switch lowering/bp-bux was already reinstated/closed before this task; no hashtable execution claim here.

Run headless, TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp;
unset DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS, BROWSER; never LLVM -view-*.
Export beads before committing .beads, commit explicit own paths with BEADS_HOOK_TIMEOUT=20.
No push. The orchestrator owns the session worklog and any subsequent push.
