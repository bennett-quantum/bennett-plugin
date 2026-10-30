# bennett-plugin

The C++ LLVM module-pass plugin of the Bennett compiler core, built from one source
for LLVM 18 and 23. Contracts: dialect 0.2.7 at 95c3cd3, ISA 0.8. The plugin is the
only LLVM-linked component; the eventual scheduler integration is a binary edge.

M1 is in progress: marker recognition, device analysis, provenance, region content
keys, scalar reference-object lowering and a local legality gate. Eleven published
reference objects check byte-for-byte on both majors; static descriptor extraction
is a reference-only interface. The gate separately prints one M2 deferral and
two upstream runtime blockers (66/63/1/2/0 per major). Whole-program
CC/R/action lowering is explicitly unimplemented; analysis-only success is not a
production compile. No push has been made.

See [the architecture and milestone plan](docs/PLAN.md), [build/test instructions](docs/BUILD.md)
and [verified progress and remaining work](docs/PROGRESS.md).
