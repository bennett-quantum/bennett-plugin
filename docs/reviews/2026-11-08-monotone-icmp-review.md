# Monotone scalar ICmp and allocation images — evidence-first review, round 1

- Reviewed head: `4bd5f27209d1912bb93f5904fd1a91e00dd6ac78`, branch `job/s2-9cy`.
- Base: `3d3519c76800fe2622b2b529b754564c1b15b6d8`; commits `0381d80`, `180c999`, `1d6b682`, `4bd5f27`.
- Reviewer: gpt-6.1-sol. Evidence completed: 2026-11-08T12:53:11Z.
- Instructions: assigned brief, COMMON.md, T3CHILD.md, CLAUDE.md, and all three binding orchestrator/advisor additions. Review only; no source edits, bd writes, full gate, or follow-on work.
- Worktree: `/home/tobias/Projects/bennett-workspace/bennett-plugin-job-s2-9cy`. Receipts below are relative to `.tmp/s2-9cy-review/` unless prefixed with the author's `.tmp/s2-9cy/`.

**Disposition: REVISE.** All six inherited reports still change represented facts under non-entry basic-block reversal at `4bd5f27`. Under the explicit ruling, 9cy does **not** discharge gai-fix round 2, and **nothing on this stack lands today**. The local bottom repair and allocation-extent algebra are correct, but the complete scalar transfer is still non-monotone. The requested concrete-unreachability premise also remains unproved for sampled standalone-unit tightenings.

## Scope and exact diff inventory

`git diff --stat 3d3519c..4bd5f27`:

```text
 docs/quality.md            |   9 +-
 src/Analysis.cpp           |  33 +++---
 tests/analysis_monotone.py | 247 +++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 274 insertions(+), 15 deletions(-)
```

The allocation/initial-image implementation changes **only `src/Analysis.cpp`**; the other files are its owned regression driver and quality baseline rows. There is no change to Memory.cpp, Scalar.cpp, Normalise.cpp, runtime bodies, dialect pins, allowances, or allocation lowering. The additional allocation transfer is within the implementer's explicit grant to audit/fix other bottom special cases, and has independent red evidence. It is not a separate scope finding.

## Commands actually re-run

All commands ran headlessly with `TMPDIR=<worktree>/.tmp/s2-9cy-review/tmp`. Reviewer runners use the read-only s2-par `guard.py` and its cited Spiral class table (moderate class, UNKNOWN=124), rebinding its only writable root to this review directory. Each invoked process retains expanded argv, stdout/stderr, wall/CPU and guard receipts. Corpus replay width is derived from the census machine profile, reserving 16 GiB and eight CPUs for other jobs; `machine.json` records the observed inputs. No gate ran.

From the assigned worktree:

```sh
python3 -B .tmp/s2-9cy-review/focused.py
python3 -B .tmp/s2-9cy-review/orders.py
python3 -B .tmp/s2-9cy-review/impact.py
python3 -B .tmp/s2-9cy-review/native-witnesses.py
python3 -B .tmp/s2-9cy-review/sample.py
python3 -B .tmp/s2-9cy-review/audit-receipts.py
python3 -B .tmp/s2-9cy-review/replay.py
python3 -B scripts/quality.py --check
git diff --check
```

`focused.py` actually invokes `python3 -B tests/analysis_monotone.py --major M --plugin SO --artifacts REVIEW/monotone-MODE` for M=18,23 and both matching-major base/head SOs, plus `analysis_convergence.py` and `analysis_pointer_closure.py` at the head. Results:

| Check | LLVM18 | LLVM23 |
|---|---|---|
| Monotone regression at base | exit 1, **15 failing assertions**, 25 runs | same |
| Monotone regression at head | exit 0, **25/25 runs**, no failures | same |
| gai convergence | **3 rounds / 72 dispatches**, 46 transfers, 736 joins | same |
| strcmp convergence | **2 / 44** | same |
| Pointer closure fixtures | **10/10**, exit 0 | same |

