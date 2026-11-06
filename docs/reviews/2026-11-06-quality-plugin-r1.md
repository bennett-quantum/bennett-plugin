# Plugin quality review, round 1 — 2026-11-06

**Verdict: BLOCK — two P0 findings; no P1.**

Reviewed head: `0a1bc5b8d4d8abbf46b189955be4fa40d9f4bd78`.
Closely reviewed `253e5dd90e842f6b39e38111a7d9c19430c352ab..0a1bc5b8d4d8abbf46b189955be4fa40d9f4bd78`;
checked the earlier pin batch for interactions. Requested full comparison:
`main...job/quality-plugin`, merge-base `5a092cded3ba3351ba8cc2977a7eaf3b40f46526`
(main observed at `2f832729d44cd5fd5995c3077cf69ec2dc93e9cf`).

1. **P0-1 / bp-kya — shared-global protection depends on function order.**
   `src/Production.cpp:2300` follows callees in the same module that the loop at
   `src/Production.cpp:2833` is already rewriting. If external CC entry `helper`
   increments `@g` and appears before CC entry `top`, which calls it, the scan of
   `top` sees the replacement helper stub and misses `@g`. Its embedded device
   object still contains the original helper. Two native launches silently print
   `1 1 0` (last field: host global), versus source-native `1 2 2`.
   Moving `top` before `helper` instead produces the approved promised/pending
   diagnostic and exit 125. Confirmed on **LLVM 18 and 23**, after successful builds,
   with `timeout 60 python3 -B -` (complete inline reproduction in **bp-kya**):
   rename the existing `review-global-counter.ll` entry to `helper`, append a
   marked `top` calling it, lower with the standard plugin command, link
   `host.bc` and a two-call harness against the pinned VM, then execute with
   `review-launch-target.json`. Precompute all entries' original shared-state
   dependencies before replacing any body, and test both orders.

2. **P0-2 / bp-9t7 — the replacement normalization test loses suite coverage.**
   `tests/integer_intrinsics.py:152` validates a separate one-function
   `llvm.ctpop.i8` smoke input, replacing assertions over the actual generated
   module's intrinsic/vector residue. That module now goes straight to clang,
   which can implement missed LLVM intrinsics itself. In a reviewer mutation,
   restoring the raw source body of `f8_cttz` in generated `out.ll` leaves
   `call i8 @llvm.cttz.i8` behind; the removed regex assertion detects it, but
   the current driver still exits 0 with **602/602** cases. Ran
   `timeout 120 python3 -B -` with an in-process `contracts.run_checked`
   interceptor, then `runpy.run_path('tests/integer_intrinsics.py', run_name='__main__')`
   with `--major 18`; full reproducible interceptor is in **bp-9t7**.
   No tracked files were modified by the mutation. Validate the generated suite's
   actual output, including its helper bodies. The analogous small-fixture
   replacements in `wide.py:104` and `memory_runtime.py:75` merit the same check.

P2+ nits: **bp-3mb** (P3, `nit`): unused `subprocess` imports in
`address_spaces.py:7`, `integer_intrinsics.py:4`, `memory_runtime.py:4`,
and `scalars.py:4`.

Verification, headless with the reviewer-local TMPDIR; no full gate:

- `timeout 300 cmake --build build/llvm18 -j3` and the LLVM 23 equivalent: pass.
- `timeout 180 scripts/test`: **21/21 commands, 49.201 s** after builds
  (earlier instrumented run: 38.220 s); includes both majors' 21 exact scalar objects,
  missing-helper diagnostics, class dispatch, function-address separation and review regressions.
- LLVM 18 focused drivers: `timeout 120 python3 -B tests/wide.py --major 18`
  **110/110**; same command for `memory_runtime.py` **33/33** and
  `integer_intrinsics.py` **602/602** clean. Memory driver was retried after a
  concurrent plugin relink briefly made the library incomplete.
- `timeout 180 python3 -B tests/allocator_closure.py --major 18`: **4/4**.
  `timeout 180 python3 -B tests/production_lifts.py --major 18 --case entry-replay-byte --case rung4-mini --case rung8-mini --case listsum --case shadow-n24`: **5/5**.
- `timeout 90 python3 -B scripts/quality.py --check`: pass; ratchet mutations
  also pass within default tests. `timeout 90 scripts/coverage`: reproduces
  **70.53%, 4896/6942**. `git diff --check 253e5dd..HEAD`: pass.
- Red-on-main assessment used `git show main:<path>`, without switching branches:
  the old scalar pruning/missing-helper lookup cannot meet the new contextual-diagnostic
  assertions, and class >= 1 is explicitly refused there. Head's new tests pass.

Coverage: read closely all changed lowering code, shared harness, AST-normalized semantic
changes across every changed Python driver, quality ratchet, coverage/build/gate configuration,
pin interactions, and plan items 9–11; skimmed unchanged numerical/reference internals and
historical docs. `src/Analysis.cpp` is untouched; long Analysis/Normalise splits remain
expressly deferred. HANDOFF.md and tracked progress are retired; README points to the ecosystem
handoff. Checked each anti-slop rule: findings above are the semantic/test-integrity blockers;
the two remaining product bead identifiers are explicitly required by the approved D4 diagnostic.
No source fixes, test weakening, sibling gates or council review performed.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
