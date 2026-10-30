# Brief: bennett-plugin milestone 1, continuation (M1b)

Repository `/home/tobias/Projects/bennett-workspace/bennett-plugin` (HEAD 3be37ba). You are the sole implementer and
continue milestone 1 from `docs/PLAN.md`, `docs/PROGRESS.md` and `docs/verification.json` left by the previous pass
(read all three first, then the original brief `docs/briefs/2026-10-30-plugin-milestone-1.md`, whose rules still
bind). The orchestrator reproduced the gate: both majors 66 cases run / 63 agree / 3 diverge; nine scalar objects
match the reference's published hashes. `cmake` is not installed on this machine; the llvm-config/g++ fallback is the
build until the maintainer installs it, and the CMake path stays documented as unverified.

## Work, in order

1. **Re-pin** to dialect draft 0.2.7, commit 95c3cd3 of `../bennett-dialect-spec` (the council editor landed §9.2
   staged budget identity, PT2 modular GEP offsets, PT5 range rule, N9 `nand`). Read its `round-6/response.md`
   (`../bennett/docs/council/dialect-2026-10-29/round-6/response.md`) for exactly what changed, update
   `SPEC_VERSIONS.toml` and the PLAN pin, and re-run the gate; any case whose expectation moved is re-derived from
   the new text, never relabelled.
2. **The three divergences.** Classify each by root cause with evidence, then act:
   - `spec-sem2-adj`, `spec-sem2-compute` (L1/L5, black-box runtime exits 87): determine whether the exit comes from
     the dialect corpus's trace runtime (the dialect repo recorded that its runtime was still at ABI v0, bead
     `b-dialect-spec-566`) or from the plugin's output. If upstream, file a bead here naming the corpus file and the
     observed exit, classify the two cases as `blocked-upstream: <bead>` in the gate (counted and printed, not
     agreement, not divergence), and state it in your final message so the orchestrator relays it to the dialect
     editor. If it is the plugin, fix it red-green.
   - `fp-rot-fastmath-reassoc` (L5, FP materialisation): implement the §13/§17.7 materialisation this case needs if
     it is within the scalar/FP-carrier part of the lifting map that M1 already touches; otherwise classify it as
     `deferred: M2 (§13 FP materialisation)` in the gate with the plan item, counted and printed.
   - The gate exits 0 only when every non-deferred, non-blocked case agrees; deferred and blocked cases are listed
     loudly with their milestone or bead on every run. Exit 1 remains for any real divergence. Record the rule in
     `tests/corpus_gate.py`'s header and in PROGRESS.
3. **Finish M1's documented gaps**: the analysis/materialisation items and the production descriptor path listed as
   incomplete in `docs/PROGRESS.md`. Each closes red-green against a corpus case or a dialect example, both majors.
4. **Rung-1 slice completeness**: every scalar `spec-*` corpus case and every scalar executed `isa object=` example in
   the dialect lowers to an object that passes `bennett-isa-ref check` with the stated hash and run vectors; list
   any scalar example that still does not, with the §16 row it needs.
5. Update PLAN (what M1 delivered, what moved to M2), PROGRESS, verification.json from actual runs, HANDOFF-style
   notes stay out of your paths (the orchestrator writes HANDOFF/worklog).

Rules as before: dialect and ISA via published text and black-box binaries only; never read checker or interpreter
source; red-green; headless (rule 11, never LLVM `-view-*`); `scripts/pre-push` is the gate; `bd` for tasks and for
every dialect ambiguity you hit (name the sentence and the change); commit your paths regularly
(`BEADS_HOOK_TIMEOUT=20 git -C /home/tobias/Projects/bennett-workspace/bennett-plugin commit -- <paths>`, `bd export
-o .beads/issues.jsonl` before committing `.beads`); never push; absolute paths; no `cd` in compound commands; never
edit another repository. Final message: commit hashes, gate counts per major (run / agree / deferred / blocked /
diverge) with the classification of each non-agreeing case, the scalar objects checked with hashes, what remains for
M1 if anything, and the M2 entry point.
