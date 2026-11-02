# bp-fj1: the §5 reference analysis on the rung-4 SQLite closure, measured (for b-dialect-spec-5u3)

Status: evidence and amendment proposal for the council, written by the plugin rung-4 stream
(branch `rung4-plugin`, 2026-11-02). Nothing here changes the default build: it follows dialect
§5.1's K alone (advisor ruling on b-dialect-spec-5u3). Results of the earlier closure rules are
labelled NON-REFERENCE wherever they appear.

## 1. Setup

- Program: the rung-4 N16 closure of unmodified SQLite as the plugin's analysis sees it,
  `.tmp/rung4/mod/post-18.ll` in this checkout (sha256 prefix c5b5961480542e34; 1,487 defined
  functions, 285,525 instructions, 36,807 seed slots), LLVM 18, `lto<O3>` with the vectoriser on.
- Command (`.tmp/rung4/sq2.sh 18 <seconds> <tag>`): `opt -passes=bennett -bennett-dialect=0.2.10
  -bennett-analysis-only -bennett-analysis-trace -bennett-analysis-budget-ms=<s*1000>
  -bennett-analysis-max-rounds=100000000`, `ulimit -v 14000000`, under `perf record -F 29`.
  Flagged runs add `-bennett-analysis-early-chain-close`.
- Shared host: 12 cores, 30 GB, load 10 to 30 during these runs. Wall times are therefore upper
  bounds; user time is given where it matters.

## 2. Solver work this shift (the default, K = reference)

Each change keeps the least fixpoint; `-bennett-analysis-check-delta` and `tests/load_delta.py`
check the incremental PT6 results against full passes.

| sha | change | effect on the closure (default K) |
|---|---|---|
| c6b1902 (K0) | before this shift's speedups | 1500 s: round 1 at position 131,735 of 285,525 |
| 44f50aa (D1) | PT6 per changed slot instead of per object version | 1500 s: round 1 at 94,340 (load ~28; ROOT re-interning now 28% of the profile) |
| 885e84a (D2) | partial-overlap ROOTs as one cached set | round 1 complete at 789 s; budget hit in round 2 |
| 0317dcf (D3) | same for PT8; unions adopt their first set | round 1 at 410 s; round 2 complete at 1,407 s; then out of memory |
| afaa89c | constant images per atom; PT8 source lists only when used | not yet measured on the closure |

D2 and D3 reach the identical state after round 1 (1,408,583 slots, 391,155,526 slot atoms), so
the speedups do not change the iteration.

## 3. What the reference fixpoint looks like on SQLite

| run | after round | slots | slot atoms | value atoms | largest value |
|---|---|---|---|---|---|
| D3 (reference) | 0 | 56,312 | 360,391 | 1,754,887 | 2,429 |
| D3 (reference) | 1 | 1,408,583 | 391,155,526 | 56,176,749 | 493,295 |
| D3 (reference) | 2 | 2,643,733 | 1,210,304,346 | 138,617,196 | 247,338 |

D3 then aborted in round 3 with signal 6 at RSS 13.7 GB (the 14 GB address-space limit), 1,965 s
wall, 1,653 s user. Single objects held 92,538 slots and 81,178,844 atoms (`%3` and `%4` in
`@syncJournal`, `@syncJournal.zerobyte`, offsets [-40, 10256]).

The growth is a blob that §5 itself forces, not a plugin imprecision:

- A largest value after round 1 holds 288 objects with 1,820 offsets each. One of them is
  `%2 = alloca i64` in `@pagerOpenWalIfPresent`. Its only escape is `%38 = call i32 %37(ptr %32,
  ptr %2)`, an `sqlite3_io_methods` call. Once AV(%37) is ⊤ (the method pointer is loaded from
  memory the merged pointers already reach), §14.2 makes every address-taken function of type
  `i32 (ptr, ptr)` a candidate, and PT9 binds `%2` to the second parameter of each.
- PT2 is flow-insensitive and applies to every atom of the address. Every field offset used on any
  pointer in the merged set therefore reaches every object in it. That is 1,820 offsets per object
  by round 1, more than 10,000 by round 2, and each offset becomes a slot when stored through.
