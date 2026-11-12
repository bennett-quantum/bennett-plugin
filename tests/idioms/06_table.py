"""Generate N address-taken scalar callbacks and a pointer table.

Callbacks have distinct volatile effects and distinct return arithmetic.
One noinline external helper indexes the table modulo N and calls it.
Its integer index parameter supplies PT11 uncertainty under current seeding.
Main calls the helper with the volatile seed and consumes its return.
N counts table entries and candidate function bodies, not call sites.
The one-entry case can devirtualize; inspect post-LTO IR before interpreting.
The const table isolates lookup from mutating callback-table memory.
Use: python3 tests/idioms/06_table.py N > gen.c
"""
from common import options, emit
n, _ = options()
parts = [f'static NO unsigned cb{i}(unsigned x) {{ sink=x+{i}; return seed+{i}; }}'
         for i in range(n)]
parts += ['typedef unsigned (*Fn)(unsigned);',
          f'static Fn const table[{n}] = {{'+','.join(f'cb{i}' for i in range(n))+'};',
          f'NO unsigned pick(unsigned index) {{ return table[index % {n}](seed); }}',
          'int main(void) { unsigned x=pick(seed); sink=x; return x&255; }']
emit(parts)
