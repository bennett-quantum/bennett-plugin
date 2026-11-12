"""Generate pointer-walking array loops of length N.

Variants independently choose GEP versus uintptr_t arithmetic and bounds.
Literal bounds are supplied by main; global bounds are reduced to 0..N.
The array's volatile elements prevent replacement with a closed-form sum.
Loop unrolling, vectorization and interleaving are explicitly disabled.
N=1 can still simplify to a single element access; inspect the emitted IR.
"""
from common import options, emit
n, v = options('inbounds_const')
parts = [f'volatile unsigned data[{n}] = {{ 1 }};',
         f'volatile size_t bound = {n};',
         'static NO unsigned walk(size_t count) { unsigned sum = seed;']
if v.startswith('integer'):
    parts += ['uintptr_t p = (uintptr_t)data;',
              '#pragma clang loop unroll(disable) vectorize(disable) interleave(disable)',
              'for (size_t i=0; i<count; ++i, p+=sizeof(unsigned))',
              'sum += *(volatile unsigned *)p;']
else:
    parts += ['volatile unsigned *p = data;',
              '#pragma clang loop unroll(disable) vectorize(disable) interleave(disable)',
              'for (size_t i=0; i<count; ++i, ++p) sum += *p;']
parts += ['return sum; }']
bound = str(n) if v.endswith('const') else f'(bound % {n+1})'
parts += [f'int main(void) {{ unsigned x = walk({bound}); sink=x; return x&255; }}']
emit(parts)
