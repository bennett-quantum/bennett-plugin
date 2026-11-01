# Progress

History before 2026-10-31 and per-pass evidence: `git show de4fe2c:docs/PROGRESS.md`.

## Resume

Contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8** (pinned in
`SPEC_VERSIONS.toml`; the gate checks the pin). State: **M1 complete on the plan's definition**
(2026-10-31, `docs/PLAN.md`). Resume: **bp-9fo closed after one full dual-major gate; next bp-bux (§14.8 CC switch)**; bp-7ni stays outside this pass.
Separate CC callees preserve typed pointer/integer operands, returns, nested/recursive frames and shared memory (§14.1/§17.4).
Two probes per major pass eight complete-state reversals and four small-budget CC vectors (§9.3: outside-region CC is unbounded).
Fresh published-runtime/arith links pass S1–S5 then stop at §14.8 switch on both majors (bp-bux); conditional rung-2 gate not run.
Gate exit 0: 66/66/0/0/0 each major; recognised/materialised hashes and execution evidence are in docs/verification.json.
Obligations live only in bd (`bd list`).

Build and gate (headless, rule 11), repo root:
- Push gate: `env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER scripts/pre-push` gates the
  pushed sha (HEAD when run directly) in a detached worktree `.tmp/gate-<sha>` and removes it. `scripts/gate` runs
  the same sequence in the current tree (iteration only): build, smoke, gate_policy, contract_policy, per major 18
  and 23 recognition, analysis_edges, analysis_performance, reference_images, materialisation, aggregate_rows, allocator_closure, cc_calls, region_keys, scalars, descriptors,
  production and production_{environments,dispatch,shapes,budgets,records}, then budget_stage (five cases, four proof refusals and 316 prefixes), production_cross_major, prior_objects, corpus_gate. The gate also runs the full key audit with explicit bd accounting and independent V1–V16 validation.
  Siblings `../bennett-isa-spec` (reference CLI) and `../bennett-dialect-spec` (corpus); `BENNETT_SIBLINGS` overrides.
- Evidence of the latest pass: `docs/verification.json` (`scripts/record-verification.py`).

Counts (LLVM 18 and 23, each): legality gate **66 run / 66 agree / 0 deferred / 0 blocked / 0 diverge**
(924/924 cells on 18, 792/792 on 23); analysis_edges 20/20 and analysis_performance 3/3.
Allocator closure: 4/4 probes per major, 11 CC vectors and five full-state reversals, with recognised/materialised hashes.
Aggregate rows: 3/3 cases, 15 L vectors and 3 CC launches per major, with recognised/materialised hashes.
CC calls: 2/2 probes per major, eight full-state reversals and four small-budget CC executions (§9.3), with recognised/materialised hashes.
All 297 prior object hashes preserved; 299 equal object pairs, 45 published matches.
Both recorded hashtable modules reach the S2 fixpoint in 64 rounds (5.79s/5.64s for 18/23).
Complete suite counts and linked-pipeline evidence: `docs/verification.json`, `docs/rung2-analysis.json`.

## Passes

### Pass 1 - 2026-10-30 - 4ef1e0c..3be37ba
Pinned dialect 0.2.x drafts and ISA 0.8; PLAN; one source tree building plugins for LLVM 18 and 23.
All 23 ABI 0.2 markers recognised with section 22 diagnostics; section 4/5 device fixpoint, section 6
bitwise handle provenance, section 7 region identity. Independent headless legality gate: 66 cases, 63 agree.
Nine scalar reference objects matching published hashes. M1 stayed open (analysis audit, production).

### Pass 2 - 2026-10-30 - f7e1b1e..716df23
Re-pinned to dialect 0.2.7; gate classifies `deferred` and `blocked-upstream` loudly (66/63/1/2/0).
Eleven scalar objects byte-exact on both majors (added atomic-nand, fp-aggregate); scalar global images,
reference shapes from ABI descriptors, descriptor-reference inc8. Filed bp-c2i (ABI v0 runtime), bp-p26 (G0/G1).
CMake 3.28.3 installed afterwards; superbuild verified.

### Pass 3 - 2026-10-31 - e1e06b8..2d5f323
Pinned accepted dialect 0.2.10 @ 023f5a7; blockers bp-c2i/bp-p26 resolved at the pin; gate 66/65/1/0/0.
Published indirectbr object and fault vectors reproduced (12 exact objects, 73/74 recognition examples);
scalar materialised closure keys, symbolic zero extents, fixed-vscale bitcasts; 12 analysis regressions.
Drift check requires consistent accepted version, commit and content. Recorded in `2d5f323`.

