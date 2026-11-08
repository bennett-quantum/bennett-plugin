# bp-1bb production slice — independent rule-7 review, round 2

Reviewer: gpt-6.1-sol. Reviewed head: `9381e56bb143dfcf562de5600c9a70505a7f799f`; repair base: `8a709d7fe064569d030b9de7d9eb74c094eeaef9`; implementation base: `2319890511cdd2fa46b8c4cc748b52877408be6f`. Written: 2026-11-08T13:10:45Z.

**Disposition: ACCEPT with P2 beads.** The round-1 P1 is fixed. Independent reruns reproduce the old wrong result and establish the repaired result on both LLVM majors and both function orderings. No new P0/P1, regression, out-of-path implementation change or broken build was found. The two round-1 P2 follow-ups remain; this review makes no bead writes or code changes.

Read in full: this round's brief, COMMON.md, T3CHILD.md and repository CLAUDE.md. Started from the author's PROGRESS.md, prior review, red-first witness receipts and aggregate test log; inspected the complete repair diff. Authority is the gate-pinned dialect 0.2.13 at `1c29c8d73122`, not the live sibling. `contracts.drift()` is false. All new evidence and scripts are under `/home/tobias/Projects/bennett-workspace/bennett-plugin-job-s2-1bb-prod/.tmp/s2-1bb-prod-review2/`.

## Contract and per-link freeze

Pinned §12.5 says V is “the constant `vscale` of the link” and, for nonfixed ranges without an override, defaults to “the minimum of the `vscale_range` bounds”. It explicitly requires: “N10 replaces `llvm.vscale` by V and N21 scalarises the L·V lanes.”

Pinned §12.6 requires “one scalar instruction per lane” for elementwise instructions and names lanes `%nz.l<k>.v`. Pinned §16.4 states: “Rows of an instruction are emitted in instruction order within its block”, requires integer operands as `c<j> = lift.const.iW <unsigned decimal>`, and maps add/mul through `v = lift.<op> A B`. These are scalar lanes and concrete constants for one linked program: the two query functions cannot independently change V as earlier functions lose scalable instructions.

The repaired `normalisationVScale(Module&)` at Normalise.cpp:56 scans the complete module once, before N10/N21 or vector-ABI lowering, and records `bennett.normalisation.vscale` as a module flag. Later invocations reuse that snapshot. `normaliseScalar` selects V before `normalisePrelude`; N10 receives it explicitly, and `ScalarLanes` stores the same immutable value. `normaliseWideIntegerABI` freezes V unconditionally on entry, including when early signatures are scalar, and uses it for every scalable ABI shape. Clones preserve the module flag.

Private S2 transfer graphs select from the unchanged source module while excluding the temporary graph, or reuse an existing snapshot; they do not add metadata to source H IR. Malformed stored values fail loudly. The original fixed-range/override/minimum selection policy is otherwise unchanged.

For the two nonfixed ranges `vscale_range(2,8)` and `vscale_range(4,8)`, link V is 2. Thus `10*first()+second()` must return `10*2+2=22`. Reviewer receipts show both materialised functions using V=2, and the emitted module flag records 2, in both orders.

## Granted-path audit

`git diff --name-only 8a709d7..9381e56` lists exactly five repair files: Normalise.cpp, Wide.cpp, tests/sqlite_vector_normalise.py, and the two module-order fixtures under tests/fixtures/sqlite_vector/. **The repair changes only vscale computation, snapshot storage and its uses, plus direct regression tests.** It does not change GEP, fneg, extrema, reduction, PHI, boundary identity, dispatch or FP arithmetic semantics. There is no additional change requiring a returning Muse seat.

Every zero-context Normalise.cpp repair hunk is accounted for below. Coordinates are relative to repair base 8a709d7.

| Base hunk | Head hunk | Enclosing function/member |
|---|---|---|
| `-15,3` | `+15,13` | New `frozenLinkVScale`; selector split into `selectLinkVScale` |
| `-25,1` | `+35,1` | `selectLinkVScale`: exclude private graph |
| `-42,0` | `+53,9` | `normalisationVScale`: read/store snapshot |
| `-45,1` | `+64,1` | `normalisePrelude`: explicit V argument |
| `-236,1` | `+255,1` | `normalisePrelude`: N10 uses V |
| `-277,1` | `+296,1` | `ScalarLanes::vscale` immutable member |
| `-281,3` | `+300,1` | `ScalarLanes::laneCount` |
| `-580,1` | `+597,1` | `ScalarLanes::ScalarLanes` |
| `-650,2` | `+667,7` | `normaliseScalar`: choose once before prelude/lanes |

