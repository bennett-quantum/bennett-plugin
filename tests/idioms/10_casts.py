"""Generate N pointer/integer conversions or pointer differences.

Cast results are dereferenced through volatile lvalues to retain inttoptr.
The extra array capacity covers the wrapper's dynamic four-byte offsets.
Pointer differences use a noinline pointer selector to retain subtraction.
"""
from common import options, emit
n, v = options('cast')
parts = [f'static unsigned data[{n+4}];',
         'static NO uintptr_t obscure(uintptr_t x) { return x + (seed & 3)*sizeof(unsigned); }',
         'static NO unsigned *choose(unsigned *p) { return (seed&1) ? p : &data[0]; }',
         'int main(void) { uintptr_t x=seed;']
for i in range(n):
    if v == 'cast':
        parts += [f'uintptr_t a{i}=obscure((uintptr_t)&data[{i}]);',
                  f'unsigned *p{i}=(unsigned *)a{i}; x ^= *(volatile unsigned *)p{i};']
    else:
        parts += [f'unsigned *p{i}=choose(&data[(seed+{i}) % {n+4}]);',
                  f'x += (char *)p{i} - (char *)&data[0];']
parts += ['sink=x; return x&255; }']
emit(parts)
