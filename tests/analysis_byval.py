#!/usr/bin/env python3
"""PT9 snapshots only the source interval, including filled slots and aliases."""
import argparse
import json
import re
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
        # Both unrelated objects and out-of-range slots of the source object
        # must be excluded before copying. The window's last byte is included.
        declarations = (f'@junk = internal global [{count} x i8] zeroinitializer\n'
                        f'@source = internal global [{count} x i8] [' +
                        ', '.join(f'i8 {i % 256}' for i in range(count)) + ']\n')
        cases = {
            'recursive-alias': (declarations + """
@seed = internal global [3 x i8] [i8 1, i8 2, i8 3]
define internal i8 @copy(ptr byval([3 x i8]) %p, i1 %again) {
 %first = load i8, ptr %p
 %q = getelementptr i8, ptr %p, i64 1
 %middle = load i8, ptr %q
 %end = getelementptr i8, ptr %p, i64 2
 %last = load i8, ptr %end
 br i1 %again, label %recurse, label %done
recurse:
 %r = call i8 @copy(ptr byval([3 x i8]) %q, i1 false)
 br label %done
done:
 ret i8 %first
}
define i8 @top() {
 %r = call i8 @copy(ptr byval([3 x i8]) @seed, i1 true)
 ret i8 %r
}
""", {('copy', '%first'): ['INT(1)', 'INT(2)', 'INT(3)'],
       ('copy', '%middle'): ['INT(2)', 'INT(3)'], ('copy', '%last'): ['INT(3)']}),
            'window': (declarations + '''
define internal i8 @copy(ptr byval([4 x i8]) %p) {
 store i8 200, ptr %p
 %first = load i8, ptr %p
 %q = getelementptr i8, ptr %p, i64 3
 %last = load i8, ptr %q
 ret i8 %last
}
define i8 @top() {
 %r = call i8 @copy(ptr byval([4 x i8]) getelementptr (i8, ptr @source, i64 64))
 %original = load i8, ptr getelementptr (i8, ptr @source, i64 64)
 ret i8 %r
}
''', {('copy', '%first'): ['INT(64)', 'INT(200)'],
      ('copy', '%last'): ['INT(67)'], ('top', '%original'): ['INT(64)']}),
            'filled': (declarations + '''
declare void @llvm.memset.p0.i64(ptr, i8, i64, i1)
define internal i32 @copy(ptr byval(i32) %p) {
 %v = load i32, ptr %p
 ret i32 %v
}
define i32 @top() {
 %local = alloca [12 x i8]
 %middle = getelementptr i8, ptr %local, i64 4
 call void @llvm.memset.p0.i64(ptr %middle, i8 0, i64 4, i1 false)
 %r = call i32 @copy(ptr byval(i32) %middle)
 ret i32 %r
}
''', {('copy', '%v'): ['INT(0)'], ('top', '%r'): ['INT(0)']}),
            'alternatives': (declarations + '''
@target = internal global i8 7
@pointers = internal global [2 x ptr] [ptr @target, ptr @callee]
define internal void @callee() {
 ret void
}
define internal ptr @copy(ptr byval(ptr) %p) {
 %v = load ptr, ptr %p
 ret ptr %v
}
define ptr @top(i1 %choice) {
 %src = select i1 %choice, ptr @pointers, ptr getelementptr (ptr, ptr @pointers, i64 1)
 %r = call ptr @copy(ptr byval(ptr) %src)
 %original = load ptr, ptr @pointers
 ret ptr %r
}
''', {('copy', '%v'): ['PTR(@target,0,0)', 'FN(@callee,0,0)'],
      ('top', '%r'): ['PTR(@target,0,0)', 'FN(@callee,0,0)'],
      ('top', '%original'): ['PTR(@target,0,0)']}),
        }
        for name, (ir, expected) in cases.items():
            for reverse in (False, True):
                source = directory / f'{name}-{count}-{reverse}.ll'
                # Reverse function visitation without changing any CFG.
                if reverse:
                    functions = re.findall(r'define\b.*?^}', ir, re.M | re.S)
                    ir = re.sub(r'define\b.*?^}', '', ir, flags=re.M | re.S)
                    ir += '\n'.join(reversed(functions))
                source.write_text('target datalayout = "e-p:64:64"\n' + ir)
                report = source.with_suffix('.json')
                command = [f'/usr/lib/llvm-{args.major}/bin/opt',
                           f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                           '-bennett-dialect=0.3-r1', '-bennett-isa=0.9',
                           '-bennett-tier=reversible', '-bennett-entry=top',
                           '-bennett-analysis-only',
                           f'-bennett-report={report}', '-disable-output', source]
                result = run(command)
                source.with_suffix('.stderr').write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                data = json.loads(report.read_text())
                values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                          for v in data['values']}
                for key, atoms in expected.items():
                    assert values[key] == (False, sorted(atoms)), (name, key, values[key])
                work = data['analysis_work']
                receipts.append(dict(case=name, count=count, reverse=reverse, work=work))
                (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
                # At most two calls per round and two exact alternatives. No global
                # slot-vector copy or scan, and no scan of the source's tail.
                assert work['memory']['byval_copied_slots'] <= 8 * work['rounds_completed'], work['memory']
                assert work['memory']['byval_slot_tests'] <= 10 * work['rounds_completed'], work['memory']
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
