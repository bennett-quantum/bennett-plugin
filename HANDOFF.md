Seventh pass in progress from 32427ed. Group 1 adds production binding
OUT/MEM_IN/CLOCK/BLOCK/CONSOLE, same-layout multiple reference symbols and direct
handle/scalar phi block parameters. New tests/production_shapes.py: 7/7 independent
ISA check/run cases on LLVM 18 and 23, four published binding references exact,
all seven launch pairs equal across majors. Unchanged full baseline gate exit 0,
66/65/1/0/0 each. bp-2zv stays open: remaining finite dispatch, static files/general
memory/call environments, combined devices/multiple outputs/unified layouts;
then staged budgets and checked target/schedule-bound certificates/records.
No new deferral, push, repin or sibling modification. Prior evidence follows.

# Handoff: bennett-plugin

State (2026-10-31): scalar launch implementation **bc14d48**, host ABI fix
**563ca6a**. **bp-2zv and M1 remain incomplete.** No push. Accepted dialect
**0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8**.
Do not read/adopt the sibling working draft 0.2.11.

Production now exits 0 and emits artifacts for the C scalar descriptor and
unchanged published oracle-inc8. Fixed-width, singleton IN/ARG descriptors lower
to CC `qreg.*` and `oracle_call`; gates lower to actions and measurement consumes
a copy. Host entries use launch-0.8 stubs with embedded objects, classical
arguments/results and host-minted budget tokens. Runtime target JCS comes from
`BENNETT_TARGET`. Native signext/zeroext ABI attributes are preserved.

Actual checks per major: 3 measured launches × 2 oracle budgets = **6/6**
independent run-program results; published oracle-inc8 COMPLETED/CLOSED; 3 native
host protocol witnesses and a signext ABI witness pass. The native witnesses
mock the launch library and check the protocol/embedded bytes; they are not
real linked launch-library execution. Device objects execute independently on
the ISA reference CLI. Output certificate.json currently has hash bindings and
producer/materialisation metadata, an empty regions map and no checked
executable claims or target/schedule binding: **not full certificate acceptance**.

Final stable dual-major headless gate: **exit 0**, **66/65/1/0/0** (18),
**66/65/1/0/0** (23), ordered run/agree/deferred/blocked/diverge. The first gate
was invalidated by rebuilding during corpus execution and is not acceptance.
No new deferrals: sole corpus deferral fp-rot-fastmath-reassoc (M2 §13 / bp-7ni).
All **16** existing scalar golden objects and **40/40** vectors per major stay
exact/passing, including four binding lifts, C O3 inc8 and descriptor-reference
inc8. Production's five inc8 reference objects per major also match the complete
golden. Six generated CC objects per major have equal cross-major bytes, with
per-file hashes/paths in verification.json. No paired published CC golden exists;
new **bp-95o** tracks that evidence gap, not a waived requirement.

Continue **bp-2zv** with these exact remaining M1 sub-items:

1. Scalar OUT/MEM_IN and device production descriptors, multiple distinct
   regions/shapes, finite dispatch and general handle/CC SSA-memory/call
   environments (§8.2/§8.3, §6.5, §17.4). They still diagnose unimplemented.
2. Full budget-table selector/identity overlays and frozen capacity maxima
   (§9.2); current defaults and constant explicit records work.
3. Checked target/schedule-bound executable certificates and full coverage/build
   records (§19.9, ISA §9.2/§12), plus real linked launch-library acceptance.
4. Paired published scalar CC golden (bp-95o): §17.4 says lowering is plugin-defined;
   cross-major equality is not published-byte equality.

Determining sentences and actual failures are in PROGRESS and bp-2zv; nothing is
out of scope or newly deferred. Do not expand this single-item pass into the
remaining lifts or key audit. Existing later obligations remain bp-3w4's general
reference/tier/materialised-key audit, bp-tr5's N0 thunk-order clarification,
bp-311's entry-replay/rung4-mini/rung8-mini/listsum and entry-stack mechanics,
and bp-qql's arena-o1. Historical full-key audit remains red: 18/49 on LLVM 18,
19/50 on LLVM 23. Grover over unmodified SQLite remains core.

Run the full regression gate from any directory:

```sh
mkdir -p /home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp /home/tobias/Projects/bennett-workspace/bennett-plugin/scripts/pre-push
```

The gate now runs strict descriptors.py and production.py acceptance fixtures.
For measured launch fixtures separately, use the same headless prefix before
`python3 /home/tobias/Projects/bennett-workspace/bennett-plugin/tests/production.py --major 18`
and again with 23. `--bennett-budget-default=5,0,7,1,0` fixes the small inc8
reference layout in these fixtures; the published LLVM fixture supplies its own
explicit budget. Normal production defaults remain the dialect's values.

Never use LLVM graphical viewers. Every build/test/run needs the headless
prefix and project-local TMPDIR. Beads: `env -C <repo> BEADS_HOOK_TIMEOUT=20 bd ...`;
export `.beads/issues.jsonl` before explicit-path commits. Do not push or touch
sibling repositories. Hook repair c91c288 remains intact; no push/dry-run push
is needed to execute scripts/pre-push directly.
