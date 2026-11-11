#!/usr/bin/env python3
"""PT5 skips non-INT pairs and checks the clock on productive INT pairs."""
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
    # The clock previously expired in the useless pointer x pointer scan.
    # Skipping that scan must reach binaryPointers (or a later transfer) first.
    def invoke(threshold, case):
        report = directory / f'{case}-{threshold}.json'
        env = dict(os.environ, LD_PRELOAD=str(clock.absolute()),
                   ANALYSIS_PRODUCT_CLOCK_READS=str(threshold))
        result = run([f'/usr/lib/llvm-{args.major}/bin/opt',
                      f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                      '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                      '-bennett-analysis-budget-ms=1', f'-bennett-report={report}',
                      '-disable-output', source], env=env)
        work = json.loads(report.read_text())['analysis_work']
        inside = (result.returncode != 0 and '%difference = sub i64' in result.stderr
                  and case == 'no-ints' and work['transfer_applications'] == 4
                  and work['memory']['pointer_binary_atoms'] == 0)
        return dict(threshold=threshold, exit=result.returncode, inside=inside,
                    transfers=work['transfer_applications'],
                    pointer_atoms=work['memory']['pointer_binary_atoms'],
                    diagnostic=[line for line in result.stderr.splitlines()
                                if line.startswith('bennett:')])

    skipped = invoke(5, 'no-ints')
    (directory / 'skipped.json').write_text(json.dumps(skipped, indent=2) + '\n')
    assert skipped['pointer_atoms'] > 0 or skipped['transfers'] > 4, (
        'PT5 consumed the clock before binaryPointers despite empty INT tails', skipped)

    # Keep the clock regression on a real integer product, where every pair acts.
    source.write_text(text.replace('global i8 0', 'global i64 0').replace(
        '%x = ptrtoint ptr %p to i64', '%x = load i64, ptr %p').replace(
        '\n'.join(f'@t{i} = internal global i64 0' for i in range(count)),
        '\n'.join(f'@t{i} = internal global i64 {i}' for i in range(count))).replace(
        '@top(i64 %index) {', '@top(i64 %raw) {\n %index = and i64 %raw, 127'))
    rows = []
    matched = False
    entry_pointer_atoms = None
    for threshold in range(1, 129):
        row = invoke(threshold, 'ints')
        at_product = any('%difference = sub i64' in line for line in row['diagnostic'])
        if at_product and row['transfers'] == 4:
            entry_pointer_atoms = row['pointer_atoms']
        row['inside'] = (at_product and row['transfers'] == 5
                         and entry_pointer_atoms is not None
                         and row['pointer_atoms'] == entry_pointer_atoms)
        rows.append(row)
        (directory / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        if row['inside']:
            matched = True
            break
    assert matched, 'No allowance check fired inside the productive PT5 INT product'
    print(json.dumps(dict(major=args.major, clock_threshold=rows[-1]['threshold'], passed=True)))


if __name__ == '__main__':
    main()
