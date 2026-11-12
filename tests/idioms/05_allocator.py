"""Generate one malloc wrapper called from N separate sites.

The wrapper reads seed to vary its allocation request by up to seven bytes.
It is noinline so the wrapper allocation site can remain shared.
Each returned allocation is null checked and accessed through volatile loads.
Every site feeds its result into the next site's stored value.
N counts callers of the wrapper, not separate malloc calls in its body.
The linked runtime's actual allocator body is part of the measured module.
This case intentionally does not free allocations; analysis is the target.
Use: python3 tests/idioms/05_allocator.py N > gen.c
"""
from common import options, emit
n, _ = options()
parts = ['static NO void *my_alloc(size_t s) { return malloc(s + (seed & 7)); }',
         'int main(void) { unsigned x=seed;']
for i in range(n):
    parts += [f'volatile unsigned *p{i}=my_alloc(sizeof(unsigned));',
              f'if (!p{i}) return 1; *p{i}=x+{i}; x ^= *p{i};']
parts += ['sink=x; return x&255; }']
emit(parts)
