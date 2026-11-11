# Quality floor

The default test command is `timeout 900 scripts/test`, after building LLVM 18 and 23.
The expanded gate-coverage run passed **82/82 commands in 132.057 seconds**, exit 0,
with release builds for both LLVM majors. The driver retains its 180-second internal allowance.
The gate-only checks and their prerequisites are listed below; the full gate runs them after the default suite.
Promised shared-global semantics remain visible through
`tests/review_regressions.py --case global-counter --promised-bp-acm --major 18`.

## Shadow-stack linkage and gate coverage

The complete published budget-stage driver now runs by default on LLVM 18 and 23,
after its production-fixture prerequisite, together with the shadow-stack lifetime
and fault driver. The budget-stage acceptance includes both byte-exact H16/H32
objects, the equivalent N24 source object, no-rematch and steps-only selection,
all 316 budget prefixes, resolved tokens and the launch result. Four altered-runtime
cases must still refuse the structural proof with the logical-frame-validation diagnostic.

Archived source builds locate the regression at `5d86488` (parent `0d42b13`):
the parent passes all nine records on both majors; the child loses the linked initializer
during private-clone pruning and fails with multiply-defined stack helpers. Preserving
the implicit stack methods also preserves external state-user bodies, whose removal
would erase evidence that must refuse the single-frame proof. The runtime pin is unrelated.

The gate audit also exposed LLVM 23 native finalization following a forwarding source
definition past its provenance attribute. Finalization now checks the aliased definition.
Both majors pass all six native/interpreter result and fault comparisons. A mutation
removing provenance must still fail before producing a finalization report.

Every formerly gate-only driver that completed within the focused 60-second allowance
is now in the default suite with its original case arguments. This includes build-default
checks, analysis performance, reference images, materialisation, aggregate rows, allocator
closure, native comparison/layout/fixtures/hello/checked, CC calls/switch, reversible,
the complete soft-float driver, wide and integer intrinsics, memory runtime, region keys
and key audit, descriptors, production/environments/dispatch/shapes/budgets/records,
budget-stage, shadow-stack and production lifts. The gate calls this shared suite
instead of repeating those drivers. Independent major groups run concurrently with
two workers, preserving prerequisite order within each major. Reversible and generated
dispatch executions use the gate-pinned release interpreter; debug checks/hashes and
all vectors and semantic assertions remain.

The remaining gate-only commands are exhaustive:

| Command | Focused audit wall time | Reason |
| --- | ---: | --- |
| `scripts/build` | cold build measured by the final gate | Prerequisite to the test command |
| `review_regressions.py --case mixed-native` | LLVM 18/23 both >60 s | Compiler and native integration |
| `entry_snapshot.py` | LLVM 18/23 both >60 s | Snapshot executions |
| `production_cross_major.py` | 0.214 s on incomplete artifacts | Requires both complete snapshot suites (>60 s) |
| `prior_objects.py` | 0.215 s to first mismatch | Requires the complete object set, including snapshots |
| `corpus_gate.py` | >60 s | Full contract corpus and optimization matrix |

The bounded artifact audit refuses intentionally incomplete snapshot sets. The deliberate
standalone layout changes and their prior-object receipt revision are documented in
`docs/verification-layout-revision.json`; all 312 prior names remain checked on both majors.
Focused timeouts are runtime measurements, not full-gate acceptance.

## Mixed-native command bounds

The large device-FP object is checked with the gate-pinned release interpreter, which
already executes both numerical vectors. The small native shapes retain debug checks.
No case, stack boundary, numerical input, expected fault or exact result bit changes.
These measurements retained the interpreter pin and build declarations.

The device-FP lowering command alone has a 480-second wall timeout; other subprocesses
retain the shared 120-second limit. A 120-second wall limit cannot enclose S2's unchanged
120-second CPU allowance plus repeated analysis and scalar lowering under contention.
A five-second profile of the optimized plugin places 24.19% of samples in malloc
consolidation and 18.96% in abstract-value tree copying through Analysis::bind/step.
The object contains the complete published add closure (52/51 functions on LLVM 18/23). This is CPU work,
not a missing interpreter build or cache. Analysis.cpp is unchanged.

Measurements use `/usr/bin/time` around every command in the complete
`python3 -B tests/review_regressions.py --major MAJOR --case mixed-native` driver,
while a separate RelWithDebInfo CMake plugin build runs continuously with `-j4`.
The primary plugin uses the normal `scripts/build` (`-j3`) configuration.
The baseline measurement alone permits 300 seconds per command to finish measuring
the operation that exceeded the original 120-second limit. All semantic assertions
still run.