Red quotes, retained in `focused/monotone-base-18/stdout` and its major-23 companion: `FAIL growth-left-bottom`, `FAIL monotone-left-one`, and `FAIL function-order` with results `[{0}, {0,1}]`. Allocation malloc/calloc-size, bottom-count/TOP-size, and the unseeded cycle independently fail on base. The frozen thread CPU clock isolates these deterministic work tests; it is not a production allowance change. Quality baseline and whitespace checks pass.

**Full focused corpus replay:** `replay-summary.json` and `replay-results.json` record **2,544/2,544 paired cases**, all 5,088 executions exit 0. Full reports are byte-identical in **2,315/2,544** pairs; complete AV maps agree in **2,374**, leaving the claimed **170 cases / 468 changed values**. This is not a blanket byte-equality pass. Saved identity/source/SO hashes and all 309 impact input hashes also match (`receipt-audit.json`).

**Private serial/Jacobi replay:** the 332 exact manifest contexts were rerun using the author's existing private 2319890-based prototype binaries with only its ICmp/extent repairs, not a rebuild of the full `4bd5f27` analysis. Result: **330/332 literal AV maps**, **68/332 literal full reports**, but **332/332 represented AV sets** agree after independent exact pointer-union containment. Both residual `atexit.c` cases contain six redundant point/coset differences: e.g. `PTR(@builtin,8,0)` and `PTR(@builtin,264,0)` are already in `PTR(@builtin,8,8)`; 8,264,520,256,512,34359738368,34359738624 are all 0 mod 8. Thus the author's 330 figure is honest as a literal comparison; these two receipts do not establish a remaining semantic Jacobi discrepancy. This does not resolve the full-head block-order failures below or close bead 41p.

## Pinned contract and transfer derivation

Source of truth: dialect **0.2.13**, gate pin `1c29c8d731228b67902c3fa72e410e1bb71d16b4`, `spec/Bennett-Dialect-Spec.md`.

§5.2: “The analysis is the least fixpoint of the following rules over AV.” PT5: “on finite `INT` sets, every LLVM integer operation, cast and `icmp` is evaluated elementwise”. Therefore the finite comparison image is `{compare(x,y) | x∈X,y∈Y}`. An empty factor has no pairs and no Boolean result. Here bottom means `top=false` and no atoms; TOP is not bottom.

| Operands | Required image / code assessment |
|---|---|
| bottom / bottom | bottom; new early return emits no fact |
| bottom / known, known / bottom | bottom; new early return is exact |
| bottom / TOP, TOP / bottom | bottom; new guard runs before TOP fallback |
| nonempty finite INT / nonempty finite INT | unchanged elementwise APInt predicate evaluation |
| nonbottom numeric TOP / known, known / TOP, TOP / TOP | unchanged conservative Boolean fallback `{0,1}`; no new coarsening |
| explicit pointer provenance mixed with TOP | **still non-monotone**; the guard does not address this combination (finding 1) |

Thus replacing the empty-product Boolean default introduces neither widening nor rejection. It corrects that transfer domain without proving global monotonicity. Select/phi/freeze union value operands (PT3), casts map actual atoms (PT4), and finite arithmetic maps Cartesian products (PT5); the added audit companions cover these. This is not an exhaustive proof of unrelated nonbottom/TOP cases.

For allocation, §5.2 says: “represent every extent whose initial contents are zero under §§17.1/17.3 as a zero-byte initial image” and “represent a nonconstant extent symbolically over its possible allocated bytes.” PT1 independently seeds allocation-site identity `(X,0)`. PT6 includes zero only for a possibly valid read wholly contained in that initial extent, unioning later stores.

Let `E(bottom)=0`, `E(finite)=max(unsigned sizes)` and `E(TOP)=UINT64_MAX`. For malloc, the union of possible initial prefixes is the prefix of extent E. For calloc it is the saturating product `E(count)*E(size)`. Finite maxima, nonnegative product, saturation, and prefix inclusion are monotone. Bottom in either calloc factor produces extent zero even when the other is TOP. Subsequent arrival of size one can therefore add the one-byte image without retaining a speculative whole-address-space image. Site identity remains independent of this image, as PT1 requires.

