"""Shape-field regressions for bp-kv5, executed by production_dispatch.py."""
import hashlib,json,re,shutil
from production import run,REF
from contracts import ROOT as R,dialect_text
from production_environments import program

def cases():
 def observe(src,first,q='%x',bit=0):
  return src.replace('define void @top()', 'define i1 @top(i1 %choose)').replace(' ret void\n}\n\ndeclare',' ret i1 %seen\n}\n\ndeclare').replace(first,first+f'\n %seen = call i1 @__bennett_measure(ptr {q}, i64 {bit})',1)+'\ndeclare i1 @__bennett_measure(ptr, i64)\n'
 call='call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)'
 f='define internal i8 @f() { ret i8 1 }'
 # Function pointer selection and a no-match pointer, including storage/load.
 src=program(f+'\ndefine internal i8 @g() { ret i8 2 }',target='%x',extra='%fn = select i1 %choose, ptr @f, ptr @g',calls='\n'.join([call.replace('@f','%fn')]*2))
 src=observe(src,call.replace('@f','%fn'))
 yield 'candidate-select',src,[(0,0),(1,1)],None
 yield 'candidate-no-match',src.replace('ptr @f, ptr @g','ptr @f, ptr null'),[(0,None),(1,1)],None
 yield 'candidate-memory',src.replace('%desc = alloca', '%fp = alloca ptr\n %desc = alloca').replace('call void @__bennett_oracle(ptr %fn','store ptr %fn, ptr %fp\n %loaded = load ptr, ptr %fp\n call void @__bennett_oracle(ptr %loaded',1),[(0,0),(1,1)],None
 # Descriptor bytes changed in a predecessor block, reread at every marker.
 loop=program(f,target='%x',calls='br label %loop\nloop:\n %n = phi i32 [ 0, %0 ], [ %next, %loop ]\n'+call+'\n'+call+'\n %next = add i32 %n, 1\n %again = icmp ult i32 %next, 2\n br i1 %again, label %loop, label %exit\nexit:')
 yield 'descriptor-loop',observe(loop,call),[(0,1),(1,1)],None
 # Pointer descriptors selected at runtime, with fields in predecessor memory.
 src=program(f,target='%x')
 stores=src[src.index('%p0 ='):src.index('\n'+call)]
 clone=re.sub(r'%p(\d+)',r'%s\1',stores).replace('%desc','%second')
 src=src.replace('%desc = alloca [256 x i8]', '%desc = alloca [256 x i8]\n %second = alloca [256 x i8]').replace('\n'+call,'\n'+call,1)
 src=src.replace('\n'+call,'\n'+clone+'\n %which = select i1 %choose, ptr %desc, ptr %second\n'+call,1).replace('ptr null, ptr %desc)','ptr null, ptr %which)')
 yield 'descriptor-select',observe(src,call.replace('%desc','%which')),[(0,1),(1,1)],None
 global_desc=src.replace('%desc = alloca [256 x i8]','').replace('ptr %desc','ptr @desc').replace('ptr %desc,','ptr @desc,')
 yield 'descriptor-global','@desc = internal global [256 x i8] zeroinitializer\n'+observe(global_desc,call.replace('%desc','%which')),[(0,1),(1,1)],None
 phi=src.replace('%which = select i1 %choose, ptr %desc, ptr %second','br i1 %choose, label %left, label %right\nleft:\n br label %join\nright:\n br label %join\njoin:\n %which = phi ptr [ %desc, %left ], [ %second, %right ]')
 yield 'descriptor-phi',observe(phi,call.replace('%desc','%which')),[(0,1),(1,1)],None
 # Different register identities/widths; finite sizes must follow the selected q.
 region='define internal i8 @f(ptr %p) { %v = load i8, ptr %p\n ret i8 %v }'
 src=program(region,params=[(3,'%q','%size')],target='%t',extra='%t = call ptr @__bennett_qalloc(i64 0, i64 8)\n %q = select i1 %choose, ptr %x, ptr %y\n %size = select i1 %choose, i64 1, i64 2',calls='\n'.join([call]*2)+'\n call void @__bennett_qfree(ptr %t)')
 src=src.replace('%y = call ptr @__bennett_qalloc(i64 0, i64 8)','%y = call ptr @__bennett_qalloc(i64 0, i64 16)')
 src=src.replace('%size = select', 'call void @__bennett_gate(i32 1, ptr %q, i64 0)\n %size = select').replace('call void @__bennett_qfree(ptr %y)', 'call void @__bennett_gate(i32 1, ptr %q, i64 0)\n call void @__bennett_qfree(ptr %y)')
 yield 'memory-width-size',observe(src,call,'%t'),[(0,1),(1,1)],None
 yield 'runtime-size',observe(src.replace('%size = select i1 %choose, i64 1, i64 2','%size = add i64 %requested, 0'),call,'%t').replace('i1 %choose','i64 %requested').replace('%q = select i64 %requested, ptr %x, ptr %y','%q = select i1 true, ptr %x, ptr %y'),[(1,1),(2,None),(99,None)],None
 yield 'bad-size',observe(src.replace('i64 1, i64 2','i64 3, i64 2'),call,'%t'),[(0,1),(1,None)],None
 src=program('define internal i8 @f(i8 %v) { ret i8 %v }',params=[(1,'%q',0)],target='%t',extra='%t = call ptr @__bennett_qalloc(i64 0, i64 8)\n %q = select i1 %choose, ptr %x, ptr %y',calls='\n'.join([call]*2)+'\n call void @__bennett_qfree(ptr %t)')
 src=src.replace('%x = call ptr @__bennett_qalloc(i64 0, i64 8)','%x = call ptr @__bennett_qalloc(i64 0, i64 4)')
 src=src.replace('%q = select i1 %choose, ptr %x, ptr %y','%q = select i1 %choose, ptr %x, ptr %y\n call void @__bennett_gate(i32 1, ptr %q, i64 0)').replace('call void @__bennett_qfree(ptr %y)', 'call void @__bennett_gate(i32 1, ptr %q, i64 0)\n call void @__bennett_qfree(ptr %y)')
 yield 'input-width',observe(src,call,'%t'),[(0,1),(1,1)],None
 yield 'retired-descriptor-handle',observe(src.replace('call void @__bennett_gate(i32 1, ptr %q, i64 0)','').replace('call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)', 'call void @__bennett_qfree(ptr %q)\n call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)',1),call,'%t'),[(0,None),(1,None)],None
 # A finite allocation-width set at one source root (both execution arms).
 src=program('define internal i8 @f(i8 %v) { ret i8 %v }',params=[(1,'%x',0)],target='%y',extra='',calls='\n'.join([call]*2))
 src=src.replace(' %x = call ptr @__bennett_qalloc(i64 0, i64 8)',' %width = select i1 %choose, i64 4, i64 8\n %x = call ptr @__bennett_qalloc(i64 0, i64 %width)')
 yield 'allocation-width',observe(src,call,'%y'),[(0,0),(1,0)],None
 # The same model field takes each of its four valid codes and an invalid code.
 src=program(f,devices=[('%model','%disk',0)],target='%x',extra='%disk = call ptr @__bennett_qalloc(i64 0, i64 4096)',calls='\n'.join([call]*2)+'\n call void @__bennett_qfree(ptr %disk)')
 src=observe(src,call).replace('i1 %choose','i32 %model')
 yield 'device-model',src,[(1,1),(2,1),(3,1),(4,1),(0,None),(9,None)],None
 # Runtime CLOCK initial state is a classical operand, including a full i64.
 src=program('@__bennett_dev_clock_c = internal global i64 0\ndefine internal i8 @f() { %c = load i64, ptr @__bennett_dev_clock_c\n %v = trunc i64 %c to i8\n ret i8 %v }',devices=[(3,'null','%value')],target='%x')
 yield 'clock-value',observe(src,call).replace('i1 %choose','i64 %value'),[(0,0),(3,1),(18446744073709551615,1)],None
 # Published lift goldens through a real candidate compare tree, never the
 # descriptor-reference shortcut. No published CC launch golden exists (§17.4).
 text=dialect_text()
 for name in ['binding-out-byte','binding-clock-read','binding-block-byte','binding-console-byte']:
  body=re.search(r'```llvm lift='+name+r' [^\n]*\n(.*?)```',text,re.S)[1]
  np=[(4,'%x',1)] if name=='binding-out-byte' else []
  dev={'binding-clock-read':[(3,'null',3)],'binding-block-byte':[(2,'%disk',0)],'binding-console-byte':[(4,'%x',0)]}.get(name,[])
  src=program(body,params=np,devices=dev,target='null' if name in ['binding-out-byte','binding-console-byte'] else '%x',extra='%fn = select i1 %choose, ptr @f, ptr null\n'+('%disk = call ptr @__bennett_qalloc(i64 0, i64 4096)' if name=='binding-block-byte' else ''),calls='\n'.join([call.replace('@f','%fn')]*2)+('\n call void @__bennett_qfree(ptr %disk)' if name=='binding-block-byte' else ''))
  yield name,observe(src,call.replace('@f','%fn'),bit=3 if name=='binding-console-byte' else 0),[(1,0 if name=='binding-block-byte' else 1),(0,None)],name

