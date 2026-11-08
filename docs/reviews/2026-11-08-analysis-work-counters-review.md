# Device-analysis work counters review

Reviewer: gpt-6.1-sol. Date (UTC): 2026-11-08T11:33:36Z.
Reviewed commit: `37e402bf5414e7b291e166d534c2c52c6f4fd8d1`; baseline: `2319890`.
Scope: `git diff 2319890..37e402b`, including the quality-baseline refresh. One evidence-first review round under COMMON rule 7. No source/test edits or bead writes; the proposed bead below is for the orchestrator.

## Claims and independent reruns

All artifacts below are under `/home/tobias/Projects/bennett-workspace/bennett-plugin-job-s2-counters/.tmp/s2-counters-review/` (`D`). `H=D/head-tree` and `B=D/baseline-tree` are independent `git archive` extractions, not the author's build tree. Both use only the pinned gate cache. Commands ran headless with `TMPDIR=D/tmp` and Python bytecode disabled. Build width 9 was derived from 64 available CPUs and 52.45 GiB MemAvailable, reserving 16 CPUs/16 GiB and estimating 4 GiB per compiler process (`resources.json`). There is no plugin-local hang-guard table; the census `work/time_guard.py` moderate/long classes supplied outer guards and per-command wall/CPU receipts in `D/tmp/command-receipts.jsonl`. The full plugin gate remains the orchestrator's responsibility and was not run here.

| Author claim | Independent result at the reviewed head |
| --- | --- |
| RelWithDebInfo LLVM 18/23 builds pass | PASS for both baseline and head, four fresh builds. Baseline build walls 70.532/68.697 s; head 73.503/72.086 s. |
| New counter test RED on `2319890`, GREEN 18/18 on both majors | Reproduced RED on **both** baseline majors: exit 1, correct §5.2 allowance diagnostic, assertion `expected exactly one work receipt`. Head GREEN **18/18 each**, exit 0 (`counters-{baseline,head}-{18,23}.{stdout,stderr}`). |
| Focused runner passes 12 commands in 34.627 s | Reproduced **12/12**, 38.336 s; all policies and all nine selected standard regressions retained, analysis edges/performance on both majors. Both integrated counter suites passed 18/18 (`focused-receipt.json`). |
| Quality refresh and output-failure handling | `python3 -B "$H/scripts/quality.py" --check`: PASS, no regressions. Four deliberate output-write failures (success/round stop, both majors) each emitted exactly one receipt and an explicit output error (`review.py audit`). |
| Clock tests 5/5 | Reproduced **5/5**, reported wall 348 ms (`clock.stdout`). |
| Hashtable median wall 1.205 -> 1.168 s, 64 rounds | Same completion/round-count result; fresh paired measurements below show overlapping timings, not a repeatable speedup. |
| No `BennettPlugin.cpp` change | Confirmed from the full diff; registered option and writer in that file are unchanged. |
| Allowance-stop sample has zero dispatch counters | Correct but incomplete evidence: fresh `gai_strerror` stops below reach hundreds of completed rounds and all counters are non-zero. |
| Two combined default runs UNKNOWN at the aggregate deadline | Confirmed in the author's logs; independent diagnosis below. |

Exact rebuild/test command forms (substitute each displayed tree and major):

```sh
cmake -S "$tree" -B "$tree/build/llvm$major" -DLLVM_DIR="/usr/lib/llvm-$major/lib/cmake/llvm" -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBENNETT_OUTPUT_DIR="$tree/build"
cmake --build "$tree/build/llvm$major" -j 9
python3 -B "$H/tests/analysis_counters.py" --major "$major" --plugin "$tree/build/libbennett-plugin-$major.so" --artifacts "$D/counters-$kind"
python3 -B "$H/tests/analysis_clock.py"
python3 -B "$D/focused-test.py"
```

Here `tree=B,H`, `major=18,23`, and `kind=baseline,head`. `focused-test.py` is the author's selector with only its archive path changed to `head-tree/scripts/test`; the archived runner itself is unchanged. `review.py build`, `tests`, `focused`, `observations`, and `performance` retain the complete invocation arrays. No selected test assertion was weakened.