### Pass 4 - 2026-10-31 - 95fa83f, 91a0d7d
Analysis regressions 12 to 17 and six represented-address witnesses per major; 14/15 published
materialisation fixtures and 14/15 key assertions. Fixes: narrow-index GEP wrap, width-changing provenance,
PT3 address spaces, PT8 helper spellings, pointer xchg/N9 unions, undefined shuffle masks, repeated N14.
All-fixture key audit left red at 18/49 (LLVM 18) and 19/50 (LLVM 23): bp-3w4. Filed bp-tr5.

### Pass 5 - 2026-10-31 - 384dd54, c91c288, a2bce18
Four device-binding lifts byte-exact on both majors (binding-out-byte, clock-read, block-byte, console-byte)
with independent check/hash and five run vectors: OUT allocation/delivery, CLOCK/BLOCK/CONSOLE prologues.
Fixed pre-push under git push (inherited GIT_DIR, bp-zk2): `push --dry-run` exit 0 after the full gate.
Production scalar launch still red at that point (exit 1 at CC/marker lowering).

### Pass 6 - 2026-10-31 - bc14d48, 563ca6a, 32427ed
Scalar descriptors lowered to executable CC launch objects and host ABI stubs on both majors; measured inc8
(0, 7, 255), published-oracle inc8 and integer-ABI launches check and run via `run-program`.
Native integer ABI attributes preserved in launch stubs; native mock protocol checks pass.
First gate invalidated by a plugin digest change during the corpus run; clean rerun 66/65/1/0/0
(the recorder keeps its `plugin_sha256` digest check).

### Pass 7 - 2026-10-31 - 55d3b0d, ba7f0d8, c8b477b, c9b1b7d
Production OUT/MEM_IN and CLOCK/BLOCK/CONSOLE bindings, distinct scalar references sharing a layout,
direct handle block parameters (7 objects). JCS budget tables with per-component precedence and frozen
maxima (4 objects; published sstack vector left red: bp-piq). Artifact inventories and instruction coverage
sidecars (5 cases). Gate 66/65/1/0/0 before and after; 51 object pairs byte-equal across majors.

### Pass 8 - 2026-10-31 - a8a2d81, 5d8d1f9, 8e49ae0, 8e8118e, de4fe2c (bp-dw4)
Runtime integer descriptor kind/mode trees and ARG carriers (a8a2d81); entry-local memory handle files with
retired-tag traps (5d8d1f9); combined devices, null console, multiple/256-bit outputs (8e49ae0);
heterogeneous layouts and relocated globals (8e8118e); sole-INOUT pairs with exhaustive inverse check and
budget checks (de4fe2c). Gate 66/65/1/0/0 before and after; 97/97 object pairs byte-identical across majors.

### Pass 9 - 2026-10-31 - af8f31e, d5b8904, f9956c6 (bp-kv5 closed)
General descriptor memory reads across blocks/loops and selected/phi/global descriptors; candidate compare trees.
Finite allocation/handle widths, memory sizes and device models dispatch by §8.4/§14.2; runtime CLOCK arguments.
LLVM 18/23: 23 dispatch cases and 55 vectors each; four published binding objects byte-exact through production.
One final gate exit 0, 66/65/1/0/0 each; no new deferrals; 198 equal object pairs, all 97 prior hashes unchanged.

### Pass 10 - 2026-10-31 - d6f39b9..de2e44a (bp-311 closed)
Closure-wide lifting: direct/recursive/indirect calls, alloc/free, SCC identity, explicit replay and comparison-layout inputs.
entry-replay-byte, rung4-mini, rung8-mini, listsum and entry-stack byte-exact on LLVM 18/23; all 30 new vectors match.
N24 static/dynamic frames, idempotent init, zero fill, logical bounds and save/restore; nine stack cases and a production launch per major.
Receipt caught an unused ENTROPY prologue byte drift; restored it and added prior-object preservation to the gate before the corpus.
Final gate exit 0, 66/65/1/0/0 each, no new deferrals; 222 equal pairs, 40 published matches, all 198 previous hashes preserved.

