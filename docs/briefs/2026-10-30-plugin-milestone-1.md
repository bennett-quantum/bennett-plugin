# Brief: bennett-plugin milestone 1 (plan + device analysis + marker recognition + legality-corpus gate)

Repository `/home/tobias/Projects/bennett-workspace/bennett-plugin` (skeleton: `src/BennettPlugin.cpp`, CMake that
builds a pass plugin when `LLVM_DIR` is set). You are the sole implementer of this repo. The maintainer released
plugin work on 2026-10-30 against **dialect draft 0.2.x** (currently 0.2.5 at
`../bennett-dialect-spec/spec/Bennett-Dialect-Spec.md`, HEAD a06fcbd; a concurrent editor is producing 0.2.6 and the
council has not yet accepted it). Build against the text as it stands; pin the exact spec commit you read in
`SPEC_VERSIONS.toml` and `docs/PLAN.md`; when the text moves, the gate tells you.

The plugin consumes two published contracts and nothing else (CLAUDE.md rule 5): the dialect spec (marker ABI §3,
processing order §4, device analysis §5, handles §6, regions §7, oracle interface §8, budgets §9, taint-driven
lifting §10, normalisation §12, lifting map §16, device classical code §17, reference semantics §18, driver §19,
corpus §21, diagnostics §22) and ISA 0.8 (`../bennett-isa-spec/spec/Bennett-ISA-Spec.md`; the reference binary
`../bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref` is a black box for `check`/`hash`/
`run-oracle`). Never read or copy code from the dialect checker (`../bennett-dialect-spec/scripts/`), the reference
interpreter or any sibling; you may run their binaries and read their published fixtures and corpus
(`../bennett-dialect-spec/corpus/legality/`: 63 cases, controls, `harness/run.py`, `markers.h`, `toolchains.toml`;
`../bennett-dialect-spec/spec/bennett_markers.h` is the ABI 0.2 header).

## Read first, in full

`CLAUDE.md`, `README.md`, `docs/BUILD.md`, `SPEC_VERSIONS.toml`; `../bennett/docs/Bennett-NorthStar.md` §3 (the
compiler core: taint, outlining, markers, legality), §4, §8 (the demo ladder: rung 1 is this milestone's acceptance
shape); dialect §1–§10, §12, §16–§19, §21–§22 (skim §13–§15, §20); `../bennett-dialect-spec/docs/spikes/
2026-10-28-legality-findings.md` (what passes do to marker programs; the attribute envelope);
`../bennett/docs/plan/2026-10-29-path-to-north-star.md` (standing rule: no narrowings; R1/R2 are the hard design
problems and are the dialect's §10/§7, which you implement, not re-decide). Toolchains on this machine: LLVM 18
(`/usr/lib/llvm-18`) and 23 (`/usr/lib/llvm-23`); LLVM 20 via the Julia artifact named in `toolchains.toml`.

## Milestone 1

1. `docs/PLAN.md`: the pass architecture for the whole CLAUDE.md scope (device analysis fixpoint, outlining,
   controlled/adjoint body generation, lowering to ISA objects, sched as a binary edge, per-major build), milestones in
   order, what M1 delivers, and a table mapping every dialect section to the milestone that implements it. Short,
   decisive. Note which dialect items are `blocked:` on ISA 0.9 (dialect §25) and keep them as explicit
   `unimplemented: <item> (blocked: <bead>)` diagnostics, never silent.
2. Build: `CMakeLists.txt` building `libbennett-plugin-18.so` and `libbennett-plugin-23.so` from one source tree
   (per-major `#if` only where LLVM's API differs; record each in `docs/BUILD.md`); loadable by `opt
   -load-pass-plugin` as the module pass `bennett` with the `-bennett-dialect=<version>` option of dialect §19.1; it
   MUST do nothing in a pre-link phase.
3. Marker recognition and the device analysis (dialect §3, §4, §5): recognise every ABI 0.2 marker of
   `bennett_markers.h` by name and signature, diagnose every malformed use per §22, compute the device program
   (§4), the one-fixpoint analysis of §5 (tiers, variants, function-address sets), handle provenance per §6 (bitwise
   copies tracked; other handle-derived uses rejected fail-loud), region identity by content per §7.2–§7.3.
4. Legality-corpus gate: a test driver that runs every case under `../bennett-dialect-spec/corpus/legality/cases/`
   and `controls/` through clang/opt of LLVM 18 and 23 with the §21.1 envelope pipelines **plus** the `bennett` pass,
   and checks what the plugin reports against each case's `EXPECT:` line and the harness's L1–L6 properties (reuse
   `harness/run.py` as a black box if it accepts a plugin; otherwise write the driver in `tests/` and say so).
   Negative controls must fail for the stated reason.
5. Rung-1 slice (scalar C functions, dialect §18 reference semantics): for the scalar `spec-*` corpus cases and the
   dialect's executed `isa object=` examples that are scalar, lower the recognised oracle to an ISA 0.8 object and
   check it with `bennett-isa-ref check`; where the spec states the object's hash, reproduce it. Everything that M1
   does not lower (memory, calls, FP, vectors, effects, tdl) fails with `unimplemented: <§> (milestone N)` naming the
   plan item. These are deferrals of mechanics; the plan must show every one of them scheduled.

Red-green per feature (write the test against the corpus case first); fail fast and loud; no silent fallbacks; nothing
narrowed (rule 10): a construct the dialect admits is never rejected for convenience.

## Process

Headless (rule 11): `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `BROWSER` unset, `TMPDIR` under this
repo (`mkdir -p .tmp`); **never** any LLVM `-view-*`/`view-cfg`/`view-dom` pass (use `dot-*` if you must). Build and
test offline. `scripts/pre-push` must run the build for both majors and the corpus gate; install it with
`scripts/install-hooks.sh`. `bd init` here if `.beads/` is absent (rule 7), then `bd create` the M1 epic and tasks;
`bd export -o .beads/issues.jsonl` before committing `.beads/`. Keep `docs/PROGRESS.md` current (what is verified, by
which test, against which corpus case and LLVM major). Commit your paths regularly (`BEADS_HOOK_TIMEOUT=20 git -C
/home/tobias/Projects/bennett-workspace/bennett-plugin commit -- <paths>`, retry on `index.lock`); do not push;
absolute paths; never `cd` inside compound commands; never edit another repository (dialect gaps or ambiguities you
hit are beads here, each naming the exact dialect sentence and the change it needs; the orchestrator relays them to
the dialect editor). Final message: commit hashes, PLAN summary (10 lines), corpus gate counts per major (cases run /
agree / diverge, with the §21.1 property for each divergence), the rung-1 objects checked and their hashes, and the
next milestone.
