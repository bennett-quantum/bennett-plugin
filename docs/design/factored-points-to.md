# Exact factored points-to analysis

Status: DESIGN ONLY, for bp-fj1 on `rung4-plugin`. Advisor R16 adopts Option A:
keep the published dialect §5.1 and the accepted 5u3 interpretation. This note
proposes an implementation, changes no transfer rule, and contains no engine
implementation or SQLite performance result. Sol xhigh must review the design
under policy rule 5 before implementation starts. Rung 4 continues to require
unmodified SQLite, its normal vectorising pipeline, and the complete published
size ladder; the duration of this work is unknown.

The contracts are dialect §§5.1–5.4, 6.2–6.6, 7.2, 8.4, 14.2 and 16.4,
plus `spec/errata-0.2.12.md` (5u3) in bennett-dialect-spec. Implementations in
other repositories are not dependencies of this design. The
[corrected measurements](../notes/2026-11-02-bp-fj1-reference-k-evidence.md)
describe NON-REFERENCE D/F configurations, not a reference fixpoint or a lower
bound on the cost of every exact engine. bp-ipp repairs the default engine's
4096-pointer-offset widening independently of this redesign.

## 1. Semantic obligation

Let R be the explicit reference state: AV for each SSA value/lane/aggregate
path, memory slots with their storage intervals and representation widths,
initial byte images, and the induced call, ROOT and boundary relations. Let
gamma decode a symbolic state into that reference state. The obligation is
equality to the reference least fixpoint under its abstract order, including
its specified conservative fallbacks. Computing a more precise concrete
semantics instead would also change the reference result and is not this plan.

K=4096 applies only to INT atoms of each individual AV. It is neither a bound
on pointer offsets nor a bound on intervals, candidates, roots or objects.
When K is exceeded, remove that AV's INT alternatives and set its non-handle
top flag exactly as the reference does. Retain PTR, FN and ROOT alternatives.
Top does not encode a handle. A large finite pointer union never creates a
residue, EXT or top by cardinality. Extent checks, numerical uncertainty and
unknown-address alternatives arise only from the published transfers.

Every representation change must preserve finite-width address images,
storage intervals, representation widths, explicit ROOT/FN alternatives,
handle-use/escape verdicts, candidate sets, descriptor shapes and dispatch
domains. Enumeration, sharing and acceleration are choices of storage and
evaluation; they do not permit Option B bounds or Option C pruning.

## 2. Values and memory as exact relations

Use immutable, solve-scoped, interned relation nodes. A fast representation is
a union of rectangles O_j × D_j: an object set O_j and an offset set D_j.
Do not replace a general relation by its object and offset projections. For
example `{(A,0),(B,8)}` is two pairs, not `{A,B} × {0,8}`. Coalesce rectangles
only when the union is equal, such as identical offset rows shared by more
objects. Retain exceptions and holes explicitly. Group objects only when
address space, pointer/index widths, alignment, extent/image predicates and
other transfer-relevant attributes agree for the operation being evaluated.

Offset sets support singleton, bounded residue/stride and interval unions,
and finite-width symbolic predicates. A range here denotes exactly its
members; a convex hull or a gcd of an arbitrary sample is not a compression.
Use a reduced decision diagram for relations that do not remain rectangles:
finite object ids and offset bits are coordinates, and shared subgraphs
encode repeated rows. Fixed variable order, hash-consing, exact Boolean
operations and existential projection give an equality decision procedure.
Small explicit sets remain a useful leaf representation; conversion must
preserve the same denotation. Diagram ids are never semantic object ids.

An AV has a pointer relation, explicit FN and ROOT id sets, an exact INT set
with its representation width, and a non-handle top bit. Preserve address
origin distinctions used by the reference to separate numerical uncertainty
from host escape. Address space, P(a), I(a), high pointer bits and alignment
constraints are part of pointer-image operations, never inferred from an
unqualified signed 64-bit offset. Internal interval comparisons use enough
bits for endpoints and carries; only the specified address operations wrap.

