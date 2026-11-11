#!/usr/bin/env python3
"""Pure transfers share immutable operand images, retaining exact store facts."""
import argparse
import json
from pathlib import Path

from contracts import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--major', type=int, choices=(18, 23), required=True)
    p.add_argument('--plugin', type=Path, required=True)
    p.add_argument('--artifacts', type=Path, required=True)
    args = p.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for count in (16, 32, 64):
        globals_ = 'target datalayout = "e-p:64:64"\n@cell = internal global ptr null\n'
        globals_ += '\n'.join(f'@t{i} = internal global i8 0' for i in range(count))
        globals_ += f'\n@table = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr @t{i}' for i in range(count)) + ']\n'
        body = f''' %index = and i64 %arg, {count - 1}
 %address = getelementptr ptr, ptr @table, i64 %index
 %set = load ptr, ptr %address
'''
        body += '\n'.join(' store ptr %set, ptr @cell' for _ in range(count))
        body += '\n %read = load ptr, ptr @cell\n br label %exit'
        blocks = {'entry': 'br label %body', 'body': body, 'exit': 'ret ptr %read'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        for order in ('original', 'functions', 'blocks'):
            block_order = ('entry', 'exit', 'body') if order == 'blocks' else ('entry', 'body', 'exit')
            top = 'define ptr @top(i64 %arg) {\n' + '\n'.join(
                b + ':\n' + blocks[b] for b in block_order) + '\n}\n'
            source = directory / f'{count}-{order}.ll'
            source.write_text(globals_ + (top + helper if order == 'functions' else helper + top))
            report = source.with_suffix('.json')
            argv = [f'/usr/lib/llvm-{args.major}/bin/opt',
                    f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                    '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                    f'-bennett-report={report}', '-disable-output', source]
            result = run(argv)
            source.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0, result.stderr
            data = json.loads(report.read_text())
            values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                      for v in data['values']}
            pointers = [f'PTR(@t{i},0,0)' for i in range(count)]
            assert values['top', '%set'] == (False, sorted(pointers)), values
            assert values['top', '%read'] == (False, sorted(['INT(0)', *pointers])), values
            domains.append(values)
            work = data['analysis_work']['memory']
            receipts.append(dict(count=count, order=order, argv=list(map(str, argv)), work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            assert work['input_snapshot_copied_atoms'] <= 8 * count + 32, work
        assert domains[0] == domains[1] == domains[2], (count, 'evaluation order')
    # The same aggregate operand has distinct leaf images; loop growth must
    # leave prior instruction snapshots immutable until each transfer revisits.
    source = directory / 'growing-fields.ll'
    source.write_text('''target datalayout = "e-p:64:64"
@a = internal global i8 0
@b = internal global i8 0
@c = internal global i8 0
@pair = internal global {ptr, ptr} zeroinitializer
define ptr @top(i1 %condition) {
entry: br label %loop
loop:
 %left = phi ptr [@a, %entry], [%right, %loop]
 %right = select i1 %condition, ptr %left, ptr @b
 %first = insertvalue {ptr, ptr} poison, ptr %left, 0
 %pair = insertvalue {ptr, ptr} %first, ptr @c, 1
 store {ptr, ptr} %pair, ptr @pair
 br i1 %condition, label %loop, label %done
done:
 %read0 = load ptr, ptr @pair
 %read1 = load ptr, ptr getelementptr ({ptr, ptr}, ptr @pair, i64 0, i32 1)
 ret ptr %read0
}
''')
    report = source.with_suffix('.json')
    result = run([f'/usr/lib/llvm-{args.major}/bin/opt',
                  f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                  '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                  f'-bennett-report={report}', '-disable-output', source])
    source.with_suffix('.stderr').write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text())
    values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
              for v in data['values']}
    assert values['top', '%left'] == (False, ['PTR(@a,0,0)', 'PTR(@b,0,0)']), values
    assert values['top', '%read0'] == (False, ['INT(0)', 'PTR(@a,0,0)', 'PTR(@b,0,0)']), values
    assert values['top', '%read1'] == (False, ['INT(0)', 'PTR(@c,0,0)']), values
    assert data['analysis_rounds'] >= 3, data['analysis_rounds']
    # Narrow integer source modes still supply a native pointer layout and
    # valid comparison bases. Real comparison keeps rejecting invalid bases.
    source = directory / 'narrow-source.ll'
    source.write_text('target datalayout = "e-p:64:64-p1:8:8"\n'
                      'define i8 @source(i8 %x) { %r = add i8 %x, 1\n ret i8 %r }\n')
    argv = [f'/usr/lib/llvm-{args.major}/bin/opt',
            f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
            '-bennett-dialect=0.2.13', '-disable-output', source]
    for mode in ('-bennett-analysis-only', '-bennett-validate-only', '-bennett-normalise-only'):
        result = run([*argv, mode])
        assert result.returncode == 0, (mode, result.stderr)
    result = run([*argv, '-bennett-comparison', '-bennett-layout-data-base=0'])
    assert result.returncode != 0 and 'BD-E-COMPARISON-LAYOUT' in result.stderr, result.stderr
    print(json.dumps(dict(major=args.major, cases=len(receipts) + 5, passed=True)))


if __name__ == '__main__':
    main()
