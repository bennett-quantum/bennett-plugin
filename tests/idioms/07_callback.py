"""Generate N objects holding destructor callbacks and a data pointer.

The destroy helper reads volatile fields to retain the struct-load shape.
The sentinel variant adds -1 and guards the indirect call against it.
Both variants use the same callback bodies and shared unsigned data.
"""
from common import options, emit
n, v = options('plain')
parts = ['struct Obj { void (*xDel)(void *); void *p; };',
         '#define SENTINEL ((void (*)(void *))(uintptr_t)-1)']
parts += [f'static NO void del{i}(void *p) {{ sink=*(unsigned *)p + {i}; }}'
          for i in range(n)]
guard = 'if (x != SENTINEL)' if v == 'sentinel' else ''
parts += ['static NO void destroy(volatile struct Obj *o) {',
          f'void (*x)(void *)=o->xDel; {guard} x(o->p); }}',
          'int main(void) { unsigned value=seed;']
for i in range(n):
    cb = f'(seed & 1 ? del{i} : SENTINEL)' if v == 'sentinel' else f'del{i}'
    parts += [f'volatile struct Obj o{i}={{ {cb}, &value }}; destroy(&o{i});']
parts += ['return (int)(sink & 255); }']
emit(parts)
