# Handoff: bennett-plugin

State (2026-10-31): fourth-pass code/tests **95fa83f** advanced item 1; **M1 remains incomplete**.
No push. Accepted dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. Do not read/adopt the sibling working draft 0.2.11.

Fresh dual-major headless gate: **66/65/1/0/0** per major
(run/agree/deferred/blocked/diverge), exit 0 before and after. Sole deferral:
fp-rot-fastmath-reassoc (M2 §13 / bp-7ni). Twelve full published objects and
all 35 run vectors reproduce on each major; no additional example is complete.

Fourth-pass checks: 17/17 analysis regressions, 6/6 address/provenance cases,
14/14 materialisation fixtures and key assertions on LLVM 18, 15/15 of each on
23. Full published key acceptance audit is separately **red**, 18/49 on 18,
19/50 on 23 (four base assertions included). Run with `--all-fixtures`.
PROGRESS has a witness/status row for every §4/§5 rule, every N rule and V1–V16.
verification.json records actual digests, objects, hashes, vectors and failures.

Next, finish item 1 (bp-3w4): general symbolic/residue/wide represented-address
images, all composite/atomic transfers, exact host/address/entry/boundary /
generation tier seeding and all materialised keys. Resolve **bp-tr5**: §7.2's
source forwarding-thunk resolution makes the published N0 widenable wrapper an
external intrinsic candidate, while its materialised body is defined `ret true`.
The required virtual materialisation/resolve order needs clarification.

Then item 2 (bp-2zv): production scalar descriptors/CC launch objects, host
replacement, records; descriptor-reference is still test-only. Item 3 still
requires binding-out-byte/clock-read/block-byte/console-byte, entry-replay-byte,
rung4-mini, rung8-mini, listsum, entry-stack and arena-o1. Exact missing rows and
existing mechanical owners bp-311/bp-qql are in PROGRESS/PLAN; none is out of scope.
No new M2 deferral was added. Grover over unmodified SQLite remains core.

Run the full regression gate from any directory:

```sh
mkdir -p /home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp /home/tobias/Projects/bennett-workspace/bennett-plugin/scripts/pre-push
```

For full-key acceptance, use that same headless prefix before
`python3 /home/tobias/Projects/bennett-workspace/bennett-plugin/tests/region_keys.py --major 18 --all-fixtures`
and again with 23. These commands currently exit 1; this is not M1 acceptance.
Never run LLVM graphical viewer passes. Every build/test/run uses the headless
prefix and project-local TMPDIR. Beads: `env -C <repo> BEADS_HOOK_TIMEOUT=20 bd ...`;
export `.beads/issues.jsonl` before explicit-path commits. Do not push.
