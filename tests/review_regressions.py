#!/usr/bin/env python3
"""Correct-result regressions for the plugin batch review."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from contracts import ROOT, sibling
REF = sibling('bennett-isa-spec') / 'reference-interpreter/target/debug/bennett-isa-ref'


def run(command, timeout=120):
    result = subprocess.run(list(map(str, command)), capture_output=True,
                            text=True, timeout=timeout)
    assert result.returncode == 0, (command, result.returncode, result.stdout, result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path, help='Use an explicitly selected instrumentation build')
    parser.add_argument('--case', action='append', choices=('shuffle', 'byval', 'global-counter', 'byte-order', 'native-abi', 'block-order', 'control', 'dynamic-gate', 'mixed-native', 'unresolved-call'))
    args = parser.parse_args()
    tool = f'/usr/lib/llvm-{args.major}/bin/'
    plugin = args.plugin or ROOT / f'build/libbennett-plugin-{args.major}.so'
    work = ROOT / f'.tmp/review-regressions/{args.major}'
    work.mkdir(parents=True, exist_ok=True)
    command = [tool + 'opt', '-load-pass-plugin=' + str(plugin),
               '-passes=bennett', '-bennett-dialect=0.2.13', '-disable-output']
    rows = []
    failures = []
    for case in args.case or ('shuffle', 'byval', 'global-counter'):
        if case == 'unresolved-call':
            original = (ROOT / 'tests/probes/review-host-import.ll').read_text()
            successor = original.replace(' ret i32 %z', ' br label %after\nafter:\n ret i32 %z')
            after_call = original.replace(
                ' ret i32 %z',
                ' %next = add i32 %x, 1\n br label %after\nafter:\n ret i32 %next')
            indirect = original.replace(' %safe =', ' %safe =', 1).replace(
                ' br i1 %safe', ' %callee = select i1 %safe, ptr @identity, ptr @host_fn\n br i1 %safe')
            indirect = indirect.replace('call i32 @host_fn(i32 %x)', 'call i32 %callee(i32 %x)')
            indirect += '\ndefine internal i32 @identity(i32 %x) { ret i32 %x }\n'
            start = original.index(' %safe =')
            helper = original[:original.index('define i32 @top')] + '''define i32 @top(i32 %x) {
 %q = call ptr @__bennett_qalloc(i64 0,i64 1)
 call void @__bennett_qfree(ptr %q)
 %value = call i32 @helper(i32 %x)
 ret i32 %value
}
define internal i32 @helper(i32 %x) {
''' + original[start:]
            for name, body in [('review', original), ('successor', successor),
                               ('after-call', after_call), ('indirect', indirect), ('callee', helper)]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / 'input.ll'
                source.write_text(body)
                run([*command, '-bennett-out=' + str(directory), source])
                obj = directory / 'top/launch.bennett'
                run([REF, 'check', obj])
                safe = json.loads(run([REF, 'run-program', obj, 'top', '--args', '0',
                                       '--budget', '1000,0,32,32', '--reverse']).stdout)
                assert safe['status'] == 'REVERSED' and safe['results'] == [{'type':'i32','value':'7'}] and safe['equals_entry'], safe
                assert not safe['host_requests'], safe
                replies = directory / 'replies.json'
                replies.write_text(json.dumps([dict(service='bennett.fault', payload='0800000000000000', reply='')]))
                reached = json.loads(run([REF, 'run-program', obj, 'top', '--args', '1',
                                          '--budget', '1000,0,32,32', '--replies', replies]).stdout)
                assert reached['status'] == 'FAILED' and reached['host_requests'][0]['service'] == 'bennett.fault', reached
                assert reached['host_requests'][0]['payload'] == '0800000000000000', reached
                for filename in ('coverage.json', 'all-coverage.json'):
                    coverage = json.loads((directory / 'top' / filename).read_text())
                    assert any(row['classification'] == 'trapped' and 'host_fn' in row['reason'] for row in coverage['entries']), (name, filename, coverage)
                rows.append(dict(case=case, name=name, safe=safe, reached=reached))
        if case == 'mixed-native':
            original = (ROOT / 'tests/probes/review-mixed-native.ll').read_text()
            for name, body in [('review', original), ('host-fp', original + '''
define double @native_fp(double %a,double %b) {
 %sum = fadd double %a,%b
 ret double %sum
}
''')]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / 'input.ll'
                source.write_text(body)
                run([*command, '-bennett-out=' + str(directory), source])
                host = run([tool + 'opt', '-passes=verify', '-S', directory / 'host.bc', '-o', '-']).stdout
                assert 'load <8 x i1>' in host and 'extractelement <8 x i1>' in host, host
                if name == 'host-fp':
                    assert '%sum = fadd double %a, %b' in host and 'call i64 @__bennett_sf_' not in host, host
                obj = directory / 'top/launch.bennett'
                run([REF, 'check', obj])
                result = json.loads(run([REF, 'run-program', obj, 'top', '--args', '37',
                                         '--budget', '1000,0,0,0', '--reverse']).stdout)
                assert result['status'] == 'REVERSED' and result['equals_entry'] and result['results'] == [
                    {'type':'i8','value':'37'}], result
                rows.append(dict(case=case, name=name, actual=result))
            directory = work / case / 'device-fp'
            directory.mkdir(parents=True, exist_ok=True)
            source = directory / 'input.ll'
            source.write_text(original.replace('-i64:64-f80:', '-i64:64-i128:128-f80:') + '''
define double @device_fp(double %x) {
 %sum = fadd double %x, 2.000000e+00
 ret double %sum
}
!llvm.module.flags = !{!0}
!0 = !{i32 1, !"bennett.sstack", i64 4096}
''')
            run([*command, '-bennett-oracle=device_fp', '-bennett-scalar-shape=IN(64,zext);tgt=64',
                 '-bennett-scalar-stack=262144', '-bennett-scalar-heap=65536',
                 '-bennett-out=' + str(directory), source])
            obj = directory / 'ref.bennett'
            run([REF, 'check', obj])
            # The published add closure has over 114k location cells. Its
            # exercised call chain exceeds 65,536 cells; retain that boundary
            # and give the successful numerical witness a sufficient stack.
            numerical_ref = sibling('bennett-isa-spec') / 'reference-interpreter/target/release/bennett-isa-ref'
            boundary = json.loads(run([numerical_ref, 'run-oracle', obj, 'ref', '--input', '4607182418800017408',
                                       '--budget', '1000000,65536,65536,128']).stdout)
            assert boundary['code'] == 3 and boundary['payload'] == 0, boundary
            result = json.loads(run([numerical_ref, 'run-oracle', obj, 'ref', '--input', '4607182418800017408',
                                     '--budget', '1000000,65536,262144,128']).stdout)
            assert result['code'] == 0 and int(result['payload']) == 4613937818241073152, result
            rows.append(dict(case=case, name='device-fp', actual=result, small_stack=boundary))
        if case == 'dynamic-gate':
            original = (ROOT / 'tests/probes/review-dynamic-gate.ll').read_text()
            directory = work / case
            directory.mkdir(parents=True, exist_ok=True)
            run([*command, '-bennett-out=' + str(directory / 'review'), ROOT / 'tests/probes/review-dynamic-gate.ll'])
            body = original.replace('top(i32 %op)', 'top(i32 %op, i32 %inverse, i64 %index)')
            body = body.replace('qalloc(i64 0, i64 1)', 'qalloc(i64 0, i64 2)')
            body = body.replace('call void @__bennett_gate(i32 %op, ptr %q, i64 0)',
                                'call void @__bennett_gate(i32 %op, ptr %q, i64 %index)\n'
                                'call void @__bennett_gate(i32 %inverse, ptr %q, i64 %index)')
            source = directory / 'input.ll'
            source.write_text(body)
            run([*command, '-bennett-out=' + str(directory), source])
            obj = directory / 'top/launch.bennett'
            run([REF, 'check', obj])
            for op, inverse in [(1,1),(2,2),(3,4),(4,3),(5,6),(6,5),(7,7),(8,8)]:
                for index in (0,1):
                    result = json.loads(run([REF, 'run-program', obj, 'top', '--args', f'{op},{inverse},{index}',
                                             '--budget', '1000,0,0,0', '--reverse']).stdout)
                    assert result['status'] == 'REVERSED' and result['equals_entry'] and not result['faults'], result
                    rows.append(dict(case=case, op=op, index=index, actual=result))
            for inputs in ('0,1,0', '9,1,0', '1,1,2', '1,1,18446744073709551615'):
                result = json.loads(run([REF, 'run-program', obj, 'top', '--args', inputs, '--budget', '1000,0,0,0']).stdout)
                assert result['status'] == 'FAILED', result
                rows.append(dict(case=case, invalid=inputs, actual=result))
            measured = directory / 'measured.ll'
            measured.write_text('''target datalayout = "e-p:64:64"
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32,ptr,i64)
declare i1 @__bennett_measure(ptr,i64)
define i1 @top(i64 %index) {
 %q = call ptr @__bennett_qalloc(i64 0,i64 2)
 call void @__bennett_gate(i32 1,ptr %q,i64 %index)
 %value = call i1 @__bennett_measure(ptr %q,i64 %index)
 call void @__bennett_gate(i32 1,ptr %q,i64 %index)
 call void @__bennett_qfree(ptr %q)
 ret i1 %value
}
''')
            dest = directory / 'measured'
            run([*command, '-bennett-out=' + str(dest), measured])
            obj = dest / 'top/launch.bennett'
            run([REF, 'check', obj])
            for index in (0,1):
                result = json.loads(run([REF, 'run-program', obj, 'top', '--args', str(index),
                                         '--budget', '1000,0,0,0']).stdout)
                assert result['status'] == 'COMPLETED' and result['results'] == [{'type':'i1','value':'1'}], result
                rows.append(dict(case=case, measurement_index=index, actual=result))
        if case == 'control':
            original = (ROOT / 'tests/probes/review-control.ll').read_text()
            declaration = 'declare void @__bennett_gate(i32, ptr, i64)\n'
            for name, body, valid in [
                    ('review', original, True),
                    ('superposition', original.replace('call void @__bennett_ctrl',
                        'call void @__bennett_gate(i32 2, ptr %q, i64 0)\ncall void @__bennett_ctrl').replace(
                        'call void @__bennett_qfree', 'call void @__bennett_gate(i32 2, ptr %q, i64 0)\ncall void @__bennett_qfree') + declaration, True),
                    ('index-outside', original.replace('ctrl(ptr %q, i64 0', 'ctrl(ptr %q, i64 1'), False),
                    ('dead-control', original.replace('call void @__bennett_ctrl',
                        'call void @__bennett_qfree(ptr %q)\ncall void @__bennett_ctrl'), False)]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / 'input.ll'
                source.write_text(body)
                run([*command, '-bennett-out=' + str(directory), source])
                obj = directory / 'top/launch.bennett'
                run([REF, 'check', obj])
                result = json.loads(run([REF, 'run-program', obj, 'top', '--budget', '1000,0,0,0',
                                         *(['--reverse'] if valid else [])]).stdout)
                if valid:
                    assert result['status'] == 'REVERSED' and result['equals_entry'] and not result['faults'], result
                    assert 'action_call @' in obj.read_text(), obj.read_text()
                    build = json.loads((directory / 'top/build.json').read_text())
                    assert build['controlled_identity_proofs'][0]['generation_steps'] == 1, build
                else:
                    assert result['status'] == 'FAILED', result
                rows.append(dict(case=case, name=name, actual=result))
        if case == 'block-order':
            directory = work / case
            run([*command, '-bennett-out=' + str(directory), ROOT / 'tests/probes/review-block-order.ll'])
            obj = directory / 'top/launch.bennett'
            run([REF, 'check', obj])
            for value in (0, 7, 255):
                result = json.loads(run([REF, 'run-program', obj, 'top', '--args', str(value),
                                         '--budget', '1000,0,0,0', '--reverse']).stdout)
                assert result['status'] == 'REVERSED' and result['results'] == [
                    {'type': 'i8', 'value': str((value+3) % 256)}] and result['equals_entry'], result
                rows.append(dict(case=case, input=value, actual=result))
        if case == 'native-abi':
            original = (ROOT / 'tests/probes/review-pointer-abi.ll').read_text()
            for name, body in [
                    ('pointer', original),
                    ('pointer-result', original.replace('define i8 @top', 'define ptr @top').replace('ret i8 %x', 'ret ptr %p')),
                    ('aggregate', original.replace('i8 @top(ptr %p)', '{i8,i16} @top({i8,i16} %p)').replace('%x = load i8, ptr %p', '').replace('ret i8 %x', 'ret {i8,i16} %p')),
                    ('float', original.replace('i8 @top(ptr %p)', 'float @top(float %p)').replace('%x = load i8, ptr %p', '').replace('ret i8 %x', 'ret float %p')),
                    ('big-i24', original.replace('"e-', '"E-').replace('i8 @top(ptr %p)', 'i24 @top(i24 %p)').replace('%x = load i8, ptr %p', '').replace('ret i8 %x', 'ret i24 %p'))]:
                directory = work / case / name
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / 'input.ll'
                source.write_text(body)
                run([*command, '-bennett-out=' + str(directory), source])
                host = run([tool + 'opt', '-passes=verify', '-S', directory / 'host.bc', '-o', '-'])
                if name == 'pointer':
                    assert 'ptrtoint ptr %p to i64' in host.stdout, host.stdout
                if name == 'pointer-result':
                    assert 'inttoptr i64' in host.stdout, host.stdout
                run([REF, 'check', directory / 'top/launch.bennett'])
                if name in ('aggregate', 'float'):
                    harness = directory / 'main.ll'
                    if name == 'float':
                        harness.write_text('''declare float @top(float)
define i32 @main() {
 %value = call float @top(float 1.250000e+00)
 %ok = fcmp oeq float %value, 1.250000e+00
 %status = select i1 %ok, i32 0, i32 1
 ret i32 %status
}
''')
                    else:
                        harness.write_text('''declare {i8,i16} @top({i8,i16})
define i32 @main() {
 %value = call {i8,i16} @top({i8,i16} {i8 7,i16 300})
 %a = extractvalue {i8,i16} %value, 0
 %b = extractvalue {i8,i16} %value, 1
 %aok = icmp eq i8 %a, 7
 %bok = icmp eq i16 %b, 300
 %ok = and i1 %aok, %bok
 %status = select i1 %ok, i32 0, i32 1
 ret i32 %status
}
''')
                    library = sibling('bennett-vm') / 'target/debug'
                    executable = directory / 'native'
                    run([tool + 'clang', directory / 'host.bc', harness, '-L' + str(library),
                         '-Wl,-rpath,' + str(library), '-lbennett_vm', '-o', executable])
                    environment = dict(os.environ, BENNETT_TARGET=(ROOT / 'tests/probes/review-launch-target.json').read_text())
                    actual = subprocess.run([str(executable)], capture_output=True, text=True,
                                            env=environment, timeout=120)
                    assert actual.returncode == 0, (name, actual.returncode, actual.stderr)
                rows.append(dict(case=case, name=name, host_verified=True))
        if case == 'byte-order':
            for endian in ('e', 'E'):
                for operation in ('load', 'store'):
                    directory = work / case / (endian + '-' + operation)
                    directory.mkdir(parents=True, exist_ok=True)
                    source = directory / 'input.ll'
                    body = '%value = load i16, ptr @g\n ret i16 %value'
                    expected = 258
                    if operation == 'store':
                        body = '''store i16 258, ptr @g
 %first = load i8, ptr @g
 %secondp = getelementptr i8, ptr @g, i64 1
 %second = load i8, ptr %secondp
 %hi = zext i8 %first to i16
 %lo = zext i8 %second to i16
 %upper = shl i16 %hi, 8
 %value = or i16 %upper, %lo
 ret i16 %value'''
                        expected = 258 if endian == 'E' else 513
                    source.write_text(f'''target datalayout = "{endian}-p:64:64-i64:64-n8:16:32:64"
@g = internal global i16 258
define i16 @oracle() {{
 {body}
}}
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
define i16 @top() {{
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %q)
 %v = call i16 @oracle()
 ret i16 %v
}}
''')
                    for tier in ('L', 'CC'):
                        dest = directory / tier
                        flags = ['-bennett-oracle=oracle', '-bennett-scalar-shape=;tgt=16'] if tier == 'L' else []
                        run([*command, *flags, '-bennett-out=' + str(dest), source])
                        obj = dest / ('ref.bennett' if tier == 'L' else 'top/launch.bennett')
                        run([REF, 'check', obj])
                        execution = [REF, 'run-oracle', obj, 'ref', '--input', ''] if tier == 'L' else [REF, 'run-program', obj, 'top']
                        result = json.loads(run([*execution, '--budget', '1000,0,32,32']).stdout)
                        actual = result['payload'] if tier == 'L' else int(result['results'][0]['value'])
                        assert actual == expected and (result.get('code', 0) == 0), (endian, operation, tier, expected, result)
                        rows.append(dict(case=case, endian=endian, operation=operation, tier=tier, actual=actual))
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
                library = sibling('bennett-vm') / 'target/debug'
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
