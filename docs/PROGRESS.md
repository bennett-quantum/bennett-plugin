# Third pass — 2026-10-31 (M1c, in progress)

Accepted contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**;
ISA **0.8**. Round-8 freeze receipt: spec SHA-256
`d4f3c1a88391cc147f8c8fa4f80f82852e3ebe6f880610fc16cd5151f33d7206`.
The sibling worktree is draft 0.2.11; it is not the accepted compatibility unit.
The drift gate checks the accepted-release registry and pinned blob digest, and
reports working draft/HEAD differences separately. Cases, header, opaque harness
and runtime now come from one immutable commit, with a pin-specific baseline cache.

## Observed behavioural changes from 0.2.7

- §5.2/PT1/PT6: alloca and allocation-site zero initial images survive stores.
  `pt6-zero-stack` and `pt6-zero-heap` now give raw/idx `{0,1}`, widths `{1,3}`;
  the old analysis omitted zero (and opaque `free` incorrectly tainted heap bytes).
- PT8: clipped byte-image copies carry zero into a nonzero-initialised global;
  `pt8-zero-copy` now gives the same `{0,1}` / `{1,3}` domains. Full interval
  stores still union with these initial bytes.
- PT3: equal geometry copies lanes; changed geometry packs/resegments bit patterns
  in DataLayout order. The earlier pass already passed byte-lane 257/256/unpack3;
  this pass fixes sub-byte bit positions and constant-expression bitcasts and
  checks Cartesian lane alternatives (257/258/513/514), little and big endian.
- PT10/N15: out-of-range dynamic extraction contributes zero; published lane-zero
  width domain changes from `{2,4}` to `{1,2,4}`.
- PT4/PT5: the new wide-wrap witness exposed an APInt assertion on a 2^64
  displacement. Low pointer-width modular displacement now retains the table
  candidate instead of crashing. General represented-address images remain M1.
- map 0.2.9/§16.3: globals are 1-based; atomic-nand's G0 becomes G1. Object
  and closure hashes change, while its payload 63/code0/16 steps stays equal.
- Zero initial images also reach descriptor allocas. Reference emission uses an
  independent local reaching-store proof at the call rather than deleting zeros
  from normative S2 domains; ambiguous paths retain explicit unimplemented errors.
- The pinned harness now selects ABI 0.2 for spec-sem2-adj/compute; both former
  exit-87 upstream blockers execute successfully and become agreements. Historical
  ABI-v0 cases remain unchanged. No EXPECT line was edited.
- N33 own-format libm carrier corrections are part of the pin; arithmetic/helper
  closure materialisation remains explicit M2 work, not claimed implemented here.

## Symbolic extents and fixed-vscale bitcasts

Two extra audit checks were red (10/12) then green **12/12 per major**:
zero-byte symbolic initial extents now cover the full represented address domain,
including the read beyond 2^60 that exposed a finite internal cap; widened interval
arithmetic prevents signed overflow in overlap/containment and clipped copies.
Scalable vectors use the prescribed fixed-vscale=1 lane geometry during S2;
`<vscale x 2 x i8>` to `<vscale x 1 x i16>` now packs to 256. Pointer integer
addition/subtraction uses APInt modular arithmetic rather than C++ signed overflow.
These regressions do not close the remaining general PT2/PT4/PT5 image audit.

## Materialised scalar region keys and N15

Keys now run the implemented scalar normalisation slice on a private cloned
closure before stripping/printing. Red 1/3 → green 3/3 per major: nsw/plain
closures have equal keys, freeze/plain closures have equal keys, and original
H IR retains its flags/freeze. The existing name/global-image smoke checks pass.
This fixes scalar keys; it does not claim all N0–N35/V1–V16 closure keys complete.
N15 constant totalisation plus constant lane renaming reproduces the complete
`n-constant-lane` instruction lists on both majors (materialisation 5/5).
LLVM23 branch emission uses CondBrInst/UncondBrInst; clean incremental builds
produce no deprecation warnings and the reference object text is unchanged.

## Additional scalar map delivery

