#!/usr/bin/env python3
"""Production environment obligations of bp-dw4. Failures are never deferrals."""
import argparse,hashlib,json,shutil
from production import run, REF
from contracts import ROOT as R
DECL='''
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
declare void @__bennett_oracle(ptr, ptr, ptr)
declare void @__bennett_inplace(ptr, ptr, ptr, ptr)
'''
def descriptor(fields):
 return '\n'.join(f'%p{i} = getelementptr i8, ptr %desc, i64 {off}\n store {ty} {v}, ptr %p{i}' for i,(off,ty,v) in enumerate(fields))
def program(region,params=(),devices=(),target='null',calls=None,extra=''):
 fields=[(0,'i32','2'),(4,'i32',str(len(params))),(8,'i32',str(len(devices))),(12,'i32','0'),(16,'ptr',target),(24,'ptr','%fault')]
 for i,(kind,q,size) in enumerate(params):fields.extend([(32+32*i,'i32',str(kind)),(36+32*i,'i32','0'),(40+32*i,'ptr',q),(48+32*i,'i64','0'),(56+32*i,'i64',str(size))])
 for i,(model,q,value) in enumerate(devices):
  off=32+32*len(params)+24*i;fields.extend([(off,'i32',str(model)),(off+4,'i32','0'),(off+8,'ptr',q),(off+16,'i64',str(value))])
 return region+'''\ndefine void @top() {
 %x = call ptr @__bennett_qalloc(i64 0, i64 8)
 %y = call ptr @__bennett_qalloc(i64 0, i64 8)
 %fault = call ptr @__bennett_qalloc(i64 0, i64 4)
 %desc = alloca [256 x i8]
'''+extra+'\n'+descriptor(fields)+'\n'+(calls or '\n'.join(['call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)']*2))+'''
 call void @__bennett_qfree(ptr %fault)
 call void @__bennett_qfree(ptr %y)
 call void @__bennett_qfree(ptr %x)
 ret void
}
'''+DECL

