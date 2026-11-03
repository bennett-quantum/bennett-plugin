# bp-fj1: non-reference analysis measurements on the rung-4 SQLite closure

Status: historical implementation evidence from `rung4-plugin` (2026-11-02), corrected after
council `plugin-bpfj1-2026-11-03` round 1, B1/B2, and advisor R16 (2026-11-03).

**The D-series runs used an additional non-reference closure after 4096 pointer offsets per
provenance. Their logged sizes and timings describe that solver configuration, not the exact
§5 reference least fixpoint. K bounds INT atoms only; no objects×4096 pointer-atom cap follows
from the spec.** This closure was active even without `-bennett-analysis-early-chain-close`;
bp-ipp fixes that default-path bug. The F-series adds further NON-REFERENCE closure rules.
The measurements are retained with corrected labels; no corrected-default SQLite run has
been made for this revision. Option A is adopted; the published dialect K is unchanged.

## 1. Setup

- Program: the rung-4 N16 closure of unmodified SQLite as the plugin's analysis sees it,
  `.tmp/rung4/mod/post-18.ll` in this checkout (sha256 prefix c5b5961480542e34; 1,487 defined
  functions, 285,525 instructions, 36,807 seed slots), LLVM 18, `lto<O3>` with the vectoriser on.
- Command (`.tmp/rung4/sq2.sh 18 <seconds> <tag>`): `opt -passes=bennett -bennett-dialect=0.2.10
  -bennett-analysis-only -bennett-analysis-trace -bennett-analysis-budget-ms=<s*1000>
  -bennett-analysis-max-rounds=100000000`, `ulimit -v 14000000`, under `perf record -F 29`.
  NON-REFERENCE F-series runs add `-bennett-analysis-early-chain-close`; the historical
  flag-off D-series was also NON-REFERENCE because of its unconditional pointer closure.
- Shared host: 12 cores, 30 GB, load 10 to 30 during these runs. Wall times are therefore upper
  bounds; user time is given where it matters.

## 2. Solver work in the measured configuration (historical flag-off, NON-REFERENCE)

The speedups were checked with `-bennett-analysis-check-delta` and `tests/load_delta.py`:
incremental PT6 results agreed with full passes of the same explicit engine. These checks do
not establish that the engine's pointer closure implements the reference least fixpoint.

| sha | change | effect on the measured closure configuration |
|---|---|---|
| c6b1902 (K0) | before this shift's speedups | 1500 s: round 1 at position 131,735 of 285,525 |
| 44f50aa (D1) | PT6 per changed slot instead of per object version | 1500 s: round 1 at 94,340 (load ~28; ROOT re-interning now 28% of the profile) |
| 885e84a (D2) | partial-overlap ROOTs as one cached set | round 1 complete at 789 s; budget hit in round 2 |
| 0317dcf (D3) | same for PT8; unions adopt their first set | round 1 at 410 s; round 2 complete at 1,407 s; then out of memory |
| afaa89c | constant images per atom; PT8 source lists only when used | not yet measured on the closure |

D2 and D3 reach the identical recorded state after round 1 (1,408,583 slots, 391,155,526 slot
atoms). Agreement between these NON-REFERENCE runs does not repair their reference mismatch.

## 3. Partial D-series states on SQLite (NON-REFERENCE; no reference-size conclusion)

| run | after round | slots | slot atoms | value atoms | largest value |
|---|---|---|---|---|---|
| D3 (NON-REFERENCE) | 0 | 56,312 | 360,391 | 1,754,887 | 2,429 |
| D3 (NON-REFERENCE) | 1 | 1,408,583 | 391,155,526 | 56,176,749 | 493,295 |
| D3 (NON-REFERENCE) | 2 | 2,643,733 | 1,210,304,346 | 138,617,196 | 247,338 |

D3 then aborted in round 3 with signal 6 at RSS 13.7 GB (the 14 GB address-space limit), 1,965 s
wall, 1,653 s user. Single objects held 92,538 slots and 81,178,844 atoms (`%3` and `%4` in
`@syncJournal`, `@syncJournal.zerobyte`, offsets [-40, 10256]).

