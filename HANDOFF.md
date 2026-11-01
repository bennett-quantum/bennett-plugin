# Handoff

Rewritten at session end with `date -u`: **2026-11-01T08:59:53Z**.

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. M1 remains complete; M2 and the North Star ladder remain in progress.
Obligations live in bd. This pass closes **bp-tav**; **bp-7ni is unchanged**. No push.

Implementation: **0f90deb13fc7b0b1e30190d522723dc5aba7f2bb**. Published malloc/calloc/free/memset definitions
are normalised and expanded as ordinary CC control flow through their allocation primitives,
not heap summaries or host libc. Alloc/free retain complete dead/zero allocation histories;
zero-fill is real byte stores. Newly expanded allocator closures report explicit fault codes
through `hostcall bennett.fault` then trap (§11.5). N27 overflow field shells are projected
without running a heap-eliding optimiser. Dominator-first emission handles LLVM23's LTO CFG;
allocator-only launches receive checked memory layouts and fault-service envelopes.

Four probes per major link the exact published runtimes and SHA-pinned arith, then lto<O3>.
Red malloc refusal became 4/4 green: 11 CC vectors and five full-state reversals per major,
covering zero-fill, dead/zero-sized history, memset, calloc overflow code request, heap limits,
null/interior/double free and dead/out-of-bounds loads. Recognition, normalisation and verified
materialisation digests, object hashes and execution results are in docs/verification.json.
Allocator object bytes differ across the majors' actual LTO CFGs; each is independently checked.

One full **scripts/gate exit 0**: **66 run / 66 agree / 0 deferred / 0 blocked / 0 diverge**
each major; cells **924/924** (18), **792/792** (23). All **297** prior object hashes preserved;
**297** equal object pairs and **45** published matches. Gate log: `.tmp/bp-tav-gate.log`.
Receipt: `docs/verification.json` (python3 scripts/record-verification.py --pass bp-tav).

## Next measured rung-2 frontier

Both recorded postlink inputs and **fresh clang -O2 -flto marked-C inputs** were linked with
major-matched published runtimes and pinned arith, then lto<O3>. Both analyses complete.
Both productions now pass the allocator calls and explicitly stop at §17.4:
`tail call fastcc void @ht_third_pass(ptr %3, i64 %0)`.
**bp-9fo**, labels consumer,m2,rung2, owns ordinary CC calls under §14.1's determining sentence.
Commands, durations, publication/input/plugin digests and diagnostics: `docs/rung2-analysis.json`.
The conditional rung-2 gate was not run because production remains incomplete. No hashtable
executor, reversal or §17.7 materialised native comparison success is claimed. No sibling edits.

Run headless: unset DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER;
TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp. Never LLVM -view-*.
Use scripts/gate for iteration; scripts/pre-push gates a frozen commit in a detached worktree.
Record only completed gates with python3 scripts/record-verification.py. Export beads with
bd export -o .beads/issues.jsonl before committing .beads; commit explicit paths. Never push
from this implementation task. The orchestrator owns the session worklog and any later push.