Memory is a relation over logical records:

`(object, location descriptor, stored byte length, representation, atom)`

with a parallel pointwise top relation. A location descriptor retains the
reference's singleton/residue/`*` semantics and its interval interpretation;
it is not a replacement byte map. Representation includes the distinctions
required for compatible whole-value reads, not merely the byte length.
Separate records describe zero-filled initial extents and known initializer
bytes. Symbolic extents retain the reference's possible allocated ranges.
They are never silently replaced by zero or an arbitrary finite cutoff.

Factor a store into its exact destination relation and a shared payload AV.
Intern identical payloads across logical slots. Region nodes describe sets
of interval *starts with an unchanged length and representation*, not one
large interval containing all those starts. Two adjacent eight-byte stores
therefore remain two eight-byte representations, even when their payloads
are equal. This prevents a later sixteen-byte load from acquiring a whole
value that the reference does not represent. Interval shape, partial reads,
ROOT provenance and FN alternatives must survive every region operation.

K is pointwise: many slots containing one distinct INT each do not overflow
K just because their shared relation contains more than K distinct INTs in
total. Exact distinct-counting (saturated at 4097) partitions the affected
logical slots when their payloads differ. Count unions after deduplication,
including intersections of rectangles. An implementation can use a bounded
explicit INT leaf per distinct AV, or decision-diagram counting per row.
Never apply K to the whole memory relation or to an aggregate of pointer
coordinates. Top may discard INTs only at the affected reference AVs.

## 3. Transfers without product expansion

### PT2: exact address images

Lift the reference address-image operation over each relation partition.
For GEP, sign-extend/truncate sequential indices to I(a), scale and accumulate
modulo 2^I(a), and preserve pointer bits above I(a). Include every represented
base pattern allowed by DataLayout/alignment. Express the input/output bit
relation, intersect it with the current input relation, and project the
inputs; bounded residues and simple translations have cheaper exact paths.
Zero accumulated offset copies the input AV. PT4/PT5 use their own published
width/conversion/fallback rules rather than reusing full-pointer addition
for GEP. Vector lanes and aggregate paths stay separate.

Partition by object metadata before testing whether an address can leave
its object. Add EXT/top exactly where the reference requires it, retaining
original provenance for escape checks. A shared offset row can yield
different extent outcomes for different objects. Sharing the row must not
share that outcome indiscriminately. Results remain unions of rectangles
where possible, and general exact relations otherwise.

### PT7: union writes at logical intervals

For a stored lane/field at displacement d and representation rho, translate
the destination relation by the prescribed d and union its product with the
payload into memory records keyed by the original stored width. A block
O × D written with one payload requires no loop over |O|×|D|×|payload| atoms.
Overlapping writes add possibilities; they do not overwrite the flow-
insensitive state or its initial images. Differing widths and locations
remain different records, even if they contain the same atom. Changes in
shared rows notify every reader of the changed logical intervals.

### PT6: interval joins, not union of nearby values

Join load addresses with memory on object and the reference interval-overlap
predicate, retaining the load start/width and stored start/width until the
classification is complete. The join may be evaluated over diagram blocks;
do not materialise every pair just to discard its coordinates afterward.

- An identical storage interval with a compatible representation contributes
  its whole AV. Distinct stored intervals cannot be glued into that AV.
- Known immutable byte images decode the accessed bytes using DataLayout and
  the requested type. Equal decoded ranges can share a result, but this does
  not authorise reconstruction from arbitrary overlapping mutable stores.
- A load wholly contained in a possibly valid zero-filled initial extent
  contributes the zero of its load width; all overlapping store/copy
  possibilities still participate. A store never deletes that initial zero.
- Partial, spanning or otherwise inexactly represented bits contribute
  non-handle top. Preserve all overlapping ROOT alternatives and the exact
  interval facts used by §6.2's partial-handle checks. Preserve whole FN
  alternatives only where the reference whole-value rule permits them.