The observed blob motivates an exact factored representation. The following describes the
measured implementation's propagation, not a derivation that all this growth is spec-forced:

- A sampled large value after round 1 is close to a product over 288 objects with roughly
  1,820 offsets per object. One of them is
  `%2 = alloca i64` in `@pagerOpenWalIfPresent`. Its only escape is `%38 = call i32 %37(ptr %32,
  ptr %2)`, an `sqlite3_io_methods` call. Once AV(%37) is ⊤ (the method pointer is loaded from
  memory the merged pointers already reach), §14.2 makes every address-taken function of type
  `i32 (ptr, ptr)` a candidate, and PT9 binds `%2` to the second parameter of each.
- PT2 is flow-insensitive and applies to every atom of the address. Every field offset used on any
  pointer in the merged set therefore reaches every object in it. That is 1,820 offsets per object
  by round 1, more than 10,000 by round 2, and each offset becomes a slot when stored through.
- §5.1 bounds INT atoms by K = 4096 only. The D-series additionally closed a provenance after
  4096 pointer offsets, replacing them with a residue summary plus EXT/top. This is an
  unauthorised widening, not a reference bound. Pointer offsets may be compressed exactly;
  pointer-offset sets and memory intervals have no additional cardinality cutoff. Neither
  the exact reference sizes nor the reference fixpoint were measured by these runs.

The council's sol B1 witness isolates the bug without a displacement cycle: an internal
8192-byte constant array of ones, an internal `sink(ptr p)` that loads i8, and an internal
action entered through `__bennett_adj` calling sink at offsets 0 through 4096. Both 4096 and
4097 calls must be accepted with the exact in-bounds offsets, load result `{INT(1)}`, and
`top=false`, with no EXT/residue introduced by cardinality. The regression is in
`tests/reference_k.py` and registered in `tests/analysis_edges.py`.

## 4. Additional experimental closure rules (NON-REFERENCE, `-bennett-analysis-early-chain-close`)

In addition to the historical 4096-pointer-offset closure, this NON-REFERENCE flag closes an
offset chain past 4 offsets outside the object's literal extent, or past 32 offsets of an
object with no literal extent. It also collapses an object past max(64, extent/4) store-created
slots. Accepted 5u3 does not authorise these rules. After bp-ipp, the 4096-pointer-offset
closure is also restricted to this default-off NON-REFERENCE flag.

