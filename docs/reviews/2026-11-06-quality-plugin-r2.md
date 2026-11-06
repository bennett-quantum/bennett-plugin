# Plugin quality review, round 2 — 2026-11-06

**Verdict: CLEAR — no P0/P1 findings. Council review remains required for this critical batch.**

Reviewed SHA: `cd6943d134c61705f1f6e770a64da18631e60ae3`.
Closely reviewed the fixes in `28a4ff0..cd6943d` against the round-one review;
inspected the requested `main...job/quality-plugin` comparison for context.
Merge-base: `5a092cded3ba3351ba8cc2977a7eaf3b40f46526`;
main observed at `054ad426e54d164fd53aeb96804a47a872185bbc`.

- **R1 P0-1 / bp-kya: fixed.** `src/Production.cpp:2523` computes every
  entry's original global dependencies before replacing any body. Ran
  `timeout 180 python3 -B tests/review_regressions.py --major 18 --case global-diagnostic`
  and the LLVM 23 equivalent: **5/5 each**. Both helper-first and top-first
  source-native baselines print `1 2 host_global=2`; both generated host programs
  exit 125 with the approved promised/pending diagnostic and no result output.
  Repeat, host-write and two-entry cases also pass. The promised semantic test remains available.
- **R1 P0-2 / bp-9t7: fixed.** `tests/contracts.py:63` now checks the actual
  generated module before clang. Its independent LLVM reader visits all defined
  functions, including materialized helpers. Ran
  `timeout 180 python3 -B tests/normalisation_scope.py --major 18` and the LLVM 23
  equivalent: **5/5 mutations rejected each**, after accepting each pristine module.
  These reproduce scalar cttz, vector ctpop, helper-body intrinsic, non-byte wide
  memory and memmove residue in the real suites, including the original R1 witness.
- **bp-sjm: fixed.** Ran `timeout 180 python3 -B tests/reversible.py --major 18`
  and the LLVM 23 equivalent: **8/8 each**, including forward/reverse results,
  budget edges, verified bitcode and checked full-musl artifacts. The three expected
  production exits now use `code=3`; the runtime digest comes from the immutable gate pin.
  An additional `timeout 120 python3 -B -` in-process reviewer mutation, on both
  majors, changed the first production status from 3 to 0 and separately replaced
  the runtime digest with zeroes: the driver rejected both at the intended assertions.

Other focused verification, headless with reviewer-local TMPDIR:

- `timeout 300 cmake --build build/coverage18 -j3` and
  `timeout 300 cmake --build build/llvm23 -j3`: pass.
- Each driver run separately under `timeout 180 python3 -B tests/<driver>.py --major <major>`:
  wide **110/110** on both; integer_intrinsics **602/602** (18), **697/697** (23);
  memory_runtime **33/33** (18), **34/34** (23).
- `timeout 90 python3 -B scripts/quality.py --check`: pass;
  `git diff --check 28a4ff0..HEAD`: pass. No full gate or sibling gate run.

Executable-line coverage: `timeout 90 scripts/coverage` reproduced **66.86%, 4646/6949**.
The previous **70.53%, 4896/6942** used a different workload: allocator_closure,
cc_calls, production, production_budgets, production_lifts and mixed-native were
listed there; the new measurement clears counters and instead includes memory_runtime
and the repaired reversible driver. The denominator also grew by seven executable
lines. This is not a same-suite coverage comparison; Reversible.inc improves from
0/124 to **118/124**, while the omitted integration paths lower the overall numerator.
Those integration tests remain in the slow gate. No coverage threshold is claimed.

P2+ nits: **bp-pgb** (P3, `nit`, carries forward **bp-3mb**): unused subprocess imports in `tests/address_spaces.py:7`, `tests/integer_intrinsics.py:4`, `tests/memory_runtime.py:4`, `tests/scalars.py:4`; no new nits.

Coverage of review: read closely every round-two production, harness, verifier,
mutation-test and evidence change; skimmed unchanged surrounding lowering and
historical context. Main-side and pre-fix code were read with `git show`, without
switching branches: main lacks the shared-state guard, and its old whole-suite
intrinsic assertion detects the mutation that R1 accidentally stopped checking.
Checked each COMMON anti-slop rule: dispatch, state, fallbacks, predicates,
constants, phase boundaries/wrappers, process identifiers, litter and independent
test observations. No new semantic violation or scope narrowing found.
`src/Analysis.cpp` is untouched against main; its deferred split remains outside
this job. The two product bead identifiers remain explicitly required by D4.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
