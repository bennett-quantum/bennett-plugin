# bp-1bb production slice — independent rule-7 review, round 1

Reviewer: gpt-6.1-sol. Reviewed head: `cd52436cbe3fce43127e422cc5ee8dbf75d7f818`; base: `2319890511cdd2fa46b8c4cc748b52877408be6f`. Commits: `b0dc27e`, `b062d1b`, `9a6ae11`, `cd52436`. Written: 2026-11-08T12:40:12Z.

**Disposition: REVISE.** One reproduced P1: link vscale changes during normalisation, producing a wrong scalar lane and concrete result on both LLVM majors. No source fixes were made. Two P2 proposals follow. No bead database writes or full gate were performed, as directed.

Read in full: job brief, COMMON.md, T3CHILD.md, repository CLAUDE.md, author brief, design REPORT.md, and implementation PROGRESS.md. Authority is the gate-pinned dialect 0.2.13, especially §§5.2, 12.5–12.6 and 16.4, rather than the live sibling checkout. All commands were headless; TMPDIR and all newly written evidence are under `/home/tobias/Projects/bennett-workspace/bennett-plugin-job-s2-1bb-prod/.tmp/s2-1bb-prod-review/`.

## Granted-path audit

`git diff --name-only 2319890..cd52436` contains exactly 43 files: `src/Normalise.cpp`, `src/Wide.cpp`, the three new `tests/sqlite_vector_*.py` drivers, and fixtures under `tests/fixtures/sqlite_vector/`. No other implementation path changed. `git diff --unified=0 2319890..cd52436 -- src/Wide.cpp` has **13 hunks**, listed individually below. Coordinates are those of **base 2319890**, not shifted head coordinates. Every enclosing function is named; every hunk is inside the granted 265–364 range. There is **no out-of-range STOP finding**.

| Base hunk | Head hunk | Enclosing function |
|---|---|---|
| `-266,0` | `+267,16` | `normaliseWideIntegerABI` |
| `-267,0` | `+284,1` | `normaliseWideIntegerABI` |
| `-279,1` | `+296,15` | `normaliseWideIntegerABI` |
| `-281,0` | `+313,9` | `normaliseWideIntegerABI` |
| `-293,1` | `+333,1` | `normaliseWideIntegerABI` |
| `-298,1` | `+338,1` | `normaliseWideIntegerABI` |
| `-300,2` | `+340,5` | `normaliseWideIntegerABI` |
| `-305,1` | `+348,1` | `normaliseWideIntegerABI` |
| `-318,1` | `+361,1` | `normaliseWideIntegerABI` |
| `-330,1` | `+373,1` | `normaliseWideIntegerABI` |
| `-341,2` | `+384,13` | `normaliseWideIntegerABI` |
| `-348,1` | `+402,1` | `normaliseWideIntegerABI` |
| `-354,1` | `+408,37` | `normaliseWideIntegerABI` |

Machine-readable audit: `.tmp/s2-1bb-prod-review/scope.json`. The insertion anchors 266, 267 and 281 are also inside the grant.

## Independent reruns

Run from the worktree above. In these exact commands, `J=.tmp/s2-1bb-prod-review`; the copied `time_guard.py` reads that directory's cited `timeouts.toml`. Each subprocess has a wall/CPU receipt under `$TMPDIR/command-receipts.jsonl`; commands and outputs are retained. Widths were derived from nproc/MemAvailable with 16 threads/16 GiB reserved: four build workers, two test workers; builds were sequential by major.

