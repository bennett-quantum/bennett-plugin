"""Generate N C struct types with stack and global objects.

Each type has an unsigned array and uses literal field indices.
Widths cycle between four and ten elements to vary layout modestly.
Volatile stack stores/loads and global accesses make the objects observable.
The chain variant feeds results between objects; independent does not.
This deliberately includes flow-insensitive memory/value-set propagation.
N counts types and objects, not the length of one large dynamic array.
Use: python3 tests/idioms/02_objects.py N > gen.c
"""
from common import options, emit
n, v = options('independent')
parts = []
for i in range(n):
    parts += [f'struct S{i} {{ unsigned a[{i%7+4}]; }};',
              f'volatile struct S{i} g{i} = {{ {{ {i+1} }} }};']
parts += ['int main(void) { unsigned x = seed;']
for i in range(n):
    value = 'x' if v == 'chain' else 'seed'
    result = f'x ^= g{i}.a[3];' if v == 'chain' else f'sink = g{i}.a[3];'
    parts += [f'volatile struct S{i} s{i}; s{i}.a[2] = {value} + g{i}.a[0];',
              f'g{i}.a[3] = s{i}.a[2]; {result}']
parts += ['sink = x; return (int)(x & 255); }'] if v == 'chain' else ['return (int)(sink & 255); }']
emit(parts)
