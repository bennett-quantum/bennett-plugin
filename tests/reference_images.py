#!/usr/bin/env python3
"""M1 acceptance witnesses for §5 represented-address images.

These witnesses do not establish every symbolic/residue-class image; a green
regression gate does not close bp-3w4. Expectations follow accepted 0.2.10,
never the sibling worktree.
"""
import argparse
import json
import subprocess
from contracts import ROOT as R

CASES = {
    'PT3-address-space-copy': (
        'e-p:64:64-p270:32:32',
        '''@g = internal global i8 0
define ptr addrspace(270) @top() {
 %v = addrspacecast ptr @g to ptr addrspace(270)
 ret ptr addrspace(270) %v
}''', {'PTR(@g,0,0)'}, False),
    'PT4-object-roundtrip': (
        'e-p:64:64',
        '''@g = internal global i8 0
define ptr @top() {
 %p = ptrtoint ptr @g to i64
 %v = inttoptr i64 %p to ptr
 ret ptr %v
}''', {'PTR(@g,0,0)'}, False),
    'PT2-numerical-not-host-escape': (
        'e-p:64:64:64:8',
        '''@g = internal global [32 x i8] zeroinitializer, align 16
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
define ptr @top() {
 %h = call ptr @__bennett_qalloc(i64 0,i64 1)
 %v = getelementptr i8, ptr @g, i8 16
 store ptr %h, ptr %v
 call void @__bennett_qfree(ptr %h)
 ret ptr %v
}''', {'PTR(@g,16,0)', 'PTR(@g,-240,0)', 'PTR(EXT,0,-1)'}, True),
    # With I=8 and alignment 16, base low bits can be 240. Adding 16
    # preserves all pointer bits above I, so that case moves -240 bytes.
    'PT2-low-index-wrap': (
        'e-p:64:64:64:8',
        '''@g = internal global [32 x i8] zeroinitializer, align 16
define ptr @top() {
 %v = getelementptr i8, ptr @g, i8 16
 ret ptr %v
}''', {'PTR(@g,16,0)', 'PTR(@g,-240,0)', 'PTR(EXT,0,-1)'}, True),
    # High address bits are lost. The image cannot be represented as a single
    # displacement from @g for all possible base patterns.
    'PT4-narrow-address': (
        'e-p:64:64',
        '''@g = internal global i8 0, align 16
define i8 @top() {
 %v = ptrtoint ptr @g to i8
 ret i8 %v
}''', {'PTR(@g,0,-1)', 'PTR(EXT,0,-1)'}, True),
    # Explicit fixed reference fallback in PT5 for widening pointer integers.
    'PT5-widen-address': (
        'e-p:64:64',
        '''@g = internal global i8 0
define i128 @top() {
 %p = ptrtoint ptr @g to i64
 %v = zext i64 %p to i128
 ret i128 %v
}''', {'PTR(@g,0,-1)', 'PTR(EXT,0,-1)'}, True),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True)
    major = parser.parse_args().major
    rows = []
    for name, (layout, body, atoms, top) in CASES.items():
        dest = R / f'.tmp/reference-images/{major}/{name}'
        dest.mkdir(parents=True, exist_ok=True)
        source, report = dest / 'in.ll', dest / 'report.json'
        source.write_text(f'target datalayout = "{layout}"\n{body}\n')
        report.unlink(missing_ok=True)
        result = subprocess.run([
            f'/usr/lib/llvm-{major}/bin/opt',
            '-load-pass-plugin=' + str(R / f'build/libbennett-plugin-{major}.so'),
            '-passes=bennett', '-bennett-dialect=0.2.10',
            '-bennett-analysis-only', '-bennett-report=' + str(report),
            '-disable-output', str(source)], text=True, capture_output=True)
        actual = next((value for value in json.loads(report.read_text())['values']
                       if value['value'] == '%v'), None) if result.returncode == 0 else None
        rows.append({'case': name,
                     'ok': actual is not None and set(actual['atoms']) == atoms and actual['top'] == top,
                     'expected': {'atoms': sorted(atoms), 'top': top},
                     'actual': actual, 'diagnostic': result.stderr if result.returncode else ''})
    audit = {'major': major, 'cases': len(rows), 'passed': sum(row['ok'] for row in rows),
             'bead': 'bp-3w4', 'results': rows}
    (R / f'.tmp/reference-images-{major}.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))
    return audit['passed'] != audit['cases']


if __name__ == '__main__':
    raise SystemExit(main())
