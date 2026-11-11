#!/usr/bin/env python3
"""A controlled CPU clock interrupts non-INT Cartesian pairs inside PT5."""
import argparse
import json
import os
from pathlib import Path

from contracts import run

CLOCK = r'''
#define _GNU_SOURCE
#include <stdlib.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
int clock_gettime(clockid_t clock,struct timespec *time) {
  if(clock!=CLOCK_THREAD_CPUTIME_ID)return syscall(SYS_clock_gettime,clock,time);
  static unsigned long reads=0;
  unsigned long threshold=strtoul(getenv("ANALYSIS_PRODUCT_CLOCK_READS"),0,10);
  time->tv_sec=(++reads>threshold);time->tv_nsec=0;return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, choices=(18, 23), required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'product.ll'
    count = 128
    text = 'target datalayout = "e-p:64:64"\n'
    text += '\n'.join(f'@t{i} = internal global i8 0' for i in range(count))
    text += f'\n@table = internal constant [{count} x ptr] [' + ', '.join(
        f'ptr @t{i}' for i in range(count)) + ']\n'
    text += '''define i64 @top(i64 %index) {
 %address = getelementptr ptr, ptr @table, i64 %index
 %p = load ptr, ptr %address
 %x = ptrtoint ptr %p to i64
 %difference = sub i64 %x, %x
 ret i64 %difference
}
'''
    source.write_text(text)
    clock = directory / 'clock.so'
    built = run(['cc', '-shared', '-fPIC', '-x', 'c', '-o', clock, '-'], input=CLOCK)
    assert built.returncode == 0, built.stderr
    rows = []
    matched = False
    for threshold in range(1, 65):
        report = directory / f'{threshold}.json'
        env = dict(os.environ, LD_PRELOAD=str(clock.absolute()),
                   ANALYSIS_PRODUCT_CLOCK_READS=str(threshold))
        result = run([f'/usr/lib/llvm-{args.major}/bin/opt',
                      f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                      '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                      '-bennett-analysis-budget-ms=1', f'-bennett-report={report}',
                      '-disable-output', source], env=env)
        data = json.loads(report.read_text())
        work = data['analysis_work']
        # Four transfers have started, but binaryPointers has not started yet.
        # An expiry on the next return or at sub's entry does not meet this.
        inside = (result.returncode != 0 and '%difference = sub i64' in result.stderr
                  and work['transfer_applications'] == 4
                  and work['memory']['pointer_binary_atoms'] == 0)
        rows.append(dict(threshold=threshold, exit=result.returncode, inside=inside,
                         transfers=work['transfer_applications'],
                         pointer_atoms=work['memory']['pointer_binary_atoms'],
                         diagnostic=[s for s in result.stderr.splitlines() if s.startswith('bennett:')]))
        (directory / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        if inside:
            matched = True
            break
    assert matched, 'No allowance check fired inside the PT5 non-INT product'
    print(json.dumps(dict(major=args.major, clock_threshold=rows[-1]['threshold'], passed=True)))


if __name__ == '__main__':
    main()
