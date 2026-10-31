#!/usr/bin/env python3
"""Production descriptor binding goldens, not the descriptor-reference shortcut."""
import argparse, hashlib, json, re, shutil
from production import run, REF
from contracts import ROOT as R, dialect_text

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',required=True,type=int);a=p.parse_args()
 d=R/f'.tmp/production-shapes/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 text=dialect_text();objects=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',text,re.S));cases=[]
 for name,body in re.findall(r'```llvm lift=(binding-[^ ]+) [^\n]*\n(.*?)```',text,re.S):
  if name not in ['binding-out-byte','binding-clock-read','binding-block-byte','binding-console-byte']:continue
  dest=d/name;dest.mkdir();out=dest/'out'
  output=name in ['binding-out-byte','binding-console-byte'];block=name=='binding-block-byte'
  dev={'binding-clock-read':(3,3),'binding-block-byte':(2,0),'binding-console-byte':(4,0)}.get(name)
  np=int(name=='binding-out-byte');nd=int(dev is not None)
  src=body+"""
%H = type { i32, i32, i32, i32, ptr, ptr }
%B = type { i32, i32, ptr, i64, i64 }
%D = type { i32, i32, ptr, i64 }
%Desc = type { %H, [NP x %B], [ND x %D] }
define void @top() {
 %t = call ptr @__bennett_qalloc(i64 0, i64 8)
 %fault = call ptr @__bennett_qalloc(i64 0, i64 4)
 BLOCK
 %desc = alloca %Desc
 store %Desc { %H { i32 2, i32 NP, i32 ND, i32 0, ptr TARGET, ptr %fault }, [NP x %B] PARAM, [ND x %D] DEVICE }, ptr %desc
 call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)
 call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)
 BLOCKFREE
 call void @__bennett_qfree(ptr %fault)
 call void @__bennett_qfree(ptr %t)
 ret void
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_oracle(ptr, ptr, ptr)
"""
  # Aggregate constants cannot contain local SSA operands: insertvalue constructs
  # the record, then the ordinary store tests the published memory ABI.
  src=src.replace('NP',str(np)).replace('ND',str(nd)).replace('TARGET','null' if output else '%t').replace('PARAM','[%B { i32 4, i32 0, ptr %t, i64 0, i64 1 }]' if np else 'zeroinitializer').replace('DEVICE',('[%%D { i32 %d, i32 0, ptr %s, i64 %d }]'%(dev[0],'%disk' if block else '%t' if output else 'null',dev[1])) if dev else 'zeroinitializer').replace('BLOCKFREE','call void @__bennett_qfree(ptr %disk)' if block else '').replace('BLOCK','%disk = call ptr @__bennett_qalloc(i64 0, i64 4096)' if block else '')
  # Emit individual field stores, so local SSA values are legal LLVM.
  aggregate=re.search(r' store %Desc .*?, ptr %desc',src)[0]
  stores=[]
  fields=[(0,'i32','2'),(4,'i32',str(np)),(8,'i32',str(nd)),(12,'i32','0'),(16,'ptr','null' if output else '%t'),(24,'ptr','%fault')]
  if np:fields += [(32,'i32','4'),(36,'i32','0'),(40,'ptr','%t'),(48,'i64','0'),(56,'i64','1')]
  if dev:fields += [(32+np*32,'i32',str(dev[0])),(36+np*32,'i32','0'),(40+np*32,'ptr','%disk' if block else '%t' if output else 'null'),(48+np*32,'i64',str(dev[1]))]
  for i,(offset,ty,v) in enumerate(fields):stores += [f' %p{i} = getelementptr i8, ptr %desc, i64 {offset}',f' store {ty} {v}, ptr %p{i}']
  src=src.replace(aggregate,'\n'.join(stores));(dest/'input.ll').write_text(src)
  cmd=[f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10',f'-bennett-budget-default=1000,{int(output)},128,8,0','-bennett-out='+str(out),'-disable-output',dest/'input.ll']
  z=run(cmd);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr};cases.append(row)
  if z.returncode:continue
  obj=out/'top/launch.bennett';ref=out/'top/oracle-0/ref.bennett'
  row['reference_exact']=ref.read_bytes()==objects[name].encode();row['sha256']=hashlib.sha256(obj.read_bytes()).hexdigest()
  c=run([REF,'check',obj]);row['check']=c.returncode==0;row['check_output']=c.stdout+c.stderr
  z=run([REF,'run-program',obj,'top','--args','1000,1000','--budget',f'10000,{int(output)},128,8']);row['run_output']=z.stdout+z.stderr
  row['run']=z.returncode==0 and json.loads(z.stdout)['status']=='COMPLETED'
 for name,region,bindings,alloc,desc,expected in [
  ('mem-in', 'define internal i8 @f(ptr %p) { %v = load i8, ptr %p\n ret i8 %v }', 'MEM_IN(1)', '%x = call ptr @__bennett_qalloc(i64 0, i64 8)', [(32,'i32','3'),(40,'ptr','%x'),(56,'i64','1')], None),
  ('two-regions', 'define internal i8 @f(i8 %x) { %v = add i8 %x, 1\n ret i8 %v }\ndefine internal i8 @g(i8 %x) { %v = add i8 %x, 2\n ret i8 %v }', 'IN(8,zext)', '%x = call ptr @__bennett_qalloc(i64 0, i64 8)', [(32,'i32','1'),(40,'ptr','%x')], None)]:
  dest=d/name;dest.mkdir();out=dest/'out'
  fields=[(0,'i32','2'),(4,'i32','1'),(8,'i32','0'),(12,'i32','0'),(16,'ptr','%t'),(24,'ptr','%fault'),(32,'i32','0'),(36,'i32','0'),(40,'ptr','null'),(48,'i64','0'),(56,'i64','0')]
  fields=[(off,ty,next((v for o,t,v in desc if o==off),val)) for off,ty,val in fields]
  stores='\n'.join(f'%p{i} = getelementptr i8, ptr %desc, i64 {off}\n store {ty} {val}, ptr %p{i}' for i,(off,ty,val) in enumerate(fields))
  calls='\n'.join(f'call void @__bennett_oracle(ptr @{f}, ptr null, ptr %desc)' for f in (['f','g','g','f'] if name=='two-regions' else ['f','f']))
  src=region+f'\ndefine void @top() {{\n {alloc}\n %t = call ptr @__bennett_qalloc(i64 0, i64 8)\n %fault = call ptr @__bennett_qalloc(i64 0, i64 4)\n %desc = alloca [64 x i8]\n {stores}\n {calls}\n call void @__bennett_qfree(ptr %fault)\n call void @__bennett_qfree(ptr %t)\n call void @__bennett_qfree(ptr %x)\n ret void\n}}\ndeclare ptr @__bennett_qalloc(i64, i64)\ndeclare void @__bennett_qfree(ptr)\ndeclare void @__bennett_oracle(ptr, ptr, ptr)\n'
  (dest/'input.ll').write_text(src)
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budget-default=1000,0,128,8,0','-bennett-out='+str(out),'-disable-output',dest/'input.ll']);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr};cases.append(row)
  if z.returncode:continue
  obj=out/'top/launch.bennett';row['sha256']=hashlib.sha256(obj.read_bytes()).hexdigest();c=run([REF,'check',obj]);row['check']=c.returncode==0;row['check_output']=c.stdout+c.stderr
  z=run([REF,'run-program',obj,'top','--args',','.join(['1000']*(4 if name=='two-regions' else 2)),'--budget','10000,0,128,8']);row['run_output']=z.stdout+z.stderr;row['run']=z.returncode==0 and json.loads(z.stdout)['status']=='COMPLETED'
  row['reference_exact']=None # no published paired object (bp-95o)
  row['no_published_golden']=True
 dest=d/'handle-phi';dest.mkdir();out=dest/'out'
 (dest/'input.ll').write_text("""define i8 @top(i1 %choose) {
 %x = call ptr @__bennett_qalloc(i64 0, i64 1)
 %y = call ptr @__bennett_qalloc(i64 0, i64 1)
 br i1 %choose, label %yes, label %no
yes:
 br label %join
no:
 br label %join
join:
 %q = phi ptr [ %x, %yes ], [ %y, %no ]
 %v = phi i8 [ 7, %yes ], [ 9, %no ]
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_qfree(ptr %x)
 call void @__bennett_qfree(ptr %y)
 ret i8 %v
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
""")
 z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-out='+str(out),'-disable-output',dest/'input.ll']);row={'name':'handle-phi','exit':z.returncode,'diagnostic':z.stderr,'no_published_golden':True};cases.append(row)
 if z.returncode==0:
  obj=out/'top/launch.bennett';row['sha256']=hashlib.sha256(obj.read_bytes()).hexdigest();c=run([REF,'check',obj]);row['check']=c.returncode==0;row['check_output']=c.stdout+c.stderr;row['runs']=[]
  for arg,expected in [(0,9),(1,7)]:
   z=run([REF,'run-program',obj,'top','--args',str(arg)]);v=json.loads(z.stdout) if z.returncode==0 else {};row['runs'].append({'output':z.stdout+z.stderr,'ok':v.get('status')=='COMPLETED' and v.get('results')==[{'type':'i8','value':str(expected)}]})
  row['run']=all(x['ok'] for x in row['runs'])
 report={'major':a.major,'cases':cases};(R/f'.tmp/production-shapes-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not all((x.get('reference_exact') or x.get('no_published_golden')) and x.get('check') and x.get('run') for x in cases)
if __name__=='__main__':raise SystemExit(main())