## Stops after rounds begin

`review.py observations` reads the exact `gai_strerror` argv from `bennett/.tmp/census/musl-census.json`, retains its `prlimit --as=2415919104`, dialect/ISA/budget configuration and bitcode, and substitutes only the independently built plugin, owned output/report paths, and the requested stop option. Each major ran once with `-bennett-analysis-budget-ms=5000` and twice with `-bennett-analysis-max-rounds=10` (the other original stop option retained). Every run exited 1 with the original §5.2 diagnostic, exactly one stderr receipt, and a matching `analysis_work` report object.

LLVM 18, 5000 CPU ms allowance:

```text
bennett-analysis-work:{"av_merges":4351837,"cpu_ms":{"deterministic":false,"value":5000.2820000000002},"field_joins":989,"function_visits":{"top":{"gai_strerror":989},"top_limit":10,"total":989},"join_count":4353814,"rounds_completed":988,"slot_joins":988,"transfer_applications":14837,"worklist_pops":23718}
```

LLVM 18, 10-round limit, first of two runs:

```text
bennett-analysis-work:{"av_merges":1211,"cpu_ms":{"deterministic":false,"value":1.1847000000000001},"field_joins":10,"function_visits":{"top":{"gai_strerror":10},"top_limit":10,"total":10},"join_count":1231,"rounds_completed":10,"slot_joins":10,"transfer_applications":164,"worklist_pops":240}
```

LLVM 23, 5000 CPU ms allowance:

```text
bennett-analysis-work:{"av_merges":4737914,"cpu_ms":{"deterministic":false,"value":5002.3633},"field_joins":1039,"function_visits":{"top":{"gai_strerror":1039},"top_limit":10,"total":1039},"join_count":4739991,"rounds_completed":1038,"slot_joins":1038,"transfer_applications":15597,"worklist_pops":24935}
```

LLVM 23, 10-round limit, first of two runs:

```text
bennett-analysis-work:{"av_merges":1211,"cpu_ms":{"deterministic":false,"value":1.1702999999999999},"field_joins":10,"function_visits":{"top":{"gai_strerror":10},"top_limit":10,"total":10},"join_count":1231,"rounds_completed":10,"slot_joins":10,"transfer_applications":164,"worklist_pops":240}
```

Both max-round runs have byte-identical receipt lines **after removing only `cpu_ms`**, independently checked on LLVM 18 and 23 (`gai-*-rounds-{a,b}.deterministic.txt`). Their deterministic objects also agree across these two majors: 164 transfers, 240 dispatches, 10 completed rounds/visits, 1211 AV merges, 10 field joins, 10 slot joins, 1231 total joins. The allowance runs reach 988 and 1038 completed rounds respectively; every requested counter is non-zero. CPU allowance stops are time-cut: their counts and CPU field are not expected to be byte-equal between runs. This distinction is essential when consuming the receipt.

## Successful fixpoint, report compatibility and cost

Five alternating baseline/head pairs per major used the author's hashtable command, with independent libraries and reports:

```sh
/usr/lib/llvm-$major/bin/opt -load-pass-plugin="$tree/build/libbennett-plugin-$major.so" -passes=bennett -bennett-dialect=0.2.13 -bennett-analysis-only -disable-output "$tree/tests/probes/hashtable-postlink-$major.ll" -bennett-report="$D/hashtable-$major-$kind-$trial.json"
```

| Major | Baseline median wall (range), s | Head median wall (range), s | Baseline/head median child CPU, s |
| --- | --- | --- | --- |
| 18 | 1.318 (1.169–1.334) | 1.319 (1.269–1.320) | 1.287 / 1.270 |
| 23 | 1.823 (1.720–2.233) | 1.871 (1.719–2.137) | 1.815 / 1.855 |

These are observations, not performance thresholds. LLVM 18 changes by about 1 ms; LLVM 23 by about 48 ms (2.6%), within overlapping sample ranges. This does not establish a repeatable counter regression or the author's apparent speedup. Final measurements ran without another review build/test active; an initial timing set whose last samples overlapped the focused runner was discarded and retained as `performance-initial.json`.

