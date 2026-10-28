# bennett-plugin

The C++ LLVM pass plugin of the Bennett compiler core, and the **only
LLVM-linked component**. It performs:

- taint analysis over the whole-program call graph,
- region outlining,
- controlled / adjoint body generation,
- lowering to the virtual ISA (bennett-isa-spec),
- calls into `bennett-sched` for scheduling.

## Depends on

- `bennett-dialect-spec` (marker-function ABI, legality requirements)
- `bennett-isa-spec` (target of lowering)
- `bennett-sched` (as a **binary** edge: a sched built against ISA spec vN is
  replaceable without rebuilding the plugin)

The plugin is replaceable by a competitor's plugin that passes the dialect
spec's legality corpus; the driver talks to it only through the plugin
invocation interface in the dialect spec.

## Per-LLVM-major branches

One branch per LLVM major, named `llvm-18`, `llvm-19`, `llvm-20`. Only `main`
exists now. Convention: `main` tracks the newest supported major plus shared
code; a `llvm-NN` branch is cut when a major is added and receives
cherry-picks of shared fixes. See `docs/BUILD.md`.

## Status

Skeleton: `src/BennettPlugin.cpp` holds a commented `llvmGetPassPluginInfo`
behind `BENNETT_HAVE_LLVM`. CMake configures without LLVM (it prints a status
message and skips the target).