The brief's “malloc undefined image” premise does **not** match this pinned materialised memory model. §17.1 explicitly says: “shadow-stack frames and heap allocations are zero-filled in both builds; globals hold their initialisers.” Both malloc and calloc therefore seed zero possibilities here. Ordinary source-C malloc semantics are not the materialised allocator's initial-image contract. Zero-sized requested payloads supply no accessible payload byte (§17.1); the allocator's max(n,1) history charge does not justify an extra initial load fact. The new extent tests agree with these rules. Their byte-eight read tests absence of an initial-image fact, not successful concrete execution of an out-of-bounds read.

## Changed-value sample and concrete-witness requirement

`sample.py` freshly reanalysed the three named corpus units on both majors, with both plugins, in original, reversed-function, renamed-control and reversed-block order. All represented AVs agree across these orders for each plugin (`sample-reruns.json`). `sample-classification.json` records **22 individually identified changed AVs**, all strict subsets, including six AVs from the published `getenv` cells. This covers finite comparisons, bottom comparisons, select, zext and load propagation.

Classification follows the binding definitions: **a** requires a disqualified old order/not-fixpoint oracle; **b** requires both fixpoints plus a sound new subset; **c** is unresolved and P1. The serial synthetic producer/consumer and no-seed-cycle witnesses establish **a** for the defective old comparison mechanism. Mere whole-unit order agreement does not establish **b**, and a finite operand oracle evaluated from the new report is not a proof that the operand covers concrete execution.

For the 22 corpus samples, the required exclusion proof cannot be asserted. Native `clang -O0` executions of the actual census function IR compiled at O0, augmented only with observation stores and explicit valid external bindings, observe the excluded values below. Clearenv starts with a valid nonnull environment array; getenv has `X=Y`, query `X`, and exact helper results for that query; tfind receives a valid node/root and a comparator returning 1. Each observer is initially set to the opposite expected value, and main returns 0 only after every required observation matches. Both-major compile and execution receipts are in `native-witnesses.json`; all six executions exit 0.

These are **completed external contexts**, not assertions that an incomplete standalone module is a complete pinned program. They show precisely why its empty external slots/no local comparator candidates cannot serve as an unqualified concrete-unreachability witness. They do not refute the local empty-Cartesian-product algebra. Per the explicit unwitnessed-tightening rule, the concrete classification remains **c/P1**, rather than accepting 468 order-equality flags as soundness proofs. No sample is claimed b.

`B={0,1}`; `⊥` means no represented value. Each row has its own native observation; the shared receipt executes all observations for that function/major.

| # | Source/function | LLVM | Value | Base → head | Executed excluded value | Class / receipt |
|---:|---|---:|---|---|---|---|
| 1 | `src/env/clearenv.c` / `clearenv` | 18 | `%2` | {0,1} → {1} | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/clearenv.c/receipt.json) |
| 2 | `src/env/clearenv.c` / `clearenv` | 18 | `%5` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/clearenv.c/receipt.json) |
| 3 | `src/env/clearenv.c` / `clearenv` | 18 | `%11` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/clearenv.c/receipt.json) |
| 4 | `src/env/getenv.c` / `getenv` | 18 | `%12` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/getenv.c/receipt.json) |
| 5 | `src/env/getenv.c` / `getenv` | 18 | `%13` | {0,1} → {0} | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/getenv.c/receipt.json) |
| 6 | `src/env/getenv.c` / `getenv` | 18 | `%16` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/env/getenv.c/receipt.json) |
| 7 | `src/search/tfind.c` / `tfind` | 18 | `%12` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/search/tfind.c/receipt.json) |
| 8 | `src/search/tfind.c` / `tfind` | 18 | `%14` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/search/tfind.c/receipt.json) |
| 9 | `src/search/tfind.c` / `tfind` | 18 | `%15` | {0,1} → ⊥ | `1` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/search/tfind.c/receipt.json) |
| 10 | `src/search/tfind.c` / `tfind` | 18 | `%17` | TOP → ⊥ | `null` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/search/tfind.c/receipt.json) |
| 11 | `src/search/tfind.c` / `tfind` | 18 | `%18` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/18/src/search/tfind.c/receipt.json) |
| 12 | `src/env/clearenv.c` / `clearenv` | 23 | `%2` | {0,1} → {1} | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/clearenv.c/receipt.json) |
| 13 | `src/env/clearenv.c` / `clearenv` | 23 | `%5` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/clearenv.c/receipt.json) |
| 14 | `src/env/clearenv.c` / `clearenv` | 23 | `%11` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/clearenv.c/receipt.json) |
| 15 | `src/env/getenv.c` / `getenv` | 23 | `%12` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/getenv.c/receipt.json) |
| 16 | `src/env/getenv.c` / `getenv` | 23 | `%13` | {0,1} → {0} | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/getenv.c/receipt.json) |
| 17 | `src/env/getenv.c` / `getenv` | 23 | `%16` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/env/getenv.c/receipt.json) |
| 18 | `src/search/tfind.c` / `tfind` | 23 | `%12` | {0,1} → ⊥ | `false` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/search/tfind.c/receipt.json) |
| 19 | `src/search/tfind.c` / `tfind` | 23 | `%15` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/search/tfind.c/receipt.json) |
| 20 | `src/search/tfind.c` / `tfind` | 23 | `%16` | {0,1} → ⊥ | `1` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/search/tfind.c/receipt.json) |
| 21 | `src/search/tfind.c` / `tfind` | 23 | `%18` | TOP → ⊥ | `null` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/search/tfind.c/receipt.json) |
| 22 | `src/search/tfind.c` / `tfind` | 23 | `%19` | {0,1} → ⊥ | `true` | c / [receipt](../../.tmp/s2-9cy-review/native-execute-v2/23/src/search/tfind.c/receipt.json) |