Every head trial reaches 64 rounds and has an identical deterministic receipt within its major. LLVM 18 repeats the author's exact totals: 14571 transfers, 41024 dispatches, 192 visits, 3476408 AV merges, 384 field joins, 17097 slot joins, 3493889 joins. LLVM 23: 14334 transfers, 41536 dispatches, 192 visits, 2919031 AV merges, 384 field joins, 73482 slot joins, 2992897 joins. Different LLVM IR need not have equal work counts.

For each major, removing only `analysis_work` from **every** head report yields the baseline report object exactly, including nested values. The retained fields are `analysis_rounds`, `dialect`, `isa`, `mode`, `functions`, `regions`, and `values` (`performance.json`). This checks compatibility more strongly than checking field names alone.

## Combined default UNKNOWN investigation

The author's `scripts-test.txt` ends in `tests/production_lifts.py --major 18 --case entry-replay-byte --case rung4-mini --case rung8-mini --case listsum --case shadow-n24`: only 0.466920378 s remained, so prior work used 179.533079622 s of the shared 180 s guard. `scripts-test-final.txt` ends in the nine-case `tests/review_regressions.py --major 18` invocation: only 6.258959365 s remained, so prior work used 173.741040635 s. Every completed command was green. Neither log preserves per-command durations or host load, so retrospective attribution of each earlier second is impossible; those two runs remain UNKNOWN, not PASS or a proved counter regression.

The independent rerun loaded the unchanged runner with `python3 -B "$D/trace_default.py" "$H/scripts/test" "$D/default-head-commands.jsonl"`; the observer records each subprocess's wall/CPU usage, deadline and exit without changing argv, policies, driver selection or timeouts. It ran without another local review build/test active. Start/end `uptime` load averages were **11.79,12.74,9.42** / **19.30,15.83,11.19** on this 64-CPU host. This was a locally quiet slot, not an idle host.

Head: **UNKNOWN**, 180.194 s wall, 322.142 s combined child CPU (both majors run concurrently). All **68 completed commands exited 0**. Both majors were interrupted in `production_environments`: LLVM 18 had **13.220039523 s** left; LLVM 23, **13.572064202 s**. On the LLVM 18 path, shared policies used **28.575 s** (including `pin_policy` 20.916 s), then completed drivers used about **138.2 s**, and the interrupted driver used 13.237 s. The largest completed driver costs were `aggregate_rows` **30.626 s**, `reversible` **28.432 s**, `softfloat` **14.402 s**, and `native_checked` **7.906 s**; other completed drivers consumed about 56.8 s. Full determining receipts: `default-head-commands.jsonl`, `default-head.{stdout,stderr}`.

To test attribution, the identical observer/runner invocation was run once on the fresh **2319890 baseline**, substituting `B` for `H`. It also returned **UNKNOWN**, 180.164 s wall, 326.019 s combined child CPU, with **76 completed commands all exit 0**. Both groups were interrupted later in `budget_stage`: only **1.374763819 s** (LLVM 18) and **2.562760495 s** (LLVM 23) remained. Policies consumed 28.485 s; each major group consumed the remaining approximately 151.5 s. Start/end load averages were **15.18,15.18,11.17** / **15.60,15.83,12.14** (`default-baseline-*`). Thus the aggregate guard already fails to cover the baseline suite in this slot.

There is a small measurable cost for the **added test coverage**: `analysis_performance` took 2.205/2.861 s on head versus 1.437/2.000 s on baseline (18/23), approximately **0.77/0.86 s extra per major**. That is separate from hot-loop counter overhead. The baseline control also reused the native checker compiled during the head run: `native_checked` dropped from 7.906/8.043 s to 1.357/1.304 s. The pinned checker CLI explicitly caches its executable under `$TMPDIR/native-check`; both cached executables have timestamps within the head run. This explains most of that particular difference; a single sequential control cannot assign every other timing difference to code or load. Dominant driver wall/CPU times are close (for example head `aggregate_rows` 30.626/30.642 s), so host scheduling delay alone is not established as the cause.

