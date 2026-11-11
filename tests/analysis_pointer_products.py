#!/usr/bin/env python3
"""PT5 classifies non-INT alternatives once, preserving finite displacements.

Pointer-only operands contribute their originating object(*)/EXT/TOP image;
pairing the same non-INT alternatives quadratically produces no additional
facts. Real INT alternatives must still generate every finite displacement.
Oracles below follow PT5's reference fallback and modulo-64 integer arithmetic.
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
    for kind, opcode, count in product(('same', 'separate', 'finite-left', 'finite-right', 'mixed'),
                                       ('add', 'sub'), (16, 32, 64)):
        distinct = kind in ('separate', 'mixed')
        finite = kind.startswith('finite') or kind == 'mixed'
        globals_ = 'target datalayout = "e-p:64:64"\n'
        globals_ += ('\n'.join(f'@{side}{i} = internal global [64 x i8] zeroinitializer'
                             for side in ('left', 'right') for i in range(count))
                     if distinct else f'@base = internal global [{count + 64} x i8] zeroinitializer')
        for side in ('left', 'right'):
            globals_ += f'\n@{side}Table = internal constant [{count} x ptr] [' + ', '.join(
                f'ptr getelementptr (i8, ptr @{side}{i}, i64 8)' if distinct else
                f'ptr getelementptr (i8, ptr @base, i64 {8 + i})' for i in range(count)) + ']\n'
        body = (f' %ai = and i64 %a, {count - 1}\n %bi = and i64 %b, {count - 1}\n'
                if finite else ' %ai = add i64 %a, 0\n %bi = add i64 %b, 0\n')
        body += ''' %ap = getelementptr ptr, ptr @leftTable, i64 %ai
 %bp = getelementptr ptr, ptr @rightTable, i64 %bi
 %p = load ptr, ptr %ap
 %q = load ptr, ptr %bp
 %x = ptrtoint ptr %p to i64
 %y = ptrtoint ptr %q to i64
'''
        if kind.startswith('finite'):
            body += ' %mix = select i1 true, i64 %x, i64 4\n'
            operands = '%mix, 2' if kind == 'finite-left' else '2, %mix'
        elif kind == 'mixed':
            body += ' %mix = select i1 true, i64 %y, i64 2\n'
            operands = '%x, %mix'
        else:
            operands = '%x, %y'
        body += f' %r = {opcode} i64 {operands}\n br label %exit'
        blocks = {'entry': 'br label %body', 'body': body, 'exit': 'ret i64 %r'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        precise = kind == 'finite-left' or (kind == 'finite-right' and opcode == 'add')
        if precise:
            delta = 2 if opcode == 'add' else -2
            number = 6 if opcode == 'add' else 2
            expected = (False, sorted([f'PTR(@base,{8 + i + delta},0)' for i in range(count)]
                                      + [f'INT({number})']))
        else:
            atoms = ({f'PTR(@{side}{i},0,-1)' for side in ('left', 'right') for i in range(count)}
                     if distinct else {'PTR(@base,0,-1)'}) | {'PTR(EXT,0,-1)'}
            expected = (True, sorted(atoms))
        for order in ('original', 'functions', 'blocks'):
            source = directory / f'{kind}-{opcode}-{count}-{order}.ll'
            report = source.with_suffix('.json')
            block_order = ('entry', 'exit', 'body') if order == 'blocks' else ('entry', 'body', 'exit')
            top = 'define i64 @top(i64 %a, i64 %b) {\n' + '\n'.join(
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
            assert values['top', '%r'] == expected, (kind, opcode, count, values['top', '%r'], expected)
            domains.append(values)
            work = data['analysis_work']
            receipts.append(dict(kind=kind, opcode=opcode, count=count, order=order,
                                 argv=list(map(str, command)), work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            memory = work['memory']
            assert memory['pointer_binary_pairs'] <= 2 * count, memory
            assert memory['pointer_binary_atoms'] <= 4 * count + 16, memory
            if kind == 'mixed' or precise:
                assert memory['pointer_binary_pairs'] == count, memory
        assert domains[0] == domains[1] == domains[2], (kind, opcode, count, 'evaluation order')
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