For tfind's pointer observation, null is an actual reachable pointer value and is absent from bottom. The driver does not infer pointer reachability from a printed symbolic atom. The initial LLVM23 scratch driver lacked an explicit node type after LLVM had erased it from the original; that compile failure is preserved under `native-compile/`. The corrected `native-v2` driver adds that driver-only type and both majors pass. No product workaround or test weakening occurred.

## Inherited gai-fix check — mandatory 36-cell matrix

The read-only gai reviewer harness supplies `original.ll`, `reversed.ll`, `named.ll`, and `reversed-blocks.ll`; its pure `audit.compare` checks represented facts, including exact pointer-coset containment, with TOP absorbing numerical INT facts while retaining explicit provenance. `orders.py` reruns **all 36 requested cells**, plus 12 independent naming controls. Every cell exits 0. All naming-only controls preserve represented sets. Basic-block reversal preserves the entry block and changes only the enumeration of remaining blocks. Numeric names are restored only in report comparison.

Each cell links its own argv/wall/CPU/guard receipt. “different(n)” counts semantically changed AVs against the original order of the **same plugin**. Cosmetic atom order and redundant coset members are excluded. Base is `3d3519c`, head is `4bd5f27`.

| Report | Base original | Base function-reversed | Base block-reversed | Head original | Head function-reversed | Head block-reversed |
|---|---|---|---|---|---|---|
| `src/malloc/mallocng/malloc.c` (LLVM18) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/base-functions/receipt.json) | [**different(4)**](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/head-functions/receipt.json) | [**different(4)**](../../.tmp/s2-9cy-review/orders/18/src/malloc/mallocng/malloc.c/head-blocks/receipt.json) |
| `src/malloc/mallocng/malloc.c` (LLVM23) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/base-functions/receipt.json) | [**different(4)**](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/head-functions/receipt.json) | [**different(4)**](../../.tmp/s2-9cy-review/orders/23/src/malloc/mallocng/malloc.c/head-blocks/receipt.json) |
| `src/malloc/oldmalloc/malloc.c` (LLVM18) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/base-functions/receipt.json) | [**different(2)**](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/head-functions/receipt.json) | [**different(2)**](../../.tmp/s2-9cy-review/orders/18/src/malloc/oldmalloc/malloc.c/head-blocks/receipt.json) |
| `src/malloc/oldmalloc/malloc.c` (LLVM23) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/base-functions/receipt.json) | [**different(2)**](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/head-functions/receipt.json) | [**different(2)**](../../.tmp/s2-9cy-review/orders/23/src/malloc/oldmalloc/malloc.c/head-blocks/receipt.json) |
| `src/regex/regexec.c` (LLVM18) | [equal](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/base-functions/receipt.json) | [**different(5)**](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/head-functions/receipt.json) | [**different(5)**](../../.tmp/s2-9cy-review/orders/18/src/regex/regexec.c/head-blocks/receipt.json) |
| `src/regex/regexec.c` (LLVM23) | [equal](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/base-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/base-functions/receipt.json) | [**different(5)**](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/base-blocks/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/head-original/receipt.json) | [equal](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/head-functions/receipt.json) | [**different(5)**](../../.tmp/s2-9cy-review/orders/23/src/regex/regexec.c/head-blocks/receipt.json) |

