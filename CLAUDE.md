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

## Rules

The one rulebook is bennett/docs/process/COMMON.md; it binds here. Gate: `scripts/pre-push`. Tasks: `bd` (`bd prime` lists its commands).
