"""Generate N struct-copy sites with pointer, integer and byte fields.

Choose memcpy or memmove, with constant or global variable byte length.
Global lengths are reduced modulo object size plus one for valid ranges.
Memmove's destination selection permits source aliasing to retain its opcode.
Each destination is consumed before the next copy site updates its source.
"""
from common import options, emit
n, v = options('memcpy_const')
op = v.split('_')[0]
parts = ['struct Block { void *p; uintptr_t x; unsigned char bytes[32]; };',
         'static struct Block src, dst;',
         'volatile size_t copy_length=sizeof(struct Block);',
         'static NO uintptr_t consume(struct Block *p) { return (uintptr_t)p->p + p->x + p->bytes[3]; }',
         'int main(void) { uintptr_t x=seed; src.p=(void *)&sink; src.x=seed; src.bytes[3]=seed;']
parts += ['struct Block *d=(seed&1) ? &dst : &src;'] if op == 'memmove' else ['struct Block *d=&dst;']
size = 'sizeof(struct Block)' if v.endswith('const') else '(copy_length % (sizeof(struct Block)+1))'
for i in range(n):
    parts += [f'src.x=x+{i}; {op}(d,&src,{size}); x ^= consume(d);']
parts += ['sink=x; return x&255; }']
emit(parts)
