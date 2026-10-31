# Implementation plan

Contract: dialect **0.2.10**, accepted commit **023f5a771a814270634db3be9cfde88ded69f975**;
ISA **0.8**. The full draft string is the compatibility unit. Published contracts,
fixtures and executable black boxes are the only sibling dependencies.

M1 acceptance is still open; [PROGRESS.md](PROGRESS.md) distinguishes verified
slices from outstanding obligations and records the final pinned corpus matrix.

## Architecture

One source tree, separate LLVM-major build directories and shared objects. The explicit
post-link module pass `bennett` registers no pre-link extension point. S1 recognises
markers and checks the positive attribute envelope before rewriting marker invokes.
S2 computes a single monotone inclusion fixpoint for values, field-sensitive memory,
function addresses, region candidates, handle roots and descriptor fields. S3 derives
the device graph and tier variants; H retains the original, device clones share globals.
S4 checks handle uses/containment, then S5 checks region closures. Region keys use
content after alias/thunk resolution, never source symbols. S6 partitions generation
and coherent slices with may-Co state; S7 materialises every device variant and runs
an independent residual validator. S8 emits canonical reference wrappers/lprocs and
verifies in-place inverses. S9 lowers CC/R and controlled/adjoint event bodies, writes
objects, materialised bitcode, coverage, certificates and build records. Scheduling
is a replaceable **binary** edge to bennett-sched, never an LLVM library dependency.
No recognised program may silently fall through to native marker execution.

## Ordered milestones

1. **M1 — analysis and scalar rung 1.** Dual-major build, exact ABI recognition,
   device fixpoint, bitwise handle provenance, region candidates/content keys;
   corpus gate on both majors; scalar integer reference objects checked/hash/run
   against the ISA binary. Analysis-only reports are explicitly non-production.
2. **M2 — full normalisation and lifted memory/calls.** N0–N35, V1–V16,
   descriptors/shapes, entry-state replay, shadow-stack logical lifetimes, heap,
   phis/loops/switch/indirect calls, wide results, FP/soft-float, vectors, EH,
   varargs, fibers, asm. Rung 2 and the full map/reference differential suite.
3. **M3 — generation, CC/R and TDL.** Tier cloning/launch stubs; handle register
   files and boundary QREGs, action outlining, controlled/adjoint/compute event
   generation including deferred measurement; may-Co, arena, inverse discovery,
   observation, cancellation, firstfault and budgets. Rungs 1–3 end to end.
4. **M4 — program integration.** Effects/models, runtimes/arith links, comparison
   layout, scheduler binary edge, certificates/coverage/build records, platform,
   driver modes/closed-unit/mixed majors. Rung 4 SQLite then rungs 5–8.
5. **M5 — ISA dependency removal.** After ISA 0.9 acceptance and a dialect bump,
   replace blocker paths without changing source capabilities; full conformance.

An unavailable mechanic fails `unimplemented: §<section> (milestone N)` with context;
it is an implementation failure, **not** a dialect rejection or an accept verdict.
Only §22.1 codes may reject. Future mechanics remain promised, not disallowed.

## Section ownership

| Dialect section | Milestone / obligation |
|---|---|
| §1 | M1 verdict distinction; M4 full conformance |
| §2 | M1 terminology |
| §3 | M1 all marker names/signatures/attributes/invokes |
| §4 | M1 graph/tiers; M3 clones; M4 native addresses/layout |
| §5 | M1 reference fixpoint; M2 all normalised shapes |
| §6 | M1 provenance/use/containment; M3 static files/boundary/wires |
| §7 | M1 candidates/thunks/content; M3 kinds/generation/dispatch |
| §8 | M1 scalar IN shapes; M2 descriptors/replay/wide/in-place |
| §9 | M2 budget tables; M3 run-time tokens and instrumentation |
| §10 | M3 entire TDL mechanism (R1), no capability narrowing |
| §11 | M4 effects in every tier |
| §12 | M1 scalar subset; M2 N0–N35 and V1–V16 |
| §13 | M2 deterministic soft-float in every format |
| §14 | M2 calls/recursion/indirect/varargs/EH/sjlj/fibers |
| §15 | M2 asm and intrinsic classification; M4 platform rows |
| §16 | M1 scalar canonical map; M2 every map row and shape |
| §17 | M3 CC/R, logical memory and reversible history; M4 comparison |
| §18 | M1 scalar oracle semantics; M3 full events; M4 differentials |
| §19 | M1 explicit post-link/version interface; M4 all driver modes/outputs |
| §20 | M4 riscv64-bennett-virt, MMIO/interrupts/processes |
| §21 | M1 legality gate; M2–M4 DA–DX suites and rung ladder |
| §22 | M1 S1–S5 diagnostics; M2–M4 later rejections/traps/warnings |
| §23 | M1 exact version pin; every milestone rechecks pin |
| §24 | M1–M4 defaults at owning section; no default rejection |
| §25 | M1 track dependencies; M3 bounded realisations; M5 removal |
| Appendices A–C | M1 traceability; M2 all generic intrinsics |

