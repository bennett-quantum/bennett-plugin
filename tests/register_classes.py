#!/usr/bin/env python3
"""Execute configured-class allocations against independent target class tables."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from contracts import ROOT, sibling


def run(command, env=None):
    result = subprocess.run(list(map(str, command)), capture_output=True,
                            text=True, timeout=60, env=env)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path)
    parser.add_argument('--promised-target-bp-ok6', action='store_true',
                        help='Exercise target-aware native execution, pending in the pinned executor')
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
        # ISA §3.3 class references are link-table names. This exact mapping
        # assertion complements execution while the pinned reference executor
        # explicitly defers target-aware loads.
        allocations = [line.split()[3] for line in obj.read_text().splitlines()
                       if len(line.split()) == 5 and line.split()[2] == 'qreg.new']
        expected_classes = {'any', 'alpha', 'beta'} if operand == '%class' else {'any', ('alpha', 'beta')[int(operand)-1]}
        assert set(allocations) == expected_classes, (allocations, expected_classes)
        harness = directory / 'main.c'
        harness.write_text('#include <stdbool.h>\n#include <stdlib.h>\n'
                           'extern bool top(unsigned long long);\n'
                           'int main(int argc, char **argv) { return top(strtoull(argv[1],0,10)) ? 0 : 1; }\n')
        library = sibling('bennett-vm') / 'target/debug'
        executable = directory / 'classes'
        run([f'/usr/lib/llvm-{args.major}/bin/clang', directory / 'host.bc', harness,
             '-L' + str(library), '-Wl,-rpath,' + str(library), '-lbennett_vm', '-o', executable])
        for index, name in ((1, 'alpha'), (2, 'beta')):
            if operand != '%class' and int(operand) != index:
                continue
            names = ('alpha', 'beta') if operand == '%class' else (name,)
            target = dict(target_template, classes={n: target_template['classes']['data'] for n in names})
            path = directory / f'{name}.json'
            path.write_text(json.dumps(target))
            if args.promised_target_bp_ok6:
                run([executable, str(index)], env=dict(os.environ, BENNETT_TARGET=json.dumps(target)))
            result = json.loads(run([reference, 'run-program', obj, 'top',
                                     '--args', str(index),
                                     '--budget', '1000,0,0,0']).stdout)
            assert result['status'] == 'COMPLETED', result
            assert result['results'] == [{'type': 'i1', 'value': '1'}], result
        if operand == '%class':
            invalid = json.loads(run([reference, 'run-program', obj, 'top', '--args', '3',
                                      '--budget', '1000,0,0,0']).stdout)
            assert invalid['status'] == 'FAILED', invalid
    print(f'LLVM {args.major}: configured constant and runtime classes passed')


if __name__ == '__main__':
    main()
