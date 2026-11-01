# Handoff

Rewritten at session end with `date -u`: **2026-11-01T09:40:14Z**.

Pinned contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**,
ISA **0.8**. M1 remains complete; M2 and the North Star ladder remain in progress.
This pass closes **bp-9fo**; next measured frontier **bp-bux**. **bp-7ni unchanged**. No push.

Implementation: **680ea61a824cd946e09824ffb85fdaa6f0818f43**.
Ordinary direct calls, including internal fastcc/tail calls, emit real typed ISA CC call/ret
closures (§14.1/§17.4, ISA §4.1), with one callee environment per invocation and retained
nested frames for LIFO reversal (ISA §7.4). Pointer/integer parameters and pointer/integer/void
returns retain their carriers; callers and callees share the relocated memory and allocation
history. Recursive SCC identities are computed after the full memory layout is fixed.
Internal direct-only callees stay inside the caller's launch; their H bodies are retained.
§9.3 explicitly gives device CC outside regions no budget: small depth/stack tokens do not
bound these CC calls. Existing lifted region depth/stack faults remain unchanged.

Two probes per major (`cc-calls.ll`, `cc-self-call.ll`) exercise nested calls, pointer returns,
void calls in loops, mutual and launch-entry recursion, heap memory and mutable globals.
Each major passes eight full-state reversals (including allocation/handle/memory equality)
and four small-budget CC executions. Recognised/materialised digests, verified bitcode,
independently checked/hashed objects and complete execution results are in docs/verification.json.

One complete **scripts/gate exit 0**: **66 run / 66 agree / 0 deferred / 0 blocked / 0 diverge**
each major; cells **924/924** (18), **792/792** (23). All **297** committed prior object hashes
preserved; **299** equal object pairs and **45** published matches. Log: `.tmp/bp-9fo-gate.log`.
Receipt recorded with scripts/record-verification.py --pass bp-9fo. An obsolete pre-green
`.tmp/cc-calls/<major>/calls` directory was removed before the final receipt inventory; final
cross-major and prior-object checks were rerun successfully against the committed baseline.

## Next measured rung-2 frontier

Fresh marked C was compiled with each major's clang -O2 -flto, linked with published runtimes
and SHA-pinned arith via llvm-link --only-needed, then lto<O3>. Linked analyses pass on both.
Production now passes the ordinary-call refusal and exits 1 at the next rule (§14.8 switch):

LLVM18 (25.72s):
```llvm
switch i64 %104, label %116 [
  i64 -9223372036854775808, label %105
  i64 -9223372036854775807, label %113
]
```
LLVM23 (29.33s):
```llvm
switch i64 %113, label %125 [
  i64 -9223372036854775808, label %114
  i64 -9223372036854775807, label %122
]
```

**bp-bux**, labels consumer,m2,rung2, quotes the determining §14.8 sentence requiring the
§16.4 compare tree of icmp/br in CC/R. Full commands, timings, input/plugin/publication hashes
and diagnostics: docs/rung2-analysis.json `cc_calls_after`; frontier commit **6571074**.
The conditional rung-2 gate was not run because production remains incomplete. No hashtable
executor admission, forward/native agreement, reversal or §17.7 materialised native comparison
success is claimed. No sibling source or spec edits; no dialect-ambiguity bead was needed.

Run headless: unset DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER;
TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp. Never LLVM -view-*.
Use scripts/gate for iteration; scripts/pre-push gates a frozen commit in a detached worktree.
Record only completed gates with scripts/record-verification.py. Export beads with
bd export -o .beads/issues.jsonl before committing .beads; commit explicit paths. Never push
from this implementation task. The orchestrator owns the session worklog and any later push.