- EXT and an address top bit each contribute the required unknown-address
  alternative, including when the known-interval join is empty.

Project to the result AV only after these classifications, then union and
apply its INT K rule. In particular, sharing a payload between offsets 0
and 8 cannot make a handle at `[0,8)` overlap an integer at `[8,16)`.

### PT8: preserve copy correlations and fill widths

For a known copy, retain `(source object, source base, slot start, slot
length, destination object, destination base, copy length)` through the
join. For each wholly contained source slot, constrain the destination
start to `destination base + slot start - source base`, and copy the same
atom, interval length and representation. Only then project source keys.
Independent reference source/destination alternatives form their required
Cartesian product, but the slot-to-base displacement remains correlated.
Separate interval tests identify partially overlapping atoms and contribute
the prescribed top plus explicit ROOT provenance at the affected destination
interval; they never copy a whole component INT as a partial value.

Copy zero-byte initial images over the actual copied ranges, retaining
symbolic extents. Unknown offsets/lengths use precisely the reference `*`
rules, not an invented bounded range. Fill joins affected logical intervals
and repeats a known byte to *each slot's representation width*; an unknown
byte gives the specified top. Preserve interval boundaries and all initial
and previous possibilities. Memmove's flow-insensitive inclusion can form a
cycle; evaluate it to closure rather than treating an aliasing copy as inert.

PT1/PT3/PT9/PT10/PT11/PT12 consume these same AVs and memory relations.
Actual-parameter/return binding, byval copy objects, undefined-call reachability,
ROOT seeds and host boundary seeds must not enumerate or approximate a
product at their interfaces. Otherwise the cost merely moves out of PT6.

## 4. Fixpoint, SCCs and incremental evaluation

For each unaccelerated transfer t, establish
`gamma(t_symbolic(S)) = t_reference(gamma(S))`, including pointwise K and
every conservative reference fallback. Seeding must satisfy the same equality.
Exact union/intersection/difference/projection provide the relation algebra;
the obligations above specify which keys may be projected away. Equal
relation nodes give equal denotations, but pointer identity is only an
equality shortcut, never the definition of convergence across representations.

Start at the reference seeds and use a fair worklist of inclusions. Revisit
every dependent transfer when its input changes. New indirect candidates,
host/device reachability, object edges or ROOT/boundary seeds add constraints
and invalidate the corresponding dependency/SCC summaries. Schedule until
no constraint changes, then freeze verdicts and domains. Every ordinary step
is the reference step, so it stays below the reference least fixpoint. A
stable result satisfying every constraint is therefore exactly that least
fixpoint. This proof uses the reference abstract order: removal of absorbed
INT atoms after top is not removal of a represented reference possibility.

Acceleration is allowed only with an exact SCC closure proof. Apply 5u3's
pure modular-translation rule when every cyclic edge is an unfiltered fixed
displacement at one bit width W preserving a provenance/base coordinate.
Choose root-to-vertex path displacements p_v and compute
`g = gcd(2^W, {p_u + d_uv - p_v})`. A seed a at u contributes at v exactly
`a - p_u + p_v + k*g (mod 2^W)`. Keep vertex-specific paths and distinct seed
cosets; taking a gcd across unrelated finite alternatives is forbidden.
This operation replaces the internal SCC iteration by its least closure,
not by a speculative larger invariant.

For GEP, prove the same statement on the actual I(a)-bit low coordinate
with preserved high bits; splitting base-pattern partitions may be necessary.
Account separately for all reference out-of-object EXT/top contributions.
For memory SCCs, prove that complete storage intervals and representation
widths are preserved and that all PT6–PT8 read/overlap results equal those of
the represented individual slots. Keep ROOT and FN alternatives explicit.
Filtered cycles, mixed widths, partial copies or evolving candidate edges
do not qualify merely because sampled offsets look periodic. Use ordinary
exact transfers or a separately proved exact relation operation when the
preconditions fail. A failed acceleration precondition never changes precision.

