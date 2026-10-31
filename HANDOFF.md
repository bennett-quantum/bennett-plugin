# Handoff

Rewritten at session end: **Sat Oct 31 23:42:27 UTC 2026**.

## State

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8** (`SPEC_VERSIONS.toml`; gate checks the accepted pin). M1 remains complete;
M2 and the North Star ladder remain in progress. `bd ready` / `bd list` are the obligation list.

This consumer-driven pass closed **bp-au6**, then **bp-1us**, with a complete in-tree gate
for each. No push. bp-7ni recursive CC soft-float closure was not changed.

- bp-au6: exact S2 cycle acceleration/caching, slot indexes and nested zero-image unions;
  original unlinked hashtable probes exceeded 300 seconds on both majors; first green
  measurements were 5.79s (18) / 5.64s (23), 64 rounds each. Iteration/time budgets diagnose
  §5.2 rule and AV element. Implementation `04006df`, receipt `569fa9c`.
- bp-1us: implementation `56eadb7`; depth-first aggregate field transport, packed calls/returns,
  N25 hidden return pointers and N22 nested/loop-carried field shells. Three probes per major
  retain recognition and verified materialisation hashes, execute 15 L vectors and three real
  CC launches. Pinned real-arith L production passes five numerical inputs on both majors.
- Final gate: **66 run / 66 agree / 0 deferred / 0 blocked / 0 diverge** each major;
  cells 924/924 (18), 792/792 (23). **297** equal object pairs, **45** published matches,
  all **288** previous object hashes preserved. Repeated oracle calls share one reference.
  Latest receipt: `docs/verification.json`.

## Rung 2 frontier

Published runtimes existed on both majors. Recorded postlink inputs were linked with those
runtimes and SHA-pinned arith (`llvm-link --only-needed`), then `lto<O3>`, then the plugin.
Both analyses reach S1–S5; final linked analysis times: 11.34s (18), 5.89s (23).
Both production runs stop explicitly at **§17.4 CC marker/call lowering: malloc(32)**;
new plugin bead **bp-tav** owns this next measured producer. Commands, input/publication/plugin
hashes and diagnostics are in `docs/rung2-analysis.json` and the verification receipt.
The hashtable has not executed or reversed on either executor; rung 2 remains red.
No dialect-spec bead was needed or filed, and no spec text was changed.

## Verification and commits

Run headless with DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER unset,
and TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp. Never LLVM -view-*.

`scripts/gate` is the in-tree iteration gate. `scripts/pre-push` gates a frozen pushed sha
in a detached worktree. Record a completed gate with **python3 scripts/record-verification.py**
(the Python script is not executable), supplying --pass, --date, --commits and --gate-exit 0.
Export beads with `bd export -o .beads/issues.jsonl`; commit explicit paths. The orchestrator
pushes after reviewing the commits. See `docs/PROGRESS.md` passes 18–19 for this pass.