The two Wide.cpp repair hunks, `-268,1/+268,1` and `-271,3/+271,1` relative to 8a709d7, are both inside `normaliseWideIntegerABI` (the latter is its `laneCount` lambda). For the entire implementation, `git diff --unified=0 2319890..9381e56 -- src/Wide.cpp` still has exactly 13 hunks. Each lies inside the original granted **base 265–364**, not merely inside shifted head coordinates:

| Base hunk | Head hunk | Enclosing function |
|---|---|---|
| `-266,0` | `+267,14` | `normaliseWideIntegerABI` |
| `-267,0` | `+282,1` | `normaliseWideIntegerABI` |
| `-279,1` | `+294,15` | `normaliseWideIntegerABI` |
| `-281,0` | `+311,9` | `normaliseWideIntegerABI` |
| `-293,1` | `+331,1` | `normaliseWideIntegerABI` |
| `-298,1` | `+336,1` | `normaliseWideIntegerABI` |
| `-300,2` | `+338,5` | `normaliseWideIntegerABI` |
| `-305,1` | `+346,1` | `normaliseWideIntegerABI` |
| `-318,1` | `+359,1` | `normaliseWideIntegerABI` |
| `-330,1` | `+371,1` | `normaliseWideIntegerABI` |
| `-341,2` | `+382,13` | `normaliseWideIntegerABI` |
| `-348,1` | `+400,1` | `normaliseWideIntegerABI` |
| `-354,1` | `+406,37` | `normaliseWideIntegerABI` |

The cumulative range contains 45 implementation/test files, all within Normalise.cpp, the granted Wide.cpp range, tests/sqlite_vector_* and tests/fixtures/sqlite_vector/. The separately authorised round-1 review document is the only inherited nonimplementation path. Machine-readable hunk/path/source-hash receipt: `scope.json`. No source function outside the grant was edited; no anti-slop finding was introduced.

## Independent reruns

Run from the named worktree with display/browser variables unset, `PYTHONDONTWRITEBYTECODE=1`, and `TMPDIR=$PWD/.tmp/s2-1bb-prod-review2/tmp`. In the exact commands below, `J=.tmp/s2-1bb-prod-review2`. The copied, cited `$J/timeouts.toml` supplies hang-guard classes; all subprocess wall/CPU receipts are in `$TMPDIR/command-receipts.jsonl`. Current machine derivation reserves 16 threads/16 GiB, yielding max nine workers; builds use four workers sequentially by major, suites two workers. Build launch had load 7.47 and over 53 GiB available.

| Exact command | Independently observed result |
|---|---|
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/builds.py"` | PASS; fresh Release configure/build on LLVM18 and LLVM23. 119.85 s wall / 268.40 s CPU. Both fresh plugin hashes equal the author's repaired binaries. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/rerun.py" focused` | PASS; 156.19 s / 314.78 s. Old forward witness gives 24 and reversed gives 22, independently native and interpreter, both majors. Repaired witnesses give 22 in all eight order/major/execution combinations. Oracle **31/31**, scalar-analysis **31/31**, boundary **3/3**, and pinned FP arithmetic pass per major. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/fneg_both.py"` | PASS; 25.60 s / 52.17 s. Invokes `python3 -B "$J/fneg_native.py" --major 18` and `--major 23` under the same guard. All **56/56 hand-derived production lanes per major**, including reversible step-checks, pass. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/rerun.py" corpus` | PASS; 112.78 s / 223.29 s. **20/20** unchanged SQLite/musl modules scalarise and independently LLVM-verify. All 20 raw-production exits, stderr and input hashes match both pre-repair and author repair receipts. |

Focused driver commands are recorded in `{witness,oracle,scalar-analysis,boundary,fp}-{18,23}/receipt.json`. They invoke the actual tracked `tests/sqlite_vector_normalise.py` with `--major M --plugin "$J/build/libbennett-plugin-M.so" --guard-table "$J/timeouts.toml" --mode oracle` or `--mode scalar-analysis`, plus `--output "$J/green"`; boundary/FP use the corresponding tracked driver and same plugin/guard/output arguments. Dedicated witness runs add `--case vector-scalable-module-order --case vector-scalable-module-order-reversed` and use `$J/witness`. All original 29 cases remain and pass alongside the two new cases.

The old red runs use the round-1 reviewer's retained plugins, whose hashes match the reviewed pre-repair binaries. Each exits 1 for the forward payload 24 versus expected 22; the reversed case passes. A separate `clang -O0 -shared -fPIC` compilation of each old scalar output reproduces native 24/22. Green runs independently assert native `top()==22`, interpreter code 0/payload 22 and restoration. Receipts: `red-native-{18,23}.json`, `witness-{18,23}.json`, and per-case emitted graphs/objects.

