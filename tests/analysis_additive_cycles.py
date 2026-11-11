#!/usr/bin/env python3
"""Integer copy cycles close exact finite step orbits, never non-cycles."""
import argparse
from collections import deque
import json
from pathlib import Path

from contracts import run


def orbit(width, seeds, steps, opcode, reverse=False):
    modulus = 1 << width
    reached = {x % modulus for x in seeds}
    todo = deque(reached)
    while todo:
        value = todo.popleft()
        for step in steps:
            result = (step - value if reverse else value + step if opcode == 'add' else value - step) % modulus
            if result not in reached:
                reached.add(result)
                todo.append(result)
    return reached


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, choices=(18, 23), required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    cases = [('small', 8, [1], [2, 3], 'add', False),
             ('phi-copies', 8, [1], [2, 3], 'add', False),
             ('deep-copies', 8, [1], [2, 3], 'add', False),
             ('large', 16, [1], [2, 3], 'add', False),
             ('subtract', 16, [1], [2, 3], 'sub', False),
             ('cosets', 16, [1, 2], [16384, 32768], 'add', False),
             ('wide-cosets', 128, [(1 << 100) + 1, (1 << 101) + 2], [1 << 126, 1 << 127], 'add', False),
             ('negative', 16, [7], [-1, 0], 'add', False),
             ('zero', 16, [7], [0, 0], 'add', False),
             ('reflection', 16, [1], [0, 0], 'sub', True)]
    receipts = []
    for name, width, seeds, steps, opcode, reverse in cases:
        expected = orbit(width, seeds, steps, opcode, reverse)
        for order in ('original', 'blocks', 'functions'):
            t = f'i{width}'
            operands = f'{t} %step, %copy' if reverse else f'{t} %copy, %step'
            blocks = {'entry': f'%step = select i1 %choice, {t} {steps[0]}, {t} {steps[1]}\n br label %loop',
                      'loop': f'%p = phi {t} [{seeds[0]}, %entry], [%feedback, %loop]\n'
                              f' %copy = freeze {t} %p\n %next = {opcode} {operands}\n'
                              f' %feedback = select i1 %choice, {t} %next, {t} {seeds[-1]}\n'
                              ' br i1 %choice, label %loop, label %done',
                      'done': f'ret {t} %p'}
            if name == 'deep-copies':
                chain = ''.join(f' %copy{n} = freeze {t} ' + ('%p' if n == 0 else f'%copy{n-1}') + '\n' for n in range(300))
                blocks['loop'] = blocks['loop'].replace(f' %copy = freeze {t} %p\n', chain + f' %copy = freeze {t} %copy299\n')
            if name == 'phi-copies':
                blocks['loop'] = f'%p = phi {t} [{seeds[0]}, %entry], [%feedback, %join]\n br i1 %choice, label %left, label %right'
                blocks['left'] = f'%leftvalue = phi {t} [%p, %loop]\n br label %join'
                blocks['right'] = 'br label %join'
                blocks['join'] = (f'%joined = phi {t} [%leftvalue, %left], [%p, %right]\n'
                                  f' %copy = freeze {t} %joined\n %next = add {t} %copy, %step\n'
                                  f' %feedback = select i1 %choice, {t} %next, {t} {seeds[-1]}\n'
                                  ' br i1 %choice, label %loop, label %done')
                labels = ('entry', 'done', 'join', 'right', 'left', 'loop') if order == 'blocks' else ('entry', 'loop', 'left', 'right', 'join', 'done')
            else:
                labels = ('entry', 'done', 'loop') if order == 'blocks' else ('entry', 'loop', 'done')
            top = f'define {t} @top(i1 %choice) {{\n' + '\n'.join(
                label + ':\n ' + blocks[label] for label in labels) + '\n}\n'
            helper = 'define internal i8 @helper() { ret i8 9 }\n'
            source = directory / f'{name}-{order}.ll'
            source.write_text('target datalayout = "e-p:64:64"\n' + (top + helper if order == 'functions' else helper + top))
            report = source.with_suffix('.json')
            result = run([f'/usr/lib/llvm-{args.major}/bin/opt',
                          f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                          '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                          '-bennett-analysis-max-rounds=8', f'-bennett-report={report}',
                          '-disable-output', source])
            source.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0, (name, order, result.stderr)
            data = json.loads(report.read_text())
            row = next(v for v in data['values'] if v['function'] == 'top' and v['value'] == '%p')
            if len(expected) > 4096:
                assert row['top'] and not row['atoms'], row
            else:
                assert not row['top'] and sorted(row['atoms']) == sorted(f'INT({x})' for x in expected), row
            receipts.append(dict(case=name, order=order, rounds=data['analysis_rounds'], cardinality=len(expected)))
    (directory / 'results.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