- §5.1 bounds INT atoms by K = 4096 only. The plugin's reading of the ruling closes the offsets of
  one provenance only past 4096. Nothing bounds the number of provenances in a value or the slots
  of an object. A value can therefore legitimately hold (number of merged objects) × 4096
  explicit atoms, and each object up to tens of thousands of slots.

## 4. The earlier closure rules (NON-REFERENCE, `-bennett-analysis-early-chain-close`)

The flag closes an offset chain past 4 offsets outside the object's literal extent, or past 32
offsets of an object with no literal extent. It also collapses an object past max(64, extent/4)
store-created slots (the rules in b-dialect-spec-5u3).

| run (NON-REFERENCE) | result |
|---|---|
| F1, 7e5c640 (before this shift's speedups) | round 2 at 5,880 s wall, no fixpoint |
| F2, 0317dcf | **fixpoint**: "S1-S5 complete" in 64 rounds, 1,231 s of analysis, 1,279 s wall, 1,255 s user, RSS 2.5 GB; 186,351 slots, 28,306,064 slot atoms, 110,805,551 value atoms, largest value 4,294 |

F2's rounds 11 to 64 each re-ran the same four steps and added two value atoms per round. That is
a slow additive cycle the solver could accelerate; it does not change the fixpoint.

## 5. Assessment

- With the explicit-atom representation, the reference fixpoint does not fit in 14 GB on this
  closure: round 2 alone holds 1.2 × 10^9 slot atoms, and growth continues. The same solver
  reaches the flagged fixpoint in about 20 minutes and 2.5 GB.
- This is not yet a proof that K is intractable for every engine. The blob is close to a product,
  objects × offsets with the same offsets for every object. A factored representation (an object
  set times an offset set, with slots for object-set × offset-range regions) could hold it
  exactly and compactly. Such an engine is a redesign of PT2/PT6/PT7/PT8, not a tuning step. It is
  unproven that its stores and loads stay below the product size, because PT6 still distinguishes
  each overlapped slot.
- Consequences beyond cost: §7.2 candidate sets and §8.4 dispatch domains are computed from these
  sets. A dispatch domain over a value of 10^5 to 10^6 atoms is itself a production-size problem
  for rung 4, whichever engine computes it.

## 6. Proposal for the council (exact changes requested)

Option A, keep K and require nothing new: the plugin builds the factored engine. Cost: a
redesign of the analysis core of unknown duration, with rung 4 blocked meanwhile.

Option B, normative bounds beside K in §5.1, so that every conforming analysis reaches the same
verdicts at a tractable size. Text proposal:

> Offsets of one provenance (X, numerical) in an abstract value are closed when they exceed any
> of: K offsets; 4 offsets outside X's literal extent; 32 offsets when X has no literal extent.
> Closing replaces them with the residue class of the lowest set bit of all their pairwise
> differences, adds (EXT, `*`) and sets the non-handle top flag. An object with more than
> max(64, extent/4) slots created by stores (no literal extent: 64) is collapsed: every later
> access uses (X, `*`), and PT6 of an overlapping load gives ⊤ with explicit ROOT provenance kept.

These are the rules F2 measured. They can only move a verdict toward rejection or a larger
dispatch domain (b-dialect-spec-5u3). Before ratifying them, the council may want the same
measurement for looser constants (for example 16 outside the extent and 256 without one), and
the effect on rung 1 to 3 verdicts. The plugin can run both on request.

Option C, a precision change at the source of the blob instead of a bound: for example
type-filtered parameter binding for ⊤ candidates, or per-call-site candidate pruning by
argument provenance. The measurements above do not cover it.

The plugin's recommendation: B now, with its constants as the council's choice, because it is
measured and keeps all implementations in agreement. A stays open as a longer-term precision
improvement that a later spec version could allow as the reference.

## 7. Fat object (bennett-4ht)

No option changes the host/device boundary. The analysis models the host side through PT11
seeds and EXT. In a mixed fat object only the marked modules form the device closure, and their
exported functions are PT11 boundaries, so the same bounds apply to a smaller closure. The
bounds are per object and per value: none of them assumes the device object is the whole binary.

## 8. Artefacts

`.tmp/rung4/prof/trace-{K0,D1,D2,D3,F2}.log`, `perf-*.data`, call-graph samples
`cg-{D2,D3,F2}-N.data` with `cg-*.index`; `.tmp/rung4/logs/sq-*.out`. Not committed (size).
