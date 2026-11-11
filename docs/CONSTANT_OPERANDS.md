# Constant-expression operands

Runtime constant expressions are materialised as LLVM instructions before
ordinary scalar normalisation and lowering. This includes legacy expressions
read from published bitcode even when the current LLVM textual assembler no
longer accepts their spelling. Nested expressions and constant aggregates use
the same instruction lowerers as equivalent explicit IR.

A PHI expression is evaluated on its incoming edge. An edge block is introduced
when the predecessor has other successors, keeping evaluation off unrelated
paths. Aliases resolve to their actual global/function or offset, with no change
to the aliased definitions. Existing GEP operands retain their representation
when no nested expression needs materialisation. EH clauses remain constant
descriptors for exception lowering.

Global initializers remain symbolic for the existing link-layout/image pass.
The materialiser does not guess global or function addresses, fold comparisons
using host placement, create images for undefined linker symbols, or replace
constructor/finalizer callbacks. The comparison layout continues to supply the
actual bases and function addresses.

`tests/constant_operands.py --major 18` (and `23`) checks native results, R
forward/reversal, PHI and aggregate operands, scalar lifting, two fixed data
bases, fixed function-pointer images, and observable constructor/finalizer
cleanup. `tests/r_process_arguments.py` retains the published runtime process
preparation, atexit/stdio cleanup and exit checks.

Materialised casts/GEPs retain their constant-expression descriptor. Scalar
materialisation reconstructs a cast/GEP only when all of its current operands
are constants, before analysis and residual validation. This preserves the
published L constant-operand spelling and index-width rules. Classical
lowering continues to consume their instruction form.