| Command | Baseline LLVM 18 (s) | Fixed LLVM 18 (s) | Fixed LLVM 23 (s) |
| --- | ---: | ---: | ---: |
| native review: lower | 0.033 | 0.012 | 0.022 |
| native review: verify host.bc | 0.016 | 0.011 | 0.018 |
| native review: compile harness | 0.129 | 0.078 | 0.103 |
| native review: execute harness | 0.004 | 0.002 | 0.003 |
| native review: check object | 0.007 | 0.003 | 0.005 |
| native review: reverse program | 0.008 | 0.003 | 0.006 |
| host FP: lower | 0.035 | 0.014 | 0.023 |
| host FP: verify host.bc | 0.026 | 0.014 | 0.020 |
| host FP: compile harness | 0.132 | 0.085 | 0.116 |
| host FP: execute harness | 0.004 | 0.002 | 0.003 |
| host FP: check object | 0.007 | 0.004 | 0.006 |
| host FP: reverse program | 0.007 | 0.004 | 0.006 |
| device FP: lower full closure | 204.504 | 119.357 | 144.132 |
| device FP: check object | 125.286 | 41.516 | 36.887 |
| device FP: 65,536-cell stack fault | 32.157 | 18.156 | 32.349 |
| device FP: 262,144-cell stack result | 20.223 | 51.902 | 40.083 |
| Sum of command wall times | 382.578 | 231.161 | 253.784 |

The measured lowering maximum is **204.504 seconds**; the **480-second** limit
provides **2.35x** that observed maximum (275.496 seconds of margin).
The original debug checker took **125.286 seconds**, exceeding 120 seconds;
release checks took **41.516/36.887 seconds**.
Observed one-minute load at command boundaries ranged from 4.33 to 8.80;
the four-job build was active throughout every measured command.

All three runs pass all three cases. All 16 stdout/exit-status pairs agree exactly
between baseline and fixed LLVM 18, including complete debug/release checker
object/symbol hashes. Both majors retain native reversal, fault 3 at the smaller
stack, and exact 3.0 result bits (4613937818241073152) at the larger stack. LLVM 23
has a 51-function add closure versus LLVM 18's 52; its hashes and step counts differ,
while both numerical result/fault expectations agree. The lowering implementation
is unchanged; the wall allowance accommodates its observed host/build sensitivity.
Per-command argv, CPU/RSS, load and outputs are retained locally in
`.tmp/quality-plugin/gatefix4-baseline-18-commands.json` and
`.tmp/quality-plugin/gatefix4-fixed-{18,23}-commands.json`.
The focused measurements above used the gate's interpreter pin at measurement time,
`ecaaac060c44e317d1181345fa6b8e38c096c099`.

## Soft-float gate regressions

The default suite now runs the same S2 and direct-CC record functions used by the
soft-float gate, on both LLVM majors:

```sh
timeout 60 python3 -B tests/softfloat.py --major 18 --case analysis-closure --case published-cc
timeout 60 python3 -B tests/softfloat.py --major 23 --case analysis-closure --case published-cc
```

Before the fixture corrections, both commands passed 3/11 records and failed the same
eight gate records; `timeout 900 scripts/test --major 18` also failed at the newly included
soft-float driver. After correction, both commands pass **11/11**, including exactly the
two S2 records and all six published direct-CC numerical cases. Reversal, entry-state
restoration, memory restoration, fault absence and exact result bits remain asserted.
The quality baseline below is unchanged.
The complete `timeout 300 python3 -B tests/softfloat.py --major 18` driver passes
**112/112**, and its LLVM 23 counterpart passes **116/116**; both exit 0.

The LLVM 18 adjacent source snapshots and pin-isolation runs establish these transitions:

| Records | Last passing input | First failing input | Cause |
| --- | --- | --- | --- |
| S2-comparison-closure, S2-FP-atomic | 0d42b13 (5d86488 parent) | 5d86488 | Arithmetic discovery now follows device tiers; these fixtures contained only host functions. |
| Six published-production-CC-numerical records | 6231c2d (33e7edb parent), arithmetic 0dea42d001ff | 33e7edb selects arithmetic 5e9b4509f3ee; 5d3cc36 aligns its SPEC_VERSIONS/digests | The published comparison helper closure becomes memoryless, so the old nonzero memory budget is invalid. |

The b71b053 compiler with only its explicit published arithmetic input changed back to
0dea42d001ff passes all six numerical cases and emits a layout; with 5e9b4509f3ee it emits
no layout and the unchanged commands fail with the pinned interpreter's §5.4 diagnostic.
The two S2 failures persist with either arithmetic pin. These are stale fixtures, not an
arithmetic implementation failure or a production-lowering regression.

The normative basis is the pinned dialect 0.2.13 §§4.2 and 12.1: a function containing a
marker call and its CC closure are device variants, and **“H variants are untouched.”**
The two S2 fixtures now allocate/free one quantum register, placing the same comparison
and atomic bodies in CC; their original exact atom expectations stay unchanged.
Pinned ISA 0.8 §§5.4 and 7.2 require **“for a memoryless object (§7.2)
`heap_limit = stack_limit = depth_limit = 0`.”** The six direct-CC runs therefore use
`1000000,0,0,0`; the step allowance is unchanged. Other memory-using soft-float launches
retain their existing budgets. Production source, publication pins and expected values
are unchanged.

Exact opt/run-program commands, source snapshots, outputs and artifact hashes are retained
in `.tmp/quality-plugin/bisect/`; the resume file records final pin verification.
The full gate remains the orchestrator's responsibility.

## Coverage

The preceding quality-floor coverage sample recorded **66.86% (4646 / 6949 lines)**, GCC/gcov 13, LLVM 18.
That sample measures the default suite and the changed numerical/reversible drivers, with
counters cleared before execution. The instrumented configuration and commands were:

