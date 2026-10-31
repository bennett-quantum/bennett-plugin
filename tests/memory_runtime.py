#!/usr/bin/env python3
"""N26: every memory intrinsic, ordinary helper closure, logical memory and faults."""
import argparse,ctypes,json,re,subprocess,random
from contracts import ROOT as R
from scalars import REF
p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();d=R/f'.tmp/memory-runtime/{a.major}';d.mkdir(parents=True,exist_ok=True);tool=f'/usr/lib/llvm-{a.major}/bin/';plugin=R/f'build/libbennett-plugin-{a.major}.so';rows=[]
def run(args):
 z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=180);assert z.returncode==0,z.stderr;return z
source=[];cases=[]
for op in ['memcpy','memmove','memset','memcpy.inline','memset.inline','memcpy.element.unordered.atomic','memmove.element.unordered.atomic','memset.element.unordered.atomic']:
 fill=op.startswith('memset');atomic='atomic' in op;inline='inline' in op;name=op.replace('.','_');suffix='p0.i32' if fill else 'p0.p0.i32';params='ptr,i8,i32,' if fill else 'ptr,ptr,i32,';params+='i32 immarg' if atomic else 'i1 immarg'
 source.append(f'declare void @llvm.{op}.{suffix}({params})')
 args=f'ptr align 1 %d,'+('i8 %v,' if fill else 'ptr align 1 %s,')+('i32 8,' if inline else 'i32 %n,')+('i32 1' if atomic else 'i1 false')
 source.append(f'define void @{name}(ptr %d,ptr %s,i8 %v,i32 %n) {{ call void @llvm.{op}.{suffix}({args})\n ret void }}');cases.append((name,fill,inline))
if a.major==23:
 source.append('declare void @llvm.experimental.memset.pattern.p0.i16.i32(ptr,i16,i32,i1 immarg)\ndefine void @pattern(ptr %d,i16 %v,i32 %n) { call void @llvm.experimental.memset.pattern.p0.i16.i32(ptr %d,i16 %v,i32 %n,i1 false)\n ret void }')
source.append('declare void @__bennett_rt_memcpy(ptr,ptr,i64)\ndefine void @copy_helper(ptr %d,ptr %s,i8 %v,i32 %n) { %len = zext i32 %n to i64\n call void @__bennett_rt_memcpy(ptr %d,ptr %s,i64 %len)\n ret void }');cases.append(('copy_helper',False,False))
src=d/'in.ll';src.write_text('\n'.join(source));out=d/'out.ll'
run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-normalise-only','-S',src,'-o',out]);assert not re.search('call void @llvm.',out.read_text())
so=d/'memory.so';run([tool+'clang','-shared','-fPIC','-O0',out,'-o',so]);lib=ctypes.CDLL(str(so))
for name,fill,inline in cases:
 fn=getattr(lib,name);fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint8,ctypes.c_uint32]
 for dest,srcpos in [(0,1),(1,0),(0,0),(4,8)]:
  for length in ([8] if inline else [0,1,7,8]):
   value=bytearray(range(32));want=value[:]
   want[dest:dest+length]=bytes([171])*length if fill else value[srcpos:srcpos+length]
   b=ctypes.create_string_buffer(bytes(value),32);fn(ctypes.byref(b,dest),ctypes.byref(b,srcpos),171,length);assert b.raw==want,(name,dest,srcpos,length,b.raw,want)
 if not inline:fn(None,None,0,0)
 rows.append(name+'/native-overlap-zero')
if a.major==23:
 fn=lib.pattern;fn.argtypes=[ctypes.c_void_p,ctypes.c_uint16,ctypes.c_uint32];b=ctypes.create_string_buffer(16);fn(b,0xabcd,8);assert b.raw==bytes.fromhex('cdab')*8;fn(None,0,0);rows.append('pattern/typed-repeat-zero')
