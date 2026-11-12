#!/usr/bin/env python3
"""PT8 snapshots source objects without copying unrelated whole-program slots."""
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
    for count in (128, 1024):
        for intrinsic in ('memcpy', 'memmove'):
            for reverse in (False, True):
                source = directory / f'{intrinsic}-{count}-{reverse}.ll'
                report = source.with_suffix('.json')
                helper = 'define internal void @helper() { ret void }\n'
                top = f'''define i8 @top(i1 %choice) {{
 %src = select i1 %choice, ptr @source, ptr @other
 call void @llvm.{intrinsic}.p0.p0.i64(ptr @destination, ptr %src, i64 4, i1 false)
 %first = load i8, ptr @destination
 %last = load i8, ptr getelementptr (i8, ptr @destination, i64 3)
 ; Source and destination alias: all reads must precede the writes.
 call void @llvm.{intrinsic}.p0.p0.i64(ptr getelementptr (i8, ptr @source, i64 1), ptr @source, i64 3, i1 false)
 %alias = load i8, ptr getelementptr (i8, ptr @source, i64 3)
 ret i8 %last
}}
'''
                source.write_text('target datalayout = "e-p:64:64"\n' +
                    f'@junk = internal global [{count} x i8] zeroinitializer\n' +
                    '@source = internal global [4 x i8] [i8 1, i8 2, i8 3, i8 4]\n' +
                    '@other = internal global [4 x i8] [i8 5, i8 6, i8 7, i8 8]\n' +
                    '@destination = internal global [4 x i8] zeroinitializer\n' +
                    f'declare void @llvm.{intrinsic}.p0.p0.i64(ptr, ptr, i64, i1)\n' +
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
                # Flow-insensitive aliased copies propagate every source prefix.
                assert values['top', '%first'] == (False, ['INT(0)', 'INT(1)', 'INT(5)']), values
                assert values['top', '%last'] == (False, ['INT(0)', 'INT(1)', 'INT(2)', 'INT(3)', 'INT(4)', 'INT(8)']), values
                assert values['top', '%alias'] == (False, ['INT(1)', 'INT(2)', 'INT(3)', 'INT(4)']), values
                work = data['analysis_work']
                receipts.append(dict(count=count, intrinsic=intrinsic, reverse=reverse, work=work))
                (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
                assert work['memory']['memtransfer_copied_slots'] <= 12 * work['rounds_completed'], work['memory']
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