`indirectbr-two-blocks` was red as a required scalar object, then green on both
majors: complete untrimmed fixture bytes, all symbol hashes, `check`, and the
three published vectors (4096→7/9 steps, 4097→9/12, 4098→fault4/10).
§14.9 block ordinals use layout order and the comparison-layout backing global;
short domains use §14.2's linear leaf tree. Balanced large domains and general
comparison-link supplied layouts remain explicit M2 mechanics, not a rejection.
The complete supported-object count becomes 12, with eight lift fixtures still
explicitly unavailable. This does not complete brief 1b item 4.

## Before/after evidence

Stable 07f942c sources were rebuilt in `.tmp/before-build`; both majors reproduced
66 run / 63 agree / 1 deferred / 2 blocked / 0 diverge; the old pin-drift gate
exited 1. A first overlapping build/gate attempt was invalidated by the existing
plugin-digest guard and discarded; only the isolated rerun supplies these totals.
The first accepted 0.2.10 corpus run is 66/65/1/0/0 on each major (exit 0).
New domain assertions were red 4/7 then published recognition passed 73/73 (18)
and 74/74 (23). Constant-expression packing was independently red 1/8.

**M1 remains open.** No general audit, full materialised keys or production launch
completion is claimed by these checks. The earlier pass record follows for history;
its pin, runtime blocker, CMake and G0 statements are superseded by this section.

---

# Progress — 2026-10-30 (M1b)

**M1 remains incomplete.** Epic bp-a41 and its implementation tasks remain open.
No push. Contract: dialect **0.2.7**, **95c3cd332f5f72c07fd5f2515f328deaa40c08b9**;
ISA **0.8**. The authorized re-pin is committed; current published text/HEAD match.

## Verified implementation

- `scripts/build`: both major plugins build/load with llvm-config/g++; CMake is
  absent and its superbuild remains **unverified**, bp-ahz.
- `tests/smoke.py`: both majors, pre-link inert; all 23 header prototypes accepted
  and 23 malformed signatures diagnosed. Region keys ignore function names and
  retain referenced global images.
- `tests/recognition.py`: **63/63 LLVM 18**, **64/64 LLVM 23** published examples.
  `pt5-range` is explicitly published for LLVM 23 only. New assertions check
  `pt2-wrap` offset/candidates and both applicable PT5 witnesses' exact `{1,3}`
  sets. The load-!range assertion failed before removing erased range evidence.
- `tests/analysis_edges.py`: **4/4 per major**, from 1/4 before implementation:
  PT9 separate byval copy objects, PT10 equal-bit packed 2xi32→i64,
  PT12 finite integer-nand transfer, and ordinary host closure tiers. These
  witnesses do not establish the remaining general analysis cases below.
- `tests/materialisation.py`: **4/4 per major**. Instruction lists match the
  published `n-flags`, `n-shift`, `n-query`, `n-atomic-nand` outputs. The M1 scalar
  N1–N10/N14 slice is applied to a private module before reference lowering;
  `materialised.bc` is emitted. The original H module is preserved. This is
  not the complete N0–N35/V1–V16 normaliser/validator.
- `tests/scalars.py`: **all 20 published lift blocks are attempted**, with **11
  complete objects checked per major**, exact fixture bytes, explicitly compared
  published hashes, and **all stated run/budget/ARG vectors**. `fp-aggregate`
  adds FP carriers and padding-free constant aggregate returns; `atomic-nand`
  adds scalar global images, bounds checks, loads/stores and closure hashes.
  Plain C inc8 at clang O3 still reproduces the published object.
- `tests/descriptors.py`: a descriptor built by ordinary C stores using the ABI
  header derives the inc8 reference shape/object on **both majors**. Explicit
  `-bennett-descriptor-reference` is non-production; the same module in production
  mode still fails loudly at unavailable CC lowering. This does **not** close the
  production launch path. Device-binding syntax formerly fell through silently
  in the scalar shape parser; the all-lifts test exposed it and it now fails M2.

## Corpus gate and root causes

The authorized raw re-pin reproduced **66 run / 63 agree / 3 diverge** per major
before classification. `scripts/pre-push` now exits **0** on both majors, with:

| LLVM | Run | Agree | Deferred | Blocked | Diverge | Cells run | Cells agree |
|---|---:|---:|---:|---:|---:|---:|---:|
| 18 | 66 | 63 | 1 | 2 | 0 | 924 | 892 |
| 23 | 66 | 63 | 1 | 2 | 0 | 792 | 764 |

**Exit rule:** exit 0 only when every non-deferred, non-blocked case agrees,
with no pin drift. Deferred/blocked cases are separately counted, never agreements,
and printed with milestone/bead on **every run**. A new failing property, plugin
failure, changed ABI-probe exit, or missing check stays a real divergence, exit 1.
`tests/gate_policy.py` checks these mutation cases (seven assertions).

| Case | Property | Classification and evidence |
|---|---|---|
| spec-sem2-adj | L1/L5, all pipelines | **blocked-upstream: bp-c2i (b-dialect-spec-566)**; ABI 0.2 calls exit 87 with `FAULT host-segv` without bennett and after bennett, both codegen levels/majors |
| spec-sem2-compute | L1/L5, all pipelines | **blocked-upstream: bp-c2i (b-dialect-spec-566)**; same isolation and result |
| fp-rot-fastmath-reassoc | L5: default<O0>, strip, strip-nondebug, mergefunc | **deferred: M2 (§13 FP materialisation)**; fast-math survives and llc O0/O3 traces differ |

**ABI isolation:** local probe copies of each spec-sem2 case remove only the new
budget operand and use the v0 declaration. The **same untouched opaque runtime
binaries** then exit **0 at O0/O3 on LLVM 18/23**, versus **87** for the original
ABI 0.2 call. Null budget occupies the old runtime's env position. This isolates
an upstream ABI-v0 runtime, not a plugin rewrite. No corpus EXPECT was changed;
the probes never replace gate fixtures. Relay bp-c2i to the dialect editor.

**FP scope:** the failing case has sitofp i64 (the §13 rewrite uses i128), f64
multiply/add/divide and loop-carried FP arithmetic. It needs linked deterministic
soft-float helpers and their materialised call closure/native comparison build
(§13/§17.7), beyond the bit-exact carriers/packing verified by M1. M2 owns those
mechanics; removing fast-math alone would not satisfy §13.

The three negative attribute/dereference controls retain their stated diagnostics;
`c-pure-attr-wrapper` retains §3.8's source-effect-lie diagnostic. Region-twin
content identity remains recorded under bp-tye, not changed to symbol identity.

**Gate limits remain:** L1 is optimized pre/post plugin; L4 is key stability
across the plugin, not full cross-pipeline materialised comparison. Frontend
LTO/rustc/Julia envelopes remain open. A green gate with the explicit unavailable
counts is not full §21 conformance or M1 completion.

## Scalar objects and outstanding examples

These complete objects are byte-identical on both majors and to the pin. Full
object hashes, all symbol hashes and run vectors are in `verification.json`.

| Object | @ref interface hash |
|---|---|
| oracle-empty-output | `358a1b87139653df3c5a82465215f8af96a12d0e8ad02610e04696c2d588a91c` |
| oracle-empty-fault | `863fd42e300d5bba79d561ceca8c8b72ee1ad384d60f770d961cf25a8e258181` |
| oracle-discard-return | `622ca26e17519d6e64af5f64f8e0f9c3d9af6c5d36a97740de5d6cbc2b2f62f3` |
| atomic-nand | `c55111b84ee5e99801d9947547fcec2dbaf65dd0d76d4f8d61eb22f501c6da85` |
| pointer-as270 | `62693b6dfefab4480cce6de8257132bcc9fead16250518602c354083332dd16a` |
| gep-index-obj | `5b3c7d1f368fcc8c24286cc303a71c12b5b615f467149f29928099befd3de534` |
| gep-index-const | `591f1b48288e000c626c349165ead9ff9158c05c472c9c569bfec3dac42de091` |
| inc8 | `151baad5625b3605eadf87005a19ea6e012e4347d6dfe096dbc4edcf2b68b94a` |
| add2 | `5b4c6624e0f20b5d60780fd8f27056f3f7efd4d27b9d47af8a70c8126100a10a` |
| switch5 | `0575354a0ecceee58d8dfbcc5cb9a9b8851c5c2b3193bf543395bed13604ce80` |
| fp-aggregate | `1139edfe71a34500be515f3ff61380020ab781c254339eafbad172a94e095d69` |