`order-matrix.json` retains every changed AV. At the head:

- mallocng: `alloc_slot` comparisons %258/%301 (18), %256/%299 (23), their select and downstream arithmetic differ: **4/4** changed AVs.
- oldmalloc: `__bin_chunk`'s `and i64 ..., -4096` and its inttoptr differ: %296/%302 (18), %295/%301 (23), **2/2** changed AVs.
- regexec: %996 (18)/%1014 (23), `and ...,7`, changes between `{0,…,7}` and TOP with pointer provenance. Its arithmetic descendants and comparison %1162 (18)/%1217 (23) differ: **5/5** changed AVs. The comparison changes from TOP plus object/EXT provenance to `{0,1}` under reversal.

**Responsible transfers and executed witnesses.** The scalar non-add/sub pointer path at Analysis.cpp:2002 emits a conservative pointer result only if the other operand's atom list is nonempty. Growing that operand from `{INT(0)}` to TOP with no atoms removes the pointer image. The ICmp fallback at :2083 then resets TOP and emits `{0,1}` when no atoms were emitted. The unchanged TOP-mask branch at :1973 also discards explicit pointer provenance when TOP appears: the pointer-only mask emits TOP plus object/EXT; the larger pointer-plus-TOP input emits only integers 0…15. That is bead **bennett-plugin-4zi**, reproduced again in `top-mask-witness.json`, four successful head executions. These two mechanisms account for the direct compare and mask failures above; PT3/PT4/arithmetic propagate them.

The predecessor's minimal ICmp loop was freshly re-executed at the head on both majors (`icmp/{18,23}/{forward,back-first}/receipt.json`). It has an entry `x=ptrtoint @a`, loop `y=phi [0,entry],[unknown(),back]`, and `c=icmp eq x,y`. Move only back before loop. Both orders end with identical operands `x=PTR(@a,0)` and `y=TOP`, but forward gives `c=TOP+PTR(@a,*)+PTR(EXT,*)`, back-first gives `c={0,1}`. No bottom operand is present in the final comparison. This independently disproves global transfer monotonicity and the claimed order-independent least fixpoint. Block reversal is the standard required test for future least-fixpoint claims; this review makes no whole-head independence claim from function reversal alone.

## Published impact and dialect-pin faithfulness

`impact.py` reran the required three published contexts on matching-major base/head plugins; all six executions exit 0, every input SHA256 matches, and both raw AV maps match the author's corresponding saved report (`impact-reruns.json`).

