# Typed R faults — review round 1

Reviewed `main...3cfcf49718c34bbdc9a9a0a78d4d92029b7b940c`, commits `20e40fa` through `3cfcf49`, merge base `1b92b497ee79c3c9ff57318c77e986b0c3fe2707` (varargs head, merged into main at `2319890`). Verdict: **CLEAR**. No P0/P1 findings; no implementation changes.

Rung 3 / oracle checks: exact 0→4 and full-u64 fault causes, pre-instruction step exhaustion, terminal caller behavior, reversible prefixes/open recursive activations, profile identities/module flags/build-record binding, and ISA §9.2 original-key array envelopes all passed. Existing legacy assertions were preserved. Main's version check rejects 0.3-r1, and its counter/fault paths emit trap: the new tests would fail there. The array regression independently distinguishes the old dotted recipe.

Verification, all through `.tmp/r3-typed-faults/slot.py` with headless review-local TMPDIR/CARGO_TARGET_DIR, timeout guards and sequential workspace build locking:

- `cmake --build build/llvm18 -j3` and `cmake --build build/llvm23 -j3`: exit 0, current builds.
- `python3 -B tests/<driver>.py --major <18|23>` for each of `r_typed_faults`, `r_envelopes`, `dialect_version`, `reversible`, `production`, `production_records`, `varargs`: all 14 invocations exit 0. Typed-fault wall/CPU: 41.206/41.085 s (18), 37.414/37.334 s (23). Recursive compiler wall: 25.153/23.076 s with the default analysis allowance. N23 objects still admit, execute and reverse.
- Separate inline Python/hashlib derivation, importing no producer/test hash helpers: the produced `R0` envelope hashes to `d9147ad347c8a0e1df1e288cc1ace1aa7ed8d4bd6dbfbdc669c7854a1ce720c0` on both majors. All 28 current LLVM18 snapshot objects match the historical pre-T inventory. Both legacy dialect tests retain pinned object SHA-256 `201b40a382bdcfd04b9d307f0d69d9f8a748f31b2c8d1b0f2f1b4b4a389f3ccb`.
- `.tmp/r3-typed-faults/guard-check.py`: seven controls pass; `snapguard-controls.py`: forced expiry remains UNKNOWN/124 and assertion failures remain failures. `python3 -B scripts/quality.py --check`: no regressions; `git diff --check main...3cfcf49`: clean.

P2+ nits: **bp-z8u** — `tests/r_typed_faults.py:125` retains source-allowance-derived/bare subprocess caps; `scripts/test:165` omits child CPU in receipts, with guard class/machine-scaling provenance not yet durable. Rule 9 makes these nonblocking.

Coverage: read closely all changed source, tests, scripts, version/pin files and applicable profile/ISA clauses; checked each anti-slop rule, quality ratchet registration and retired HANDOFF/README pointer. Skimmed surrounding unchanged lowering. Inspected prior gate failures and snapshot measurement/acceptance receipts; did not rerun the long snapshot driver or full gate. Full-gate disposition remains with the orchestrator; this review does not assert a gate PASS.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
