# SQLite device analysis: divide-and-conquer exploration log

Maintainer question: "cant we incrementally/divide and conquer this?" (bead bp-fj1, follow-ups
bennett-plugin-j3l / -aba). This is a running log of small experiments. Each entry: what was run, the numbers,
what it suggests, the next experiment. Tags: **[measured]** = a command I ran showed it; **[source]** = read
from code or spec text; **[conjecture]** = not yet tested.

All runs use plugin analysis source identical to main c608310 (`src/Analysis.cpp` and `src/Bennett.h` are
byte-identical to feb12a9), plus a diagnostic probe that only reads state. The probe is not committed. LLVM 18,
`-bennett-analysis-only`, the default 30,000 ms analysis allowance, dialect 0.2.13.

## Starting point (from j3l2's 2026-11-11 receipts, not re-run)

- All four full-SQLite cells (18/23 × N16, N256 queued) run out of the 9 GiB memory cap inside **round 0**,
  after 160-280 s. **[measured by j3l2]**
- Census at the 9 GiB point, 18/N16, after about 159k of roughly 285k instructions had been stepped:
  - values: 161k SSA values holding 44.1M atoms;
  - pure-input snapshots: 20.0M atoms;
  - memory slots: 112k slots holding 7.2M atoms.

  One call site in `sqliteDefaultBusyCallback` (rules PT8/PT9/PT12) added about 6M value atoms per 512 MiB of
  heap, with no worklist progress. **[measured by j3l2]**
- The solver is plain round-robin Kleene iteration. Each round re-steps every instruction of the module and
  recomputes each transfer from the full operand sets (`Analysis::run`, `step`). There is no worklist, no
  difference propagation and no SCC ordering. An AV is a `std::set<Atom>`, one tree node per atom, roughly
  100+ bytes each. Sets are not shared between values: `setField` merges the same atoms into both `fields`
  and `values`. **[source]**

## Finding 1 — single-function blow-ups: the musl premise is stale, and two mechanisms remain

**Run.** I took the musl units named in bp-fj1, `gai_strerror.c` and `__stdio_write.c`, alone. I then
re-ran the whole musl census, 1,347 already-compiled units from the 2026-11-08 census, through the current
analysis: 24-way parallel, 30 s allowance, 34 s wall in total. **[measured]**

| unit | result now | rounds | worklist pops |
|---|---|---|---|
| gai_strerror | pass, 1.2 ms CPU | 3 | 72 |
| __stdio_write | pass, 1.9 ms CPU | 3 | 231 |

Both were fixed on 2026-11-08 by pattern-specific exact accelerations (`closePointerOrbit`, the
`longAdditiveCycle` extensions). **[measured, source]**

**Census.** 1,306 units pass and 41 fail. Of the failures, 34 are unrelated diagnostics (unimplemented PT10,
§13.5 and others). Only **7 units still exhaust the 30 s allowance alone**: qsort, iconv, vfscanf, vfwscanf,
floatscan, random and resolvconf. The slowest passing unit is regcomp at 0.58 s. Cost is therefore extremely
concentrated: almost every unit is cheap, and a few are pathological. **[measured]**

I probed five of the seven, with one probe line per completed round. qsort crashed under the probe (a probe
defect). Without the probe it fails normally at PT2 in `trinkle`. **[measured]**

**Mechanism A — counter crawl, one INT atom per round.**

- `__get_resolv_conf` has the loop `%25 = phi [%170, 0]`, `%139 = add nsw i32 %25, %138`, where
  `%138 = zext i1` has the value set {0, 1}.
- Every round adds exactly one new INT to `%25` and to its copies (`%134`, `%139`, `%170`, `%177`).
- After 2,747 rounds and 29 s CPU, each of these holds 2,747 INTs and the value set is still growing. Its
  least fixpoint is ⊤: the orbit of 0 under +{0,1} modulo 2^32 has more than K = 4096 elements. Reaching ⊤
  needs about 4,097 rounds.
- Every round re-steps the whole module and re-merges sets of growing size, so cost grows about as
  K² × (module size).
- `longAdditiveCycle` misses this case because it accepts only `ConstantInt` steps (`Analysis.cpp:1825`).
  **[measured, source]**

The same shape appears in:

| unit | rounds | where it crawls |
|---|---|---|
| vfscanf / vfwscanf | 2,349 | `%49`, `%647`, `%672`, about 2,350 INTs each |
| random | 1,289 | `initstate` `%85 = or`; the crawl passes through memory, slots `@i` and `@j` hold 1,545 INTs |
| floatscan | 188 | partly this: 2,048-INT `and` and `add` values |

**[measured]**

**Mechanism B — explicit address enumeration.**

- In `iconv`, 7 GEP values hold 105,451 of the 113,633 value atoms (93%). Examples:
  - `%27`/`%819` hold 24,227 exact `(@jis0208, o)` atoms, o = 0..48,450;
  - `%395` holds 23,814 `(@gb18030, o)` atoms.
- Memory holds one slot per table element: @gb18030 has 23,941 slots, @big5 13,974, @ksc 8,743.
- The first set is **dense**: 24,227 atoms over 0..48,450 at stride 2 is every member of the residue class
  (0 mod 2)[0, 48452). The spec's own offset vocabulary (§5.1) can write that set as one atom; the engine
  stores it as 24,227. **[measured]**
- floatscan shows the same on a local array: 2,049 exact `(%4, o)` atoms, o = -4..8,184 at stride 4.
  **[measured]**
- This matches the shape j3l traced in SQLite: 157,636 addresses on one load in `sqlite3SetTextEncoding`,
  and 73,779 in `sqlite3LocateCollSeq`. I have not checked yet whether those SQLite sets are dense.
  **[conjecture]**

**What it suggests.**

1. "One function blows up alone" is two different things, and neither is about closure size.
2. **Mechanism A** is an iteration-strategy cost, not a precision problem. The exact answer is cheap: a cycle
   x = x0 ∪ (x + D) mod 2^W has orbit x0 + ⟨gcd(D ∪ {2^W})⟩. This is the general form of what
   `longAdditiveCycle` and `closePointerOrbit` already do for hand-picked shapes. Solving it per SCC of the
   value graph would give the same least fixpoint in one step. That is Option A ("exact acceleration")
   territory under council plugin-bpfj1-2026-11-03, with no spec change. **[source, conjecture on gain]**
3. **Mechanism B** is a representation cost. Holding a dense set as a residue class or interval preserves
   the denoted set exactly. The shelved factored-points-to design (`feaa972` on
   `refs/archive/branches/remote/wip/*`; reviewed REVISE 2026-11-03) was built for exactly this, with
   object × offset rectangles and one payload shared per stored width. It was never resumed: the revision
   job was quota-blocked, and then bp-1bb and the incremental j3l fixes took its place. Nobody decided
   against it. Its P1 review findings (bp-9g8 member-interval semantics, bp-eiq address recurrences) still
   apply. **[source, via archive search]**

**Next.** Step 2 of the plan: a per-function cost census of the SQLite closure (each function alone, short
cap). It answers three questions:

- Is SQLite's cost concentrated in a few functions, as in musl?
- Is it mechanism A, mechanism B, or call/memory fan-out of the `sqliteDefaultBusyCallback` kind, which a
  single function cannot show?
- Are the large SQLite address sets dense?

## Finding 2 — SQLite per function: cheap in memory, expensive only by counter crawl; the blow-up needs connected functions

**Run.** Input: the original full LLVM 18 / N16 input, 1,473 defined functions (the 1,218-function sqlite closure
plus runtime). Each function was extracted alone with `llvm-extract --func=F --rglob='.*'`, which keeps every global and
its initialiser, so the function sees the real data image. Callees and other functions become declarations, so they
take PT12 host-call semantics. F was made non-local so that its parameters get the PT11 unknown-caller seeds.
Settings: 30 s allowance, production budget argv, 32-way parallel. Total wall time 51 s. **[measured]**

**Concentration.**

- 1,457 of 1,473 functions finish alone. Their analysis CPU sums to 325 s.
- Per-function CPU: median 155 ms, p90 366 ms, p99 1.17 s. Only 19 passing functions take more than 1 s; the
  slowest passing one takes 17.9 s.
