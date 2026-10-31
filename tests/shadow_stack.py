#!/usr/bin/env python3
"""N24 zero fill, logical lifetimes, saved points and cross-frame faults."""
import argparse,json,shutil
from contracts import ROOT as R
from scalars import run,REF
CASES={
 'overflow':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 129, i64 8)
 ret i8 7
}''',2,0),
 'runtime-name-is-ordinary':('''define i8 @__bennett_rt_user(ptr %p) {
 %v = load i8, ptr %p
 ret i8 %v
}
define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 8, i64 8)
 call void @__bennett_rt_ss_pop(ptr %p)
 %v = call i8 @__bennett_rt_user(ptr %p)
 ret i8 %v
}''',7,0),
 'zero-frame':('''define i8 @f() {
 %p = alloca i8
 %v = load i8, ptr %p
 ret i8 %v
}''',0,0),
 'zero-reuse':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 8, i64 8)
 store i8 77, ptr %p
 call void @__bennett_rt_ss_pop(ptr %p)
 %q = call ptr @__bennett_rt_ss_push(i64 8, i64 8)
 %v = load i8, ptr %q
 ret i8 %v
}''',0,0),
 'popped-frame':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 8, i64 8)
 call void @__bennett_rt_ss_pop(ptr %p)
 %v = load i8, ptr %p
 ret i8 %v
}''',7,0),
 'unused-capacity':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 1, i64 1)
 %q = getelementptr i8, ptr %p, i64 1
 %v = load i8, ptr %q
 ret i8 %v
}''',7,0),
 'dynamic-boundary':('''define i16 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 1, i64 1)
 %q = call ptr @__bennett_rt_ss_alloca(i64 1, i64 1)
 %r = call ptr @__bennett_rt_ss_alloca(i64 1, i64 1)
 %v = load i16, ptr %q
 ret i16 %v
}''',7,0),
 'restore-releases':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 1, i64 1)
 %s = call ptr @__bennett_rt_ss_save()
 %q = call ptr @__bennett_rt_ss_alloca(i64 1, i64 1)
 call void @__bennett_rt_ss_restore(ptr %s)
 %v = load i8, ptr %q
 ret i8 %v
}''',7,0),
 'parent-live':('''define i8 @f() {
 %p = call ptr @__bennett_rt_ss_push(i64 1, i64 1)
 store i8 7, ptr %p
 %q = call ptr @__bennett_rt_ss_push(i64 1, i64 1)
 call void @__bennett_rt_ss_pop(ptr %q)
 %v = load i8, ptr %p
 ret i8 %v
}''',0,7),
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();rows=[]
 for name,(body,code,payload) in CASES.items():
  d=R/f'.tmp/shadow-stack/{a.major}/{name}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
  for fn,sig in {'__bennett_rt_ss_push':'ptr @__bennett_rt_ss_push(i64, i64)','__bennett_rt_ss_pop':'void @__bennett_rt_ss_pop(ptr)','__bennett_rt_ss_alloca':'ptr @__bennett_rt_ss_alloca(i64, i64)','__bennett_rt_ss_save':'ptr @__bennett_rt_ss_save()','__bennett_rt_ss_restore':'void @__bennett_rt_ss_restore(ptr)'}.items():
   if '@'+fn in body:body+='\ndeclare '+sig+'\n'
  body+='\n!llvm.module.flags = !{!0}\n!0 = !{i32 1, !"bennett.sstack", i64 128}\n';src=d/'input.ll';src.write_text(body)
  width=16 if name=='dynamic-boundary' else 8
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle=f',f'-bennett-scalar-shape=;tgt={width}','-bennett-scalar-stack=4096','-bennett-scalar-heap=128','-bennett-out='+str(d),'-disable-output',src]);row={'name':name,'lowered':z.returncode==0,'diagnostic':z.stderr};rows.append(row)
  if z.returncode:continue
  obj=d/'ref.bennett';z=run([REF,'check',obj]);row['check']=z.returncode==0;row['check_output']=z.stdout+z.stderr
  z=run([REF,'run-oracle',obj,'ref','--input','','--budget','100000,128,4096,16']);row['output']=z.stdout+z.stderr
  v=json.loads(z.stdout) if z.returncode==0 else {};row['ok']=v.get('code')==code and v.get('payload')==payload
 report={'major':a.major,'cases':rows};(R/f'.tmp/shadow-stack-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not all(r.get('check') and r.get('ok') for r in rows)
if __name__=='__main__':raise SystemExit(main())