| Command | Independently observed result |
|---|---|
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/builds.py"` | Fresh Release configure/build for LLVM18 and LLVM23 PASS; 121.12 s wall / 269.96 s CPU. Both new plugin hashes exactly equal the author's tested binaries. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/rerun.py" focused` | PASS, 133.01 s / 267.74 s. On baseline plugins, exactly 9/10 original cases red per major. On reviewed plugins, oracle 29/29, scalar-analysis 29/29, boundary 3/3, FP lane/link checks and targeted virtual ABI 2/2 pass per major. Full virtual-analysis mode intentionally returns 1: 15/29 cases remain red per major on the recorded Analysis queue. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/rerun.py" corpus` | PASS, 90.58 s / 176.55 s. All 20 unchanged inputs scalarise and independently LLVM-verify. All 20 production exits and stderr match the author's receipts byte for byte. Input/plugin hashes checked before execution. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/regressions.py"` | PASS, 21.93 s / 42.60 s. Existing materialisation, normalisation_scope, wide and softfloat suites all pass on both majors (8/8 commands). Tracked-source copy confines their outputs to the review directory. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/fneg_native.py" --major 18` | PASS for all 56 hand-derived production lane results and reversible step-checks; native comparison qualifications below. 24.13 s / 24.54 s. |
| Same command with `--major 23` | PASS for all 56 production lane results and reversible step-checks; 24.08 s / 24.46 s. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/gep_edges.py"` | PASS both majors, 0.22 s / 0.21 s: per-lane K boundary, out-of-object provenance and mixed-width AS270 indices. |
| `python3 -B "$J/time_guard.py" moderate python3 -B "$J/vscale_order.py"` | Reproduction harness exits 0 because it records the defect: native and interpreter produce **24**, expected **22**, on both majors. See finding 1; this is not a correctness PASS. |

The focused harness invokes the actual tracked drivers with explicit `--major M --plugin .../.tmp/s2-1bb-prod/build/libbennett-plugin-M.so --guard-table "$J/timeouts.toml" --output "$J/green"`, using `--mode oracle` and `--mode scalar-analysis` for `sqlite_vector_normalise.py`. Baseline reruns use the design's `s2-b71/work/plugin-M` binaries and the ten original named cases. Those red outputs include GEP/PHI/ABI V13 and reduction V4 diagnostics; elementwise extrema is the one pre-existing green case.

Fresh and author plugin SHA-256s are identical:

- LLVM18: `52f4b84541e9c59daf9664b166b716bb98368b6cf95705bec610657165312b1e`.
- LLVM23: `9c8532bdbd9d47f9e82391e2871c2c17600cbd9b2055bb32821b78a26ada8cb7`.

No hang guard tripped in this review. The author's aggregate `scripts/test` remains UNKNOWN due to its existing aggregate allowance, tracked as `bennett-plugin-8hk`; this review does not relabel that aggregate as green or claim to have rerun all 86 default commands.

## Six-class evidence and its limits

| Class | Reproduced evidence on both majors |
|---|---|
| GEP | Scalar base/vector index, vector base/scalar index and zipped vector/vector indices give offsets 4/12, 4/12 and 4/20 respectively; oracle deltas 8/8/16. Existing P64/I32 high-bit-wrap fixture returns 8589934591; AS270 delta is 4294967295. Review fixture mixes i16/i64 index operands in AS270: offsets 2 and 7, with explicit 8192-byte object alignment excluding low-I32 wrap. |
| fneg | Per-format 8-lane review fixtures preserve sign-only behaviour for zeros, quiet/signalling NaNs and finite carriers; full table below. Existing f32 packed NaN result is 9205677896870470469. |
| Extrema | Existing elementwise result 3; scalar graph retains N27 compare/select, including signed/unsigned reduction predicates SGT, SLT, UGT and ULT. |
| Reductions | Concrete smax of [1,9] is **9**. Explicit scalar analysis retains abstract **{1,9}**, as PT3 requires. Signed-min/unsigned-max/unsigned-min concrete results are 2147483648/4294967295/1. |
| PHI | Both labelled branch paths return 1/5; loop-carried PHI returns 3; forward block dependency returns 7. Scalar PHI shells and dead-vector cycle cleanup LLVM-verify. |
| ABI | Internal, nested, recursive and indirect fixtures return 3. Defined/external/callback boundary adapters pass native result, identity and idempotence assertions. Selected vector-entry payload is 12884901889. |

The review GEP fixture derives `{0,…,4095}` from a mask: exactly 4096 integer alternatives remain finite. Selecting the additional value 4096 produces 4097 alternatives and TOP in lane 0; lane 1 remains exactly `PTR(@buf,1,0)` before and after saturation. The finite lane-0 GEP has exactly 4096 object offsets. For an 8-byte object, offsets 1/9 yield lane 0 `PTR(@small,1,0)`, top=false; lane 1 retains `PTR(@small,9,0)` **and** `PTR(EXT,0,-1)`, top=true. It is not clipped to object bounds or stripped of its original provenance. This checks the materialised scalar path; it does not claim the unfixed virtual vector GEP transfer passed.