Conclusion: the existing 180 s aggregate budget is insufficient for these runs, including the baseline; the observed UNKNOWN is **not demonstrated to be caused by this change**. No timeout threshold was raised and no combined run is claimed green. The author's existing repeated-UNKNOWN bead request remains open for the orchestrator; reconcile the guard with measured suite demand rather than treating these incomplete runs as failures of analysis semantics. The unchanged runner leaks `TimeoutExpired` as raw exit 1 instead of UNKNOWN's prescribed 124; the trace establishes the UNKNOWN classification despite that pre-existing harness defect. Landing still requires the orchestrator's full gate result.

## Exit-path and implementation audit

- `BudgetScope` covers `Analysis::run()` from seeding through post-fixpoint work; its destructor emits the successful receipt, and the atexit callback covers allowance/round-limit stops and helper `fail()`/`unimplemented()` calls that use `std::exit`. Fresh tests exercise fixpoint, CPU and round stops, PT2/PT10, a helper type failure, later missing arithmetic import, no-report success/stop, and unavailable CPU clock. Stops count attempted dispatches before the clock check and transfers only after cache bypass; completed rounds increment after a complete scan. This matches the documented definitions and the hand-derived scalar/cache oracles.
- For the supported LLVM `opt` path, the atexit handler is sound: `std::exit` leaves the automatic scope and its counter storage alive; the handler avoids the destructible `completedReceipt` TLS document. LLVM's `InitLLVM` and `llvm_shutdown_obj` invoke `llvm_shutdown()` from automatic destructors, which `std::exit` skips; LLVM ManagedStatic cleanup is explicit. Normal return restores `activeBudget` before shutdown. Four output-error reruns additionally verify one receipt on both the success and round-stop paths. No callback performs a transfer or budget check. Setting the enum to Emitted before output prevents recursive failure from emitting twice. This is a C++ exit handler, not a signal/crash handler; no signal-safety claim is made.
- The registered-option lookup names the existing `cl::opt<std::string> Report` at `BennettPlugin.cpp:30`. Its unchecked concrete downcast couples the reader to that declaration, but both pinned majors use that exact type and a missing option fails loudly. No missing-option zero/default path exists. Passing the destination explicitly would reduce coupling in a future interface change; the current lookup is not a demonstrated failure.
- One `AnalysisWork` struct owns the counters. Increment sites add integer operations/TLS checks, not allocations; function identities/storage are allocated before the fixpoint loop. Sorting/JSON construction happens at emission. CPU unavailability produces explicit `null` plus an error and a loud stop in the checked path; it never silently substitutes zero. No process identifiers were added to product source/output. Join counts intentionally include attempts and sum the three disclosed categories.
- The 218-line `analysis_counters.main` is below the 300-line finding threshold. Its central helper owns shared receipt validation, and its scalar/cache expected counts are hand-derived; the clock shim makes interruption deterministic. As a sequential test scenario driver it is acceptable. Splitting the independent scenario groups would improve navigation, but there is no separate nit bead. The new test does not cover the function-name collision below.

## Numbered findings

1. **P2 — named and unnamed functions can collide in `function_visits.top`.** `src/Analysis.cpp:55–56` stores a named function's raw name but an unnamed function's printed operand label; line 68 then inserts into a JSON object by that string. Valid IR containing both `define void @0() { ret void }` and `define void @"@0"() { ret void }` completes successfully on both fresh majors but reports `"function_visits":{"top":{"@0":1},"top_limit":10,"total":2}`. Two visited definitions have become one reported entry although fewer than ten functions exist. The existing unnamed-only test misses it. Reproduced with `D/visit-label-collision.ll`; full stderr in `collision-{18,23}.stderr`. Proposed bead: **Use one unambiguous LLVM operand-name representation for every function visit key and add the mixed named/unnamed collision regression.** Counts used by the current rung-2 hashtable and the requested musl probes are correct; no current §8 rung instance or build/gate break was demonstrated for this label edge case, so rule 7 makes it P2. No `bd` writes were made.

P0: none. P1: none. One proposed P2 bead; no nit bead.

Suggestions (optional): pass the report destination through an explicit interface when the shared writer is next changed; split the test driver's scenarios into named groups without changing the assertions. The collision repair and regression belong to the single proposed P2 bead above.

Disposition: ACCEPT with P2 beads
