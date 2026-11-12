# Points-to idiom measurements

Deterministic C generators for the whole-program PT1–PT12 analysis. Each takes
`N [--variant NAME]` and prints C; `run.py` builds with the LLVM 18 musl gate
recipe and runs an externally supplied diagnostic plugin and runner. No plugin
or runtime source is changed. `main(void)`, volatile accesses and noinline
helpers retain observable work through O2/LTO O3. The index helpers in 06/12
have external integer parameters so PT11 supplies an unknown index; a volatile
global with a known initializer alone can remain a singleton in this analysis.

| Generator | Parameter / variants |
| --- | --- |
| 01_scalar | N distinct direct callees, scalar arithmetic |
| 02_objects | N struct types, volatile stack/global arrays, constant indices; `independent` accesses or `chain` unsigned value feedback |
| 03_walk | Array length N; `inbounds_const`, `inbounds_global`, `integer_const`, `integer_global`; pointer vs uintptr_t recurrence; global bound reduced to 0..N |
| 04_heap | N malloc sites linked as `list` or binary `tree`, recursive traversal |
| 05_allocator | One malloc wrapper called at N distinct sites |
| 06_table | N function pointers, bounded variable index, one indirect call |
| 07_callback | N destructor callbacks in volatile struct fields; `plain` or guarded `sentinel` (-1) |
| 08_variadic | `config`: N method structs via va_arg and a global copy; `printf`: N va_list wrappers, mutable strings and `%s` byte traversal |
| 09_copy | N copy sites between structs: `memcpy_const`, `memcpy_global`, `memmove_const`, `memmove_global`; variable size reduced to object bounds; memmove destination can alias source |
| 10_casts | N `cast` round trips with pointer arithmetic and volatile dereferences, or `subtract` pointer differences |
| 11_linkage | N retained identical pointer-taking bodies with `exported` or `static` linkage; both remain host reachable from main |
| 12_strings | N string literals, bounded variable index and byte loads |

Supply the diagnostic plugin, its unchanged runner, runtime distribution, and
arithmetic bitcode using environment variables or the equivalent flags:

```sh
export IDIOMS_PLUGIN=... IDIOMS_RUNNER=... IDIOMS_RUNTIME=... IDIOMS_ARITH=...
export LLVM18_BIN=...
PYTHONDONTWRITEBYTECODE=1 python3 tests/idioms/run.py --sizes 1 4 16 64 256
```

`--only 03_walk:integer_global 08_variadic` selects series; `--resume` reuses
completed results (only for unchanged generators, plugin, and build inputs).
`--out` defaults to `.tmp/idioms/`. Builds and measurements run serially with
nice 10 inside `bennett.slice`, with per-scope MemoryMax=2G/MemorySwapMax=0.
Every measurement uses 60000 ms, VA=CFSKIP=VANOREG=WS=1 and other runner switches
unset. DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS/BROWSER are unset;
LC_ALL=C. A readonly TMPDIR set through BASH_ENV prevents the supplied runner's
hard-coded TMPDIR override; its expected readonly warning is in runner.log.
A 180-second wall guard is an infrastructure failure, never a 60-second
analysis result. A series stops after any missing fixpoint or build failure.
CPU times, not wall times, support comparisons on the shared host.

After a matrix, export CSV/JSON and finite-size fits with:

```sh
python3 tests/idioms/ir_check.py .tmp/idioms
python3 tests/idioms/summarize.py .tmp/idioms --out .tmp/idioms
```

The fitted models use only converged points with N >= 16, and fit an intercept
plus a nonnegative scale times log2(N), N or N² (plus a constant model). A
linear fit is preferred when its RMSE is under 3% of the observed range.
These are descriptive fits, not asymptotic proofs; small CPU observations
can be below useful timer resolution, and a budget failure is censored.

Each run retains C, bitcode, postlink IR, build/runner logs, the probe's files,
an IR operation census and parsed result.json. Report all counters from the
last completed ROUND; missing FINAL means no measured fixpoint. Rounds count
completed ROUND lines; total user/system CPU comes from `/usr/bin/time -v`.
The probe's `cpu=` has only 0.1-second precision and includes process startup.
`ir_check.py OUTPUT_ROOT` checks the idioms in postlink IR and writes evidence
beside each run. N=1 array walks lose their loop and N=1 function tables become
direct calls; retain these as explicitly marked simplified baselines. Memory
copy intrinsics, casts, larger pointer recurrences and callback fields must
survive. Results are finite-size observations; extrapolated growth or rule
causality beyond explicit diagnostics must be marked as conjecture.
