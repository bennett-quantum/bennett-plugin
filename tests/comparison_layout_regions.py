"""Text follows the complete §19.5 layout, including oracle interfaces."""

import hashlib
import json

from production_environments import program
from comparison_layout import sections


def check_regions(directory, producer, tool, reference, run):
    directory.mkdir(parents=True, exist_ok=True)
    region = '''target datalayout = "e-p:64:64-i64:64-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
define internal i64 @callback(i64 %x) { ret i64 %x }
define internal i8 @f(ptr %p, i64 %address) {
 %v = ptrtoint ptr %p to i64
 %eq = icmp eq i64 %v, %address
 %r = zext i1 %eq to i8
 ret i8 %r
}
'''
    source = program(region, params=[(3, '%x', 16), (2, 'null', 0)], target='%y',
                     extra='%address = ptrtoint ptr @callback to i64',
                     calls='''store i64 %address, ptr %p14
 call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)
 %r = call i1 @__bennett_measure(ptr %y, i64 0)
 call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)''')
    source = source.replace('define void @top()', 'define i8 @top()').replace(
        ' ret void\n}', ' %result = zext i1 %r to i8\n ret i8 %result\n}')
    source = source.replace('%x = call ptr @__bennett_qalloc(i64 0, i64 8)',
                            '%x = call ptr @__bennett_qalloc(i64 0, i64 128)')
    ll = directory/'input.ll'
    ll.write_text(source+'\ndeclare i1 @__bennett_measure(ptr,i64)\n')
    # No globals. Heap [131072,135168); align16 gives m0=[135168,135184).
    # Selected text 135168 therefore promotes to align2097152(135184)=2097152.
    # Extract the SAME source definitions, and independently link the native
    # callback at that hand-derived text address. Neither path dereferences p.
    native_bc = directory/'native.bc'
    run([tool/'llvm-extract', '--func=f', '--func=callback', ll, '-o', native_bc])
    runner = directory/'runner.c'
    runner.write_text('''extern unsigned char f(void*,unsigned long);
extern unsigned long callback(unsigned long);
void entry(void) {
 unsigned char result=f((void*)135168,(unsigned long)&callback);
 long r;
 __asm__ volatile("syscall" : "=a"(r) : "a"(1L),"D"(1L),"S"(&result),"d"(1L) : "rcx","r11","memory");
 __asm__ volatile("syscall" :: "a"(60L),"D"(r==1?0L:1L) : "rcx","r11","memory");
 __builtin_unreachable();
}
__attribute__((naked,noreturn)) void _start(void) {
 __asm__("andq $-16,%rsp; call entry; ud2");
}
''')
    exe = directory/'native'
    run([tool/'clang', '-O2', '-nostdlib', '-static', '-no-pie', native_bc, runner,
         '-Wl,--build-id=none,-e,_start,--section-start=.text=0x200000', '-o', exe])
    symbols = run([tool/'llvm-nm', exe])
    assert any(line.split()[-1] == 'callback' and int(line.split()[0], 16) == 2097152
               for line in symbols.splitlines()), symbols
    native = run([exe], binary=True)
    assert native == bytes([0]), native
    for label, text in (('promoted', 135168), ('disjoint', 2097152)):
        out = directory/label
        run([*producer, '--bennett-layout-data-base=131072',
             f'--bennett-layout-text-base={text}', '-bennett-budget-default=1000,4096,128,8,0',
             f'-bennett-out={out}', ll])
        obj = out/'top/launch.bennett'
        sec = sections(obj)
        layout = json.loads(sec['layout'])
        assert (layout['heap_base'], layout['heap_limit_max']) == (131072, 4096), layout
        assert layout['interface_regions'] == {'ref': {'m0': {'base': 135168}}}, layout
        run([reference, 'check', obj])
        result = json.loads(run([reference, 'run-program', obj, 'top', '--args', '1000,1000',
                                 '--budget', '100000,4096,128,8']))
        assert result['status'] == 'COMPLETED' and not result['faults'], result
        assert result['results'] == [dict(type='i8', value=str(native[0]))], result
        assert 'const.i64 2097152' in sec['functions'], sec['functions']

    # Data ends at 131080, so the heap starts at 135168 and ends at 139264.
    # Two distinct oracle interfaces occupy [139264,139280),[139280,139296).
    # Even text selected at the SECOND interface must promote to 2097152.
    # Load a function pointer image and call through a finite dispatch tree;
    # the returned value and descriptor constant must use that same map.
    image_source = ll.read_text().replace('define internal i64 @callback',
                                        '@slot = constant ptr @callback, align 8\ndefine internal i64 @callback', 1)
    image_source = image_source.replace('define i8 @top()', 'define i64 @top(i1 %which)')
    image_source = image_source.replace('%address = ptrtoint ptr @callback to i64', '''%fp = load ptr, ptr @slot
 %selected = select i1 %which, ptr %fp, ptr @other
 %bits = ptrtoint ptr %selected to i64
 %address = call i64 %selected(i64 %bits)''')
    image_source = image_source.replace('ret i8 %result', 'ret i64 %address')
    image_source += '\ndefine internal i64 @other(i64 %x) { ret i64 %x }\n'
    # A second shape creates a separately reserved interface, rather than a
    # duplicate call to the already-interned first reference object.
    image_source = image_source.replace('define internal i8 @f', '''define internal i8 @g(ptr %p, i64 %address) {
 %v = ptrtoint ptr %p to i64
 %eq = icmp ne i64 %v, %address
 %r = zext i1 %eq to i8
 ret i8 %r
}
define internal i8 @f''', 1)
    image_source = image_source.replace(' call void @__bennett_qfree(ptr %fault)', ''' call void @__bennett_oracle(ptr @g, ptr null, ptr %desc)
 call void @__bennett_oracle(ptr @g, ptr null, ptr %desc)
 call void @__bennett_qfree(ptr %fault)''')
    image_ll = directory/'images.ll'
    image_ll.write_text(image_source)
    out = directory/'images'
    run([*producer, '--bennett-layout-data-base=131072', '--bennett-layout-text-base=139280',
         '-bennett-budget-default=1000,4096,128,8,0', f'-bennett-out={out}', image_ll])
    obj = out/'top/launch.bennett'
    sec = sections(obj)
    layout = json.loads(sec['layout'])
    assert layout['interface_regions'] == {'ref': {'m0': {'base': 139264}},
                                           'ref1': {'m0': {'base': 139280}}}, layout
    assert sec['data'] == 'G1 '+(2097152).to_bytes(8, 'little').hex(), sec['data']
    run([reference, 'check', obj])
    # callback is ordinal 0. Then g,f,top and six declarations precede other,
    # so its address is 2097152+10*16=2097312, independently of producer output.
    for which, expected in ((1, 2097152), (0, 2097312)):
        result = json.loads(run([reference, 'run-program', obj, 'top', '--args', f'{which},1000,1000,1000,1000',
                                 '--budget', '100000,4096,128,8']))
        assert result['status'] == 'COMPLETED' and not result['faults'], result
        assert result['results'] == [dict(type='i64', value=str(expected))], result

    error = run([*producer, '--bennett-layout-data-base=131072',
                 '--bennett-layout-text-base=9223372036854775807',
                 '-bennett-budget-default=1000,4096,128,8,0',
                 f'-bennett-out={directory}/impossible', ll], code=None)
    assert 'BD-E-COMPARISON-LAYOUT' in error and 'no comparison function address' in error, error

    # An externally supplied native map is authoritative: if its callback
    # overlaps the input region, diagnose it rather than moving device text.
    report = directory/'structure.ll'
    mapped = dict(schema='bennett-comparison-layout-1', ptr_width=64,
                  materialised_structure_sha256='0'*64, data_end=131072,
                  heap_base=131072, globals={}, functions={'callback': dict(address=2097152)})
    mapping = directory/'overlapping-map.json'
    mapping.write_text(json.dumps(mapped))
    argv = [*producer, '--bennett-layout-data-base=131072', '--bennett-layout-text-base=135168',
            f'-bennett-comparison-layout={mapping}', '-bennett-budget-default=1000,4096,128,8,0',
            f'-bennett-out={directory}/overlapping-map', ll]
    error = run([*argv, f'-bennett-comparison-structure-report={report}'], code=None)
    assert 'resolved map belongs to a different materialised module' in error, error
    mapped['materialised_structure_sha256'] = hashlib.sha256(report.read_bytes()).hexdigest()
    mapped['functions']['callback']['address'] = 135168
    mapping.write_text(json.dumps(mapped))
    error = run(argv, code=None)
    assert 'BD-E-COMPARISON-LAYOUT' in error and 'resolved function address overlaps device ranges' in error, error
    mapped['functions']['callback']['address'] = 2097152
    mapping.write_text(json.dumps(mapped))
    run(argv)
    obj = directory/'overlapping-map/top/launch.bennett'
    run([reference, 'check', obj])
    result = json.loads(run([reference, 'run-program', obj, 'top', '--args', '1000,1000',
                             '--budget', '100000,4096,128,8']))
    assert result['status'] == 'COMPLETED' and not result['faults'], result
    assert result['results'] == [dict(type='i8', value='0')], result
