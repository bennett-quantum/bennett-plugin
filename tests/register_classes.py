#!/usr/bin/env python3
"""Execute configured-class allocations against independent target class tables."""
import argparse
import json
from pathlib import Path
import subprocess

from contracts import ROOT, sibling


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path)
    args = parser.parse_args()
    work = ROOT / f'.tmp/register-classes/{args.major}'
    work.mkdir(parents=True, exist_ok=True)
    plugin = args.plugin or ROOT / f'build/libbennett-plugin-{args.major}.so'
    reference = sibling('bennett-isa-spec') / 'reference-interpreter/target/debug/bennett-isa-ref'
    target_template = json.loads((sibling('bennett-targets') / 'targets/ideal-all-to-all.json').read_text())
    body = '''target datalayout = "e-p:64:64"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
declare i1 @__bennett_measure(ptr, i64)
define i1 @top(i64 %class) {
 %q = call ptr @__bennett_qalloc(i64 CLASS, i64 1)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 %bit = call i1 @__bennett_measure(ptr %q, i64 0)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_qfree(ptr %q)
 ret i1 %bit
}
!llvm.module.flags = !{!0}
!0 = !{i32 6, !"bennett.classes", !1}
!1 = !{!"alpha", !"beta"}
'''
    for operand in ('1', '2', '%class'):
        directory = work / ('dynamic' if operand == '%class' else operand)
        directory.mkdir(exist_ok=True)
        source = directory / 'input.ll'
        source.write_text(body.replace('CLASS', operand))
        run([f'/usr/lib/llvm-{args.major}/bin/opt', '-load-pass-plugin=' + str(plugin),
             '-passes=bennett', '-bennett-dialect=0.2.13',
             '-bennett-out=' + str(directory), '-disable-output', source])
        obj = directory / 'top/launch.bennett'
        run([reference, 'check', obj])
        for index, name in ((1, 'alpha'), (2, 'beta')):
            if operand != '%class' and int(operand) != index:
                continue
            target = dict(target_template, classes={name: target_template['classes']['data']})
            path = directory / f'{name}.json'
            path.write_text(json.dumps(target))
            result = json.loads(run([reference, 'run-program', obj, 'top',
                                     '--args', str(index), '--target', path,
                                     '--budget', '1000,0,32,16']).stdout)
            assert result['status'] == 'COMPLETED', result
            assert result['results'] == [{'type': 'i1', 'value': '1'}], result
    print(f'LLVM {args.major}: configured constant and runtime classes passed')


if __name__ == '__main__':
    main()