Actual post-production H IR is compared byte for byte with plain-opt canonical IR by the oracle tests; analysis output has the same independent check. All those immutability checks passed. Restoration is checked in the pinned interpreter, including both boolean PHI paths. Virtual and explicit ABI facts agree in the targeted internal-device/H-boundary cases (precise INT(3) versus PT11 host TOP as appropriate). General virtual/materialised field equivalence remains unfulfilled on the explicitly queued Analysis paths; the materialised results above do not establish that broader claim.

Production corpus frontier remains four SQLite cells at Analysis PT10 vector GEP (`%8845` on LLVM18, `%9989` on LLVM23), ten musl cells at Analysis PT10 vector fneg, and six ordinary LLVM18 H-only completions. That is consistent with the declared slice boundary, not bp-1bb end-to-end acceptance. No vectoriser was disabled, input reduced, fixture weakened, or capability rejected by the reviewed change.

## fneg: hand-derived per-format native comparison

Each review fixture has eight lanes: `[+0,-0,+Q,-Q,+N,-N,+F,-F]`, where Q is a quiet NaN and N a signalling NaN with the literal nonzero payload below. The expected carriers are `[-0,+0,-Q,+Q,-N,+N,-F,+F]`: toggle exactly the specified sign mask S, leaving every other bit intact. In the table, `-Q`, `-N` and `-F` mean XOR S of the shown positive/mixed-component carrier. Complete literal input/output pairs and native outputs are in `fneg-native-{18,23}.json`; one LLVM fixture and one native C program per format/major are under `fneg-native/M/FORMAT/`.

| LLVM format / native C type | S (hex) | Q / N / F input carriers (hex) | Production lanes LLVM18 / LLVM23 | Native matches LLVM18 / LLVM23 |
|---|---|---|---|---|
| half / `_Float16` | `8000` | `7e35` / `7c35` / `3e00` | 8/8 / 8/8 | **6/8** / 8/8 |
| bfloat / `__bf16` one-element vector | `8000` | `7fd5` / `7f95` / `3fc0` | 8/8 / 8/8 | **6/8 / 6/8** |
| float / `float` | `80000000` | `7fc12345` / `7fa12345` / `3fc00000` | 8/8 / 8/8 | 8/8 / 8/8 |
| double / `double` | `8000000000000000` | `7ff8123456789abc` / `7ff0123456789abc` / `3ff8000000000000` | 8/8 / 8/8 | 8/8 / 8/8 |
| x86_fp80 / `long double` | `80000000000000000000` | `7fffc123456789abcdef` / `7fff8123456789abcdef` / `3fffc000000000000000` | 8/8 / 8/8 | 8/8 / 8/8 |
| fp128 / `__float128` | `80000000000000000000000000000000` | `7fff8123456789abcdef0123456789ab` / `7fff0123456789abcdef0123456789ab` / `3fff8000000000000000000000000000` | 8/8 / 8/8 | 8/8 / 8/8 |
| ppc_fp128 / two native `double` components | `80000000000000008000000000000000` | `7ff8123456789abc7ff8123456789abc` / `7ff0123456789abc7ff0123456789abc` / `80000000000000003ff8000000000000` | 8/8 / 8/8 | 8/8 / 8/8, component oracle |

The host compilers are `/usr/lib/llvm-{18,23}/bin/clang`, invoked with **`-O0 -std=gnu11`**, without fast-math. Native C uses `memcpy` into a typed object, `y=-x`, and `memcpy` out for each lane; it never computes expected values with the plugin. Production executes the separately normalised LLVM fixture in the pinned ISA interpreter and performs exhaustive restoration checks. Source inspection confirms each scalar FNeg becomes the existing unconditional carrier XOR in `materialiseFPBits`; there is no value-dependent NaN path. That establishes the sign-only transformation beyond the sampled carriers.

