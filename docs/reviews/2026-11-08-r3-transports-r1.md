# Native runtime transports — review round 1

**CLEAR — no P0/P1 findings.** Reviewed `origin/main..job/r3-transports`, base
`2319890511cdd2fa46b8c4cc748b52877408be6f`, head
`3fda7b494dec0c92e5c2a861af41f47e644932a1` (four commits).

The transport-family predicate replaces source wrappers with imports and removes
import aliases from the definition report. Ordinary prepared definitions still
require the exact materialisation stamp; unstamped legacy transport definitions,
unknown/stamped-unknown imports, runtime helpers and transport retargeting fail
loud. The existing console adapter ABI is retained. Main's finalise condition
rejects the red import fixture's declaration; its marker dispatcher rejects the
new non-console effects, establishing red-first attribution by source inspection
without switching the checkout.

Verification: every build/test used `python3 -B .tmp/r3-transports/slot.py env
TMPDIR=$PWD/.tmp/rev-r3-transports-r1/tmp
CARGO_TARGET_DIR=$PWD/.tmp/rev-r3-transports-r1/target` as its command prefix,
headless, sequentially, under the existing wrapper timeout. No tracked hang-guard
class table/machine profile was found.

- `scripts/build`: PASS LLVM 18/23.
- `python3 -B .tmp/rev-r3-transports-r1/focused.py`: **12/12 PASS**;
  `native_transports.sh` and the five existing native suites on both majors,
  including actual native hello bytes and checked fault outcomes.
- `python3 -B .tmp/rev-r3-transports-r1/extra.py`: PASS both majors; executed
  deterministic stubs verify hand-derived `CEORWCEORWX` call order, operands and
  console bytes through direct/finalise/host paths; a novel transport-family
  import succeeds and a wrong nonempty provenance stamp fails.
- Driver `actual_scalar_r_requires_real_program_binding_before_startup`
  fixture: PASS both majors against runtimes `642c53c`, reaching
  `BD-E-NATIVE-STARTUP` after prepare/check/finalise with no executable.
  Review-local copy preserves every assertion AST; only runtime pin and plugin
  path change. Command/receipt: `.tmp/rev-r3-transports-r1/driver.txt`.
- `python3 -B scripts/quality.py --check` and
  `git diff --check origin/main...HEAD`: PASS. No full gate was run.

P2+ nits: **bp-dyk** (priority 3): `tests/native_transports.sh:87,100` checks
marker absence without executing replacement effects; commit an operands/order/
console-byte regression like the independent review probe. Non-blocking.

Coverage: closely read all five changed files, main-side provenance/marker code,
pinned dialect §§11.2/17.7/19.5 and driver fixture/link ordering; skimmed existing
native harnesses and quality tooling. Checked every COMMON anti-slop rule; gate
ratchet exists, repo HANDOFF.md is retired, README points to the ecosystem handoff.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9).
Focused and supplemental receipts live under `.tmp/rev-r3-transports-r1/`.
