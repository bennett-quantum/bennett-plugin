# Handoff

Rewritten at session end with `date -u`: **2026-11-01T16:56:46Z**.

Pinned contract remains dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8**.

## Resume

**Pass 26 prerequisite complete: bp-ehi CLOSED.** Effort was spent on adopting the larger arith publication and completing its full gate. Next implementation bead is **bp-ozp** (LLVM18 vector fshl in musl memcpy), then bp-xyn, bp-xv0, bp-xkg/bp-is0 audit, bp-xms/bp-7ni, then bp-xb8/bp-zeg/bp-75y. All original requested beads remain open/blocked; bp-ivy is still partial. No later implementation was started.

## Publication and build

Arith **0dea42d001ffe832493fa0711da4a59b8cc1dd10** is now pinned, including immutable manifest provenance in SPEC_VERSIONS.toml. Live hashes and llvm-nm were checked: **1,134 definitions per major**.

- LLVM18: `8d99956e8741803f2115e48fa28c6c71795fb0041e992f8835851b71dd4b6fc1`
- LLVM23: `59563a3a10949b1ea48ca8b79027310ac9f9f7e28c85a30e70a013ced04a6793`

Use the live dist; **unset BENNETT_ARITH_PINNED_ROOT**. The historical allocator probe still needs BENNETT_ALLOCATOR_PINNED_ROOT=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp/allocator-pinned (runtimes 469246e, original digest checks); current musl publication remains the R-hello input.

CMake's nested builds did not invalidate their compiled arith hashes on a TOML change. SPEC_VERSIONS.toml is now a configure dependency. The superbuild uses RelWithDebInfo. Expanded numerical production/recognition probes use the existing direct-CC 180000ms S2 allowance and a 600s outer production timeout. **The default 30s wall-clock guard is unchanged; bp-xv0 remains open.** No test case, oracle width, runtime budget or CC timeout was reduced or waived.

## Verification

Final **scripts/gate exit 0**, implementation **fd6a9e9**, recorder head **4f67f6d**; BENNETT_ARITH_PINNED_ROOT unset throughout. LLVM18/23 each **66/66/0/0/0**, cells 924/924 and 792/792; softfloat 112/112 and 116/116; 312 equal object pairs, 45 published matches, all 312 prior hashes preserved. Recorded with `python3 scripts/record-verification.py` in docs/verification.json (the script file itself is not executable).

Unchanged 64-wire/two-oracle CC launches **COMPLETED in 1677.381647455s/1639.770126202s** (18/23), original args 1000000,1000000 and budget 1000000,65536,65536,128. Successful zero-input L probes: code 0, payload 0, 45049/70276 steps. These are existing numerical witnesses under the new pin, not full seven-format bp-7ni closure. bp-7ni remains blocked on bp-xms; do the requested full scope audit before closing either.

Raw final gate: `.tmp/pass26-arith-final-gate.log`. `docs/arith-m2-repin.json` records earlier failed stale-build and analysis attempts separately, their hashes, focused generation timings and a separate successful corpus invocation. None is substituted for the final full gate.

## R and comparison remainders

Fresh R probes retain prior behavior: whole-musl LLVM18 reaches the vector `llvm.fshl.v4i32` frontier (bp-ozp); LLVM23 emits verified objects and exit 3 BD-B-ISA7. No fresh full hello forward/native/reset/replay success is claimed. Existing exploratory fault 7, argv/envp storage, full startup/exit cleanup and runtime-budget plumbing remain bp-ivy; native materialisation/link-map work remains bp-xyn.

**bp-is0 now records the precise hello trigger:** selecting whole-program R entry main requires the mandatory §17.6 pre-instruction budget point F(1), even when generous limits permit success (§11.5/§1.6). Generic trap cannot report arbitrary code 1. ISA 0.9 draft K5, §4.1/§4.9/§10 defines typed `fault C`, exact terminal code, no later source effect and retained reversible prefix; the draft explicitly gives exhaustion as `fault 1`. Migration is b-isa-spec-fuk. No 0.9 producer mode or accepted-contract change was made; independent bp-ivy/bp-xyn mechanics are not claimed resolved.

Own code commits: **229e4df, 8aaf80d, fd6a9e9**; the receipt/handoff commit follows. Concurrent **af1e243/4f67f6d** add bead metadata only; verified no source/test/build/pin differences from fd6a9e9 and preserved both. No sibling source edited, no dialect ambiguity bead filed, no push. The orchestrator owns the session worklog and eventual push.

Run headlessly: unset DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS/BROWSER; TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp. Never LLVM -view-*. Export beads before committing .beads; commit explicit paths with BEADS_HOOK_TIMEOUT=20. Never push from this implementation task.
