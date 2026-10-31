# Handoff

Rewritten at session end only. Mid-session state lives in chat, the worklog and bd.

## State (2026-10-31)

**M1 is complete on the plan's definition** (`docs/PLAN.md`; maintainer ruling in
`bennett/docs/council/README.md`, watcher pass 4): 17 scalar objects byte-exact on LLVM 18 and
23, 40 vectors per major, legality gate 66/65/1/0/0 per major, production scalar launches.
Accepted dialect 0.2.10 @ 023f5a7, ISA 0.8. Sole gate deferral: fp-rot-fastmath-reassoc (bp-7ni).

## Open beads by milestone (`bd list`; labels `m2`/`m3`/`m4`)

- **M2:** bp-kv5 (general descriptor dispatch), bp-piq (budget-stage shadow-stack vector),
  bp-311 (replay, device bindings, lifted memory/calls), bp-7ni (soft-float).
- **M3:** bp-rbl (general handle environments), bp-65x (parameterised INOUT, budget minima),
  bp-qql (arena-o1); ISA blockers bp-2tw, bp-2bi, bp-ckk, bp-is0.
- **M4:** bp-o7f (executable certificate reproduction; upstream 8r4/47t).
- **Unmoved M1 leftovers needing maintainer disposition:** bp-2zv, bp-3w4, bp-tr5, bp-tye.

## How to run the gate

`scripts/pre-push` gates a clean checkout: it reads the sha being pushed from the refs git
supplies on stdin (HEAD when run directly), creates a detached worktree at
`.tmp/gate-<sha>`, builds both majors and runs the full gate there with TMPDIR inside it,
removes the worktree, and exits with the gate's status. Run it headless:

`env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER /home/tobias/Projects/bennett-workspace/bennett-plugin/scripts/pre-push`

`scripts/gate` runs the same sequence in the current (possibly dirty) tree for iteration; it
is not a push gate. After a gate, `scripts/record-verification.py --pass NAME --date D
--commits A,B --gate-exit 0` rewrites `docs/verification.json` (latest pass only). Never LLVM
`-view-*`. Export beads (`bd export -o .beads/issues.jsonl`) and commit explicit paths.

## Pushing

The orchestrator pushes normally (`git push`); the pre-push hook is the gate, so
`--no-verify` is retired for code pushes. Install the hook with `scripts/install-hooks.sh`.

## Next

M2, starting with **bp-kv5** (dialect 8.4 compare trees over candidate/width/size/device
fields and arbitrary descriptor memory loads). One pass per bead until it closes, one gate.
