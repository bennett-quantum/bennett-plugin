# Plugin batch review — 2026-11-03

**Verdict: BLOCK — 4 P0, 7 P1.**

Reviewed `dc3c64c380ac72a5d0f0fa1d8e40610b0ecc4444..661d4edcfd9c9d337e0222b6e2fcc7f950f50a4e` (176 commits; 134 changed tracked files). Contracts: pinned dialect 0.2.10 (`023f5a771a814270634db3be9cfde88ded69f975`), ISA 0.8, North Star. Source/tests/scripts matched this endpoint; later commits are excluded.

Reproductions: `timeout 180s python3 .tmp/rev-plugin/review_repros.py --case CASE` for each case below, on LLVM18 and LLVM23. Headless job environment; at most four subprocesses. The full focused command without `--case` exited 0: 24 observations reproduced, 40 existing analysis regressions passed, four native baseline runs passed. Bug-reproduction success is **not** compiler correctness. Outputs: `.tmp/rev-plugin/review-results.json`; exact inputs and commands are also in each bead.

| Priority | File:line | Failure scenario and observed result | CASE / bead |
|---|---|---|---|
| P0 | `src/Normalise.cpp:353` | Shuffle mask `[undef,1]` over `[7,9]`: S2 says 7; emitted oracle returns 0; residual validator accepts. N7 requires lane zero. | `shuffle` / **bp-kem** |
| P0 | `src/Production.cpp:1326` | Callee writes 9 through `ptr byval(i8)`; caller returns 9 instead of native 7. Calls omit the private copy. | `byval` / **bp-ie6** |
| P0 | `src/Production.cpp:2107,2197` | `top(){return ++g;}` across two launches prints `1 1 host_global=0`; identical native IR prints `1 2 host_global=2`. Each call reloads/unloads private globals. | `global-counter` / **bp-acm** |
| P0 | `src/Scalar.cpp:516,669` | Accepted big-endian global/load of i16 258 returns 513 (little-endian control: 258); source image byte order and ISA load disagree. | `endian-E` / **bp-pcn** |
| P1 | `src/Production.cpp:2120` | `top(ptr p)` compiles successfully, but LLVM rejects emitted host.bc: “Bitwidth for integer type out of range”. Stub assumes integer arguments. | `pointer_abi` / **bp-k1y** |
| P1 | `src/Production.cpp:1197` | Valid block order entry/use/def, CFG entry→def→use, must compute x+3; lowering rejects the dominating definition before naming it. | `block_order` / **bp-cii** |
| P1 | `src/Production.cpp:1332` | Valid `__bennett_ctrl` of an empty action aborts with unimplemented marker lowering. Controlled-anything is omitted. | `control` / **bp-3lp** |
| P1 | `src/Production.cpp:88,1051` | Host-input gate opcode, including valid X=1, aborts with “scalar descriptor finite dispatch”; §3.4 requires runtime dispatch. | `dynamic_gate` / **bp-onu** |
| P1 | `src/SoftFloat.cpp:41` | Adding an unrelated H-only `<8 x i1>` load to a working marked module aborts arith discovery. Native code is forced through device normalisation, blocking the mixed fat object (bennett-4ht). | `mixed_native_vector` / **bp-yyp** |
| P1 | `src/Production.cpp:1332` | An unresolved callee in one branch rejects the whole function, losing x=0→7 on the safe branch. §4.5 requires hostcall or reached F(8), with coverage. | `host_import` / **bp-dc7** |
| P1 | `scripts/build:23; src/SoftFloat.cpp:35,51` | Fresh no-CMake build omits both `BENNETT_ARITH_DEFAULT_*` definitions and cannot compile. LLVM18 fallback-flags syntax check exits 1 with undeclared names. | fallback-flags syntax check / **bp-osi** |

Fallback command: `timeout 30s g++ -I/usr/lib/llvm-18/include -std=c++17 -fno-exceptions -funwind-tables -D_GNU_SOURCE -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS -fPIC -fsyntax-only src/SoftFloat.cpp` (exit 1).

P2+ collection: **bp-y89** (`nit`, P3): source issue/milestone references; descriptor-specific gate diagnostics; namespace/declaration litter; missing fallback-cache dependency inputs (stale-cache execution consequence unconfirmed).

Coverage: closely read analysis transfers/verdicts, region keys, scalar/vector/stack normalisation, CC/lifted lowering, descriptor/budget handling and host ABI; skimmed wide numerical runtime details, R/asm, native comparison adapters, remaining tests, scripts and CMake. No `include/` tree exists. No source fixes or full gates.

Provenance/R14: gpt-6.1-sol xhigh reviewed this batch under the R14 quota direction; opposite-model rule 2 remains outstanding for the Codex subset (orchestrator queues Claude cross-check). Tagged Codex (13): a3757b17, e74a8c9f, 53560530, 6e921fbe, 2aba17a6, 0c1e3743, b8b92e57, 78c4f107, 1d3ac90a, 933d13b8, d5c3d5f2, 0ac61808, 661d4edc. Tagged Claude (28): 3457f38b, 287714d0, 8d68a295, 975aa9a3, 18f780b8, c7ab6196, ce442295, 2991461d, 90711166, b9cd2825, 157d4bd1, c93f68ab, 78d5c116, 63360adb, 3a856a7f, 83b0afb3, b9c31896, ed329d9f, 5554b633, db2e9e7d, 10652d09, 85b5ca05, 23cf87b5, b42a88a4, ab317be4, a3c4a1e8, a0400513, 2a41c048. Other 135 commits have neither requested marker; authorship is unclassified.
