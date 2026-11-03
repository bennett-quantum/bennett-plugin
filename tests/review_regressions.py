#!/usr/bin/env python3
"""Correct-result regressions for the plugin batch review."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = Path(os.environ.get('BENNETT_SIBLINGS', ROOT.parent))
REF = SIBLINGS / 'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'


def run(command, timeout=120):
    result = subprocess.run(list(map(str, command)), capture_output=True,
                            text=True, timeout=timeout)
    assert result.returncode == 0, (command, result.returncode, result.stdout, result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--case', action='append', choices=('shuffle', 'byval', 'global-counter'))
    args = parser.parse_args()
    tool = f'/usr/lib/llvm-{args.major}/bin/'
    plugin = ROOT / f'build/libbennett-plugin-{args.major}.so'
    work = ROOT / f'.tmp/review-regressions/{args.major}'
    work.mkdir(parents=True, exist_ok=True)
    command = [tool + 'opt', '-load-pass-plugin=' + str(plugin),
               '-passes=bennett', '-bennett-dialect=0.2.10', '-disable-output']
    rows = []
    failures = []
    for case in args.case or ('shuffle', 'byval', 'global-counter'):
        if case == 'global-counter':
            original = (ROOT / 'tests/probes/review-global-counter.ll').read_text()
            extra_entry = original + original[original.index('define i32 @top()'):].replace('@top()', '@other()')
            for name, body, actions, expected in [
                    ('repeat', original, 'unsigned a=top(), b=top();', '1 2 host_global=2\n'),
                    ('host-write', original, 'unsigned a=top(); g=40; unsigned b=top();', '1 41 host_global=41\n'),
                    ('two-entries', extra_entry, 'unsigned a=top(), b=other();', '1 2 host_global=2\n')]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source, harness = directory / 'input.ll', directory / 'main.c'
                source.write_text(body)
                harness.write_text('#include <stdio.h>\nextern unsigned top(void), other(void), g;\n'
                                   'int main(void) {' + actions +
                                   'printf("%u %u host_global=%u\\n",a,b,g); return 0;}\n')
                run([*command, '-bennett-out=' + str(directory), source])
                run([tool + 'opt', '-passes=verify', '-disable-output', directory / 'host.bc'])
                library = SIBLINGS / 'bennett-vm/target/debug'
                executable = directory / 'counter'
                run([tool + 'clang', directory / 'host.bc', harness, '-L' + str(library),
                     '-Wl,-rpath,' + str(library), '-lbennett_vm', '-o', executable])
                environment = dict(os.environ, BENNETT_TARGET=(ROOT / 'tests/probes/review-launch-target.json').read_text())
                actual = subprocess.run([str(executable)], capture_output=True, text=True,
                                        env=environment, timeout=120)
                ok = actual.returncode == 0 and actual.stdout == expected
                rows.append(dict(case=case, name=name, expected=expected, actual=actual.stdout,
                                 exit=actual.returncode, stderr=actual.stderr, ok=ok))
                if not ok:
                    failures.append(rows[-1])
        if case == 'byval':
            original = (ROOT / 'tests/probes/review-byval.ll').read_text()
            duplicate = original.replace('void @mutate(ptr byval(i8) %p)',
                                         'i8 @mutate(ptr byval(i8) %p, ptr byval(i8) %other)')
            duplicate = duplicate.replace(' ret void', ' %before = load i8, ptr %other\n ret i8 %before')
            duplicate = duplicate.replace('call void @mutate(ptr byval(i8) %x)',
                                          '%before = call i8 @mutate(ptr byval(i8) %x, ptr byval(i8) %x)')
            duplicate = duplicate.replace(' ret i8 %v', ' %sum = add i8 %v, %before\n ret i8 %sum')
            indirect = original.replace('define i8 @top()', 'define i8 @top(i1 %choose)')
            indirect = indirect.replace(' call void @mutate(ptr byval(i8) %x)',
                                        ' %callee = select i1 %choose, ptr @mutate, ptr @other\n'
                                        ' call void %callee(ptr byval(i8) %x)')
            indirect += '\ndefine internal void @other(ptr byval(i8) %p) {\n store i8 12, ptr %p\n ret void\n}\n'
            for name, body, width, expected in [
                    ('review', original, 8, 7),
                    ('two-bytes', original.replace('i8', 'i16').replace('i16 7', 'i16 258'), 16, 258),
                    ('independent-copies', duplicate, 8, 14),
                    ('indirect-0', indirect, 8, 7), ('indirect-1', indirect, 8, 7)]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / 'input.ll'
                source.write_text(body)
                run([*command, '-bennett-out=' + str(directory), source])
                obj = directory / 'top/launch.bennett'
                run([REF, 'check', obj])
                for reverse in ([], ['--reverse']):
                    inputs = ['--args', name[-1]] if name.startswith('indirect-') else []
                    result = json.loads(run([REF, 'run-program', obj, 'top',
                                             '--budget', '1000,16,32,32', *inputs, *reverse]).stdout)
                    assert result['status'] == ('REVERSED' if reverse else 'COMPLETED') and result['results'] == [
                        {'type': f'i{width}', 'value': str(expected)}], result
                    if reverse:
                        assert result['equals_entry'] and result['memory_equals_entry'], result
                    rows.append(dict(case=case, name=name, actual=result))
        if case == 'shuffle':
            cases = [('review', None, 7, 8)]
            for mask, expected in (('undef, i32 1', 0x0907),
                                   ('poison, i32 3', 0x0D07),
                                   ('2, i32 undef', 0x070B)):
                cases.append(('lanes-' + str(len(cases)), mask, expected, 16))
            for name, mask, expected, width in cases:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = ROOT / 'tests/probes/review-shuffle.ll'
                if mask is not None:
                    source = directory / 'input.ll'
                    source.write_text('''target datalayout = "e-p:64:64"
define i16 @oracle() {
 %vec = shufflevector <2 x i8> <i8 7, i8 9>, <2 x i8> <i8 11, i8 13>, <2 x i32> <i32 MASK>
 %a = extractelement <2 x i8> %vec, i32 0
 %b = extractelement <2 x i8> %vec, i32 1
 %lo = zext i8 %a to i16
 %hi = zext i8 %b to i16
 %upper = shl i16 %hi, 8
 %result = or i16 %lo, %upper
 ret i16 %result
}
'''.replace('MASK', mask))
                report = directory / 'analysis.json'
                run([*command, '-bennett-analysis-only', '-bennett-report=' + str(report), source])
                if mask is None:
                    values = json.loads(report.read_text())['values']
                    assert any(v['value'] == '%v' and v['atoms'] == ['INT(7)'] and not v['top'] for v in values)
                run([*command, '-bennett-oracle=oracle',
                     f'-bennett-scalar-shape=;tgt={width}',
                     '-bennett-out=' + str(directory), source])
                obj = directory / 'ref.bennett'
                run([REF, 'check', obj])
                result = json.loads(run([REF, 'run-oracle', obj, 'ref', '--input', '',
                                         '--budget', '1000,0,32,32']).stdout)
                assert result['code'] == 0 and result['payload'] == expected, (name, expected, result)
                rows.append(dict(case=case, name=name, expected=expected, actual=result))
    result = dict(major=args.major, cases=len(rows), passed=len(rows)-len(failures), results=rows)
    receipt = json.dumps(result, indent=2) + '\n'
    (ROOT / f'.tmp/review-regressions-{args.major}.json').write_text(receipt)
    if args.case:
        (ROOT / f'.tmp/review-regressions-{"-".join(args.case)}-{args.major}.json').write_text(receipt)
    print(json.dumps(dict(major=args.major, cases=len(rows), passed=result['passed'])))
    assert not failures, failures


if __name__ == '__main__':
    main()
