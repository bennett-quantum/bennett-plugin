# bennett-plugin

## What this repo is

the C++ LLVM pass plugin, the only LLVM-linked component of the compiler core. It does taint over the whole-program call graph, region outlining, controlled/adjoint body generation, lowering to the virtual ISA, and calls bennett-sched. Built once per LLVM major.

Part of the Bennett reboot: many small repositories, two published contracts
(`bennett-dialect-spec`, `bennett-isa-spec`). Depends on: bennett-dialect-spec, bennett-isa-spec, bennett-sched (binary edge).

## Where the spec is

The published specs, at the versions in `SPEC_VERSIONS.toml`. Source documents
currently live in the Bennett.jl repo (`Bennett-NorthStar.md`,
`Bennett-ISA-Spec.md`) until the spec repos are split out. The spec wins over
any code, including code in this repo.

## Non-negotiables

0. MAINTAIN THE WORKLOG. Every session, prepend a `## Session log - YYYY-MM-DD`
   block to the highest-numbered chunk under `worklog/`. Past ~280 lines, start
   the next `NNN_` chunk. Record gotchas and surprises not derivable from the diff.
1. FAIL FAST, FAIL LOUD. Assertions and clear errors, never silent returns or
   quiet fallbacks. Unsupported means a crash with context.
2. ONE IMPLEMENTER PER CHANGE. Independent review is batched over several landed
   changes, not required per change.
3. RED-GREEN TDD. Write the test, watch it fail, make it pass, then refactor.
4. EXHAUSTIVE VERIFICATION against the spec conformance suites for the versions
   in `SPEC_VERSIONS.toml`. "Runs without errors" is not a pass.
5. COUPLED TO OTHER REPOS ONLY THROUGH THE PUBLISHED SPECS. No shared code across
   a contract boundary. This repo must be replaceable by a competitor's
   implementation of the same spec without the rest noticing.
6. NO GITHUB CI. Local gates only: `scripts/pre-push` (install with
   `scripts/install-hooks.sh`). No workflows, no remote automation.
7. Use beads (`bd`) for tasks if initialised in this repo. No TODO.md files.
8. SKEPTICISM. Verify subagent output, earlier work, and your own assumptions.
   Reproduce before believing.
