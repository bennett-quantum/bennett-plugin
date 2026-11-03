# Review of feaa972 (bp-ipp, Codex sol-rung4-ipp) — Claude Sonnet 5.5, 2026-11-03T12:56:09Z

**Commit:** feaa972 on rung4-plugin (parent f46548a). **Verdict: CLEAR for the diff** (rider 2 of advisor R16 is implemented
correctly and the witness is a real red-green test). **One P1 exposed by the fix, not caused by a defect in it:** bp-2e7
(pointer recurrences through memory/recursion now exhaust the budget on the default path). The orchestrator must route
bp-2e7; it is not a reason to restore the widening.

## Method
Built feaa972 (new) and f46548a (old) from `git archive` copies under `.tmp/sonnet-rev-ipp/{new,old}`, LLVM 18 (and 23 for
the new tree), `cmake -DLLVM_DIR=… && make -j4`, headless, own TMPDIR.

## Risk checks
1. **Default path exact — OK.** Diff and grep of src/Analysis.cpp: the pointer closure in `canonical()` (L314) is gated by
   `EarlyChainClose &&`; `settle()` (L477) now returns early on pointers unless the flag; the collapse in `store()` (L1046) was
   already flag-gated. Remaining numeric limits on the default path all concern INT atoms or index sets, i.e. §5.1's K:
   L370 (>4096 INT → top), L1614/1616 (bit-pack INT product), L1736 (intrinsic constant folding tuples), L2350 (GEP index
   set >4096 → orbit not computed, falls to the ordinary rounds), L2570–2600 (dense bitwise INT), L2765–2794 (SCEV index bounds ≤4096).
   None returns top/EXT for a pointer set by cardinality. (L1959 comment: additive INT cycle, exact.)
2. **Flag default-off in every build mode — OK.** One `cl::opt<bool>(…,cl::init(false))`; CMakeLists.txt and the no-CMake
   path of scripts/build pass no defines for it; grep finds no other setter. Help text, stderr line and report field
   (`non_reference`, L3314) all say NON-REFERENCE when on; reference_k checks both ('flag-labelled'), and checks the default is unlabelled.
3. **Witness can fail — OK.** Ran the new tests/ against the OLD plugin: `python3 tests/reference_k.py --major 18` →
   18/22, failing exactly `unknown-extent-K+1-exact`, `constant-calls-4097-exact-offsets`, `constant-calls-4097-load-one` (top, 2 atoms)
   and `flag-labelled` (old wording). New plugin: 22/22. Expected sets are `{PTR(@bytes,n,0) | n<count}` built in Python, not read
   from the plugin. The witness is registered in analysis_edges (33/33, 18).
4. **Blow-up is loud — OK, but see P1.** Exact offsets never fail quietly: exhaustion ends in the existing
   `unimplemented: §5.2 … budget exhausted at AV(…)` (exit 1), never a fallback to top.

## Findings
**P1 — bp-2e7. Default now rejects pointer recurrences through memory / recursion that the spec accepts.**
Fixtures: docs/reviews/2026-11-03-ipp-repro/{mem,call,phi}.ll. Command (LLVM 18, new vs old plugin):
`opt -load-pass-plugin=…/libbennett-plugin-18.so -passes=bennett -bennett-dialect=0.2.10 -bennett-analysis-only -bennett-report=… -disable-output X.ll`
(add `--bennett-tier=reversible --bennett-entry=top` for R: same).
- mem.ll (load @cell, gep 8, store back, loop): new rc=1 after 17–24 s, 2.15 GB RSS, "PT6 budget exhausted at AV(%r)"; old rc=0 in 0.7 s.
- call.ll (self-recursive callee with p+8): new rc=1, 18–22 s, 2.15 GB, "PT8/PT9/PT12 budget exhausted"; old rc=0 in 0.6 s.
- phi.ll (phi + gep 8): both rc=0 in 0.01 s (`PTR(@g,0,8)`+EXT, the 5u3 §5.2 coset form).
Errata 5u3 §5.2 gives these an exact finite answer (subgroup closure of a pure fixed-displacement SCC, memory relation
included), so the spec accepts them; the old accept came from the non-reference closure, the new reject is the missing
exact acceleration. Loud and consistent with 5u3 §24 ("unfinished build"), so the commit is right, but it is on the rung-3/4 critical
path (linked structures, SQLite) and neither the bp-fj1 note nor a test records it. Also unchecked here: musl hello R closure (bp-loq).
Needs the §5.2 coset closure for memory/call SCCs (bp-fj1 engine or ahead of it) and a pinning test.

P2+ (bp-43y): budget message does not name which resource ran out (stopped at 17 s with budget 100 s, so not time);
reversible.py / softfloat.py fail on this host on sibling pins (env drift, not feaa972); flag-on 4097 pointer closure unexercised.

## Other checks
- docs/design/factored-points-to.md: design only (commit touches src/Analysis.cpp only for code; no engine); design not reviewed here.
- Focused suites on new/18: reference_k 22/22, analysis_edges 33/33, analysis_performance 3/3, reference_images, load_delta, production pass; reference_k 23: 22/22.
- Notes relabelling (bp-fj1 evidence note): reads correctly (D-series NON-REFERENCE, numbers retained).
