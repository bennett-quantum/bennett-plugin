# Handoff: bennett-plugin

State (2026-10-31): fifth-pass bindings **384dd54**, hook fix **c91c288**;
**requested production launch Item A and M1 remain incomplete**.
No push. Accepted dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. Do not read/adopt the sibling working draft 0.2.11.

Fresh dual-major headless gate: **66/65/1/0/0** per major
(run/agree/deferred/blocked/diverge). Fresh before corpus and after full hook
gate exited 0. Initial pre-push encountered new strict binding tests with old
binaries and exited 1 (TDD red), not a passing baseline gate. Sole deferral:
fp-rot-fastmath-reassoc (M2 §13 / bp-7ni). Sixteen full published objects and
all 40 run vectors reproduce on each major. The four new completed objects are
binding-out-byte, binding-clock-read, binding-block-byte and binding-console-byte:
strict red 0/4 → green 4/4, five vectors on each major. Descriptor-reference and
C O3 inc8 remain exact. No production launch implementation landed.

Fresh fifth-pass checks: 17/17 analysis regressions, 6/6 address/provenance cases,
14/14 materialisation fixtures and key assertions on LLVM 18, 15/15 of each on
23. Historical fourth-pass full key acceptance remains **red**, 18/49 on 18,
19/50 on 23 (four base assertions included). Run with `--all-fixtures`.
PROGRESS has a witness/status row for every §4/§5 rule, every N rule and V1–V16.
verification.json records actual digests, objects, hashes, vectors and failures.

Next, finish item 1 (bp-3w4): general symbolic/residue/wide represented-address
images, all composite/atomic transfers, exact host/address/entry/boundary /
generation tier seeding and all materialised keys. Resolve **bp-tr5**: §7.2's
source forwarding-thunk resolution makes the published N0 widenable wrapper an
external intrinsic candidate, while its materialised body is defined `ret true`.
The required virtual materialisation/resolve order needs clarification.

The requested fifth-pass Item A (bp-2zv) still needs production scalar
descriptors/CC launch objects, host replacement and records. Fresh
`tests/descriptors.py --major <18|23> --require-production` exits 1 at CC/marker
event lowering, with empty isolated production output directories. The default
test checks reference equality and loud production failure; it is not acceptance.
Determining requirements: accepted dialect §17.4 marker calls lower to region
calls and qreg.* with §6.5's handle environment; §19.9 requires host launch stubs,
device objects, certificates, coverage and resolved build records; ISA §10 says
a run executes a device CC entry. This is a repository implementation gap.
The pinned dialect publishes no CC launch-object golden (§17.4 is plugin-defined);
the inc8 golden is the reference oracle/lproc object. No requirement is waived.

Item 3 now still requires entry-replay-byte, rung4-mini, rung8-mini, listsum,
entry-stack and arena-o1. Exact missing rows and
existing mechanical owners bp-311/bp-qql are in PROGRESS/PLAN; none is out of scope.
No new M2 deferral was added. Grover over unmodified SQLite remains core.

bp-zk2 is closed: actual `git push --dry-run` ran the full dual-major gate
and exited 0. No push. pre-push unsets GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE and
resolves its installed symlink before root discovery; unsetting alone still
started git inside .git/hooks and failed. PROGRESS and verification.json record
the runs, object hashes and remaining production failure.

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
