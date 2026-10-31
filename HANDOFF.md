# Handoff: bennett-plugin

State (2026-10-31): third implementation pass landed locally; **M1 remains
incomplete**. No push. Accepted dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. The sibling worktree is unaccepted draft 0.2.11; gate drift is against
the accepted registry and pinned blob, with worktree/HEAD differences reported.

Verified: CMake 3.28.3 dual-major build/load; 23 markers; 73/74 applicable published
recognition examples; 12 analysis regressions; five materialisation fixtures;
scalar materialised keys; 12 exact reference objects and 35 stated vectors per
major; C/descriptor-derived inc8. Legality: **66/65/1/0/0** per major
(run/agree/deferred/blocked/diverge), gate exit 0. Sole deferral:
fp-rot-fastmath-reassoc, L5, M2 §13 / bp-7ni. Former ABI runtime and global-numbering
blockers are resolved at the accepted pin. See docs/verification.json for actual
plugin digests, object/symbol hashes, vectors and before/after totals.

Next: finish **M1** general reference analysis/all-rule materialised keys
(bp-3w4) and production descriptor/CC launch path, host entry replacement and
records (bp-2zv). Static descriptor-reference remains a test interface. Brief 1b
item 4 still has eight scalar-typed lift examples plus two object-only integration
vectors missing; their exact rows and owning beads are in docs/PROGRESS.md.
Do not close M1 or narrow the north star: Grover over unmodified SQLite is core.
Existing M2 mechanics: FP/helper/native comparison linking (bp-7ni), full
normalisation, calls/memory/device bindings/replay (bp-311); M3 arena/action
outlining (bp-qql). General TDL/CC-R and all later demo rungs remain scheduled.

Run the full gate from any directory:

```sh
mkdir -p /home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp /home/tobias/Projects/bennett-workspace/bennett-plugin/scripts/pre-push
```

Never use LLVM graphical viewer passes. Every build/test/run uses the same
headless prefix and project-local TMPDIR. Beads commands use
`env -C /home/tobias/Projects/bennett-workspace/bennett-plugin BEADS_HOOK_TIMEOUT=20 bd ...`;
export `.beads/issues.jsonl` before explicit-path commits. The orchestrator pushes.