- 16 functions exhaust 30 s alone: checkTreePage, constructAutomaticIndex, convertToWithoutRowidTable, exprAnalyze,
  exprNodePatternLengthEst, generateSortTail, jsonGroupInverse, sqlite3FindInIndex, sqlite3Insert, sqlite3ParseUri,
  sqlite3Pragma, sqlite3VdbeExec, sqlite3VdbeHalt, sqlite3WalCheckpoint, sqlite3_str_vappendf and wherePathSolver.
  **[measured]**

**Mechanism.** All 16 are CPU problems, not memory problems. Heap at the stop is 10–23 MB, against 9 GiB in the
whole-program run. **[measured]**

| shape | functions | evidence |
|---|---|---|
| A, counter crawl | 13 of 16 | Largest values are integer `phi`/`add` chains growing about one INT per round: jsonGroupInverse 1,761 INTs after 880 rounds; exprNodePatternLengthEst 1,752 after 1,751; sqlite3FindInIndex 2,408 after 601; checkTreePage 441 after 441. Same shape as musl resolvconf (finding 1). |
| A2, large spec-mandated INT sets | sqlite3VdbeExec, sqlite3VdbeHalt, sqlite3_str_vappendf (exprAnalyze partly) | `and x, m` with x = ⊤ gives every submask of m (PT5), which yields 256–4,096-element INT sets. Elementwise binary transfers then cost about the product of the operand set sizes. VdbeExec: 18 rounds, about 1.7 s per round. |
| B, address sets | none dominant | Largest per-function address sets are 256–257 atoms: table lookups into @sqlite3UpperToLower, @sqlite3CtypeMap, @aDigits and @aPrefix (offsets 0..255, step 1), and @sqlite3Pragma.encnames (0..4,080, step 16). **Every one is dense, i.e. exactly one residue class.** |

**[measured]**

**The full-run blow-up is not in any function alone.**

- j3l's whole-program runs stopped in sqlite3SetTextEncoding (157,636 addresses on one load), sqlite3_db_release_memory
  and sqliteDefaultBusyCallback (6M atoms per 512 MiB). These three have no direct callees.
- Alone, each analyses in 0.10–0.12 s and 80 MB RSS. **[measured]**
- Their pathological values therefore enter from outside:
  - parameters bound by PT9 at indirect call sites. SQLite reaches the VFS, pager and busy handler through function
    pointers, and REPORT.md counts 2,229 indirect sites, 1,247 of them with 8–40 candidates;
  - memory reached through shared globals, heap objects and EXT.

  bp-fj1's 2026-11-02 note already named one instance: under §14.2 top candidates, an `alloca` of
  pagerOpenWalIfPresent is bound to every i32(ptr,ptr) function. **[measured + source; route of entry is conjecture]**

**What it suggests.** Divide-and-conquer splits the problem cleanly into two independent costs:

1. **Per-function CPU (A/A2).** It is bounded and parallel by construction: 1,457 functions cost 325 s CPU in total,
   and 16 crawl. Exact acceleration of integer recurrences fixes the crawl. Today's pattern-specific
   `longAdditiveCycle` would need generalising to non-constant steps, `or`/`and` chains and cycles through memory.
   That would remove A without changing any AV. **[conjecture on gain]**
2. **Whole-program memory, about 44M value atoms in round 0.** It appears only when functions are connected, so the
   right divide-and-conquer probe is a growing sub-closure along call edges that include indirect candidates.
   Per-function slicing cannot see it.
3. **Density.** Every large address set seen so far, in musl and in SQLite, is a dense residue class. If the 157,636
   set also is, a residue/interval representation (factored-points-to, mechanism B) would hold it in O(1) atoms
   without changing the denoted set. **[conjecture until measured]**

**Next.** Growing sub-closures that follow indirect calls:

- Start from sqlite3SetTextEncoding and sqliteDefaultBusyCallback.
- Add callers and indirect-call candidates in BFS order, using §14.2 type and address-taken candidates.
- Run each size (about 10, 30, 100, 300, … functions) with a 4 GB / 120 s cap and the probe on.

Look for the size at which heap jumps from MB to GB, which value or slot carries the blob, its density, and whether it
enters via PT9 parameter binding or via memory.

## Finding 3 — growing sub-closures: the early CPU wall is a pulled-in crawler; past ~100 functions three connected-program costs appear

**Run.** I dumped a call graph from the LLVM 18 / N16 input:

- 1,473 functions; 305 have their address taken; 2,414 indirect call sites.
- Each indirect site is joined to every address-taken function of the same type, as a §14.2 worst case.

Sub-closures grow by BFS on that undirected graph from sqlite3SetTextEncoding and from sqliteDefaultBusyCallback. Each
sub-closure is extracted with every global and initialiser and keeps its original linkage.

Two series:

- **"all"**: the plain BFS.
- **"−crawl"**: the same BFS with the 16 functions that exhaust 30 s alone (finding 2) left as declarations.
  Diagnostic only: those calls take PT12 host-call semantics.

Every run: `systemd-run --user -p MemoryMax=4G` after `admit.py` ADMIT, 120 s CPU allowance (two points at 600 s),
probe on. **[measured]**

| root | series | functions / instructions | result (wall s) | RSS MB | rounds at stop | carrier at stop (probe) |
|---|---|---|---|---|---|---|
| SetTextEncoding | all | 10 / 6,189 | cap 120 | 87 | 172 | sqlite3Pragma `%2769` INT crawl (A) |
| SetTextEncoding | all | 10 / 6,189 | **cap 600** | 88 | 435 | same `%2769`: 1,385 → 3,481 INTs, about +8 per round; still about 75 rounds short of K |
| SetTextEncoding | all | 30 / 7,164 | cap 120 | 89 | 162 | same (A) |
| SetTextEncoding | −crawl | 10 / 975 | pass 1.3 | 84 | — | — |
| SetTextEncoding | −crawl | 30 / 1,991 | pass 1.7 | 90 | 4 | — |
| SetTextEncoding | −crawl | 100 / 17,974 | cap 120 | 608 | 2 | address blob + load scans (C1) |
| SetTextEncoding | −crawl | 300 / 83,783 | cap 120 | 585 | 2 | C1 + C2 |
| SetTextEncoding | −crawl | 1,000 / 205,587 | cap 120 | 638 | 0 (120k pops) | candidate ROOTs (C3) |
| BusyCallback | all | 10 / 911 | pass 0.34 | 82 | — | — |
| BusyCallback | all | 30 / 20,698 | cap 120 | 98 | 34 | sqlite3VdbeExec, pager_end_transaction 4,096-INT `and`/`or` (A2) |
| BusyCallback | all | 30 / 20,698 | **cap 600** | 98 | 148 | same; value atoms still +37 per round |
| BusyCallback | −crawl | 30 / 6,695 | pass 8.6 | 122 | — | — |
| BusyCallback | −crawl | 100 / 12,844 | pass 5.0 | 167 | 5 | — |
| BusyCallback | −crawl | 300 / 83,529 | cap 120 | 240 | 2 | A2 + C3 |
| BusyCallback | −crawl | 1,000 / 207,855 | cap 120 | 630 | 0 (120k pops) | C3 |

Without crawlers, earlier "all" runs at 100 and 300 functions match the −crawl rows at the same sizes.
**[measured]**

**Reading the table.**

