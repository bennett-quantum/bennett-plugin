"""Generate N separate noinline scalar functions and N direct calls.

N counts call sites and function bodies, rather than loop iterations.
Each call consumes its predecessor's result and a volatile global load.
The unsigned arithmetic avoids signed-overflow assumptions.
The final value is stored to a volatile sink and returned modulo 256.
There are no pointer arguments or indirect calls in this case.
The common module supplies headers and the seed/sink declarations.
Use: python3 tests/idioms/01_scalar.py N > gen.c
Build and measure gen.c with run.py's LLVM 18 gate recipe.
"""
from common import options, emit

n, _ = options()
parts = [f'static NO unsigned f{i}(unsigned x) {{ return (x ^ {i+3}u) + seed; }}'
         for i in range(n)]
parts += ['int main(void) { unsigned x = seed;']
parts += [f'x = f{i}(x);' for i in range(n)]
parts += ['sink = x; return (int)(x & 255); }']
emit(parts)
