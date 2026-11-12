# S2 varargs transfers

The contracts are dialect §5.2 / §14.3 (0.2.13 for the default profile,
0.3-r1 for the R profile) and ISA 0.9 for R emission. The §14.3 rows agree
in the default pin and the rung-3 contract at dialect commit `9bbf6de`.

§5.2: “S2 models the value effects of the specified normalisation before
verdicts and dispatch domains freeze; pre-normalisation syntax does not
permit omitting a value produced by the materialised execution.”

§14.3: “A call site spills its variadic arguments (as the front end promoted
them) into a va block”, in argument order, with each offset aligned to
max(8, ABI alignment), occupying its size rounded up to eight bytes.
Every defined variadic callee receives the union of its call-site block
pointers (PT9). The block is a private N23 alloca, stable for that call
instruction across S2 rounds. Its initial zero image follows §5.2 / §17.3.
Host-visible implicit block parameters also receive PT11's external pointer.
For undefined callees, PT12 reaches the block and its stored pointer leaves.
Defined allocator calls that are variadic or carry N23's argument block still
bind PT9 parameters and body effects; the allocation-result summary does not
replace that binding. N23 call metadata preserves the obligation after the
variadic ABI has become a fixed block parameter.

§14.3: “`llvm.va_start(ptr ap)` builds the target's `va_list` so that the
front end's inline `va_arg` takes its memory path”. The same `writeVaList`
graph serves materialisation and S2: x86-64 System V writes 48, 176, the
block pointer and null; AAPCS64 writes the stack pointer, two null register
tops and two zero offsets; RISC-V LP64 writes the block pointer.

§14.3: “IR `va_arg` is expanded by the same memory layout;
`llvm.va_copy(d, s)` copies the `va_list` record (24, 32 or 8 bytes);
`llvm.va_end` is deleted.” S2 runs precisely that expansion, including
alignment, cursor advancement and all reads before the copy's writes.
N23's `ptrmask` expansion is also shared. Aggregate/vector actuals retain
leaf transfers. No control-path pruning is added: the inline register-save
branch can still contribute top under the flow-insensitive PT rules.
Private graphs are released before rewriting or cloning source bodies.

## No-effect audit

`Analysis::step` still excludes **every intrinsic reaching its final call
fallback** from PT12. This is a complement rule, not a small whitelist.
The following partition describes that complete fallback set, including
major-specific and target intrinsic IDs:

* Justified by §12.2 N5 deletion: `assume`, `sideeffect`, `donothing`,
  `pseudoprobe`, `fake.use`, `dbg.*`, `experimental.noalias.scope.decl`,
  `codeview.annotation`, `var.annotation`, `reloc.none`, `prefetch`,
  `pcmarker`, `clear_cache`, `experimental.convergence.*`, `seh.*`,
  `xray.*`, `experimental.stackmap`, `eh.unwind.init`,
  `asan.check.memaccess`, `hwasan.check.memaccess*` (all prefixed `llvm.`).
* Justified by §12.2 N6 deletion: `llvm.lifetime.start`,
  `llvm.lifetime.end`, `llvm.invariant.start`, `llvm.invariant.end`.
* Unjustified: **all remaining fallback IDs/overloads**. Purity does not
  justify an empty result. These include N5's operand-returning calls,
  N10's queries, N24's stack/address operations, the N26 memory families
  not recognised as `MemTransferInst`/`MemSetInst`, the remaining N27
  integer expansions, residual N0/N28 operations and N31 target calls.
  Vector FP signatures that do not select the scalar FP graph also remain
  in this complement unless an earlier composite transfer handles them.

The exclusions from that fallback partition are the earlier transfers:
scalar integer smax/smin/umax/umin and signed/unsigned add/sub overflow;
ctpop/ctlz/cttz; VP merge/select; integer add/mul/and/or/xor VP/vector
reductions; recognised memory transfers/sets; the private scalar FP graphs
(selected by scalar FP result/argument or their explicit environment/query
predicate); and now va_start/va_copy/va_end/IR va_arg/ptrmask. Scalar-only
conditions matter: recognising a scalar overload does not justify ignoring
its vector overload. Private FP graphs must themselves be audited for any
residual fallback calls. N0 preprocessing can remove an ID before S2.

The printf inputs on both majors contain unjustified fallback calls:
`llvm.abs`, `llvm.fshl` and `llvm.umul.with.overflow`. Turning the entire
fallback into a hard error would stop those existing productions. Their
transfers and existing failure behaviour are outside this varargs change.
The audit therefore does not claim that the general intrinsic omission
problem is fixed.

Varargs cases without an implemented lowering diagnose §14.3 rather than
silently leave a result empty: missing target ABI rows, an IR va_arg/spill
without a fixed ABI size, va_start outside a variadic definition, and N23's
existing invoke/byval limitations. A nonvariadic call type targeting a
variadic definition is also diagnosed because its N23 call rewrite is not
implemented. These are implementation/contract-coverage gaps, not proof
that the corresponding source capability is inert or outside the North Star.
