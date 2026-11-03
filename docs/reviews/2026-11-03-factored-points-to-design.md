# Review: exact factored points-to design (bp-fj1)

Subject: `docs/design/factored-points-to.md` at feaa972 (rung4-plugin HEAD at review start: 9240920).
Reviewer: Claude Opus 5.5 (opposite model; design author gpt-6.1-sol, commit feaa972). 2026-11-03.

**Verdict: REVISE.** The design's frame is right: K bounds only INT atoms, there is no widening on the
default path, resource exhaustion is loud, and the bennett-4ht scope is kept open. Implementation
may start only after the three P1 changes below. Separately, the review found a pre-existing P0 in
the explicit engine (bp-6rz). The design names that engine as its oracle.

## What was checked

- Read: the design; dialect §5.1–5.2 (PT2, PT6–PT8) and errata-0.2.12 5u3; the council
  plugin-bpfj1-2026-11-03 report; the ipp review and bp-2e7; `src/Analysis.cpp` (`canonical()`,
  `settle()`, the `EarlyChainClose` gates, the phi orbit closure, `overlaps()`, `store()`, `loadPair()`).
- Probes: LLVM 18 plugin builds of feaa972 (`new`) and f46548a (`old`) from `.tmp/sonnet-rev-ipp`, run as
  `opt-18 -passes=bennett -bennett-dialect=0.2.10 -bennett-analysis-only`, headless, timeout 60–90 s.
  The probe files are in `.tmp/opus-rev-fpt/probe/`, and the two key programs are inlined below.

## Answers

1. **Exactness.** PT2, PT7 and PT8 as written denote the spec rules. INT K is pointwise. Because
   K(A∪B) = K(K(A)∪K(B)), the granularity of memory-level K cannot be observed as long as K is applied
   to every SSA AV, which the design does. 5u3 acceleration is the exact least closure: in Z/2^W the
   generated monoid equals the generated subgroup gcd(2^W, …)·Z, and every such subgroup is a
   power-of-two residue, so it can be represented. **Fails on residue memory semantics (P1-1, on top of
   P0-A).**
2. **Least fixpoint.** The argument "every step is a reference step, and the stable state is a fixpoint"
   is valid for monotone transfers. Monotonicity of image and zero-extent rebuilds is asserted, not
   proved (P2). Equality with the reference can be checked on rungs 1–3 only where the explicit engine
   terminates. **The 64-bit acceleration has no independent oracle (P1-3).**
3. **Complexity honesty.** OK. §5 labels its figures illustrative and NON-REFERENCE and states no
   polynomial bound. §7 says exhaustion is reported as an unfinished build, never as top, a rejection
   or a fault.
4. **bennett-4ht.** OK. §9 takes the device closure plus the boundary host functions with PT11 seeds,
   keys per root context, and requires no certificates for native-only code. No lock-out found.
5. **Test plan.** The B1 and B2 witnesses are hand-derived (good). The differential steps use the
   explicit engine as the truth, so they pass an engine that copies P0-A. **P1-3.**
6. **bp-2e7.** The design accelerates `mem.ll` and `call.ll` exactly: the store and load addresses
   are outside the SCC and the edges are pure +8 translations. **It does not accelerate
   address-dependent memory recurrences (P1-2).** Neither case involves a hidden widening.

## P0 (existing code, the design's oracle)

**P0-A — bp-6rz. `loadPair()` residue-slot rule rejects a valid program.** In a residue slot
(X, r mod s, bytes) where s < bytes, every load is classed as `partial`, giving top plus ROOTs. The
identical-interval member that PT6 copies whole is never used, so explicit PTR atoms are lost.

```llvm
@g = internal global [64 x i8] zeroinitializer
@hc = internal global ptr null
; %h = qalloc; store %h -> @hc
loop: %p = phi [@g],[%q]; %i = phi [0],[%i1]; store ptr @hc, ptr %p; %q = gep i8 %p, 4
      %i1 = add %i,1; br (%i1 <u 2) loop, exit      ; concrete stores at 0 and 4
exit: %x = load ptr, (@g+4); %hh = load ptr, %x; gate %hh; gate %hh; qfree %h
```