Deltas are exact relation differences, not lists of enumerated pairs. Each
value and interval relation has a version; consumers join changed blocks
with their retained inputs. For a binary monotone join, include both
`deltaA join oldB` and `newA join deltaB`, deduplicating their intersection.
Retain enough keys to apply K pointwise. Repartitioning a diagram or merging
equal rows is not a semantic change and must not lose reader registrations.

Some cached *contributions* can change beyond simple growth: a constant-image
read can gain overlapping written slots, and a zero image can change its
represented extent. Invalidate and rebuild that contribution when its
classification changes, rather than only appending atoms to a stale cache.
The complete reference state still grows in the abstract order. Interning,
operation memos, reader indexes and SCC summaries need solve-scoped ownership
and bounded caches; process-global tables retaining every intermediate state
would defeat the memory goal.

Keep `-bennett-analysis-check-delta` as a full recomputation check. A symbolic
check compares incremental and full symbolic results by exact equality.
On small inputs also expand into the repaired explicit engine and compare
both differences, top bits, intervals and representations. Agreement between
two incremental configurations alone did not expose bp-ipp and is insufficient.

## 5. Cost on the observed SQLite shape

D3 recorded 2,643,733 slots, 1,210,304,346 slot-atom memberships and
138,617,196 value-atom memberships after round 2 before failing in round 3
at RSS 13.7 GB. These are partial NON-REFERENCE states. They do not establish
the corrected default's closure size or convergence cost. One sampled shape
was described as 288 objects with roughly 1,820 offsets per object; the
reported largest value after round 1 was 493,295 atoms. Those figures do not
assert an exact common offset row for every object.

For an actual uniform product, 288×1,820 is 524,160 logical pairs; its two
coordinate sets contain 2,108 entries. A translation or union of identical
rows works on the shared offset set and object set, instead of repeatedly
allocating 524,160 pairs. At 10,000 offsets, a single such rectangle denotes
2,880,000 pairs with 10,288 coordinates. These are illustrative counts,
not measurements of the proposed engine. Exceptions increase representation
size and must be retained. No objects×4096 bound is assumed.

The larger gain must come from memory: repeated stores of the same large AV
into many locations can share that payload and a location relation. A
uniform block with L locations and A payload alternatives needs O(L+A)
coordinate/payload storage instead of O(L*A) memberships, and a regular
location region can compress L further. The D3 slot memberships alone would
take about 4.84 billion bytes at four bytes per membership, before vector
capacity, slots, indexes and caches. Merely using smaller atom ids cannot
solve that duplication. PT6/PT8 must operate on shared interval blocks to
avoid recreating it as a temporary join.

Let N be live relation nodes plus explicit leaves, I the interval partition
and image metadata, and E the transfer/dependency graph. Persistent storage
is O(N+I+E), plus budgeted operation caches. Diagram Boolean apply can cost
O(N1*N2); projection and poor variable orders can cause exponential growth
in the number of coordinates. A union of many unrelated rectangles or many
different interval payloads can approach the explicit relation size. There
is no general polynomial-size guarantee, no demonstrated SQLite node bound,
and no promise that observed partial-state factoring proves completion.
Before implementation is called successful, the orchestrator must schedule
new corrected-reference measurements of both analysis passes used by
production, on LLVM 18 and 23 and the required database sizes.

## 6. Candidate sets and production dispatch

§7.2 candidates are derived from FN alternatives and the reference top
fallback over address-taken functions, followed by the specified alias/
forwarding-thunk resolution after N0. Indirect calls retain §14.2's required
LLVM function-type filter; oracle/inplace use their specified broader domain.
Do not infer a smaller candidate set from object/offset compression, and
do not prune PT9 binding by argument provenance. Cache exact function-id
bitsets indexed by the required type; their size depends on functions, not
the number of ordinary pointer pairs in a value. A million pointer atoms
does not imply a million distinct function candidates.

