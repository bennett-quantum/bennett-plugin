#!/usr/bin/env python3
"""PT6 unions a pointer table without rescanning unrelated pointer atoms.

The immutable table has N distinct pointer cells, each holding its own pointee.
An unknown stride-8 index selects their full union, plus EXT/TOP for out-of-object
addresses. No pointer family from a different object can absorb a table member;
no INT survives TOP.
"""

import argparse
from itertools import product
import json
from pathlib import Path

from contracts import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--major', type=int, required=True, choices=(18, 23))
    p.add_argument('--plugin', type=Path, required=True)
    p.add_argument('--artifacts', type=Path, required=True)
    args = p.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for shared, count in product((False, True), (16, 32, 64)):
        targets = [f'getelementptr (i8, ptr @target, i64 {i})' if shared else f'@t{i}'
                   for i in range(count)]
        globals_ = 'target datalayout = "e-p:64:64"\n' + '\n'.join(
            f'@cell{i} = internal global ptr {targets[i]}' for i in range(count)) + '\n'
        globals_ += (f'@target = internal global [{count} x i8] zeroinitializer' if shared
                     else '\n'.join(f'@t{i} = internal global i8 0' for i in range(count)))
        globals_ += f'\n@table = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr @cell{i}' for i in range(count)) + ']\n'
        blocks = {'entry': 'br label %body', 'body': '''
 %p = getelementptr ptr, ptr @table, i64 %index
 %cell = load ptr, ptr %p
 %r = load ptr, ptr %cell
 br label %exit''', 'exit': 'ret ptr %r'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        for order in ('original', 'functions', 'blocks'):
            source = directory / f'{shared}-{count}-{order}.ll'
            report = source.with_suffix('.json')
            block_order = ('entry', 'exit', 'body') if order == 'blocks' else ('entry', 'body', 'exit')
            top = 'define ptr @top(i64 %index) {\n' + '\n'.join(
                b + ':\n ' + blocks[b] for b in block_order) + '\n}\n'
            source.write_text(globals_ + (top + helper if order == 'functions' else helper + top))
            command = [f'/usr/lib/llvm-{args.major}/bin/opt',
                       f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                       '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                       f'-bennett-report={report}', '-disable-output', source]
            result = run(command)
            assert result.returncode == 0, result.stderr
            source.with_suffix('.stderr').write_text(result.stderr)
            data = json.loads(report.read_text())
            values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                      for v in data['values']}
            expected = [f'PTR(@target,{i},0)' if shared else f'PTR(@t{i},0,0)' for i in range(count)]
            assert values['top', '%r'] == (True, sorted(expected)), values
            domains.append(values)
            work = data['analysis_work']
            receipts.append(dict(shared=shared, count=count, order=order,
                                 argv=list(map(str, command)), work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            # Two round scans, two loads: at most two unions into the result
            # and its SSA slot per scan, plus the individual cell images.
            # Every object has one exact pointer and no family for its peers.
            memory = work['memory']
            assert memory['merge_family_visits'] <= 8 * count + 16, memory
            assert memory['merge_top_visits'] <= 8 * count + 16, memory
        assert domains[0] == domains[1] == domains[2], (count, 'evaluation order')
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