The concrete run reads `@hc` back and the program is valid. Both `new` and `old` exit with rc=1,
`BD-E-HANDLE-UNTRACKED §6.2`. The same stores at explicit offsets 0, 4 and 8 are accepted, with
AV(%x) = {PTR(@hc,0)}, top and AV(%hh) = {ROOT(%h)}, top. Because the larger represented set gives the
smaller result, the explicit engine depends on its representation, and the rejection is a narrowing.

## P1 (design)

**P1-1 — bp-9g8. §2 and §3 PT6 classification semantics are ambiguous, and the ambiguity changes the
verdict.** §2 keeps "the reference's singleton/residue/`*` semantics" for location descriptors but
defines region nodes as sets of member interval starts. The two disagree for the program above.
5u3 acceleration produces exactly these residue forms, so an engine that matches the oracle rejects a
valid program. *Required:* state that PT6, PT7 and PT8 classify over the represented member intervals,
independent of representation and schedule (council suggestion 5); fix bp-6rz before the explicit
engine serves as an oracle; and pin this program with the hand-derived expectation: accept, with
PTR(@hc,0) ∈ AV(%x).

**P1-2 — bp-eiq. §4 does not cover the address-dependent memory recurrence.**

```llvm
loop: %p = phi ptr [@g, %entry], [%nx, %loop]
      %slot = gep i8 %p, 8 ; %next = gep i8 %p, 16
      store ptr %next, ptr %slot ; %nx = load ptr, ptr %slot ; br ...
```

The store and load addresses are SCC values. §4's precondition (fixed vertex-to-vertex
displacements) therefore fails, and the fallback, ordinary semi-naive iteration, adds one offset per
round, about 2^60 rounds. The current default plugin fails on this program (rc=1, `PT7 budget
exhausted at AV(%slot)`, 30 s). The exact answer is the coset (@g, 0 mod 16) plus the PT2 EXT/top
alternatives and the PT6 zero-image alternative. 5u3's memory clause applies because the storage
interval and width are preserved. Arena and free-list initialisers have this shape, and they are on
the SQLite path. *Required:* specify the SCC closure at the relation level (the translation o→o+16
composed through slot o+8 on one object coordinate), or another proved exact relation closure. Pin
this program, and say that bp-2e7 is otherwise only partly covered.

**P1-3 — bp-m7h. The differential tests cannot catch an engine that is wrong in the same way as the
oracle, and the 64-bit case has no oracle.** Steps 3, 6 and 8 of §8 trust the explicit engine (see
P0-A), and step 6 compares acceleration only on small domains. *Required:* hand-derived spec
expectations, never engine output, for the bp-2e7 `mem`, `call`, `phi` and P1-2 programs at W=64.
For example, `mem.ll` should give AV(%r) = {(@g, 0 mod 8), (EXT,`*`)}, top. Also add p:16/i:16
DataLayout variants checked against unaccelerated explicit iteration, and an equivalence test for the
P0-A program between its residue and explicit forms.

## P2 (bp-ubk)

- §4: state monotonicity in the abstract order as a lemma covering the image-classification and
  zero-extent rebuilds. The least-fixpoint argument depends on it, and the code has a shrink-rebuild
  path.
- §4: GEP acceleration with I(a) < P(a) is left at "may be necessary". The current reference closes
  only when pw == iw.
- §7: budgets are given in bytes only. Time exhaustion, as with the current `AnalysisMilliseconds`,
  must report an unfinished build in the same way.
- §2: the per-slot K machinery cannot be observed (K(A∪B) = K(K(A)∪K(B))), so it could be simplified.
  Its tests do not detect anything unless a load unions the slots.
- §8.8: wherever the explicit engine exhausts its budget on rungs 1–3, there is no baseline. Name that
  case and use small-width variants instead.
- The status line asks for a "Sol xhigh" review, but policy rule 2 makes this the opposite-model
  Claude review.