Retain original source function/alias address alternatives A(S), including
ones resolving to a shared candidate. Interning resolved candidate bodies
does not erase the source-address dispatch map. Compare sorted keys in the
published compare-tree order; preserve unique-invalid-candidate rejection,
multi-candidate trap bodies, coverage, and no-match behavior. No new fault,
blanket top rejection, first-N candidate limit or replacement ISA is proposed.

§8.4 shapes include the region candidate and specified kind/mode/width/size/
device fields. Compute exactly their reference value sets and products;
do not introduce correlations the flow-insensitive reference discarded, or
discard correlations it retained in representations and handle roots.
ARG `value` and `size` remain runtime classical arguments, not extra shape
specialisations. Unbounded enum fields use their published finite domains
(5 kinds, 2 modes, 4 models). Initial zero and invalid enum cases retain the
specified table/no-match behavior. ROOT alternatives determine the same
handle widths and static register environments as the explicit engine.

Store shared shape suffixes or a factored product while planning, and stream
all required shapes and source-address leaves into the existing reference
object/compare-tree construction in canonical order. Storage sharing cannot
remove required bodies or change their identity, mapping, charged execution
or dispatch domains. If C candidates and independent fields of sizes d_i
are required, output can still need C*product(d_i) shapes. Work to emit those
objects is at least proportional to that output. The note's 10^5–10^6-atom
values are not measured shape counts; measure candidates, source keys,
shapes and emitted bytes separately. A too-large output is unfinished
production with a named resource, not permission to truncate a domain.

## 7. Memory and resource bound

The operational goal is the current 14 GB job limit, not a theorem that all
reference states fit it. Express internal budgets in bytes and use the
stricter actual cgroup/address-space limit (the historical `ulimit -v` uses
KiB). Set the symbolic arena cap to at most 8,000,000,000 bytes and lower it
when resident LLVM/module/output state plus 2,000,000,000 bytes of headroom
would exceed the effective process limit. The arena budget includes live
nodes, leaves, unique tables, roots, reader indexes, caches and operation
temporaries; count allocated capacity, not only live logical nodes. Other
allocations and process peak RSS must be measured too. This is a ceiling,
not a request to reserve that memory on the shared host.

Bound apply/difference/join caches, collect unreachable solve-scoped nodes,
and stream bounded output batches. A cache miss may recompute an exact
operation; it may never substitute top. Chunk explicit fallback enumeration
and check resources inside diagram construction, projections, decoding and
output loops. An irreducible relation can exhaust the limit despite these
measures. Report an unfinished build naming the rule, value/location and
exhausted implementation resource; do not publish a completed verdict or
partial certificate and do not turn exhaustion into a source rejection or
runtime fault. bp-fj1 remains open until the required builds complete.

## 8. Validation and implementation sequence after review

1. Establish a reviewed explicit baseline with bp-ipp fixed and the
   NON-REFERENCE flag off. Keep that engine selectable as an oracle while
   introducing the symbolic representation; do not replace all transfers
   at once. Save verdicts, AVs, intervals/widths, boundary roots, candidate
   source maps, shapes and dispatch domains before comparisons.
2. Check representation algebra against enumeration on exhaustive small
   domains: holes, unequal object rows, overlapping rectangles, repeated
   INTs, mixed widths and top/ROOT/FN alternatives. Test K at 4096/4097 per
   value and per slot, including thousands of slots with one INT each.
   Equal compressed/explicit denotations must survive each operation.
3. Differentially check each PT2/PT6/PT7/PT8 transfer and completed fixpoint
   against the explicit baseline on both majors. Include small P/I widths,
   preserved high bits, differing alignments/extents, all vector lanes,
   wraparound, immutable decoding, zero images, mixed/partial/spanning
   loads, copy boundaries, unknown lengths, memmove cycles and fills of
   different widths. Preserve partial-handle failures as well as acceptance.
