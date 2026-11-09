#!/usr/bin/env python3
"""PT2 zipped lane images; expectations use byte strides and modular arithmetic."""

import argparse
import json
from pathlib import Path

from contracts import run


LAYOUT = 'target datalayout = "e-p:64:64-p270:64:64:64:32"\n'
GLOBAL = '@buf = internal global [8192 x i8] zeroinitializer, align 8192\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    opt = f'/usr/lib/llvm-{args.major}/bin/opt'
    rows = []

    def check(name, body, expected, prelude=GLOBAL, diagnostic=None):
        source = args.artifacts / (name + '.ll')
        report = args.artifacts / (name + '.json')
        source.write_text(LAYOUT + prelude + 'define void @top() {\n' + body + '\n ret void\n}\n')
        command = [opt, f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                   '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                   f'-bennett-report={report}', '-S', source, '-o', '-']
        result = run(command)
        (args.artifacts / (name + '.stderr')).write_text(result.stderr)
        if diagnostic:
            assert result.returncode != 0 and diagnostic in result.stderr, (name, result.stderr)
            rows.append(dict(case=name, work=json.loads(report.read_text())["analysis_work"]))
            return
        assert result.returncode == 0, (name, result.stderr)
        canonical = run([opt, '-S', source, '-o', '-'])
        assert canonical.returncode == 0 and canonical.stdout == result.stdout, 'H IR mutated'
        data = json.loads(report.read_text())
        facts = {v['value']: (v['top'], set(v['atoms'])) for v in data['values']
                 if v['function'] == 'top'}
        for value, want in expected.items():
            assert facts[value] == want, (name, value, facts[value], want)
        rows.append(dict(case=name, work=data['analysis_work']))

    def ptr(*offsets, top=False):
        return top, {f'PTR(@buf,{n},0)' for n in offsets}

    extract = '\n %p0 = extractelement <2 x ptr> %p, i32 0\n %p1 = extractelement <2 x ptr> %p, i32 1'
    for name, base, indices, offsets in (
        ('scalar-vector', 'ptr @buf', '<2 x i64> <i64 1, i64 3>', (4, 12)),
        ('vector-scalar', '<2 x ptr> <ptr @buf, ptr getelementptr(i8, ptr @buf, i64 8)>', 'i16 1', (4, 12)),
        ('vector-vector', '<2 x ptr> <ptr @buf, ptr getelementptr(i8, ptr @buf, i64 8)>', '<2 x i64> <i64 1, i64 3>', (4, 20)),
    ):
        check(name, f' %p = getelementptr i32, {base}, {indices}' + extract,
              {'%p0': ptr(offsets[0]), '%p1': ptr(offsets[1]), '%p': ptr(*offsets)})
    check('constant-expression', '''
 %p0 = extractelement <2 x ptr> getelementptr(i32, ptr @buf, <2 x i64> <i64 1, i64 3>), i32 0
 %p1 = extractelement <2 x ptr> getelementptr(i32, ptr @buf, <2 x i64> <i64 1, i64 3>), i32 1
''', {'%p0': ptr(4), '%p1': ptr(12)})
    check('mixed-width-struct', '''
 %p = getelementptr {i8, [4 x i16]}, ptr @buf, <2 x i16> <i16 0, i16 1>, i32 1, <2 x i64> <i64 1, i64 -1>
''' + extract, {'%p0': ptr(4), '%p1': ptr(10)})
    check('wrap-index', '''
 %p = getelementptr i8, ptr addrspace(270) @buf, <2 x i64> <i64 4294967296, i64 -1>
 %p0 = extractelement <2 x ptr addrspace(270)> %p, i32 0
 %p1 = extractelement <2 x ptr addrspace(270)> %p, i32 1
''', {'%p0': ptr(0), '%p1': (True, {'PTR(@buf,-1,0)', 'PTR(@buf,4294967295,0)', 'PTR(EXT,0,-1)'})},
          '@buf = internal addrspace(270) global [8192 x i8] zeroinitializer, align 8192\n')
    check('outside', ' %p = getelementptr i8, ptr @buf, <2 x i64> <i64 1, i64 9>' + extract,
          {'%p0': ptr(1), '%p1': (True, {'PTR(@buf,9,0)', 'PTR(EXT,0,-1)'})},
          '@buf = internal global [8 x i8] zeroinitializer\n')
    check('lane-alternatives', '''
 %ix = select i1 true, <2 x i64> <i64 1, i64 3>, <2 x i64> <i64 2, i64 5>
 %p = getelementptr i32, ptr @buf, <2 x i64> %ix
''' + extract, {'%p0': ptr(4, 8), '%p1': ptr(12, 20)})
    # Lane 0 contains K or K+1 INTs; summary TOP must not erase lane 1.
    for extra in (False, True):
        body = '''
 %x = call i64 @external()
 %mask = and i64 %x, 4095
'''
        if extra:
            body += ' %ix = select i1 true, i64 %mask, i64 4096\n'
        body += f''' %a = insertelement <2 x i64> zeroinitializer, i64 {'%ix' if extra else '%mask'}, i32 0
 %b = insertelement <2 x i64> %a, i64 1, i32 1
 %p = getelementptr i8, ptr @buf, <2 x i64> %b
''' + extract
        expected = {'%p1': ptr(1)}
        if not extra:
            expected['%p0'] = ptr(*range(4096))
        else:
            expected['%p0'] = (True, {'PTR(@buf,0,-1)', 'PTR(EXT,0,-1)'})
        check('saturation-' + str(extra), body, expected, GLOBAL + 'declare i64 @external()\n')
    # ROOT is explicit even for a nonzero index. A numeric unknown cannot
    # replace its provenance, nor can an empty lane acquire the other lane.
    check('root', '''
 %h = call ptr @__bennett_qalloc(i64 0, i64 1)
 %v = insertelement <2 x ptr> zeroinitializer, ptr %h, i32 0
 %p = getelementptr i8, <2 x ptr> %v, <2 x i64> <i64 1, i64 0>
''' + extract, {'%p0': (False, {'ROOT(%h,0,0)'}), '%p1': (False, {'INT(0)'})},
          'declare ptr @__bennett_qalloc(i64, i64)\n', diagnostic='BD-E-HANDLE-USE')
    (args.artifacts / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(dict(major=args.major, passed=len(rows))))


if __name__ == '__main__':
    main()
