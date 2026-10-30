# bennett-plugin

The C++ LLVM module-pass plugin of the Bennett compiler core, built from one source
for LLVM 18 and 23. Contracts: dialect 0.2.6 at ff249d5, ISA 0.8. The plugin is the
only LLVM-linked component; the eventual scheduler integration is a binary edge.

M1 is in progress: marker recognition, device analysis, provenance, region content
keys, scalar reference-object lowering and a local legality gate. Whole-program
CC/R/action lowering is explicitly unimplemented; analysis-only success is not a
production compile. No push has been made.

See [the architecture and milestone plan](docs/PLAN.md), [build/test instructions](docs/BUILD.md)
and [verified progress and remaining work](docs/PROGRESS.md).
