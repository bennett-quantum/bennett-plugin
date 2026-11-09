#!/usr/bin/env python3
"""§19.5/§24 bases: independent addresses, relocations and native lookup."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from contracts import ROOT, DIALECT, sibling


def sections(path):
    return {part.split('\n', 1)[0]: part.split('\n', 1)[1].strip()
            for part in path.read_text().split('\n\nsection ')[1:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', required=True, type=int)
    parser.add_argument('--plugin', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'.tmp/comparison-layout')
    args = parser.parse_args()
    directory = args.output/str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    tool = Path(f'/usr/lib/llvm-{args.major}/bin')
    plugin = args.plugin or ROOT/f'build/libbennett-plugin-{args.major}.so'
    guard = runpy.run_path(str(ROOT/'scripts/test'))['COMMAND_HANG_GUARDS_S']['native_layout']
    receipts = []

    def run(argv, code=0, binary=False):
        result = subprocess.run(list(map(str, argv)), capture_output=True,
                                text=not binary, timeout=guard)
        receipts.append(dict(argv=list(map(str, argv)), exit=result.returncode))
        (directory/'commands.json').write_text(json.dumps(receipts, indent=2)+'\n')
        assert result.returncode == code, (argv, result.returncode, result.stdout, result.stderr)
        return result.stdout

    producer = [tool/'opt', f'-load-pass-plugin={plugin}', '-passes=bennett',
                f'-bennett-dialect={DIALECT}', '-disable-output']
    source = directory/'addresses.ll'
    source.write_text('''target datalayout = "e-p:64:64-i64:64-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@bytes = constant [3 x i8] c"abc", align 1
@slot = global ptr @bytes, align 8
define i64 @addresses(i1 %which) {
 %p = load ptr, ptr @slot
 %s = select i1 %which, ptr @slot, ptr %p
 %v = ptrtoint ptr %s to i64
 ret i64 %v
}
''')
    reference = sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
    hashes = []
    # §19.5: [base,base+3), pointer at align8(base+3), heap at
    # align4096(base+16). Values below are hand-derived, not emitted oracles.
    for label, options, bases, heap, height in (
        ('default', [], (4096, 4104), 8192, 13),
        ('mapped', ['--bennett-layout-data-base=65536'], (65536, 65544), 69632, 17),
        ('unaligned', ['--bennett-layout-data-base=65537'], (65537, 65544), 69632, 17),
    ):
        out = directory/label
        run([*producer, *options, '-bennett-oracle=addresses',
             '-bennett-scalar-shape=IN(1,zext);tgt=64', f'-bennett-out={out}', source])
        obj = out/'ref.bennett'
        sec = sections(obj)
        layout = json.loads(sec['layout'])
        assert layout['globals'] == {
            'G1': dict(base=bases[0], size=3, image='G1'),
            'G2': dict(base=bases[1], size=8, image='G2')}, layout
        assert (layout['heap_base'], layout['H'], layout['null_size']) == (heap, height, 4096), layout
        images = dict(row.split() for row in sec['data'].splitlines())
        assert images == {'G1': '616263', 'G2': bases[0].to_bytes(8, 'little').hex()}, images
        run([reference, 'check', obj])  # Independent §9.2 envelope/hash verification.
        hashes.append(hashlib.sha256(obj.read_bytes()).hexdigest())
    assert len(set(hashes)) == 3, hashes

    # Internal microvectors can carry fixed layout flags. A selected data
    # base recomputes derived addresses while retaining their null-size ABI.
    flagged = directory/'flagged.ll'
    flagged.write_text(source.read_text()+'''!llvm.module.flags = !{!0,!1,!2}
!0 = !{i32 1, !"bennett.null_size", i64 256}
!1 = !{i32 1, !"bennett.heap_base", i64 4096}
!2 = !{i32 1, !"bennett.region_base", i64 8192}
''')
    out = directory/'flagged'
    run([*producer, '--bennett-layout-data-base=65536', '-bennett-oracle=addresses',
         '-bennett-scalar-shape=IN(1,zext);tgt=64', f'-bennett-out={out}', flagged])
    layout = json.loads(sections(out/'ref.bennett')['layout'])
    assert (layout['globals']['G1']['base'], layout['heap_base'], layout['H'], layout['null_size']) == (65536, 69632, 17, 256), layout
    run([reference, 'check', out/'ref.bennett'])

    # The callback is the first function in module order. The pointer image
    # and ptrtoint must use the selected text base; text is not device memory.
    program = directory/'program.ll'
    program.write_text('''target datalayout = "e-p:64:64-i64:64-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@value = global i64 41, align 8
@pointers = constant [2 x ptr] [ptr @value,ptr @callback], align 8
define internal i64 @callback(i64 %x) { ret i64 %x }
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
define i64 @program(i1 %which) {
 %q = call ptr @__bennett_qalloc(i64 0,i64 1)
 call void @__bennett_qfree(ptr %q)
 %p = getelementptr [2 x ptr], ptr @pointers, i64 0, i64 1
 %f = load ptr, ptr %p
 %s = select i1 %which, ptr %f, ptr @value
 %v = ptrtoint ptr %s to i64
 ret i64 %v
}
''')
    for label, text, heap_capacity, expected_text, height in (
        ('text', 8388608, 4096, 8388608, 17),
        ('text-above-heap', 4194304, 4194304, 6291456, 23),
    ):
        out = directory/label
        run([*producer, '--bennett-layout-data-base=65536', f'--bennett-layout-text-base={text}',
             f'-bennett-budget-default=1000,{heap_capacity},128,8,0', f'-bennett-out={out}', program])
        obj = out/'program/launch.bennett'
        sec = sections(obj)
        layout = json.loads(sec['layout'])
        assert layout['heap_base'] == 69632 and layout['heap_limit_max'] == heap_capacity, layout
        assert layout['H'] == height, layout
        assert layout['globals']['G1']['base'] == 65536, layout
        assert layout['globals']['G2']['base'] == 65544, layout
        images = dict(row.split() for row in sec['data'].splitlines())
        assert images['G2'] == (65536).to_bytes(8, 'little').hex()+expected_text.to_bytes(8, 'little').hex(), images
        run([reference, 'check', obj])
        for mode, expected in ((0, 65536), (1, expected_text)):
            result = json.loads(run([reference, 'run-program', obj, 'program', '--args', str(mode),
                                     '--budget', '1000,0,128,8']))
            assert result['status'] == 'COMPLETED' and not result['faults'], result
            assert result['results'] == [dict(type='i64', value=str(expected))], result

    heap_only = directory/'heap-only.ll'
    heap_only.write_text('''target datalayout = "e-p:64:64-i64:64-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_nz_alloc(i64)
declare void @__bennett_nz_free(ptr)
define i64 @heap_only() {
 %q = call ptr @__bennett_qalloc(i64 0,i64 1)
 call void @__bennett_qfree(ptr %q)
 %p = call ptr @__bennett_nz_alloc(i64 8)
 %v = ptrtoint ptr %p to i64
 call void @__bennett_nz_free(ptr %p)
 ret i64 %v
}
''')
    out = directory/'heap-only'
    run([*producer, '--bennett-layout-data-base=131072',
         '-bennett-budget-default=1000,4096,128,8,0', f'-bennett-out={out}', heap_only])
    obj = out/'heap_only/launch.bennett'
    layout = json.loads(sections(obj)['layout'])
    assert (layout['heap_base'], layout['H'], layout['globals']) == (131072, 18, {}), layout
    run([reference, 'check', obj])
    result = json.loads(run([reference, 'run-program', obj, 'heap_only', '--budget', '1000,4096,32,8']))
    assert result['status'] == 'COMPLETED' and not result['faults'], result
    assert result['results'] == [dict(type='i64', value='131072')], result

    # Same source table, same native and device addresses, exhaustive byte input.
    lookup = directory/'lookup.ll'
    lookup.write_text('''target datalayout = "e-p:64:64-i64:64-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@table = internal constant [8 x i8] [i8 3,i8 1,i8 4,i8 1,i8 5,i8 9,i8 2,i8 6], align 1
define i8 @r1_lookup(i8 %x) {
 %index = and i8 %x, 7
 %wide = zext i8 %index to i64
 %p = getelementptr [8 x i8], ptr @table, i64 0, i64 %wide
 %v = load i8, ptr %p
 ret i8 %v
}
''')
    out = directory/'lookup'
    # Leave room below the first section for ELF headers: GNU ld places its
    # first LOAD one page below .rodata, so 65536 alone is not host-mappable.
    run([*producer, '--bennett-layout-data-base=131072', '--bennett-layout-text-base=8388608',
         '-bennett-oracle=r1_lookup', '-bennett-scalar-shape=IN(8,sext);tgt=8',
         f'-bennett-out={out}', lookup])
    layout = json.loads(sections(out/'ref.bennett')['layout'])
    assert layout['globals']['G1'] == dict(base=131072, size=8, image='G1'), layout
    assert layout['heap_base'] == 135168, layout
    runner = directory/'runner.c'
    runner.write_text('''extern signed char r1_lookup(signed char);
void entry(void) {
 unsigned char data[256];
 for (unsigned i=0;i<256;++i) data[i]=r1_lookup((signed char)i);
 long r;
 __asm__ volatile("syscall" : "=a"(r) : "a"(1L),"D"(1L),"S"(data),"d"(256L) : "rcx","r11","memory");
 __asm__ volatile("syscall" :: "a"(60L),"D"(r==256?0L:1L) : "rcx","r11","memory");
 __builtin_unreachable();
}
__attribute__((naked,noreturn)) void _start(void) {
 __asm__("andq $-16,%rsp; call entry; ud2");
}
''')
    exe = directory/'native'
    run([tool/'clang', '-O2', '-nostdlib', '-static', '-no-pie', out/'materialised.bc', runner,
         '-Wl,--build-id=none,-e,_start,--section-start=.text=0x800000,--section-start=.rodata=0x20000',
         '-o', exe])
    names = run([tool/'llvm-nm', exe])
    assert any(line.split()[-1] == 'table' and int(line.split()[0], 16) == 131072
               for line in names.splitlines()), names
    assert any(line.split()[-1] == 'r1_lookup' and int(line.split()[0], 16) == 8388608
               for line in names.splitlines()), names
    assert run([exe], binary=True) == bytes([3, 1, 4, 1, 5, 9, 2, 6])*32
    run([reference, 'check', out/'ref.bennett'])
    print(json.dumps(dict(major=args.major, layout_cases=3, native_lookup_inputs=256)))


if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired as error:
        print(f'UNKNOWN: comparison layout hang guard: {error.cmd}')
        raise SystemExit(124) from error
