# Quality floor

The default test command is `timeout 180 scripts/test`, after building LLVM 18 and 23.
It passed 18 driver commands in **27.621 seconds** with the LLVM 18 gcov build.
The slow integration drivers remain in `scripts/gate`; this job does not run that full gate.
Promised shared-global semantics remain visible through
`tests/review_regressions.py --case global-counter --promised-bp-acm --major 18`.

## Coverage

Measured executable-line coverage: **57.04% (4521 / 7926 lines)**, GCC/gcov 13, LLVM 18.
The instrumented configuration used:

```sh
cmake -S . -B build/coverage18 -DLLVM_DIR=/usr/lib/llvm-18/lib/cmake/llvm   -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS_DEBUG="-O0 -g1 --coverage"   -DCMAKE_MODULE_LINKER_FLAGS=--coverage -DBENNETT_OUTPUT_DIR="$PWD/build"
timeout 900 cmake --build build/coverage18 -j2
timeout 180 scripts/test
timeout 180 python3 tests/allocator_closure.py --major 18
timeout 180 python3 tests/cc_calls.py --major 18
timeout 90 scripts/coverage
```

The same instrumentation is available as `-DBENNETT_COVERAGE=ON` in a single-major GCC configuration.
Coverage counts executable lines under `src/`, including inline headers and includes, and merges
repeated header counters by source line. It is a measurement, with no threshold.

The five least-covered files in that run were Reversible.inc (0/134), Snapshot.cpp (0/60),
WideRuntime.inc (0/52), runtime/NativeComparison.inc (0/1), and runtime/ShadowStack.inc (0/1).
Reversible and general snapshot construction belong to the slow launch/history suites.
Wide runtime construction is exercised by the subsequent focused wide/intrinsic drivers.
The one-line runtime includes embed C source data; instrumenting their generated guest code
would measure the runtime implementation, not this plugin. NativeComparison.cpp's target-aware
transport is also covered by the slow native comparison/layout drivers, rather than the default suite.

## Contracts and remaining mechanics

Dialect 0.2.13 / ISA 0.8 stay pinned. Arithmetic is 5e9b4509f3ee3f95ac9f7d22b43359e72cf9fdab
(1141 exports per LLVM major); allocator and native support are both
248e468ca505c684bbf254e52eb8148f1e530c83. Published allocator bookkeeping changes are
derived and tested in allocator_closure.py, including the separate 128-byte heap boundary.
Shared native/device globals remain promised and pending the published native-sharing contract;
the approved native adapter interim prints that fact and exits 125 before state can reset.