| Published context | Base/head exits | Semantic AV changes | Fresh receipts |
|---|---|---:|---|
| rung-1 C/18/r1_sat_add pipeline | 0 / 0 | 1 (module's r1_gcd %13, B→bottom) | `impact/1/{base,head}/receipt.json` |
| runtimes llvm18/native-support.bc | 0 / 0 | 36 | `impact/25/{base,head}/receipt.json` |
| published musl thread/__lock.c, LLVM18 | 0 / 0 | 15 | `impact/226/{base,head}/receipt.json` |

The 309-context saved table is honest **as analysis-only evidence**: base/head has zero exit differences, and report verdict facts agree wherever both reports exist; **56 contexts / 197 semantic AVs** change, with **57 contexts / 201 printed changes** when the extra redundant b71 representation is counted. Category counts are rung-1 20/16 changed, rung-2 2/0, runtimes 12/2, arith 2/0, published-musl 250/36, b71 22/2 semantic, spiral-parity 1/0. Twelve historical 2319890/head exit changes are inherited from gai acceleration (4 published-musl, 8 b71). The author's missing main-health directory and allowance-stopped analyses remain limitations; neither a missing/convergence-failed value nor an UNKNOWN is a successful equality observation. This review does not re-run all 309 production contexts or claim production artifact-byte equality.

**Executed dialect receipt, not an assertion:** for the same rung-1 LLVM18 r1_sat_add context, `dialect/original/receipt.json` executes the ORIGINAL published dialect **0.2.10** pipeline, including its original `BENNETT_ARITH_BITCODE` environment and all oracle/shape/stack/ISA arguments. Only the report and output destinations are redirected to owned scratch. The original existing rung1 plugin at `bennett-conformance/.tmp/rung1-bennett-plugin-157d4bd1fab98afed8579b2367f26d1d742b0173/build/libbennett-plugin-18.so` runs successfully, exit 0, and its **complete AV map equals the author's adapted 0.2.13 base report** (`.tmp/s2-9cy/impact/001/base/report.json`). A second run adding only analysis-only also exits 0 and has the same AVs. Exact original/expanded argv, environment, binary hash and comparisons are in `dialect-faithfulness.json`. The requested rung2 same-commit binaries were also found, but no fallback was needed. This proves faithfulness for the requested one context, not all dialect-version changes.

The author's current-plugin adaptation removes old plugin/report/output options, inserts analysis-only and required dialect 0.2.13, and retains ISA, oracle, shape, stack and input. Both current binaries enforce 0.2.13 in `checkVersion` (BennettPlugin.cpp:266); retaining 0.2.10 would fail before analysis. Original argv/environment are retained as evidence. The sample execution above is the independent check of the version substitution.

## Oscillation

The argument is correct for the stored state of this defect. `Analysis::step` ends in `values[&i].merge(a)` (:2089), not assignment; `bind`, parameter/field propagation and memory updates similarly union their facts. `AV::merge` (:254) is inflationary in represented facts: TOP absorbs INTs, exact pointer cosets absorb only their members, and initial-image extent replacement only extends the represented zero prefix. Thus the non-monotone **raw** ICmp image can shrink, while its persistent joined value retains earlier spurious facts. It cannot alternate its stored Boolean set back and forth. Join-only updates do not imply schedule independence for non-monotone transfers, nor prove termination for every other recurrence.

Fresh no-seed cycle receipts (`monotone-{base,head}/{18,23}/unseeded-cycle.json`) reproduce base **3 rounds / 18 dispatches**, spurious `{0,1}`, versus head **1 / 6**, true bottom. The absence of a source seed justifies the latter abstract least solution. These work counts and the executed witnesses support the scoped no-oscillation statement without claiming that existing allowance stops are solved.

## Numbered findings

1. **P1 — all six inherited reports remain order-dependent on `4bd5f27`; the stack cannot land under the explicit advisor ruling.** The 36-cell matrix and naming controls isolate semantically different outputs under block enumeration alone. Both the scalar ICmp TOP/provenance interaction and TOP/mask provenance loss remain non-monotone. Existing related beads: **bennett-plugin-usz**, **bennett-plugin-9cy**, **bennett-plugin-4zi**. The new bottom guard is locally correct but is not gai-fix's round-2 fix. No source repair or new review round was started.

2. **P1 — the changed-value receipt does not establish the required concrete-unreachability premise for tighter standalone AVs.** All 22 freshly sampled changes are strict subsets, and order agreement holds, yet valid completed external contexts execute excluded values. Clearenv %2, for example, becomes `{1}` from a future null store in a unit with an uninitialised external __environ; the actual entry value may be nonnull, and the native witness observes false. Getenv's published cells and callback-based tfind similarly require an explicit whole-program/boundary premise. The implementer's finite comparison oracle evaluates the reported operand but does not prove that operand's concretisation. These are class c under the binding rule, rather than a claim that the empty-product repair itself should retain the old spurious Boolean. The missing context/soundness obligation must be resolved before asserting that every tightened value excludes only unreachable behaviour. No new bead was written; the orchestrator owns filing this determining finding.

No P2 scope finding or nit is added. Open 41p is not closed by this review; the fresh semantic prototype comparison is explicitly narrower than a full-head scheduler guarantee. Full gate and merge remain with the orchestrator. Review complete; stop after committing and backing up this review, with no follow-on work.

**Disposition: REVISE.**
