"""Config copies callback methods via va_arg; printf uses N va_list wrappers."""
from common import options, emit
n, v = options('config')
parts = []
if v == 'config':
    parts += ['struct Methods { unsigned (*run)(void *); void *context; };',
              'static struct Methods active;',
              'static NO void config(unsigned op, ...) { va_list ap; va_start(ap,op);',
              'if (op) active=*va_arg(ap, const struct Methods *); va_end(ap); }',
              'static NO unsigned invoke(void) { return active.run(active.context); }']
    parts += [f'static NO unsigned cb{i}(void *p) {{ return *(unsigned *)p+{i}+seed; }}'
              for i in range(n)]
    parts += ['int main(void) { unsigned value=seed, x=0;']
    for i in range(n):
        parts += [f'struct Methods m{i}={{cb{i}, &value}};',
                  f'config(seed, &m{i}); x += invoke();']
else:
    parts += ['static NO unsigned format(const char *fmt, va_list ap) {',
              'unsigned sum=0; for (; *fmt; ++fmt) if (*fmt==\'s\') {',
              'const char *p=va_arg(ap,const char *); for (; *p; ++p) sum+=(unsigned char)*p;',
              '} return sum; }']
    for i in range(n):
        parts += [f'static NO unsigned wrap{i}(const char *f, ...) {{',
                  'va_list ap; va_start(ap,f); unsigned x=format(f,ap); va_end(ap); return x; }',
                  f'static char text{i}[]="item-{i}";']
    parts += ['int main(void) { unsigned x=seed;']
    parts += [f'text{i}[0]=(char)(65+(seed&15)); x+=wrap{i}("%s",text{i});'
              for i in range(n)]
parts += ['sink=x; return x&255; }']
emit(parts)
