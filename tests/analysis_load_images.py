#!/usr/bin/env python3
"""PT6 shares identical interval transfers without changing any read image.

N distinct exact addresses read the same stride-8 pointer slot family. The
independent oracle is its N written targets plus TOP. There are three transfer
signatures: the target table, address table, and written slot family. Immutable
integer reads additionally depend on their byte offset; growing stores must
invalidate all memoized representations of the written object.
"""

import argparse
from itertools import product
import json
from pathlib import Path

from contracts import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []

    def analyse(name, source):
        path = directory / (name + '.ll')
        report = path.with_suffix('.json')
        path.write_text(source)
        command = [f'/usr/lib/llvm-{args.major}/bin/opt',
                   f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                   '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                   f'-bennett-report={report}', '-disable-output', path]
        result = run(command)
        path.with_suffix('.stderr').write_text(result.stderr)
        assert result.returncode == 0, result.stderr
        data = json.loads(report.read_text())
        receipts.append(dict(case=name, argv=list(map(str, command)), work=data['analysis_work']))
        (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
        values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                  for v in data['values']}
        return values, data['analysis_work']['memory']

    for count in (16, 32, 64):
        globals_ = 'target datalayout = "e-p:64:64"\n' + '\n'.join(
            f'@t{i} = internal global i8 0' for i in range(count))
        globals_ += f'\n@data = internal global [{count} x ptr] zeroinitializer\n'
        globals_ += f'@targets = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr @t{i}' for i in range(count)) + ']\n'
        globals_ += f'@addresses = internal constant [{count} x ptr] [' + ', '.join(
            f'ptr getelementptr (ptr, ptr @data, i64 {i})' for i in range(count)) + ']\n'
        blocks = {'entry': 'br label %body', 'body': '''
 %vp = getelementptr ptr, ptr @targets, i64 %index
 %v = load ptr, ptr %vp
 %dst = getelementptr ptr, ptr @data, i64 %index
 store ptr %v, ptr %dst
 %ap = getelementptr ptr, ptr @addresses, i64 %index
 %locations = load ptr, ptr %ap
 %r = load ptr, ptr %locations
 br label %exit''', 'exit': 'ret ptr %r'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        for order in ('original', 'functions', 'blocks'):
            block_order = ('entry', 'exit', 'body') if order == 'blocks' else ('entry', 'body', 'exit')
            top = 'define ptr @top(i64 %index) {\n' + '\n'.join(
                b + ':\n ' + blocks[b] for b in block_order) + '\n}\n'
            values, memory = analyse(f'{count}-{order}', globals_ + (
                top + helper if order == 'functions' else helper + top))
            assert values['top', '%r'] == (True, sorted(f'PTR(@t{i},0,0)' for i in range(count))), values
            domains.append(values)
            assert memory['load_image_computations'] == 3, memory
            assert memory['load_signature_hits'] == count - 1, memory
            assert memory['load_image_union_skips'] == 2 * (count - 1), memory
        assert domains[0] == domains[1] == domains[2], (count, 'evaluation order')

    for (endian, expected), count in product(
            (('e', (1, 2, 513, 770)), ('E', (4, 3, 1027, 770))), (16, 32, 64)):
        unrelated = '\n'.join(f'@unrelated{i} = internal global i8 0' for i in range(count))
        values, memory = analyse(f'immutable-{endian}-{count}',
            f'target datalayout = "{endian}-p:64:64"\n' + unrelated + '\n' + '''
@word = internal constant i32 67305985
define void @top() {
 %a = load i8, ptr @word, align 1
 %b = load i8, ptr getelementptr (i8, ptr @word, i64 1), align 1
 %c = load i16, ptr @word, align 1
 %d = load i16, ptr getelementptr (i8, ptr @word, i64 1), align 1
 %missing = load i16, ptr getelementptr (i8, ptr @word, i64 64), align 1
 ret void
}
''')
        for name, number in zip(('%a', '%b', '%c', '%d'), expected):
            assert values['top', name] == (False, [f'INT({number})']), values
        assert values['top', '%missing'] == (True, []), values
        # Four valid reads inspect 1+1+2+2 bytes of the one matching slot.
        # The out-of-object address has no candidate byte slot to inspect.
        assert memory['load_byte_slot_tests'] == 6, memory
    values, _ = analyse('invalidation', '''target datalayout = "e-p:64:64"
@cell = internal global ptr null
@a = internal global i8 0
@b = internal global i8 0
define void @top() {
 store ptr @a, ptr @cell
 %x = load ptr, ptr @cell
 store ptr @b, ptr @cell
 %y = load ptr, ptr @cell
 ret void
}
''')
    for name in ('%x', '%y'):
        assert values['top', name] == (False, ['INT(0)', 'PTR(@a,0,0)', 'PTR(@b,0,0)']), values
    values, _ = analyse('interval-class', '''target datalayout = "e-p:64:64"
@cell = internal global ptr null
@a = internal global i8 0
define void @top(i64 %index) {
 %v = select i1 true, ptr null, ptr @a
 %dst = getelementptr [2 x ptr], ptr @cell, i64 %index
 store ptr %v, ptr %dst
 %whole = load ptr, ptr @cell, align 1
 %p = getelementptr i8, ptr @cell, i64 4
 %part = load ptr, ptr %p, align 1
 ret void
}
''')
    assert values['top', '%whole'] == (False, ['INT(0)', 'PTR(@a,0,0)']), values
    assert values['top', '%part'] == (True, []), values
    values, memory = analyse('filled', '''target datalayout = "e-p:64:64"
define void @top() {
 %p = alloca [32 x i8]
 %a = load i64, ptr %p, align 1
 %q = getelementptr i8, ptr %p, i64 1
 %c = load i64, ptr %q, align 1
 ret void
}
''')
    assert values['top', '%a'] == values['top', '%c'] == (False, ['INT(0)']), values
    assert memory['load_image_computations'] == 1 and memory['load_signature_hits'] == 1, memory
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