The 31-case scalar-analysis result does not claim full virtual/materialised Analysis equivalence or a new least-fixpoint/order-independence result. The required H output comparisons and interpreter restoration assertions in the invoked tests pass. Boundary tests preserve native results/symbol addresses, repeated-pass function idempotence and the raw selected vector entry result 12884901889. The pinned FP helper receives exact lanes (1+2, 2+4), links the pinned arithmetic definition and returns packed carriers **4665729215033769984**. Arithmetic hashes and contract pins were independently checked in `pins.json`.

Fresh plugin SHA-256s:

- LLVM18: `2007f8a7149b3f1518ff0ab2dbd31b57f963d52c53d94d8b252e90bf50f560ef`.
- LLVM23: `4c27256149009afc18e0fa198f1ef57795e193db28fe8ad6c5f195d971dc9649`.

The unchanged corpus frontier remains **four SQLite Analysis vector-GEP failures, ten musl Analysis vector-fneg failures, and six LLVM18 H-only completions**. This is acceptance of the production slice and vscale repair; bp-1bb stays open for the queued Analysis mechanics. No input, vectoriser, fixture, budget or promised capability was reduced. No hang guard tripped. No full gate was requested or run; the historical aggregate `scripts/test` timeout/UNKNOWN tracked as `bennett-plugin-8hk` is not upgraded by these focused checks.

## fneg native comparison qualifications

Reused the round-1 independent harness, changing only the owned output directory and plugin path to the fresh reviewer builds. For each of seven formats it constructs eight literal lane pairs: positive/negative zero, quiet NaN, signalling NaN and finite carriers. Each expected output toggles only the specified sign mask; every lane is asserted in the produced interpreter computation. Native C uses memcpy into a typed object, unary minus and memcpy out, compiled by the corresponding clang with **-O0 -std=gnu11** and no fast-math.

| Format | Production lanes LLVM18 / LLVM23 | Native matching lanes LLVM18 / LLVM23 |
|---|---|---|
| half | 8/8 / 8/8 | 6/8 / 8/8 |
| bfloat | 8/8 / 8/8 | 6/8 / 6/8 |
| float | 8/8 / 8/8 | 8/8 / 8/8 |
| double | 8/8 / 8/8 | 8/8 / 8/8 |
| x86_fp80 | 8/8 / 8/8 | 8/8 / 8/8 |
| fp128 | 8/8 / 8/8 | 8/8 / 8/8 |
| ppc_fp128 | 8/8 / 8/8 | 8/8 / 8/8, component oracle |

The LLVM18 half and both bfloat native promotion paths quiet the two signalling NaNs, exactly as in round 1; those mismatches remain explicit, not counted as native passes. Production preserves their payload/signalling bits. PPC uses independent native negation of both binary64 components, including mixed finite signs; it does not claim host IBM128 execution. Literal inputs, expected outputs, actual native outputs and interpreter results are retained in `fneg-native-{18,23}.json`.

## Numbered findings

1. **Round-1 P1 — CLOSED by reviewed repair.** Normalise.cpp:16–60, :255, :296–300, :597, :665–673 and Wide.cpp:268–271 now preserve one link V through N10, N21 and ABI lowering. The independent red/green native/interpreter reruns establish 24 → 22 on both majors; both repaired function orders produce 22. No wrong lane/result or regression was observed.

2. **Inherited P2 — durable format/edge regression coverage remains open.** Round-1 finding 2 remains: tracked fixtures still lack the review's seven-format NaN/payload and per-lane K=4096/4097, out-of-object provenance and mixed-width GEP coverage. The independent 56-lane reruns pass; the repair does not touch GEP semantics. Preserve those probes as durable tests in the existing P2 follow-up. No repair round is requested.

3. **Inherited P2 — test-entry registration remains open.** Round-1 finding 3 remains: the three tests/sqlite_vector_* drivers are not registered in scripts/test. They passed when explicitly invoked here. Register them with cited guards and both-major oracle/scalar-analysis coverage through the existing P2 follow-up. This remains outside the reviewed implementation grant.

No new finding or nit bead. No bd writes were made, as directed; the parent owns recording/identifying the two inherited P2 beads. General Analysis work remains on bp-1bb/bp-an9; the earlier aggregate guard issue is bennett-plugin-8hk.

**Disposition: ACCEPT with P2 beads.** Accept the repaired production slice at 9381e56 with the inherited P2 follow-ups; this is the final permitted review round. The maintainer instructed “finish this review and stop”; no follow-on implementation, full gate, bead update or additional review was started.
