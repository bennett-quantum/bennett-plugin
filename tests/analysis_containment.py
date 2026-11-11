#!/usr/bin/env python3
"""Pointer-family inclusion must not scan unrelated objects for every atom.

PT5's fixed conservative AND image retains each originating object(*), EXT and
TOP. Its stride-16 store covers a later exact store of the original pointers.
There is one containing family per target object. The lookup needs at most
2N containment tests; scanning every other object's family takes N(N+3)/2.
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
    for kind, count in product(('separate', 'repeated', 'stride'), (16, 32, 64)):
        globals_ = 'target datalayout = "e-p:64:64"\n'
        globals_ += ('\n'.join(f'@cell{i} = internal global ptr null' for i in range(count))
                     if kind == 'repeated' else '@cell = internal global ptr null') + '\n'
        globals_ += ('\n'.join(f'@t{i} = internal global i8 0' for i in range(count))
                     if kind == 'separate' else f'@data = internal global [{8 * count} x i8] zeroinitializer')
        globals_ += f'\n@targets = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr @t{i}' if kind == 'separate' else
            f'ptr getelementptr (i8, ptr @data, i64 {i * (8 if kind == "stride" else 1)})'
            for i in range(count)) + ']\n'
        if kind == 'repeated':
            globals_ += f'@destinations = internal constant [{count} x ptr] [' + ', '.join(
                f'ptr @cell{i}' for i in range(count)) + ']\n'
        body = '''
 %p = getelementptr ptr, ptr @targets, i64 %index
 %exact = load ptr, ptr %p
'''
        body += ' %outer = getelementptr i64, ptr @data, i64 %index\n' if kind == 'stride' else ''' %bits = ptrtoint ptr %exact to i64
 %wide = and i64 %bits, 0
 %outer = inttoptr i64 %wide to ptr
'''
        body += ''' %dp = getelementptr ptr, ptr @destinations, i64 %index
 %cells = load ptr, ptr %dp
 %dst = getelementptr [2 x ptr], ptr %cells, i64 %index
''' if kind == 'repeated' else ' %dst = getelementptr [2 x ptr], ptr @cell, i64 %index\n'
        body += '''
 store ptr %outer, ptr %dst
'''
        body += ' store ptr %exact, ptr ' + ('%dst' if kind == 'repeated' else '@cell') + '\n'
        body += ' %r = load ptr, ptr ' + ('@cell0' if kind == 'repeated' else '@cell') + '\n br label %exit'
        blocks = {'entry': 'br label %body', 'body': body, 'exit': 'ret ptr %r'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        for order in ('original', 'functions', 'blocks'):
            source = directory / f'{kind}-{count}-{order}.ll'
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
            source.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0, result.stderr
            data = json.loads(report.read_text())
            values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                      for v in data['values']}
            expected = ({f'PTR(@t{i},0,-1)' for i in range(count)} if kind == 'separate' else
                        {f'PTR(@data,0,{8 if kind == "stride" else -1})'}) | {'PTR(EXT,0,-1)'}
            assert values['top', '%r'] == (True, sorted(expected)), values
            domains.append(values)
            work = data['analysis_work']
            receipts.append(dict(kind=kind, count=count, order=order, argv=list(map(str, command)), work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            assert work['memory']['pointer_containment_tests'] <= 2 * count, work['memory']
        assert domains[0] == domains[1] == domains[2], (count, 'evaluation order')
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