4. Retain council B1: 4096 and 4097 in-bounds constant-byte calls must have
   exactly their finite offsets and load `{INT(1)}`, top=false. Add larger
   factored variants beyond 4097, with holes and unequal object rows, to
   detect both widening and accidental Cartesian completion.
5. Retain sol B2's 80-byte handle/counter witness in both store orders:
   handle `[0,8)`, counter `[8,16)`, 63 byte stores at offsets 16..78,
   repeated handle store. Accept; ROOT(n) is empty,
   AV(n)={INT(0),INT(3)}, AV(next)={INT(1),INT(4)}. Also retain the council's
   handle/byte case with disjoint byte offset 8, AV(v)={INT(0),INT(1)}, no
   ROOT, and concrete return 1. These catch false contamination even if
   every original ROOT id remains present somewhere in the relation.
6. Compare SCC acceleration with unaccelerated iteration on small modular
   domains, multiple seeds/vertices and changing boundary inputs. Exercise
   filtered/mixed-width/partial-interval cycles that must refuse that
   acceleration and continue exact evaluation. Vary worklist and store
   order; the decoded least fixpoint must stay identical.
7. Run delta/full checks at each migration step, including growing objects,
   image-classification rebuilds and new indirect edges. Compare both
   directions of state difference, not only verdicts, counts or hashes.
   Existing focused suites are reference_k, analysis_edges,
   analysis_performance, reference_images and load_delta. The bp-ipp repair
   passed these on LLVM 18/23; that is not a symbolic-engine test result.
8. Differentially run complete rungs 1–3 against the explicit engine on both
   majors: compare analysis states/domains and normalized reference objects
   under identical mapping inputs, then native and reversible-machine
   execution using their published full-domain checks. Compressed storage
   must not alter handle verdicts, dispatch or observable results/costs.
9. Only after those checks, schedule the full unmodified SQLite measurements
   under the orchestrator's heavy-run limits. Record node/partition counts,
   cache and temporary peaks, RSS, time, candidates, shapes, output bytes,
   both production analysis passes and exact completion status. Compare
   any tractable extracted states with the explicit engine without treating
   extraction as rung-4 acceptance. Run the full required production ladder
   after convergence; a completed analysis alone does not close rung 4.

This job writes only the design and the independent bp-ipp repair. The
review must assess interval joins/copies, pointwise K, SCC preconditions,
exact equality and resource accounting before engine code is authorised.

## 9. Mixed fat object (bennett-4ht)

A mixed fat object keeps an ordinary native host binary and embeds ISA
objects for selected marked device roots and their complete linked direct
and indirect-candidate closures, including unmarked library callees. The
relation engine computes §5 over that closure plus the host functions that
exchange pointers/shared globals with it, with PT11's specified boundary
seeds. It cannot assume that marked source files alone contain every device
callee or that packaging necessarily makes the analysis smaller. Host-only
entry, argv/envp and libc need no device region/frame/certificate inventory.

Object ids and analysis caches are keyed by linked module/layout identity;
separate root/boundary bindings and root-relative certificate contexts must
not be merged just because static relation nodes are shared. Shared device
callees can reuse exact immutable sets while each selected root retains its
own invocation/context and certificate association. Factoring invents no
host-memory alias relation beyond the published boundary model, and does
not require native host code to become ISA code.

The explicit remaining contracts are the container-to-object/root/certificate
inventory, host/device launch bindings, budget/handle lifetime negotiation,
tape/run association, and general host-memory-by-reference address/layout,
range/liveness, aliasing, ownership/synchronisation, writeback and reversal
rules in `bennett-isa-spec/docs/notes/2026-11-02-rev2/fat-object-scope.md`.
Those are bennett-4ht obligations, not an ABI implemented here. The engine
must accept their future boundary relations without requiring whole-binary
lowering, universal host promotion or certificates for native-only code.
