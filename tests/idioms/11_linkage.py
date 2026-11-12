"""Generate N retained pointer-taking functions with matched bodies.

Choose external or static linkage without changing the body or call pattern.
Each function reads/writes its unsigned pointer argument and reads seed.
All functions are noinline and used to retain their signatures through LTO.
Main calls all N functions directly with the same stack object.
Thus both variants are reachable from main; static does not mean unreachable.
N counts definitions and direct callers, not array elements.
The sink and return preserve the aggregate result of these accesses.
Use: python3 tests/idioms/11_linkage.py N --variant static > gen.c
"""
from common import options, emit
n, v = options('exported')
link = '' if v == 'exported' else 'static '
parts = [f'{link}KEEP unsigned access{i}(unsigned *p) {{ unsigned x=*p; *p=x+{i}+seed; return x; }}'
         for i in range(n)]
parts += ['int main(void) { unsigned value=seed, x=0;']
parts += [f'x += access{i}(&value);' for i in range(n)]
parts += ['sink=x+value; return x&255; }']
emit(parts)