```sh
cmake -S . -B build/coverage18 -DLLVM_DIR=/usr/lib/llvm-18/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS_DEBUG="-O1 -g1 --coverage" -DCMAKE_MODULE_LINKER_FLAGS=--coverage -DBENNETT_OUTPUT_DIR="$PWD/build"
timeout 240 cmake --build build/coverage18 -j3
python3 -B - <<'RESET'
from pathlib import Path
for path in Path("build/coverage18").rglob("*.gcda"):
    path.unlink()
RESET
timeout 180 scripts/test
timeout 180 python3 -B tests/wide.py --major 18
timeout 180 python3 -B tests/integer_intrinsics.py --major 18
timeout 180 python3 -B tests/memory_runtime.py --major 18
timeout 180 python3 -B tests/reversible.py --major 18
timeout 90 scripts/coverage
```

The same gcov instrumentation is available as `-DBENNETT_COVERAGE=ON` in a single-major GCC
configuration; that option uses -O0. The measured run above uses -O1 to keep the large numerical
solver paths within their explicit resource allowances.
Coverage counts executable lines under `src/`, including inline headers and includes, and merges
repeated header counters by source line. It is a measurement, with no threshold.

The five least-covered files are Snapshot.cpp (0/57), runtime/NativeComparison.inc (0/1),
runtime/SingleFrame.inc (0/1), NativeComparison.cpp (15/355), and SoftFloat.cpp (58/269).
General snapshot construction belongs to the slow launch/history suites; the default entry-stack
fixture tests its published microvector. The one-line runtime includes embed C source data;
instrumenting generated guest code would measure runtime behavior rather than the plugin.
NativeComparison.cpp's address/target adapters and broad soft-float operations belong to the
slow native-comparison/layout/soft-float drivers. The optional mixed-native device floating probe
hit its subprocess timeout during this round (bp-r3r); its host checks completed.
Reversible.inc now has 118/124 covered lines after the repaired focused reversible driver.
These focused measurements do not claim full gate coverage or LLVM 23 coverage.

## Contracts and remaining mechanics

Dialect 0.2.13 / ISA 0.8 stay pinned. Arithmetic is 5e9b4509f3ee3f95ac9f7d22b43359e72cf9fdab
(1141 exports per LLVM major); allocator and native support are both
248e468ca505c684bbf254e52eb8148f1e530c83. Published allocator bookkeeping changes are
derived and tested in allocator_closure.py, including the separate 128-byte heap boundary.
Shared native/device globals remain promised and pending the published native-sharing contract;
the approved native adapter interim prints that fact and exits 125 before state can reset.


The remaining audit weak witnesses also have observable checks: helper/global key differences
are paired with native memory results 42, 7 and 8; the unsigned fixed-point division test checks
structured ISA fault 5 and hand-derived nonfault results 16, 8 and 0. Pointer round trips cover
every 64-bit basis vector plus seeded samples. Host-tier reports require both source functions,
so an empty report cannot pass. The additive-copy-cycle witness already checks a top result
and bounded convergence in addition to its empty exact-atom expectation.

The normalization checks parse the actual generated numerical modules with LLVM's IR reader,
including every materialized helper. They reject intrinsic calls and vector or wide scalar
values in every body; the wide suite also enforces byte-sized memory operations. Integer-runtime materialization introduces helpers
with partial-limb memory operations which production normalizes in its next closure pass, so
the first-stage integer check enforces its original intrinsic/vector contract before clang.
The bounded default suite runs `tests/normalisation_scope.py --major 18` and `--major 23`: each mutates the real output
and requires rejection of a scalar intrinsic, vector intrinsic, helper-body intrinsic, non-byte
memory access, and memory intrinsic. The baseline below registers these two new verifier files;
no existing-file allowance is raised.

Other round-one replacements still inspect their original bug classes: mixed-native executes the
emitted host.bc's byte-vector function for every byte and its native floating function; wide
constant-shift checks execute the same generated function; pointer round trips cover every bit.
The helper/global-key check supplements its original comparisons with executions of the same
linked bodies and globals. Remaining removed subprocess assertions live in the shared harness.

## Council regression evidence

At `2ecdd90`, both majors failed
`timeout 180 python3 -B tests/review_regressions.py --major <18|23> --case global-diagnostic`
with 7/13 passing. The six indirect, nested-indirect and mixed call-shape/order cases
silently returned `1 1 host_global=0`; all native baselines returned `1 2 host_global=2`.
The generated family also includes direct calls in both function orders. Each new case
uses a resolved comparison layout built from the native executable's symbol addresses,
passes the same helper addresses to both launches, and retains the default production budget.
After the dependency scan followed analysis candidates before any host body replacement,
the same command passed **13/13 on LLVM 18 and LLVM 23**, exit 0. The shared-state cases
require the approved exit-125 promised/pending diagnostic and empty stdout. This verifies
the interim guard; shared host/device memory remains promised above (SOL-S0-1, bp-46p).