### Pass 11 - 2026-10-31 - c63c721 (bp-piq closed)
§9.2 provisional baseline generation, one identity overlay and fresh final generation share frozen maxima; tokens retain both identities.
§17.3 private single-frame bookkeeping proof; contained program accesses; H16→H32 objects byte-exact on LLVM 18/23 against pinned-checker goldens.
Five staging cases, four unsafe-proof refusals and all 316 row-budget prefixes per major; published final run code=0, payload=7, steps=316.
One final gate exit 0, 66/65/1/0/0 each, no new deferrals; 232 equal pairs, 45 published matches, all 222 previous hashes preserved.

### Pass 12 - 2026-10-31 - 88649d6, d946f36, 58b7817, 540d57a, 1f45b38 (bp-3w4 open; bp-tye closed)
PT2 finite Cartesian modulo-I GEP images and exact bound intersections, PT12 wrap unions, explicit scalar-entry seeds; reference_images 10/10 per major.
N21 packed i24 memory and bitcast geometry: materialisation/keys 17/17 on LLVM 18, 18/18 on 23; independent V1–V16 reader 46/46 each.
Full raw key audit 18/49→21/49 and 19/50→22/50; all 28 unequal witnesses have determining-sentence beads; raw audit stays red, no completion claimed.
Final gate exit 0, 66/65/1/0/0 each, no new deferrals; 232 equal object pairs, 45 published matches, all 232 previous hashes preserved.

### Pass 13 - 2026-10-31 - 8511b3a..d592014 (bp-3w4 closed under explicit audit-accounting exception)
PT2/PT5 symbolic finite and wide images, PT8 partial copies/PT12 opaque transfers, and host/device boundary seeds; reference_images 23/23 per major.
N21 VP/vector and N27 integer expansions; indirect/helper/thunk closure keys 31/31 on LLVM 18, 32/32 on 23; automatic L validator 49/49 each.
Full raw key audit 21/49→26/49 and 22/50→27/50 stays red; all 23 remainders per major have exact determining sentences and concrete reasons in open bd owners.
Final complete gate exit 0, 66/65/1/0/0 each, no new deferrals; 232 equal pairs, 45 published matches, all 232 previous hashes preserved; earlier boundary/pruning failures fixed.

### Pass 14 - 2026-10-31 - 40439e3..f45bdc1 (bp-2mg closed)
Automatic CC whole-memory, complete allocation-history and handle snapshots; concat preparation, ordered replay, logical-state adoption and clean 128-bit xor128 release.
LLVM 18/23: 11 production witnesses and 14 vectors each, including dead/zero/address-only histories, multiple entries, saved-point roundtrips and pop/restore faults.
Exact wildcard-union canonicalisation removes restore analysis blowup; stopped a partial gate to add conservative dependency guards; published replay bytes unchanged.
Final complete gate exit 0, 66/65/1/0/0 each, no new deferrals; 260 equal pairs, 45 published matches, all 232 previous hashes preserved.

### Pass 15 - 2026-10-31 - 31612b6, 399cf40, 3d41121 (bp-7ni blocked; bp-xms staged arith edge)
Seven FP carriers, N16 unfused fmuladd, i128/wide slots, N33 routing, FP atomics and private S2 graphs; all eleven FP materialisation/key witnesses match on LLVM 18/23.
Pinned arith publications close native comparison: fp-rot-fastmath-reassoc agrees in all 26 cells; 84/87 FP checks include one explicit real-production N22 refusal per major, never numerical production closure.
Stopped incomplete gates for a red→green host-initializer regression and the mid-pass arith publication; remaining production/staged obligations and determining sentences are only in bd; HANDOFF untouched.
Final complete gate exit 0, 66/66/0/0/0 each, zero deferrals; 263 equal pairs, 45 published matches, all 260 prior hashes preserved.

### Pass 16 - 2026-10-31 - b1d55f1, 05fb69c, dc2fe4c (eighth M2 pass; bp-9m8 closed)
N22 limb select/phi, carry/borrow, bitwise/icmp/casts, function ABI, nonbyte/aggregate memory and N21 packing; integer-only mul/div/rem/shift slot runtimes; 110/110 N22 families per major including ISA execution and faults 5/6.
Published n-wideint/n-wide-sub materialisations and keys match; initial full gate caught eight stripped-name identity crashes per major, fixed with tracking handles and a red→green regression in dc2fe4c.
Pinned real arith production passes select i512 and reaches different rules; exact N26/N27 production and remaining soft-float obligations stay only in bp-w2b/bp-jx3/bp-7ni/bp-xms; HANDOFF untouched.
Final full gate exit 0, 66/66/0/0/0 each, zero deferrals; 264 equal pairs, 45 published matches, all 263 prior hashes preserved; latest receipt in docs/verification.json.

