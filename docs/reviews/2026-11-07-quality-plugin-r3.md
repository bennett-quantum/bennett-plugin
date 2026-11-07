# Plugin quality review, final fix check — 2026-11-07

**Verdict: CLEAR — no P0/P1 findings.** No new blocking beads.

Reviewed only `2ecdd90..c085c2e`; exact code head
`c085c2ecbb386d0c97a11dc76ed7293533b7ad11`, on `job/quality-plugin`.
Read the previous quality reviews and council report; inspected main-side code for
the red-on-main assessment without switching branches. This is the final fix
check under R32, with no further council.

- **SOL-S0-1 / bp-46p: fixed.** The frozen shared-state scan follows analysis
  candidates before replacing any entry. Ran
  `timeout 180 python3 -B tests/review_regressions.py --major M --case global-diagnostic`
  for **M=18 and 23: 13/13 each**. Direct, indirect, nested and mixed closures in
  both source orders have source-native `1 2 host_global=2`; generated hosts
  exit 125 with the approved promised/pending diagnostic and empty stdout.
  This verifies the approved interim, not implemented shared-memory transport.
- **codex-S0-1 / bp-dzb: fixed.** Compare trees share one counter per source
  block, including calls, switch and indirectbr. Ran
  `timeout 180 python3 -B tests/scalars.py --major M --step-check --case inc8 --case switch5 --case two-calls --case three-calls --case two-calls-switch --case three-calls-switch --case missing-callee`
  on both majors. All selected checks pass; each of the five new indirect
  fixtures passes exhaustive inversion over 512 inputs. The duplicate-label
  mutation is rejected. Separate complete scalar runs preserve **21/21** exact
  published objects, hashes and execution expectations on each major.
- **codex-S0-2 / bp-cks: fixed.** Declaration leaves emit fault 4 without
  accessing the absent lproc map entry. The command above compiles/checks the
  exact witness without a stack dump: `1,7` gives `(0,8)`, `0,7` gives `(4,0)`.
  Main and `2ecdd90` retain the per-call counter reset and unchecked declaration
  lookup, so these regressions detect their reported failures there.

**Test integrity and gate fixes:** The soft-float corrections retain the original
exact atom sets, numerical values, reversal/restoration checks and fault-absence
assertions. Marker roots put the two original bodies in the device tier, as
pinned dialect §§4.2/12.1 require; the memoryless direct-CC object receives zero
heap/stack/depth limits under pinned ISA §§5.4/7.2, with unchanged step allowance.
`timeout 300 python3 -B tests/softfloat.py --major M` passes **112/112 (18)** and
**116/116 (23)**. No expectation was weakened.

After successful `timeout 300 cmake --build build/llvmM -j3` builds, each of
`production`, `budget_stage`, `shadow_stack`, `native_checked`, `cc_calls`,
`cc_switch`, `reversible` and `production_dispatch` passed separately under
`timeout 180 python3 -B tests/DRIVER.py --major M` on both majors. This includes
all five budget-stage records and four proof refusals, nine stack cases, six
native comparisons and the missing-provenance mutation. Both
`normalisation_scope.py` runs reject **5/5** real-module mutations. The default/gate
driver inventories retain every previous driver and case argument; the new
default schedules 82 commands. No full default suite or full gate was rerun.

**Receipt revision:** Independently compared all 312 prior names and rows:
exactly the 16 approved old/new hash pairs change; no prior name disappears and
the previous gate claim is unchanged. All 16 function sections are identical
modulo function order; data and other non-symbol/layout sections are unchanged.
The layout changes follow the address reservation and retained heap capacity in
`6231c2d`/`6091986`; published scalar goldens remain exact. A bounded inline
Python audit reran all **148** commands in the revision report, checked their
object hashes and pinned oracle digest, and reproduced all **74** equal old/new
observations on both majors. `timeout 90 python3 -B tests/prior_objects.py`
passes **312 hashes on both majors**. Receipt-revision rejection tests and
`scripts/quality.py --check` pass; `git diff --check 2ecdd90..c085c2e` passes.

Pre-review gate evidence: main checkout
`bennett-plugin/.tmp/gate/records/c085c2ecbb386d0c97a11dc76ed7293533b7ad11.json`
records isolated **PASS**, quality check exit 0 and plugin gate exit 0 (821.3 s).
Reviewer tests were focused, headless, bounded, with reviewer-local TMPDIR; no
sibling gate or full repository gate was run.

P2+ nits: **bp-nvo** (P3, review/nit): `docs/quality.md:53–58` still says the receipt expectations remain unchanged despite the explicit 16-object revision; carries forward bp-pgb/bp-3mb's four unused subprocess imports.

Coverage: read closely every fix in the scoped production, harness, test and
receipt diff, plus the relevant pinned clauses and original layout changes;
skimmed unchanged lowering and historical context. Checked every COMMON
anti-slop rule: dispatch/state, failure defaults, predicates/constants, phase
boundaries/wrappers, process identifiers, litter and independent observations.
No new semantic violation or scope narrowing found; Analysis.cpp is untouched.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