At `2ecdd90`, on both majors, all four two/three-indirect-call variants (with and
without a following switch) compiled but failed the pinned ISA checker with a duplicate
block label. After sharing one compare-block counter per original LLVM block across calls,
switch and indirectbr, both of these commands passed for **each major 18 and 23**:

```sh
timeout 180 python3 -B tests/scalars.py --major <major>
timeout 180 python3 -B tests/scalars.py --major <major> --step-check --case inc8 --case switch5 --case two-calls --case three-calls --case two-calls-switch --case three-calls-switch
```

The default scalar driver preserves **21/21 byte-exact published objects**, their stated
hashes and execution results, plus the C inc8 fixture. The four new objects pass ISA check
and hand-derived result assertions: two calls add 2 or 4; three add 3 or 6, selected by the
same i1 input. The switch tests also exercise zero, 255 and the fallback. Each new object
passes exhaustive inverse checking over all **512 selector/byte inputs**. A mutation
renaming the second call's `.s2` back to `.s1` is rejected specifically for a duplicate
block label (codex-S0-1, bp-dzb). The switch emission and per-fixture test phases were
extracted to retain the existing quality limits; no baseline was raised.

An unrestricted `scalars.py --step-check` attempt hit the existing 60-second subprocess
allowance in add2's 65536-case debug-interpreter check on both majors (bp-v7h). Its time
limit and assertions remain intact. The pinned **release** interpreter separately passed
`step-check .tmp/scalars/<major>/add2/ref.bennett ref --exhaustive --max-bits 16 --budget 6,0,9,1`
on both majors under `timeout 180` (two sequential subprocesses limited to 85 seconds each).

The exact declaration-candidate witness aborted `opt` with `std::out_of_range` / `map::at`
at `2ecdd90` on both majors. `collectScalarFunction` deliberately excludes declarations;
scalar dispatch now retains their sorted leaves and emits `fault 4` there instead of
looking up an absent lproc. After `timeout 240 cmake --build build/llvm<major> -j3`,
`timeout 90 python3 -B tests/scalars.py --major <major> --case missing-callee --step-check`
passes on **LLVM 18 and 23**, exit 0, with compilation and ISA check accepted and no
compiler stack dump. With shape `IN(1,zext),IN(8,zext);tgt=8`, stack 256 and budget
`100,0,256,8`, input `1,7` returns `(code,payload)=(0,8)`; input `0,7` returns `(4,0)`.
Exhaustive inverse checks also pass all **512 inputs** per major (codex-S0-2, bp-cks).

After all three fixes, `timeout 900 scripts/test` passed **23/23 commands in 38.344s**
(exit 0), including both majors' scalar regressions and the generated shared-global family.
`timeout 180 python3 -B tests/reversible.py --major 18` and the LLVM 23 equivalent
also passed **8/8 each**, exit 0. `python3 -B scripts/quality.py --check` and
`git diff --check` passed with the baseline JSON unchanged. No full push gate was run.

## Function size and cognitive-complexity baseline

Device analysis work receipts (`analysis_work`, every exit path) raise the Analysis.cpp complexity
from 6021 to 6155 and its longest function from 529 to 531 lines, add tests/analysis_counters.py, and
add one line to tests/analysis_performance.py; the baseline below records them.

Run `python3 -B scripts/quality.py` to reproduce the baseline below and
`python3 -B scripts/quality.py --check` to compare against it. The single `quality baseline`
check in gate.toml runs before the slow plugin gate. No absolute score or coverage threshold is used.

Length is physical lines per function; each file records the function count, median, 90th percentile,
maximum and number above 300. Python functions and nesting come from the standard-library AST.
C++ functions use a lexical signature/brace reader with strings and comments masked; lambdas and
operator overloads are not separately inventoried. Cognitive-complexity mass is a consistent local
proxy: Python decisions cost one plus branch nesting (boolean alternatives add one); C++ decisions,
boolean operators and ternaries cost one plus brace depth. It is not a cross-tool score.
Trivial wrappers are single call/return-call functions, counted alongside complexity to expose
splits that merely add forwarding functions. New files start from zero until an explicit baseline
update is reviewed. The mutation tests independently add length, nested branches, a wrapper,
a product process identifier and tracked litter, and require each dimension to fail.

Only two production functions remain above 300 lines:

| Function | Lines | Owner and disposition |
| --- | ---: | --- |
| Analysis::step | 529 | bp-pa6; quality-plugin round 2 after rung4-plugin merges; this brief forbids editing Analysis.cpp |
| normaliseScalar | 500 | bp-pa6; same owner and sequencing; this brief expressly defers its split |

All other production functions, including the extracted Scalar and Entry phases, are at most
300 lines under this reader. Tests preserve 21/21 byte-exact scalar objects per major,
five production lift fixtures per major, interpreter results, reversal, runtime faults and budget edges.

Product process identifiers are counted under src/ and include/ with
`rg -n '\b(bp|bd|b-dialect-spec)-[a-z0-9]+\b|\b(sol|quality)-plugin\b' src`.
Exactly two remain, together in the native-sharing diagnostic, because maintainer D4 explicitly
requires both bp-acm and b-dialect-spec-6u6. The diagnostic is tested on both majors; it must
say promised/pending and must not say unsupported. They retire when the sharing contract does.
Tracked litter is zero. The script checks every `git ls-files` path for pycache, pyc, log,
lock, darc, LAST-RUN and PROGRESS files; .gitignore keeps newly generated artifacts out.