The pin has **six spec-* corpus programs**, all quantum action/generation
programs (adj/compute/ctrl in ABI v0 and 0.2); there is **no scalar oracle
spec-* case to omit**. They all run in the legality gate; action-object generation
is M3. Their inventory is in verification.json.

Every remaining scalar-typed lift is explicitly attempted and reports unavailable
M2 mechanics. These examples have scalar signatures but exceed pure scalar
integer/FP-carrier lowering; they remain promised, not rejected:

| Example | Needed §16.4 rows / associated mechanism |
|---|---|
| binding-out-byte | wrapper OUT allocation/delivery; indirect buffer load/store (§8.2/§16.2) |
| binding-clock-read | device-state prologue/store and supplied comparison layout (§11.3/§16.2) |
| binding-block-byte | device state, load/store, linked helper calls (§11.3) |
| binding-console-byte | OUT-like device buffer/projections, loads/stores, linked calls (§11.3) |
| entry-replay-byte | snapshot/replay prologue, direct calls and mutable-global entry state (§8.5) |
| indirectbr-two-blocks | blockaddress encoding plus indirectbr compare tree (§14.9) |
| rung4-mini | MEM_IN, GEP/load/store, direct/indirect calls and comparison layout |
| rung8-mini | ENTROPY binding/prologue and linked model calls |
| listsum | primitive alloc/free, direct lift.call closure, heap memory and entry allocator state |

Two executed object-only integration vectors have no `llvm lift` source:
`arena-o1` needs TDL arena outlining/hidden pointer (M3); `entry-stack` needs the
fixed linked replay/adoption helper closure (§8.5/§17.3, M2). They are inventoried,
not claimed lowered or silently treated as completed scalar fixtures.

The previous pass exhaustively step-checked byte-identical inc8 and switch5 for
256 inputs each. These are retained historical results, not rerun claims; add2's
60-second exhaustive timeout remains disclosed (all its stated vectors pass).

## Remaining M1 and M2 entry point

- **M1 acceptance still open:** exact reference-analysis audit, general finite-width
  PT2 image/carry behavior; nonbyte packed lanes/composite operations; complete
  atomics/cmpxchg; exact host/boundary and generation-sensitive variant seeding.
- Fully materialised region keys, full legality materialisation/native-comparison
  checks and independent residual validation remain open. Current keys still
  precede the complete normaliser.
- **Production descriptor integration remains open.** Static extraction/reference
  output is implemented; CC launches, host entry replacement, final device objects
  and full §19.9 records/certificates remain unavailable. General M3 CC work must
  supply/pull forward the scalar launch path before this M1 obligation closes.
- CMake validation requires the maintainer to install CMake (bp-ahz).
- **M2 entry:** link and materialise §13 soft-float/native comparison helpers;
  finish N0–N35/V1–V16, lifted calls/memory, descriptor shape dispatch and entry-state
  replay; then execute the nine inventoried lifts. §9.2's 0.2.7 staged identities
  and frozen capacities are required with budget-table integration, not relabelled
  as already implemented.
- M3 generation/TDL/CC-R and bounded ISA blocker realisations; M4 whole-program
  integration/rungs 4–8; M5 ISA dependency removal remain unchanged in scope.

Upstream relay also includes **bp-p26**: §16.3 says global numbering starts G1,
but atomic-nand uses G0 and binding-clock-read uses G1. The starting index or
comparison-layout override must be stated consistently before general layout
integration. Existing supported fixture hashes are retained exactly.

All results are from published text/fixtures and black-box binaries. No sibling
checker/interpreter/runtime implementation was read and no sibling repository
was edited. No HANDOFF/worklog file was written by this implementation sub-agent.