def execute(major,d):
 result=[]
 fixtures=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',dialect_text(),re.S))
 for name,src,inputs,golden in cases():
  dest=d/name;shutil.rmtree(dest,ignore_errors=True);dest.mkdir();ll=dest/'input.ll';ll.write_text(src);out=dest/'out'
  z=run([f'/usr/lib/llvm-{major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budget-default=1000,0,128,8,0','-bennett-out='+str(out),'-disable-output',ll])
  row={'name':name,'exit':z.returncode,'diagnostic':z.stderr,'runs':[]};result.append(row)
  if z.returncode:continue
  obj=out/'top/launch.bennett';z=run([REF,'check',obj]);row['check']=z.returncode==0;row['check_output']=z.stdout+z.stderr
  row['objects']=[{'path':str(x.relative_to(R)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(out.rglob('*.bennett'))]
  if golden:
   row['published_golden']=golden;row['reference_exact']=any(x.read_bytes()==fixtures[golden].encode() for x in out.rglob('ref.bennett'));row['check'] &= row['reference_exact']
  build=json.loads((out/'top/build.json').read_text());nt=len(build['budgets']);heap=build['layout'].get('heap_limit_max',0);stack=2**build['layout'].get('S_cells',7)
  for arg,expected in inputs:
   z=run([REF,'run-program',obj,'top','--args',','.join(map(str,[arg]+[1000]*nt)),'--budget',f'1000000,{heap},{stack},8']);v=json.loads(z.stdout) if z.returncode==0 else {}
   ok=v.get('status')=='FAILED' and v.get('fault')==4 if expected is None else v.get('status')=='COMPLETED' and v.get('results')==[{'type':'i1','value':str(expected)}]
   row['runs'].append({'arg':arg,'ok':ok,'output':z.stdout+z.stderr})
 return result