**Native mismatch, not hidden as a pass:** LLVM18 half promotes to float before unary minus and truncates afterward; both bfloat compilations likewise emit `fpext`, float `fneg`, `fptrunc`. Their native conversion sequences quiet the two signalling NaN lanes. Half `7c35/fc35` becomes `fe35/7e35`, rather than the required `fc35/7c35`; bfloat `7f95/ff95` becomes `ffd5/7fd5`, rather than `ff95/7f95`. Saved native IR proves those conversions (`half-native-18.ll`, `bfloat-native.ll`). Both production graphs preserve the signalling bit and payload exactly. Native promotion is therefore unsuitable as a bit-exact oracle on those lanes, while remaining a useful independently measured comparison.

**PPC qualification:** the host rejects `__ibm128` with “__ibm128 is not supported on this target”, saved in `ppc-native-probe.stderr`. The independent native program negates both binary64 components with C unary minus, matching the pinned §16.4 component rule. This is an independent component comparison, not a claim of native IBM double-double execution. Mixed component signs in the finite lanes ensure that flipping only one component cannot pass.

## Numbered findings

1. **P1 — mutable-module vscale selection produces a wrong N21 lane/result (REVISE).** Location: `src/Normalise.cpp:17–41`, especially the current-use filter at 25–31; invoked during destructive N10 replacement at line 236 and N21 lane counting. The helper recomputes link V from functions that still contain scalable operations. Earlier normalisation removes exactly that evidence, so later functions see a different link. Pinned §12.5 fixes one V for the link; with nonfixed ranges `(2,8)` and `(4,8)`, the specified default is their minimum bound, **2**.

   The valid reproduction has internal `first()` with `vscale_range(2,8)` and `second()` with `vscale_range(4,8)`. Each calls `llvm.vscale.i32`, inserts that value into lane 0 of `<vscale x 2 x i32>`, then extracts lane 0. `top()` returns `10*first()+second()`. Expected scalar lane values are **2 and 2**, result **22**. Normalising in module order emits `first(){ret i32 2}` and `second(){ret i32 4}`. Both native `clang -O0` execution and the pinned selected-oracle interpreter produce **24** on **both majors** (interpreter code 0, payload 24, 12 steps).

   Reproduce with `python3 -B .tmp/s2-1bb-prod-review/vscale_order.py`; inspect `vscale-order.json` and `vscale-order/{18,23}/{input.ll,scalar.ll,oracle/ref.bennett}`. The harness intentionally records the expected-result assertion instead of presenting it as a passing oracle. Freeze the link's chosen V from the complete source module before destructive normalisation, and use it consistently for N10, lane counts and ABI shapes. Add a multi-function regression that checks both orderings. No source repair was authorised for this review.

2. **P2 proposal — preserve the independent format/edge probes as durable regressions.** Location: `tests/fixtures/sqlite_vector/fneg-formats.ll` and `tests/sqlite_vector_normalise.py`. The tracked seven-format fixture contains only signed zeros; quiet/signalling NaNs are tested only in f32. No tracked fixture exercises per-lane K=4096/4097, out-of-object provenance, or mixed widths within the same GEP. The review-only probes above pass, so this is a future-detection gap, not evidence of a current fneg/GEP wrong result. Proposed bead: commit the seven-format NaN/payload cases and the hand-derived GEP edge cases, keeping native promotion/PPC limitations explicit.

3. **P2 proposal — register the new drivers with the repository test entry point.** Location: `scripts/test` and the three new `tests/sqlite_vector_*.py` files. Searching `scripts/test`/`scripts/pre-push` finds no `sqlite_vector` entry; these regressions currently run only when explicitly invoked. The author already identifies this as parent-owned integration work because scripts are outside its grant. Proposed bead: register all three with an explicit cited guard table and retain oracle/scalar-analysis coverage on both majors. Existing aggregate UNKNOWN is separately tracked by `bennett-plugin-8hk`.

No nit finding. General Analysis vector equivalence and the recorded production frontier remain bp-1bb dependencies, rather than newly discovered repairs assigned to this production slice. Anti-slop inspection found the old 500-line `normaliseScalar` split into named phases, reductions dispatched through opcode/predicate tables, and the existing complete carrier sign-mask implementation reused. No touched semantics function exceeds 300 lines; N26's extracted body and N27-before-N32 ordering are retained.

**Disposition: REVISE.** Fix and review finding 1 before landing the implementation. P2 proposals do not require a repair round under rule 7. The maintainer's direction is to finish this review and stop; no follow-on implementation or review was started.
