"""Shared deterministic C preamble; generators write C to stdout."""
import argparse


def options(default='default'):
    p = argparse.ArgumentParser()
    p.add_argument('n', type=int)
    p.add_argument('--variant', default=default)
    a = p.parse_args()
    if a.n < 1:
        p.error('n must be positive')
    return a.n, a.variant


PRE = '''#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#define NO __attribute__((noinline))
#define KEEP __attribute__((noinline,used))
volatile unsigned seed = 1;
volatile uintptr_t sink;
'''


def emit(parts):
    print(PRE + '\n'.join(parts))
