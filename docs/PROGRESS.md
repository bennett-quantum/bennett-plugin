# Progress

History before 2026-10-31 and per-pass evidence: `git show de4fe2c:docs/PROGRESS.md`.

## Resume

Contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8** (pinned in
`SPEC_VERSIONS.toml`; the gate checks the pin). State: **M1 complete on the plan's definition**
(2026-10-31, `docs/PLAN.md`). **M2 descriptor dispatch, the published replay/lift inventory and staged shadow-stack budgets are complete (bp-kv5, bp-311 and bp-piq closed);** next work is `bd ready`. Obligations live only in bd (`bd list`).

Build and gate (headless, rule 11), repo root:
- Push gate: `env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER scripts/pre-push` gates the
  pushed sha (HEAD when run directly) in a detached worktree `.tmp/gate-<sha>` and removes it. `scripts/gate` runs
  the same sequence in the current tree (iteration only): build, smoke, gate_policy, contract_policy, per major 18
  and 23 recognition, analysis_edges, reference_images, materialisation, region_keys, scalars, descriptors,
  production and production_{environments,dispatch,shapes,budgets,records}, then budget_stage (five cases, four proof refusals and 316 prefixes), production_cross_major, prior_objects, corpus_gate.
  Siblings `../bennett-isa-spec` (reference CLI) and `../bennett-dialect-spec` (corpus); `BENNETT_SIBLINGS` overrides.
- Evidence of the latest pass: `docs/verification.json` (`scripts/record-verification.py`).

Counts (LLVM 18 and 23, each): legality gate 66 run / 65 agree / 1 deferred / 0 blocked / 0 diverge
(cells 920/924 on 18, 788/792 on 23); recognition 73/73 on 18, 74/74 on 23; analysis_edges 17/17; reference_images 6/6;
materialisation and region_keys 14/14 on 18, 15/15 on 23; 22 scalar objects byte-exact with 70 run vectors; 232/232 object
pairs byte-identical across majors, 45 equal to published fixtures; all 222 prior hashes preserved.
Descriptor dispatch: 23 cases / 55 vectors per major. Budget staging: H16→H32 byte-exact,
316/316 step-budget prefixes and the published 316-step vector per major. Full object sizes, hashes and goldens are in
`docs/verification.json` (latest pass only). Sole deferral:
fp-rot-fastmath-reassoc (bp-7ni).

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
