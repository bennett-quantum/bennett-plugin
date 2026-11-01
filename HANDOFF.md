# Handoff

Rewritten at session end with `date -u`: **2026-11-01T15:08:27Z**.

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8**.
M1 remains complete. **bp-ivy remains OPEN**, **bp-ozp OPEN**; bp-loq and bp-5t9 closed.
**bp-7ni remains BLOCKED on bp-xms**; arith was not repinned. The old 606-export
publication still lacks its staged PPCDoubleDouble/own-format libm/signaling obligations.
No spec ambiguity was found, no spec bead filed, no sibling source edited, no push.
The orchestrator owns the session worklog and eventual push.

## R integration and actual limits

Whole-program R options and entry analysis now route the reachable program into R bodies.
The CC launch requests bennett.argv, initialises the logical stack, and calls R.
Effects use ISA device models/tapes (§11.2), with scalar memory/call/phi lowering,
indirect compare trees and shared global/function relocation (§14.2/§17.4/§19.5).
N31 unlisted asm traps only when reached and has named, point-bound coverage.
Each counted R instruction has a pre-instruction source-step check (§17.6).
Nested exit pseudo-exceptions propagate and the launch returns their status (§14.7).
Pinned §1.6/§11.5 requires artifacts **and exit3 BD-B-ISA7** for every R entry;
generic exhaustion traps are blocker fallbacks, never typed-fault conformance.

This is partial bp-ivy delivery. General argv/envp byte storage is explicit unimplemented
if the source consumes either pointer argument; current launch replies carry argc and
unused null pointers. Full musl startup/normal-return exit cleanup, runtime source-budget
plumbing, complete depth/heap checks and exit-frame cleanup remain on bp-ivy.
No acceptance or scope waiver is inferred from the passing small probes.

## Probes and verification

Probes: r-console.ll, r-start-exit.ll, r-callback.ll, r-asm.ll, r-budget.ll, r-hello.c.
Both majors pass8/8 checks, including forward/full-state reversal, skipped post-exit
writes, callback relocation, reached/unreached asm and budgets0/1/2 before effects/return.
Recognised/materialised/source/object hashes and LLVM verification are recorded.
Full published-musl hello reaches S1–S5 in six rounds on both majors. LLVM18 stops at
`%129 = call <4 x i32> @llvm.fshl.v4i32(...)` in memcpy: next N21/N27 rule bp-ozp.
LLVM23 emits verified artifacts; the release checker admits the unchanged object, but
exploratory forward returns FAILED/fault7 at step1160 with no console output.
The latter is preserved as measured failure, not agreement; suspected strlen word-tail
bounds require confirmation. Do not pad allocations or waive §17.1 bounds speculatively.

Final **scripts/gate exit0**, code head **60792e378950c014a37bfa6061a3343c0fea09e0**:
LLVM18/23 each **66 run /66 agree /0 deferred /0 blocked /0 diverge**,
cells924/924 and792/792; softfloat112/112 and116/116. Unchanged full-width launches
completed in373.673s/181.065s. 312 equal object pairs,45 published matches,
all305 previous hashes preserved. Recorded with scripts/record-verification.py;
docs/verification.json contains the full consumer report and exploratory failure.
Final raw log: .tmp/bp-ivy-gate.log. Prior prerequisite/coverage/manifest/CC-timeout
red logs are hashed separately; none is a green receipt. The numerical timeout was
fixed by restricting new recurrence acceleration to R analysis, retaining old CC behavior.

## Immutable publications and rung3

Use BENNETT_ARITH_PINNED_ROOT=$PWD/.tmp/arith-pinned for llvm18/23/bennett-arith.bc
extracted from arith249e619. Original b235c88a…/1c7f4009… digest checks remain;
export metadata is read from that same git publication even with only relocated .bc files.
The historical allocator probe additionally uses
BENNETT_ALLOCATOR_PINNED_ROOT=$PWD/.tmp/allocator-pinned, extracted from runtimes469246e,
with its original digest checks. The R hello separately pins the published musl
6c1741c4…/a63f0421… artifacts, extracted from runtimesfd0c522 for the consumer.
No SPEC_VERSIONS.toml change or new-arith adoption occurred.

Rung3 gate ran **once**, exit1, with --plugin-rev=60792e3 and --runtimes18/23 pointing
to those immutable musl copies; default pre-musl consumer pins/files were not edited.
Evidence: ../bennett-conformance/.tmp/rung-3/20261101T145932.061259Z/.
Frontend/link/LTO/runtime export audit PASS both; production18 stops bp-ozp,
production23 and both R probes exit3 BD-B-ISA7. The old matcher calls these UNFILED;
known bead mappings are on bp-ivy/bp-ozp, not patched into consumer evidence.
Native/admission/forward/reset/replay required rows remain BLOCKED. Reference control
and replay-API diagnostics PASS; driver cyg and pinned VM replay u8m FAIL.
ISA-0.8 R prerequisite remains red (221). No full hello/native/replay acceptance claim.

Own commits:182237c,e5f9400,02aa97c,baa8125,b8ee2ad,6dbfa3f,e1f797e,60792e3;
the final receipt/handoff commit follows these. bp-eof was closed by c93f68a before this job.
Run headless with project-local TMPDIR; unset DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS/BROWSER;
never LLVM -view-*. Export beads before committing .beads; commit explicit own paths
with BEADS_HOOK_TIMEOUT=20. Never push from this task.