Target-aware configured-class execution remains a named promised check under bp-ace:
`timeout 90 python3 tests/register_classes.py --major 18 --promised-target-bp-ace`
(and LLVM 23). The pinned interpreter explicitly defers target loads. The pinned native VM
also fails a class-zero control, so this is separate from the repaired class-table lowering.
The source keeps configured classes available; no replacement executor or private bridge is used.

<!-- quality-baseline -->
```json
{
  "files": {
    "tests/analysis_input_snapshots.py": {"complexity": 12, "functions": 1, "length_max": 100, "length_p50": 100, "length_p90": 100, "over_300": 0, "trivial_wrappers": 0},
    "tests/scalar_contract.py": {"complexity": 1, "functions": 1, "length_max": 6, "length_p50": 6, "length_p90": 6, "over_300": 0, "trivial_wrappers": 0},
    "src/NativeGlobals.inc": {"complexity": 73, "functions": 4, "length_max": 29, "length_p50": 11, "length_p90": 29, "over_300": 0, "trivial_wrappers": 0},
    "src/ProductionGlobals.inc": {"complexity": 5, "functions": 1, "length_max": 12, "length_p50": 12, "length_p90": 12, "over_300": 0, "trivial_wrappers": 0},
    "tests/r_native_globals.py": {"complexity": 4, "functions": 2, "length_max": 88, "length_p50": 2, "length_p90": 88, "over_300": 0, "trivial_wrappers": 1},
    "scripts/build": {"complexity": 9, "functions": 1, "length_max": 19, "length_p50": 19, "length_p90": 19, "over_300": 0, "trivial_wrappers": 0},
    "scripts/coverage": {"complexity": 14, "functions": 1, "length_max": 51, "length_p50": 51, "length_p90": 51, "over_300": 0, "trivial_wrappers": 0},
    "scripts/quality.py": {"complexity": 68, "functions": 6, "length_max": 46, "length_p50": 24, "length_p90": 46, "over_300": 0, "trivial_wrappers": 0},
    "scripts/record-verification.py": {"complexity": 64, "functions": 5, "length_max": 150, "length_p50": 9, "length_p90": 150, "over_300": 0, "trivial_wrappers": 1},
    "scripts/test": {"complexity": 7, "functions": 3, "length_max": 36, "length_p50": 28, "length_p90": 36, "over_300": 0, "trivial_wrappers": 0},
    "src/Analysis.cpp": {"complexity": 6847, "functions": 99, "length_max": 439, "length_p50": 12, "length_p90": 78, "over_300": 1, "trivial_wrappers": 10},
    "src/AnalysisBudgetClock.h": {"complexity": 24, "functions": 4, "length_max": 6, "length_p50": 5, "length_p90": 6, "over_300": 0, "trivial_wrappers": 0},
    "src/Bennett.h": {"complexity": 0, "functions": 1, "length_max": 1, "length_p50": 1, "length_p90": 1, "over_300": 0, "trivial_wrappers": 0},
    "src/BennettPlugin.cpp": {"complexity": 914, "functions": 35, "length_max": 134, "length_p50": 7, "length_p90": 39, "over_300": 0, "trivial_wrappers": 2},
    "src/ByteOrder.h": {"complexity": 15, "functions": 1, "length_max": 15, "length_p50": 15, "length_p90": 15, "over_300": 0, "trivial_wrappers": 0},
    "src/CCCalls.inc": {"complexity": 171, "functions": 3, "length_max": 81, "length_p50": 36, "length_p90": 81, "over_300": 0, "trivial_wrappers": 0},
    "src/ComparisonLayout.h": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "src/Integer.cpp": {"complexity": 614, "functions": 3, "length_max": 72, "length_p50": 54, "length_p90": 72, "over_300": 0, "trivial_wrappers": 0},
    "src/Memory.cpp": {"complexity": 34, "functions": 1, "length_max": 14, "length_p50": 14, "length_p90": 14, "over_300": 0, "trivial_wrappers": 0},
    "src/NativeComparison.cpp": {"complexity": 715, "functions": 36, "length_max": 75, "length_p50": 7, "length_p90": 32, "over_300": 0, "trivial_wrappers": 5},
    "src/NativeComparison.h": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "src/Normalise.cpp": {"complexity": 2166, "functions": 32, "length_max": 221, "length_p50": 13, "length_p90": 44, "over_300": 0, "trivial_wrappers": 0},
    "src/Production.cpp": {"complexity": 7785, "functions": 127, "length_max": 295, "length_p50": 9, "length_p90": 37, "over_300": 0, "trivial_wrappers": 7},
    "src/Residual.cpp": {"complexity": 604, "functions": 4, "length_max": 93, "length_p50": 7, "length_p90": 93, "over_300": 0, "trivial_wrappers": 0},
    "src/ResidualIntrinsics.inc": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "src/Reversible.inc": {"complexity": 195, "functions": 4, "length_max": 132, "length_p50": 6, "length_p90": 132, "over_300": 0, "trivial_wrappers": 0},
    "src/Scalar.cpp": {"complexity": 2491, "functions": 48, "length_max": 296, "length_p50": 10, "length_p90": 65, "over_300": 0, "trivial_wrappers": 7},
    "src/Snapshot.cpp": {"complexity": 18, "functions": 6, "length_max": 56, "length_p50": 1, "length_p90": 56, "over_300": 0, "trivial_wrappers": 1},
    "src/SoftFloat.cpp": {"complexity": 1112, "functions": 9, "length_max": 197, "length_p50": 10, "length_p90": 197, "over_300": 0, "trivial_wrappers": 2},
    "src/Varargs.inc": {"complexity": 223, "functions": 8, "length_max": 84, "length_p50": 6, "length_p90": 84, "over_300": 0, "trivial_wrappers": 0},
    "src/Wide.cpp": {"complexity": 1647, "functions": 16, "length_max": 226, "length_p50": 5, "length_p90": 188, "over_300": 0, "trivial_wrappers": 0},
    "src/WideRuntime.inc": {"complexity": 126, "functions": 1, "length_max": 55, "length_p50": 55, "length_p90": 55, "over_300": 0, "trivial_wrappers": 0},
    "src/runtime/CallerSnapshot.inc": {"complexity": 316, "functions": 26, "length_max": 67, "length_p50": 5, "length_p90": 16, "over_300": 0, "trivial_wrappers": 1},
    "src/runtime/NativeComparison.inc": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "src/runtime/ShadowStack.inc": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "src/runtime/SingleFrame.inc": {"complexity": 0, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/address_spaces.py": {"complexity": 8, "functions": 1, "length_max": 67, "length_p50": 67, "length_p90": 67, "over_300": 0, "trivial_wrappers": 0},
    "tests/aggregate_rows.py": {"complexity": 26, "functions": 1, "length_max": 179, "length_p50": 179, "length_p90": 179, "over_300": 0, "trivial_wrappers": 0},
    "tests/allocator_closure.py": {"complexity": 27, "functions": 2, "length_max": 153, "length_p50": 2, "length_p90": 153, "over_300": 0, "trivial_wrappers": 1},
    "tests/analysis_clock.py": {"complexity": 1, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_counters.py": {"complexity": 21, "functions": 3, "length_max": 230, "length_p50": 56, "length_p90": 230, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_convergence.py": {"complexity": 9, "functions": 2, "length_max": 40, "length_p50": 17, "length_p90": 40, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_slot_compaction.py": {"complexity": 15, "functions": 1, "length_max": 53, "length_p50": 53, "length_p90": 53, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_load_union.py": {"complexity": 17, "functions": 1, "length_max": 57, "length_p50": 57, "length_p90": 57, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_load_images.py": {"complexity": 32, "functions": 2, "length_max": 153, "length_p50": 17, "length_p90": 153, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_containment.py": {"complexity": 36, "functions": 1, "length_max": 69, "length_p50": 69, "length_p90": 69, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_pointer_products.py": {"complexity": 45, "functions": 1, "length_max": 82, "length_p50": 82, "length_p90": 82, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_transfer.py": {"complexity": 44, "functions": 3, "length_max": 202, "length_p50": 12, "length_p90": 202, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_vector_gep.py": {"complexity": 13, "functions": 3, "length_max": 107, "length_p50": 22, "length_p90": 107, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_integer_pointer_closure.py": {"complexity": 9, "functions": 1, "length_max": 100, "length_p50": 100, "length_p90": 100, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_monotone.py": {"complexity": 21, "functions": 4, "length_max": 206, "length_p50": 4, "length_p90": 206, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_pointer_closure.py": {"complexity": 26, "functions": 5, "length_max": 231, "length_p50": 16, "length_p90": 231, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_pt6_residue.py": {"complexity": 19, "functions": 1, "length_max": 53, "length_p50": 53, "length_p90": 53, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_edges.py": {"complexity": 23, "functions": 1, "length_max": 74, "length_p50": 74, "length_p90": 74, "over_300": 0, "trivial_wrappers": 0},
    "tests/analysis_performance.py": {"complexity": 5, "functions": 1, "length_max": 69, "length_p50": 69, "length_p90": 69, "over_300": 0, "trivial_wrappers": 0},
    "tests/budget_stage.py": {"complexity": 28, "functions": 4, "length_max": 205, "length_p50": 4, "length_p90": 205, "over_300": 0, "trivial_wrappers": 0},
    "tests/build_defaults.py": {"complexity": 4, "functions": 1, "length_max": 57, "length_p50": 57, "length_p90": 57, "over_300": 0, "trivial_wrappers": 0},
    "tests/build_fallback.py": {"complexity": 10, "functions": 1, "length_max": 120, "length_p50": 120, "length_p90": 120, "over_300": 0, "trivial_wrappers": 0},
    "tests/cc_calls.py": {"complexity": 16, "functions": 3, "length_max": 90, "length_p50": 12, "length_p90": 90, "over_300": 0, "trivial_wrappers": 1},
    "tests/cc_switch.py": {"complexity": 16, "functions": 3, "length_max": 100, "length_p50": 10, "length_p90": 100, "over_300": 0, "trivial_wrappers": 1},
    "tests/comparison_layout.py": {"complexity": 14, "functions": 3, "length_max": 198, "length_p50": 10, "length_p90": 198, "over_300": 0, "trivial_wrappers": 0},
    "tests/comparison_layout_regions.py": {"complexity": 8, "functions": 1, "length_max": 148, "length_p50": 148, "length_p90": 148, "over_300": 0, "trivial_wrappers": 0},
    "tests/contract_policy.py": {"complexity": 7, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/contracts.py": {"complexity": 9, "functions": 10, "length_max": 17, "length_p50": 9, "length_p90": 14, "over_300": 0, "trivial_wrappers": 2},
    "tests/corpus_gate.py": {"complexity": 91, "functions": 11, "length_max": 187, "length_p50": 18, "length_p90": 101, "over_300": 0, "trivial_wrappers": 1},
    "tests/descriptors.py": {"complexity": 8, "functions": 1, "length_max": 96, "length_p50": 96, "length_p90": 96, "over_300": 0, "trivial_wrappers": 0},
    "tests/dialect_version.py": {"complexity": 7, "functions": 2, "length_max": 118, "length_p50": 5, "length_p90": 118, "over_300": 0, "trivial_wrappers": 0},
    "tests/entry_runtime.py": {"complexity": 4, "functions": 1, "length_max": 51, "length_p50": 51, "length_p90": 51, "over_300": 0, "trivial_wrappers": 0},
    "tests/entry_snapshot.py": {"complexity": 35, "functions": 4, "length_max": 119, "length_p50": 52, "length_p90": 119, "over_300": 0, "trivial_wrappers": 0},
    "tests/gate_policy.py": {"complexity": 2, "functions": 1, "length_max": 8, "length_p50": 8, "length_p90": 8, "over_300": 0, "trivial_wrappers": 1},
    "tests/general_dispatch.py": {"complexity": 28, "functions": 3, "length_max": 233, "length_p50": 72, "length_p90": 233, "over_300": 0, "trivial_wrappers": 0},
    "tests/integer_intrinsics.py": {"complexity": 506, "functions": 3, "length_max": 4, "length_p50": 2, "length_p90": 4, "over_300": 0, "trivial_wrappers": 1},
    "tests/key_audit.py": {"complexity": 20, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/launch_runtime.c": {"complexity": 76, "functions": 14, "length_max": 11, "length_p50": 6, "length_p90": 11, "over_300": 0, "trivial_wrappers": 2},
    "tests/materialisation.py": {"complexity": 27, "functions": 2, "length_max": 135, "length_p50": 13, "length_p90": 135, "over_300": 0, "trivial_wrappers": 0},
    "tests/memory_runtime.py": {"complexity": 58, "functions": 2, "length_max": 22, "length_p50": 20, "length_p90": 22, "over_300": 0, "trivial_wrappers": 0},
    "tests/native_checked.py": {"complexity": 20, "functions": 1, "length_max": 208, "length_p50": 208, "length_p90": 208, "over_300": 0, "trivial_wrappers": 0},
    "tests/native_comparison.py": {"complexity": 5, "functions": 3, "length_max": 182, "length_p50": 2, "length_p90": 182, "over_300": 0, "trivial_wrappers": 1},
    "tests/native_fixtures.py": {"complexity": 8, "functions": 1, "length_max": 146, "length_p50": 146, "length_p90": 146, "over_300": 0, "trivial_wrappers": 0},
    "tests/native_hello.py": {"complexity": 3, "functions": 2, "length_max": 122, "length_p50": 18, "length_p90": 122, "over_300": 0, "trivial_wrappers": 0},
    "tests/native_layout.py": {"complexity": 20, "functions": 1, "length_max": 163, "length_p50": 163, "length_p90": 163, "over_300": 0, "trivial_wrappers": 0},
    "tests/native_link.py": {"complexity": 16, "functions": 5, "length_max": 222, "length_p50": 16, "length_p90": 222, "over_300": 0, "trivial_wrappers": 0},
    "tests/normalisation_check.cpp": {"complexity": 56, "functions": 3, "length_max": 26, "length_p50": 13, "length_p90": 26, "over_300": 0, "trivial_wrappers": 0},
    "tests/normalisation_scope.py": {"complexity": 16, "functions": 4, "length_max": 35, "length_p50": 12, "length_p90": 35, "over_300": 0, "trivial_wrappers": 0},
    "tests/pin_policy.py": {"complexity": 31, "functions": 26, "length_max": 88, "length_p50": 10, "length_p90": 32, "over_300": 0, "trivial_wrappers": 0},
    "tests/pinned_siblings.py": {"complexity": 6, "functions": 2, "length_max": 19, "length_p50": 13, "length_p90": 19, "over_300": 0, "trivial_wrappers": 0},
    "tests/prior_objects.py": {"complexity": 3, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/probes/r-hello.c": {"complexity": 0, "functions": 1, "length_max": 5, "length_p50": 5, "length_p90": 5, "over_300": 0, "trivial_wrappers": 0},
    "tests/probes/varargs-mixed.c": {"complexity": 35, "functions": 7, "length_max": 34, "length_p50": 6, "length_p90": 34, "over_300": 0, "trivial_wrappers": 1},
    "tests/production.py": {"complexity": 32, "functions": 1, "length_max": 252, "length_p50": 252, "length_p90": 252, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_budgets.py": {"complexity": 23, "functions": 2, "length_max": 124, "length_p50": 51, "length_p90": 124, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_cross_major.py": {"complexity": 6, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_dispatch.py": {"complexity": 29, "functions": 2, "length_max": 155, "length_p50": 20, "length_p90": 155, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_environments.py": {"complexity": 58, "functions": 4, "length_max": 191, "length_p50": 56, "length_p90": 191, "over_300": 0, "trivial_wrappers": 1},
    "tests/production_lifts.py": {"complexity": 43, "functions": 2, "length_max": 160, "length_p50": 18, "length_p90": 160, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_records.py": {"complexity": 19, "functions": 1, "length_max": 60, "length_p50": 60, "length_p90": 60, "over_300": 0, "trivial_wrappers": 0},
    "tests/production_shapes.py": {"complexity": 57, "functions": 1, "length_max": 319, "length_p50": 319, "length_p90": 319, "over_300": 1, "trivial_wrappers": 0},
    "tests/quality_ratchet.py": {"complexity": 2, "functions": 2, "length_max": 35, "length_p50": 17, "length_p90": 35, "over_300": 0, "trivial_wrappers": 0},
    "tests/r_envelopes.py": {"complexity": 44, "functions": 8, "length_max": 56, "length_p50": 7, "length_p90": 56, "over_300": 0, "trivial_wrappers": 2},
    "tests/r_typed_faults.py": {"complexity": 52, "functions": 5, "length_max": 238, "length_p50": 25, "length_p90": 238, "over_300": 0, "trivial_wrappers": 2},
    "tests/recognition.py": {"complexity": 62, "functions": 1, "length_max": 129, "length_p50": 129, "length_p90": 129, "over_300": 0, "trivial_wrappers": 0},
    "tests/reference_images.py": {"complexity": 8, "functions": 1, "length_max": 60, "length_p50": 60, "length_p90": 60, "over_300": 0, "trivial_wrappers": 0},
    "tests/region_keys.py": {"complexity": 28, "functions": 1, "length_max": 24, "length_p50": 24, "length_p90": 24, "over_300": 0, "trivial_wrappers": 0},
    "tests/register_classes.py": {"complexity": 11, "functions": 1, "length_max": 121, "length_p50": 121, "length_p90": 121, "over_300": 0, "trivial_wrappers": 0},
    "tests/reversible.py": {"complexity": 23, "functions": 2, "length_max": 304, "length_p50": 2, "length_p90": 304, "over_300": 1, "trivial_wrappers": 1},
    "tests/review_regressions.py": {"complexity": 208, "functions": 1, "length_max": 945, "length_p50": 945, "length_p90": 945, "over_300": 1, "trivial_wrappers": 0},
    "tests/scalars.py": {"complexity": 54, "functions": 1, "length_max": 229, "length_p50": 229, "length_p90": 229, "over_300": 0, "trivial_wrappers": 0},
    "tests/sqlite_vector_normalise.py": {"complexity": 40, "functions": 10, "length_max": 35, "length_p50": 8, "length_p90": 29, "over_300": 0, "trivial_wrappers": 1},
    "tests/sqlite_vector_fp.py": {"complexity": 2, "functions": 1, "length_max": 37, "length_p50": 37, "length_p90": 37, "over_300": 0, "trivial_wrappers": 0},
    "tests/sqlite_vector_boundary.py": {"complexity": 8, "functions": 2, "length_max": 45, "length_p50": 21, "length_p90": 45, "over_300": 0, "trivial_wrappers": 0},
    "tests/shadow_stack.py": {"complexity": 15, "functions": 1, "length_max": 68, "length_p50": 68, "length_p90": 68, "over_300": 0, "trivial_wrappers": 0},
    "tests/smoke.py": {"complexity": 18, "functions": 1, "length_max": 4, "length_p50": 4, "length_p90": 4, "over_300": 0, "trivial_wrappers": 0},
    "tests/softfloat.py": {"complexity": 109, "functions": 8, "length_max": 792, "length_p50": 11, "length_p90": 792, "over_300": 1, "trivial_wrappers": 3},
    "tests/validation.py": {"complexity": 20, "functions": 0, "length_max": 0, "length_p50": 0, "length_p90": 0, "over_300": 0, "trivial_wrappers": 0},
    "tests/varargs.py": {"complexity": 33, "functions": 10, "length_max": 76, "length_p50": 11, "length_p90": 65, "over_300": 0, "trivial_wrappers": 0},
    "tests/varargs_musl.py": {"complexity": 2, "functions": 1, "length_max": 43, "length_p50": 43, "length_p90": 43, "over_300": 0, "trivial_wrappers": 0},
    "tests/wide.py": {"complexity": 249, "functions": 2, "length_max": 4, "length_p50": 2, "length_p90": 4, "over_300": 0, "trivial_wrappers": 1}
  },
  "litter": [],
  "process_identifiers": 2
}
```