# Real ISA memory models and the ordinary generated helper definitions.
for op in ['memmove','memcpy','memset']:
 for dest,start,length in [(1,0,7),(0,1,7),(0,0,16),(16,16,0),(0,0,0),(12,0,8),(0,12,8)]:
  case=d/f'{op}-{dest}-{start}-{length}';case.mkdir(exist_ok=True);src=case/'in.ll';fill=op=='memset'
  src.write_text(f'''@data = internal global [16 x i8] c"\\00\\01\\02\\03\\04\\05\\06\\07\\08\\09\\0A\\0B\\0C\\0D\\0E\\0F"
declare void @__bennett_rt_{op}(ptr,{"i8" if fill else "ptr"},i64)
define internal i8 @f() {{{{
 %d = getelementptr i8,ptr @data,i64 {dest}
 %s = getelementptr i8,ptr @data,i64 {start}
 call void @__bennett_rt_{op}(ptr %d,{"i8 171" if fill else "ptr %s"},i64 {length})
 %read = getelementptr i8,ptr @data,i64 4
 %r = load i8,ptr %read,align 1
 ret i8 %r }}}}'''.replace('{{','{').replace('}}','}'))
  run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle=f','-bennett-scalar-stack=4096','-bennett-scalar-heap=4096','-bennett-scalar-shape=;tgt=8','-bennett-out='+str(case),'-disable-output',src]);obj=case/'ref.bennett';run([REF,'check',obj])
  bad=dest+length>16 or (not fill and start+length>16)
  data=json.loads(run([REF,'run-oracle',obj,'ref','--input','','--budget','100000,4096,4096,128']).stdout)
  if bad:assert data['code']!=0,data
  else:
   want=bytearray(range(16));want[dest:dest+length]=bytes([171])*length if fill else bytes(range(16))[start:start+length];assert data['code']==0 and data['payload']==want[4],data
  rows.append(case.name+'/ISA-overlap-logical-bounds')
# A popped frame is invalid even though the physical backing bytes still exist.
for zero in [False,True]:
 case=d/('dead-zero' if zero else 'dead-frame');case.mkdir(exist_ok=True);src=case/'in.ll';src.write_text(f'''declare ptr @__bennett_rt_ss_push(i64,i64)
declare void @__bennett_rt_ss_pop(ptr)
declare void @__bennett_rt_memset(ptr,i8,i64)
define internal i8 @f() {{ %p = call ptr @__bennett_rt_ss_push(i64 1,i64 1)
 call void @__bennett_rt_ss_pop(ptr %p)
 call void @__bennett_rt_memset(ptr %p,i8 42,i64 {0 if zero else 1})
 ret i8 7 }}
!llvm.module.flags = !{{!0}}
!0 = !{{i32 1,!"bennett.sstack",i64 128}}''')
 run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle=f','-bennett-scalar-shape=;tgt=8','-bennett-scalar-stack=4096','-bennett-scalar-heap=4096','-bennett-out='+str(case),'-disable-output',src]);obj=case/'ref.bennett';run([REF,'check',obj]);data=json.loads(run([REF,'run-oracle',obj,'ref','--input','','--budget','100000,4096,4096,128']).stdout);assert data['code']==(0 if zero else 7),data;rows.append(case.name+'/ISA-lifetime')
# Helpers and referenced globals participate in the key; unrelated globals do not.
def key(body):
 src=d/'key.ll';rep=d/'key.json';src.write_text(body+'\ndeclare void @__bennett_oracle(ptr,ptr,ptr)\ndefine void @host() { call void @__bennett_oracle(ptr @f,ptr null,ptr null)\n ret void }');run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(rep),'-disable-output',src]);return json.loads(rep.read_text())['regions'][0]['candidates'][0]['key']
body='declare void @__bennett_rt_memset(ptr,i8,i64)\ndefine internal i8 @f(ptr %p) { call void @__bennett_rt_memset(ptr %p,i8 42,i64 1)\n ret i8 0 }'
linked='@seed = internal global i8 VALUE\ndefine void @__bennett_rt_memset(ptr %p,i8 %v,i64 %n) { %x = load i8,ptr @seed\n store i8 %x,ptr %p\n ret void }'
assert key(body)!=key(body.replace('declare void @__bennett_rt_memset(ptr,i8,i64)',linked.replace('VALUE','7')))
assert key(body.replace('declare void @__bennett_rt_memset(ptr,i8,i64)',linked.replace('VALUE','7')))!=key(body.replace('declare void @__bennett_rt_memset(ptr,i8,i64)',linked.replace('VALUE','8')))
assert key(body)==key(body+'\n@unrelated = internal global i8 7');rows.append('key/helper-body-data-linked-precedence')
result=dict(major=a.major,cases=len(rows),passed=len(rows),results=rows);(R/f'.tmp/memory-runtime-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
