# Pin-plugin review, round 2

Verdict: **CLEAR**. No open P0/P1. Round-1 **P1-1 / bp-lfb** and **P1-2 / bp-88d** are fixed; independent verification notes added to both beads.

Reviewed head: **b719592eb14bc02cf5aacc1b26d82b9e9cc9e3cb** on `job/pin-plugin`. Inspected `main...job/pin-plugin` (merge base `5a092cded3ba3351ba8cc2977a7eaf3b40f46526`; main observed at `2f832729d44cd5fd5995c3077cf69ec2dc93e9cf`). Round-2 assessment covers only `afe2682..b719592`: fixes `0f330bc76332ada98f2374c86c2dc4eda02344e2` and `b719592eb14bc02cf5aacc1b26d82b9e9cc9e3cb`.

- **P1-2 / bp-88d:** `tests/contracts.py:32` now compares ISA against the immutable dialect registry. An independent `timeout 65s python3 -B -` probe read the real pinned registry (ISA 0.8), changed both consumer ISA fields to 999, and evaluated the pre-fix `drift()` extracted from `git show afe2682:tests/contracts.py` alongside the head function: **False before, True at head**. Both added corruption regressions exercise this mismatch. Main's hard-coded ISA 0.8 check already rejected 999; this restores the branch's lost validation.
- **P1-1 / bp-lfb:** `CMakeLists.txt:28-47` resolves and validates arithmetic through `arith_path()` and embeds an absolute pinned path. The configure regressions cover cache and gate layouts on LLVM18/23, plus missing publications. Reading `git show main:CMakeLists.txt` and the pre-fix version confirms they embed the relative fixture path and accept missing publications, so these tests detect the missing fix. Both existing CMake-built plugins also passed the unrelated-cwd regression with every `BENNETT_*` variable removed: pinned hash present, native execution **3/3 independent sums per major**. Their generated flags agree with the fixed defaults; no rebuild was needed.

Focused checks run from the worktree, all exit 0:

- `timeout 180s python3 -B tests/pin_policy.py -v` — **20/20**.
- `timeout 60s python3 -B tests/contract_policy.py` — registry, ISA corruption, publication/hash checks pass.
- `timeout 120s python3 -B tests/build_defaults.py` — **both majors, 6/6 sums**.
- `timeout 60s python3 -B tests/gate_policy.py` — **9 assertions**.
- `timeout 150s python3 -B tests/build_fallback.py --probe-only` — **2/2 compiler probes**.

Environment: DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS/BROWSER unset; TMPDIR and CARGO_TARGET_DIR under `.tmp/rev-pin-plugin-r2/`; build jobs 3, Rust test threads 4; Python bytecode disabled. No full repository gate, gate tool, sibling gate, branch switching or new worktree.

P2+ nits: **bp-o8d** consolidates the inherited README contract/relocation/duplication and quality-baseline/HANDOFF/tracked-progress upkeep from bp-cwl (superseded); the fixture-comment nit is fixed. No new nit in the fix diff.

Coverage: read all six round-2 changed files closely, including complete tests, resolver, CMake/build paths and prior review; skimmed earlier branch changes and unchanged consumers. Checked each COMMON Anti-slop rule: dispatch, state, silent defaults, predicates, constants, function altitude, wrappers, process identifiers, litter and independent test oracles. No new violation, weakened test, over-300-line function, silent fallback or narrowing found. `git diff main...HEAD -- src` is empty; `git diff --check afe2682..HEAD` passes. Only this review document is committed.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