def sources():
 old=json.loads((R/'docs/verification.json').read_text())['seventh_pass']['remaining_production_probes']['runs']['18']['memory-handle']['source']
 return {
 'memory-handle':old,
 'retired-handle':old.replace(' call void @__bennett_gate(i32 1, ptr %q, i64 0)', ' call void @__bennett_qfree(ptr %q)\n call void @__bennett_gate(i32 1, ptr %q, i64 0)',1),
 'helper-handle':'''define internal ptr @helper(ptr %q) { ret ptr %q }
define void @top() {
 %x = call ptr @__bennett_qalloc(i64 0, i64 1)
 %q = call ptr @helper(ptr %x)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_qfree(ptr %q)
 ret void
}
'''+DECL,
 'combined-devices':program('@__bennett_dev_clock_c = internal global i64 0\ndefine internal i8 @f() { %c = load i64, ptr @__bennett_dev_clock_c\n %v = trunc i64 %c to i8\n ret i8 %v }',devices=[(3,'null',3),(4,'null',0)],target='%x'),
 'multiple-outputs':program('define internal void @f(ptr %p, ptr %q) { store i8 1, ptr %p\n store i8 2, ptr %q\n ret void }',params=[(4,'%x',1),(4,'%y',1)]),
 'heterogeneous-layouts':program('@a = constant i8 1\n@b = constant i64 2\ndefine internal i8 @f() { %v = load i8, ptr @a\n ret i8 %v }\ndefine internal i8 @g() { %v = load i64, ptr @b\n %r = trunc i64 %v to i8\n ret i8 %r }',target='%x',calls='\n'.join(f'call void @__bennett_oracle(ptr @{f}, ptr null, ptr %desc)' for f in ['f','g','g','f'])),
 'pointer-layouts':program('@a = constant i8 1\n@b = constant i64 2\n@pa = constant ptr @a\n@pb = constant ptr @b\ndefine internal i8 @f() { %p = load ptr, ptr @pa\n %v = load i8, ptr %p\n ret i8 %v }\ndefine internal i8 @g() { %p = load ptr, ptr @pb\n %v = load i64, ptr %p\n %r = trunc i64 %v to i8\n ret i8 %r }',target='%x',calls='\n'.join(f'call void @__bennett_oracle(ptr @{f}, ptr null, ptr %desc)' for f in ['f','g','g','f'])),
 'return-console':program('@__bennett_dev_console_buf = internal global ptr null\n@__bennett_dev_console_L = internal global i64 0\n@__bennett_dev_console_n = internal global i64 0\ndefine internal i8 @f() { %p = load ptr, ptr @__bennett_dev_console_buf\n store i8 2, ptr %p\n store i64 1, ptr @__bennett_dev_console_n\n ret i8 1 }',devices=[(4,'%y',0)],target='%x'),
 'inplace-inout':program('define internal i8 @f(i8 %x) { %v = add i8 %x, 1\n ret i8 %v }\ndefine internal i8 @g(i8 %x) { %v = sub i8 %x, 1\n ret i8 %v }',params=[(5,'%x',0)],calls='call void @__bennett_inplace(ptr @f, ptr @g, ptr null, ptr %desc)\ncall void @__bennett_inplace(ptr @g, ptr @f, ptr null, ptr %desc)'),
 }
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--case',action='append');a=p.parse_args()
 d=R/f'.tmp/production-environments/{a.major}';d.mkdir(parents=True,exist_ok=True);cases=[]
 for name,source in sources().items():
  if a.case and name not in a.case:continue
  if name in ['combined-devices','multiple-outputs','return-console','heterogeneous-layouts','pointer-layouts']:
   source=source.replace('define void @top()', 'define i8 @top()').replace(' ret void\n}\n\ndeclare', ' ret i8 %observed\n}\n\ndeclare')
   call='call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)'
   observation='%a = call i1 @__bennett_measure(ptr %x, i64 0)\n %az = zext i1 %a to i8\n'
   if name in ['multiple-outputs','return-console']:observation+='%b = call i1 @__bennett_measure(ptr %y, i64 1)\n %bz = zext i1 %b to i8\n %bs = shl i8 %bz, 1\n %observed = or i8 %az, %bs'
   else:observation+='%observed = or i8 %az, 0'
   if name in ['heterogeneous-layouts','pointer-layouts']:
    call='call void @__bennett_oracle(ptr @g, ptr null, ptr %desc)'
    observation=observation.replace('ptr %y, i64 1','ptr %x, i64 1') if '%b =' in observation else '%a = call i1 @__bennett_measure(ptr %x, i64 0)\n %b = call i1 @__bennett_measure(ptr %x, i64 1)\n %az = zext i1 %a to i8\n %bz = zext i1 %b to i8\n %bs = shl i8 %bz, 1\n %observed = or i8 %az, %bs'
   source=source.replace(call,call+'\n '+observation,1)+'\ndeclare i1 @__bennett_measure(ptr, i64)\n'
  dest=d/name;shutil.rmtree(dest,ignore_errors=True);dest.mkdir();ll=dest/'input.ll';ll.write_text(source);out=dest/'out'
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-scalar-stack=128','-bennett-budget-default=1000,32,128,8,0','-bennett-out='+str(out),'-disable-output',ll]);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr};cases.append(row)
  if z.returncode:continue
  obj=out/'top/launch.bennett';c=run([REF,'check',obj]);row['check']=c.returncode==0;row['check_output']=c.stdout+c.stderr
  row['objects']=[{'path':str(x.relative_to(R)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(out.rglob('*.bennett'))]
  nt=len(json.loads((out/'top/build.json').read_text())['budgets']);z=run([REF,'run-program',obj,'top','--args',','.join(['1000']*nt),'--budget','100000,32,128,8']);row['run_output']=z.stdout+z.stderr;v=json.loads(z.stdout) if z.returncode==0 else {};row['run']=v.get('status')==('FAILED' if name=='retired-handle' else 'COMPLETED') and (name!='retired-handle' or v.get('fault')==4)
  if name in ['combined-devices','multiple-outputs','return-console','heterogeneous-layouts','pointer-layouts']:
   row['run']=row['run'] and v.get('results')==[{'type':'i8','value':str(1 if name=='combined-devices' else 3)}]
   z=run([REF,'run-program',obj,'top','--args',','.join(['0']*nt),'--budget','100000,32,128,8']);v=json.loads(z.stdout) if z.returncode==0 else {};row['common_failure_output']=z.stdout+z.stderr;row['common_failure']=v.get('status')=='COMPLETED' and v.get('results')==[{'type':'i8','value':'0'}];row['run']=row['run'] and row['common_failure']
 report={'major':a.major,'cases':cases};(R/f'.tmp/production-environments-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not all(x.get('check') and x.get('run') for x in cases)
if __name__=='__main__':raise SystemExit(main())
