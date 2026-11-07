#include <stdarg.h>
#include <stdint.h>

#ifdef NATIVE
#include <unistd.h>
void __bennett_effect_console_write(const void *p, uint64_t n) {
  if (write(1, p, n) != n) _exit(99);
}
#else
void __bennett_effect_console_write(const void *, uint64_t);
#endif

/* A vfprintf-shaped nonvariadic consumer, including its independent cursor.
 * No floating arithmetic/formatting: the argument representations must survive. */
__attribute__((noinline)) static void consume(va_list ap) {
  va_list copy;
  va_copy(copy, ap);
  for (int pass = 0; pass < 2; ++pass) {
    va_list cursor;
    va_copy(cursor, pass ? copy : ap);
    char out[9];
    out[0] = va_arg(cursor, int) == -17 ? 'i' : '!';
    out[1] = *va_arg(cursor, const char *) == 'p' ? 'p' : '!';
    out[2] = va_arg(cursor, long) == -12345678901L ? 'l' : '!';
    out[3] = va_arg(cursor, long long) == 0x123456789abcdefLL ? 'q' : '!';
    out[4] = va_arg(cursor, unsigned) == 4000000001U ? 'u' : '!';
    union { double f; uint64_t bits; } d;
    d.f = va_arg(cursor, double);
    out[5] = d.bits == UINT64_C(0x400a000000000000) ? 'd' : '!'; /* 3.25 */
    union {
      long double f;
      struct { uint64_t significand; uint16_t exponent; } bits;
    } ld;
    ld.f = va_arg(cursor, long double);
    /* x86 extended 1.5 = significand c000000000000000, exponent 3fff. */
    out[6] = ld.bits.significand == UINT64_C(0xc000000000000000) && ld.bits.exponent == 0x3fff
                 ? 'e' : '!';
    out[7] = va_arg(cursor, int) == 91 ? 'z' : '!';
    out[8] = '\n';
    __bennett_effect_console_write(out, sizeof out);
    va_end(cursor);
  }
  va_end(copy);
}

__attribute__((noinline)) static void mixed(int tag, ...) {
  va_list ap;
  va_start(ap, tag);
  consume(ap);
  va_end(ap);
}

__attribute__((noinline)) static void other(int tag, ...) {
  va_list ap;
  va_start(ap, tag);
  consume(ap);
  va_end(ap);
}

typedef void (*printer)(int, ...);
static printer volatile dispatch = mixed;

__attribute__((noinline)) static void through(printer fn) {
  fn(0, -17, "pointer", -12345678901L, 0x123456789abcdefLL, 4000000001U,
     3.25, 1.5L, 91);
}

__attribute__((noinline)) static void empty(int n, ...) {
  va_list ap;
  va_start(ap, n);
  __bennett_effect_console_write("empty", n);
  va_end(ap);
}

int main(void) {
  empty(0);
  through(dispatch);
  dispatch = other;
  through(dispatch);
  /* Reuse the caller frame only after the first consumers have returned. */
  mixed(0, -17, "pointer", -12345678901L, 0x123456789abcdefLL, 4000000001U,
        3.25, 1.5L, 91);
  return 0;
}