### Pass 17 - 2026-10-31 - 7ac69c1..637afd4 (ninth M2 pass; bp-jx3/bp-w2b closed; bp-7ni blocked)
N27 arithmetic, twenty intrinsic runtime families and wide-slot ABI: 472/547 families on LLVM 18/23; published materialisations 36/36 and 37/37, keys 47/47 and 48/48 including both wide-intrinsics roots.
N26 memmove/memcpy/memset closure, inline/atomic/pattern lowering and logical faults: 33/34 native/ISA/key families; LLVM23 N3 range-list attributes removed before residual validation.
Real arith LLVM23 L numerical vectors pass; exact production/CC/publication obligations remain only in bd. Initial gate stopped incomplete at the 600-second full-width CC probe; HANDOFF untouched.
Final complete gate exit 0, 66/66/0/0/0 each, zero deferrals; 288 equal object pairs, 45 published matches, all 264 prior hashes preserved; latest receipt in docs/verification.json.

### Pass 18 - 2026-10-31 - bp-au6 closed
Exact additive closure through PT3 copies, finite-product caching, indexed slots and nested-zero-image unions remove the S2 blowup; K=4096 unchanged.
Recorded hashtable: >300s→5.79s LLVM18, >300s→5.64s LLVM23; 64 rounds each, iteration/time budgets diagnose rule and AV element.
Both published-runtime/pinned-arith links plus lto<O3> reach S1–S5 (11.23s/13.13s); next production rule is §17.4 malloc, filed bp-tav.
Final full gate exit 0, 66/66/0/0/0 each; 288 equal pairs, 45 published matches, all 288 prior hashes preserved; one earlier gate stopped incomplete for vector-store caching.

### Pass 19 - 2026-10-31 - 56eadb7 (bp-1us closed)
Depth-first field locations, unchanged-field aliases, flattened parameters/edge moves and packed direct/indirect call results/nonconstant returns implement §16.4.
N25 hidden return pointers precede N22; nested projections and aggregate phi/select/freeze field shells preserve i129 top widths and loop-carried values.
Three recognised/materialised/verified probes per major: 15 L vectors + 3 numerical CC launches; pinned real-arith L production passes five vectors on both majors (softfloat 90/90 and 95/95).
Final full gate exit 0, 66/66/0/0/0 each; 297 equal pairs, 45 published matches, all 288 prior hashes preserved; one incomplete gate stopped for wide aggregate phis; bp-7ni untouched.

### Pass 20 - 2026-11-01 - 0f90deb (bp-tav closed)
Linked malloc/calloc/free/memset bodies expand into CC CFGs down to alloc/free and byte operations (§19.1/§17.4); dead/zero histories and zero-fill remain explicit.
N27 overflow field projections, dominator-first CFG emission and allocator-only memory layouts support both published majors; new allocator faults use §11.5 code payload then trap.
Four runtime-SHA/arith-SHA-pinned probes per major pass 11 vectors and five complete-state reversals, with recognised/normalised/materialised hashes and independent check/hash.
Recorded and freshly compiled hashtable links reach S1–S5, then production stops at `tail call fastcc void @ht_third_pass(ptr %3, i64 %0)` on both majors; filed bp-9fo (§14.1); conditional rung-2 gate not run.
One full scripts/gate exit 0: 66/66/0/0/0 each, 924/924 and 792/792 cells, 297 equal pairs/45 published matches/all 297 prior hashes preserved; bp-7ni untouched.

### Pass 21 - 2026-11-01 - 680ea61 (bp-9fo closed)
Direct CC call/ret closures preserve typed pointer/integer arguments, pointer/integer/void returns, shared memory and nested/recursive frames (§14.1/§17.4; ISA §4.1/§7.4).
Two probes per major cover nested fastcc calls, loops, mutual/root recursion and heap/global restoration: eight complete-state reversals and four unbounded CC vectors (§9.3), with recognised/materialised evidence.
Fresh marked-C -> published runtimes + pinned arith -> lto<O3> passes linked S1–S5, then production stops at §14.8 switch (%104/%113); filed bp-bux; conditional rung-2 gate not run.
One full gate exit 0: 66/66/0/0/0 each, 924/924 and 792/792 cells; 299 equal object pairs, 45 published matches, all 297 previous hashes preserved; bp-7ni untouched.
