"""Generate a table of N immutable string-literal pointers.

An external noinline helper chooses an entry using its integer index modulo N.
Its parameter supplies an unknown index under the current PT11 seeding.
A volatile seed chooses a byte within the fixed name prefix.
The selected pointer participates in the returned uintptr_t expression.
Main stores the result to a volatile sink and returns its low byte.
N counts literals and table entries rather than executed loop iterations.
Numeric suffix length changes with N; account for literal byte storage.
The one-entry case may simplify the table while retaining the string access.
Use: python3 tests/idioms/12_strings.py N > gen.c
"""
from common import options, emit
n, _ = options()
parts = [f'static const char *const names[{n}] = {{'+
         ','.join(f'"name-{i}"' for i in range(n))+'};',
         f'NO uintptr_t lookup(unsigned index) {{ const char *p=names[index % {n}];',
         'unsigned x=(unsigned char)p[seed & 3]; return (uintptr_t)p+x; }',
         'int main(void) { uintptr_t x=lookup(seed); sink=x; return x&255; }']
emit(parts)