| run (NON-REFERENCE) | result |
|---|---|
| F1, 7e5c640 (before this shift's speedups) | round 2 at 5,880 s wall, no fixpoint |
| F2, 0317dcf | **fixpoint**: "S1-S5 complete" in 64 rounds, 1,231 s of analysis, 1,279 s wall, 1,255 s user, RSS 2.5 GB; 186,351 slots, 28,306,064 slot atoms, 110,805,551 value atoms, largest value 4,294 |

F2's rounds 11 to 64 each re-ran the same four steps and added two value atoms per round. This
suggests a cycle to investigate for exact acceleration, but these logs prove neither the
5u3 acceleration preconditions nor agreement with the reference result. F2's completion is
completion of that NON-REFERENCE configuration, not rung-4 production acceptance.
F2 completed one pre-production S1–S5 analysis. It establishes neither post-normalisation
convergence nor zero-fault execution across majors and database sizes. The later production
attempt recorded in bp-fj1 timed out during its second analysis.

## 5. Assessment

- With the measured explicit-atom implementation, D3 exhausted its recorded resource limit
  before convergence: round 2 held 1.2 × 10^9 slot atoms. F2 reached its NON-REFERENCE fixpoint
  in about 20 minutes and 2.5 GB. These are costs of those configurations; they establish
  neither an exact-reference size nor a general complexity or production-completion bound.
- The observed blob is close to a product,
  objects × offsets with the same offsets for every object. A factored representation (an object
  set times an offset set, with slots for object-set × offset-range regions) could hold it
  exactly and compactly. Such an engine is a redesign of PT2/PT6/PT7/PT8, not a tuning step. It is
  unproven that its stores and loads stay below the product size, because PT6 still distinguishes
  each overlapped slot.
- §7.2 candidate sets and §8.4 dispatch domains must also be preserved exactly. A value with
  10^5 to 10^6 pointer atoms does not imply that many region candidates or descriptor shapes:
  candidates depend on FN/top and address-taken functions, while shapes depend on their
  specified fields. Their exact production sizes remain to be measured. See the
  [factored-engine design](../design/factored-points-to.md) for separate analysis and output costs.

## 6. Adopted Option A (advisor R16; no dialect semantic amendment)

Retain the §5 reference analysis and the accepted 5u3 interpretation. K=4096 applies only to
INT atoms, not to pointer-offset sets or memory intervals. The normative result remains the
exact §5 least fixpoint. Implementations MAY use exact symbolic sets, factored/shared interval
relations and qualifying SCC acceleration instead of enumeration, only while preserving
finite-width address images, explicit ROOT/FN
alternatives, storage intervals, representation widths, reference verdicts, candidate sets
and dispatch domains. Analysis acceleration changes representation only, not instruction
transfers. An implementation resource cap reports unfinished analysis with the exhausted
resource and leaves completion of the build as an implementation obligation; it does not
reject the source program or introduce a run-time fault on a valid input.

No Option B bounds and no Option C precision change are adopted. Unmodified SQLite remains
required. All non-exact closing, including the historical 4096-pointer-offset rule, remains
a NON-REFERENCE experiment. This is an implementation-only route under published §5.1 and
5u3; no new dialect version or normative K change is requested.
Option A changes no normative reference object, F_B, hash, lifting-map definition or ISA
catalog entry for unchanged program, shape, layout, mapping and budget inputs. Repairing
an implementation bug can change previously incorrect outputs; regenerate affected objects,
budget bindings and certificate/resource evidence rather than treating the old output as
the reference. Any future normative closing proposal would require its own compatibility
version and matching consumer pins, not a same-version semantic repair.

Council sol B2 demonstrates why preserving ROOT names without their storage intervals is
insufficient: in an 80-byte object, a handle stored at offset 0 must not contaminate a disjoint
i64 counter at offset 8 after 63 byte stores at offsets 16 through 78 and a repeated handle
store. The reference accepts, `ROOT(n)=empty`, `AV(n)={INT(0),INT(3)}`, and
`AV(next)={INT(1),INT(4)}`. The NON-REFERENCE collapse falsely rejects its ordinary arithmetic.

The plugin will build the exact factored/symbolic engine described in
[the design note](../design/factored-points-to.md). Its duration and completed SQLite resource
use are unknown; it is the rung-4 critical path under bp-fj1. The design requires sol xhigh
review before engine implementation starts (R16 / policy rule 5). Exact-engine implementation
and rung-4 production acceptance remain open; this note is not either acceptance claim.

## 7. Fat object (bennett-4ht)

Option A does not change the host/device boundary. A mixed fat object retains a native host
binary plus ISA objects for selected marked device roots and their complete linked direct
and indirect-candidate closures, including unmarked library callees. §5 also analyses host
functions exchanging pointers or shared globals with those closures; PT11 supplies the
specified boundary seeds. Native entry, argv/envp and host-only libc remain outside the
device certificate inventory. Mixed packaging does not itself guarantee a smaller analysis
closure. Object/root/certificate association, launch bindings, budget/handle/tape lifetime,
and general host-memory-by-reference mapping remain the explicit bennett-4ht obligations in
`bennett-isa-spec/docs/notes/2026-11-02-rev2/fat-object-scope.md`. Factoring must retain their
per-root identities and must not require whole-binary device lowering.

## 8. Artefacts

`.tmp/rung4/prof/trace-{K0,D1,D2,D3,F2}.log`, `perf-*.data`, call-graph samples
`cg-{D2,D3,F2}-N.data` with `cg-*.index`; `.tmp/rung4/logs/sq-*.out`. Not committed (size).
