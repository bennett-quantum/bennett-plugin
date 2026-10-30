State (2026-10-30 ~14:30Z, maintainer pause): milestone 1 in progress after two sol passes (0759d75 on
origin/wip/plugin-m1; main not pushed because the gate's contract-drift check is red once the pinned dialect repo moves;
re-pin to dialect 0.2.9 / aa0f72e first). Done: dual-major build (CMake path verified after the maintainer installed
cmake 3.28.3; one compiler warning to clear), all 23 markers recognised with diagnostics, §4/§5 device analysis, §6
handle provenance, §7 region identity, corpus gate with loud deferred/blocked classes (63 agree, 1 deferred to M2 FP
materialisation, 2 were blocked on the corpus runtime, fixed upstream in 0.2.9), eleven published objects reproduced
byte-for-byte on LLVM 18 and 23. Open for M1: general analysis audit, materialised region keys, production
descriptor/CC launches (docs/briefs/2026-10-30-plugin-milestone-1b.md items 3-5). Then M2 (soft-float/native linking,
full normalisation, lifted calls/memory, descriptor replay). Read ../bennett/HANDOFF.md first.

# Handoff: bennett-plugin
State: skeleton only (bootstrap commit 2026-10-28); nothing implemented.
Next: pull the relevant spec sections (see CLAUDE.md) and write the first red test.
Specs pinned in SPEC_VERSIONS.toml; no remote exists yet.
Gates: scripts/pre-push (run scripts/install-hooks.sh once).
