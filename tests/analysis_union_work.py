#!/usr/bin/env python3
"""Repeated exact unions reuse normalized immutable images without tree searches."""
import argparse
import json
from pathlib import Path

from contracts import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, choices=(18, 23), required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for count in (16, 32, 64):
        declarations = '\n'.join(f'@t{i} = internal global i8 0' for i in range(count))
        declarations += f'\n@table = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr @t{i}' for i in range(count)) + ']\n'
        top = f'''define ptr @top(i64 %index) {{
 %cell = alloca ptr
 %bounded = and i64 %index, {count - 1}
 %p = getelementptr ptr, ptr @table, i64 %bounded
 %raw = load ptr, ptr %p
 %set = select i1 true, ptr null, ptr %raw
'''
        top += '\n'.join(' store ptr %set, ptr %cell' for _ in range(count))
        top += '\n %read = load ptr, ptr %cell\n ret ptr %read\n}\n'
        helper = 'define internal void @helper() { ret void }\n'
        for reverse in (False, True):
            source = directory / f'{count}-{reverse}.ll'
            report = source.with_suffix('.json')
            source.write_text('target datalayout = "e-p:64:64"\n' + declarations +
                              (top + helper if reverse else helper + top))
            command = [f'/usr/lib/llvm-{args.major}/bin/opt',
                       f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                       '-bennett-dialect=0.3-r1', '-bennett-isa=0.9',
                       '-bennett-tier=reversible', '-bennett-entry=top',
                       '-bennett-analysis-only', f'-bennett-report={report}',
                       '-disable-output', source]
            result = run(command)
            source.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0, result.stderr
            data = json.loads(report.read_text())
            values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                      for v in data['values']}
            expected = (False, sorted(['INT(0)', *(f'PTR(@t{i},0,0)' for i in range(count))]))
            assert values['top', '%set'] == values['top', '%read'] == expected, values
            work = data['analysis_work']['memory']
            receipts.append(dict(count=count, reverse=reverse, work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            assert work['merge_atom_visits'] <= 16 * count + 32, work
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
