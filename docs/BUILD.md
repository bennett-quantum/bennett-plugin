# Building bennett-plugin

## Per-LLVM-major builds

LLVM's C++ API and IR are not stable across majors, so the plugin is built
against exactly one LLVM major at a time and released as one artifact per
major (`bennett-plugin-llvm18.so`, ...). Source branches follow the
convention `llvm-18`, `llvm-19`, `llvm-20`; only `main` exists now.

```
cmake -S . -B build-llvm19 -DLLVM_DIR=/usr/lib/llvm-19/lib/cmake/llvm
cmake --build build-llvm19
opt -load-pass-plugin build-llvm19/BennettPlugin.so -passes=bennett in.ll -o out.bc
```

Without LLVM, `cmake -S . -B build` still succeeds and skips the target.

## Precedent: Enzyme

Enzyme (automatic differentiation) is an out-of-tree LLVM plugin maintained
per LLVM major with the same approach: one branch/artifact per major, a thin
version-adaptation layer, and a user-facing driver that picks the matching
build. We follow that model; the driver selects the plugin binary whose LLVM
major matches the front-end's bitcode producer.

## Rules

- No LLVM headers outside `src/`; real code stays behind `BENNETT_HAVE_LLVM`.
- No dependence on LLVM internals beyond the stable-per-major pass plugin API.