1. **The wall at 10–30 functions is mechanism A or A2, inherited from one member.**
   - sqlite3SetTextEncoding's 10-function closure contains sqlite3Pragma. At 600 s it is still crawling: one call
     result has 3,481 INTs, about +8 per round. It ends only at K = 4,096, which needs about 510 rounds.
   - BusyCallback's 30-function closure contains sqlite3VdbeExec, sqlite3VdbeHalt and sqlite3WalCheckpoint.
   - Remove the 16 crawlers and the same neighbourhoods finish in 0.5–9 s up to 30 functions (SetTextEncoding) or
     100 functions (BusyCallback).
   - The stop sites in the messages (createCollation's indirect call `%222`, and so on) are only where the clock ran
     out. **[measured]**

2. **Past that point, the program's connectivity adds three costs. None is mechanism A or B.**
   - **C1, blob addresses × slots.** SetTextEncoding −crawl at 100 functions, round 2:
     - pointers such as `deleteTable %122` and `createCollation %92` hold about 2,060 pointer atoms over 15–17
       objects, plus 15–25 FN and 22 ROOT atoms;
     - @nofs_vfs and @memdb_vfs each carry the same 1,024 exact offsets, spanning −40..10,163 with gcd 1. The set is
       **not dense**, and the objects are 168-byte `sqlite3_vfs` structs;
     - PT6 loads through such pointers test every slot of each object: **49.1M load-slot tests in 37,181 worklist
       steps**. PT7 stores write every (object, offset) pair: 26,834 slots, 4.58M slot atoms;
     - so per-instruction cost is about |addresses| × |slots per object|. This is indirect-call / merged-pointer
       fan-in. Field offsets of larger structs reach the VFS objects; PT2/PT5 keep out-of-bounds modular
       alternatives. **[measured; cause of the merge is conjecture]**
   - **C2, identical sets copied, not distinct sets.** By 64-bit content hash, over sets of 64 atoms or more:

     | closure | large slot sets | slot atoms | large value sets | value atoms |
     |---|---|---|---|---|
     | SetTextEncoding −crawl 100 | 4,441 → **13** distinct | 4,529,213 → 8,518 (**532×**) | 613 → 211 | 2.3× |
     | SetTextEncoding −crawl 1,000 | 3,765 → 51 | **107×** | 9,848 → 1,249 | 5.6× |
     | BusyCallback −crawl 300 | 613 → 16 | 38× | 3,068 → 255 | 8.7× |

     **[measured]**
   - **C3, candidate ROOT atoms.** At 1,000 functions, round 0 is still unfinished at 120 s (120k of about 206k
     worklist steps). There, **ROOT atoms are 57–58% of all value atoms**: 1.02M of 1.79M from SetTextEncoding and
     1.04M of 1.80M from BusyCallback. At BusyCallback-300 they are 37%. These are the §6.6 candidate ROOTs.
     `run()` seeds ROOT(arg) on every pointer parameter of every non-local function, through
     `seedParameters(f, … || !f->hasLocalLinkage())`. They propagate through the whole fixpoint and are pruned only
     after it unless they reach a handle operand. **[measured, source]**

3. **Memory stays small in every sub-closure: at most 640 MB RSS.** Within 120 s, CPU is always the wall, as the
   orchestrator noted. The 9 GiB of the full run therefore comes from running these costs long enough on about
   285k instructions, not from a different mechanism. **[measured; the extrapolation is conjecture]**

**What it suggests.** Divide and conquer separates four costs that can be fixed independently, all without changing
the reference fixpoint:

| cost | fix | gain |
|---|---|---|
| A / A2 (local) | exact acceleration of integer recurrences; cheaper elementwise transfers on near-K INT sets | — |
| C1 | load and store over an address set by object and offset range, not slot by slot | — |
| C2 | hash-consed immutable AVs | 38–532× on slots, 2–9× on values, exact |
| C3 | carry candidate ROOTs as a separate per-parameter provenance, instead of 1M explicit atoms through every transfer | — |

Each fix is local to one part of `Analysis.cpp`. C2 is the one I can test cheapest, and it attacks the memory wall
directly. **[conjecture on gains beyond the measured ratios]**

**Next.** A cheap probe-side experiment before any prototype: for the 1,000-function sub-closures, record the
distinct ROOT atoms and the parameters they come from. That shows whether C3 is a few hundred candidate roots copied
everywhere (cheap to factor out) or real handle flow. Then a `.tmp` prototype of hash-consed slot values on
SetTextEncoding −crawl 100, checking that the AV maps come out identical and measuring the change in load-slot tests
and RSS.

## Finding 4 — C3 is about 2,000 candidate ROOTs copied everywhere; sharing identical sets is exact and halves CPU

### Part 1: what the C3 ROOT atoms are

**Run.** I added a ROOT census to the probe and re-ran both 1,000-function −crawl sub-closures (finding 3):
120 s each, `systemd-run` MemoryMax=4G, after an `admit.py` ADMIT. **[measured]**

| sub-closure | distinct ROOTs | from parameters of | real `qalloc`/`qborrow` site ROOTs | ROOT occurrences | values and slots carrying any ROOT |
|---|---|---|---|---|---|
| SetTextEncoding −crawl 1,000 | 2,060 | 981 functions | **0** | 1,405,321 | 23,134 |
| BusyCallback −crawl 1,000 | 2,066 | 987 functions | **0** | 1,401,179 | 22,957 |

The most frequent ROOT, `sqlite3_close %0`, sits in 14,238 values and slots. The next fourteen (sqlite3Close,
deleteTable `%1`, sqlite3ExprDeleteNN `%1`, …) each sit in about 13,900. **[measured]**

**Reading.**

- Every ROOT is a §6.6 candidate on a pointer parameter. None comes from a handle allocation.
- The source is `Analysis::run`: `seedParameters(f, entries.count(f) || !f->hasLocalLinkage())` gives every
  non-local defined function the boundary seed. That covers about 980 SQLite functions here.
- PT11's text says "for a pointer parameter i of a **device entry** E, also the candidate atom ROOT(E, i)". The code
  comment calls a non-local function a "launch boundary [that] may only stash its handle for a later entry".
- Whether every non-local function counts as a device entry under PT11 / §6.6 is a spec-reading question. I name
  the clause and stop; this note proposes no spec change.

Either way, these candidates are pruned after the fixpoint unless they reach a handle operand. They are ideal for
a factored representation: about 2,000 symbols, each carried by thousands of values.
**[measured, source; spec reading open]**

### Part 2: prototype of shared atom sets

**What I built (throwaway, in `.tmp`).** `AV::atoms` becomes a copy-on-write `shared_ptr<const std::set<Atom>>`
behind the same `std::set` interface:

- copying an AV shares the set;
- a mutation clones it only when it is shared;
- a slot value is interned by content hash after each changed PT7 merge.

No transfer rule, ordering or fixpoint logic changes. Every source file is rebuilt against the new `Bennett.h`.

**Exactness. [measured]**

| input | comparison | result |
|---|---|---|
| musl, 1,306 passing units | reports at set level (atoms and callees compared as sets) | **identical**. Raw text differs in 3 units, by atom/callee print order only, which follows pointer addresses; a re-run of the baseline shows the same order variance. |
| SetTextEncoding −crawl 30 (1,341 values) | full report | identical |
| BusyCallback −crawl 100 (8,986 values) | full report | identical |
| SetTextEncoding −crawl 100 (12,270 values) | final report, plus a stable content digest of every value, field and slot at each of the 6 round ends | identical; all 6 round digests equal |

**Cost on SetTextEncoding −crawl 100, run to completion. [measured]**

| | baseline (main-equivalent) | shared sets | ratio |
|---|---|---|---|
| finishes? | yes, with a 600 s cap (fails the 120 s cap) | **yes, inside 120 s** | |
| analysis CPU | 209.6 s | **108.6 s** | 1.93× |
| peak RSS | 1,057 MB | **230 MB** | 4.6× |
| CPU at end of round 2 / round 3 | 18 s / 169 s | 8 s / 94 s | |
| rounds / worklist pops / transfers / joins | 6 / 108,222 / 66,084 / 10,257,877 | same | |
| load-slot tests (C1) | 206,394,064 | same | 1× |

On the small musl units the prototype costs about 26% more total CPU (5.1 s → 6.5 s over 1,306 units) under the
same 24-way host load. That is the per-AV allocation of the shared set. **[measured]**

**What it suggests.**

1. Sharing identical sets is exact by construction: the same AVs in the same order, and equal digests every
   round. It removes most of the memory (4.6×) and half the CPU on the first sub-closure that shows the
   whole-program shape.
2. The CPU gain comes from no longer deep-copying sets. The code passes AVs by value everywhere (`get`, load
   images, snapshots), not from doing less analysis work.
3. Its scope is narrow: one header type plus one interning call. That makes it the cheapest candidate for the
   memory wall j3l keeps hitting at 9 GiB in round 0.
4. It does nothing for C1. The 206M load-slot tests remain and are now the dominant CPU cost here. Nor does it
   help A/A2 or C3's per-atom transfer work.
5. **[conjecture]** At full scale the same ratios would put round 0 of 18/N16 well under the 9 GiB cap. Only a
   full run can show that.

**Next.** Run the shared-set build on the original full LLVM 18 / N16 cell: one run under the shared heavy lock,
admitted, MemoryMax 9 GiB to match j3l2's cap, probe on. Compare against j3l2's census2:

- heap and RSS against round-0 progress (worklist pops at 9 GiB);
- whether round 0 completes;
- which of C1 / A2 / C3 then dominates CPU.

That settles whether this one change moves the full-SQLite memory wall. If the maintainer prefers, the
alternative is to hand the prototype to j3l as a measured, exact candidate.
