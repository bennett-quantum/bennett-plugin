#!/usr/bin/env python3
"""Function identities must remain distinct from live heap allocations."""
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
    plugin = args.plugin or ROOT / f'build/libbennett-plugin-{args.major}.so'
    work = ROOT / f'.tmp/address-spaces/{args.major}'
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'input.ll'
    source.write_text('''target datalayout = "e-p:64:64"
@seed = internal global i8 0
@unused = internal global [16 x i8] zeroinitializer
define internal void @callback() { ret void }
define i64 @top() {
 %h = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %h)
 %seed = load i8, ptr @seed
 %p = call ptr @__bennett_nz_alloc(i64 64)
 %address = ptrtoint ptr %p to i64
 %function = ptrtoint ptr @callback to i64
 %equal = icmp eq i64 %address, %function
 %result = zext i1 %equal to i64
 call void @__bennett_nz_free(ptr %p)
 ret i64 %result
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_nz_alloc(i64)
declare void @__bennett_nz_free(ptr)
''')
    run([f'/usr/lib/llvm-{args.major}/bin/opt', '-load-pass-plugin=' + str(plugin),
         '-passes=bennett', '-bennett-dialect=0.2.13',
         '-bennett-budget-default=1000,256,128,16,0',
         '-bennett-out=' + str(work), '-disable-output', source])
    obj = work / 'top/launch.bennett'
    reference = sibling('bennett-isa-spec') / 'reference-interpreter/target/debug/bennett-isa-ref'
    run([reference, 'check', obj])
    for reverse in ([], ['--reverse']):
        result = json.loads(run([reference, 'run-program', obj, 'top',
                                 '--budget', '1000,256,128,16', *reverse]).stdout)
        assert result['results'] == [{'type': 'i64', 'value': '0'}], result
        assert result['status'] == ('REVERSED' if reverse else 'COMPLETED'), result
        if reverse:
            assert result['equals_entry'] and result['memory_equals_entry'], result
    print(f'LLVM {args.major}: function/heap identity and reversal passed')


if __name__ == '__main__':
    main()
