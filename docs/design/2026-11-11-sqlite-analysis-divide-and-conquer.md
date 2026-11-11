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