## ISA blockers (explicit unimplemented dependencies)

- BLK-1 / BD-B-ISA4: `unimplemented: §25.1 BLK-1 (blocked: bp-2tw)`:
  dynamic widths, unbounded persistent handle instances; need qreg[*], width/id/from_id.
- BLK-2 / BD-B-ISA1: `unimplemented: §25.1 BLK-2 (blocked: bp-2bi)`:
  device-computed budgets; need CC budget.mint with history.
- BLK-4 / BD-B-ISA12: `unimplemented: §25.1 BLK-4 (blocked: bp-ckk)`:
  unbounded R quantum allocation; need R qreg operations/history.
- BLK-5 / BD-B-ISA7: `unimplemented: §25.1 BLK-5 (blocked: bp-is0)`:
  every R entry's typed budget/fault reporting; need R fault C preserving prefix.

These messages must never be confused with implemented blocked compilation: §1.6
requires actual objects with precise blocker traps and exit 3. M3 supplies bounded
realisations; until then the compiler reports unavailable lowering explicitly.

## Third-pass delivery and remaining acceptance (2026-10-31)

Accepted dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA 0.8. Draft 0.2.11 is not adopted. The gate checks the accepted registry and
pinned blob SHA-256; it reports later unaccepted HEAD/worktree text separately.
The opaque corpus runtime/harness/header and all cases use that same immutable pin.

Delivered: verified CMake 3.28.3 dual-major superbuild; 23-marker recognition;
73/74 applicable published recognition examples (18/23); 12 analysis regressions
including zero initial images, geometry-changing/fixed-vscale bitcasts, sub-byte
packing, Cartesian alternatives and N9 cmpxchg domains; five materialisation
fixtures; scalar materialised closure keys; 12 exact reference objects and all
published vectors; static descriptor inc8 reference extraction. The legality gate
is 66 run / 65 agree / 1 deferred / 0 blocked / 0 diverge per major.

**M1 is not delivered.** Brief 1b item 3 remains open for general reference
analysis (PT2/PT4/PT5 represented-address images, composites/atomics, exact tier and
boundary seeding), all-rule materialised keys (**bp-3w4**) and production scalar
descriptor/CC objects, launches, host entry replacement and records (**bp-2zv**).
The test-only descriptor path is not production acceptance. Pull forward that
scalar CC work from M3; general generation/TDL remains M3. No unfinished M1
obligation has been moved to M2 in this pass.

Brief 1b item 4 now checks untrimmed fixture bytes and all stated hashes/vectors
for 12/20 lift examples. Eight scalar-typed examples and the two object-only
integration vectors remain inventoried with exact missing rows in PROGRESS and
verification.json. Every scalar `spec-*` case is inventoried: the pin has six
quantum action cases and no scalar oracle case.

Existing mechanical deferrals (none removes a source capability):

| Work | Owning sentence / rows | Bead |
|---|---|---|
| M2 soft-float and native comparison closure | §13.1: “The entry points are defined by bennett-arith and are part of its bitcode the driver links.” | bp-7ni |
| M2 memory/replay/device bindings/calls, eight lift examples and entry-stack | §8.5: “The region function runs on a private copy of the caller's whole classical memory at the call”; §16.2 prologue, §16.4 load/store/alloc/calls | bp-311 |
| M3 arena-o1 outlining | TDL-4: “The objects in any may-Co set of MC are placed in the arena”; §16.2 hidden pointer and §16.4 memory | bp-qql |

The sole gate deferral is fp-rot-fastmath-reassoc (L5; bp-7ni), printed on every
run. The two ABI-v0 runtime blockers and G0/G1 ambiguity are resolved at the new
pin (bp-c2i/bp-p26 closed); the CMake validation bead bp-ahz is closed.
Full N0–N35/V1–V16, entry-state replay, comparison link and frontend envelopes
remain scheduled. General Grover over unmodified SQLite stays the core target.
