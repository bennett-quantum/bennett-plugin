#!/usr/bin/env python3
"""Runtime descriptor selectors, including invalid runtime fields (dialect 8.4)."""
import argparse, hashlib, json, shutil
from production import run, REF
from contracts import ROOT as R

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
 d=R/f'.tmp/production-dispatch/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 old=(R/'tests/probes/finite-kind.ll').read_text()
 cases=[]
 def observed(src):
  src=src.replace('define void @top(', 'define i1 @top(').replace(' ret void\n}', ' ret i1 %observed\n}')
  first='call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)'
  src=src.replace(first,'call void @__bennett_gate(i32 1, ptr %x, i64 0)\n '+first+'\n %observed = call i1 @__bennett_measure(ptr %t, i64 0)',1)
  src=src.replace(' call void @__bennett_qfree(ptr %x)', ' call void @__bennett_gate(i32 1, ptr %x, i64 0)\n call void @__bennett_qfree(ptr %x)')
  return src+'\ndeclare i1 @__bennett_measure(ptr, i64)\ndeclare void @__bennett_gate(i32, ptr, i64)\n'

 for name,src,inputs in [
  ('finite-kind',old,[(0,True),(1,True)]),
  ('across-blocks',old.replace(' call void @__bennett_oracle(ptr @f', ' br label %invoke\ninvoke:\n call void @__bennett_oracle(ptr @f',1),[(0,True),(1,True)]),
  ('runtime-kind',old.replace(' %kind = select i1 %choose, i32 1, i32 2\n','').replace('i1 %choose','i32 %kind'),[(1,True),(2,True),(0,False),(99,False)]),
  ('runtime-arg',old.replace(' %kind = select i1 %choose, i32 1, i32 2\n','').replace('i1 %choose','i64 %value').replace('store i32 %kind','store i32 2').replace('store i64 0, ptr %p9','store i64 %value, ptr %p9'),[(0,True),(7,True),(255,True)]),
 ]:
  dest=d/name;dest.mkdir();ll=dest/'input.ll';ll.write_text(observed(src));out=dest/'out'
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budget-default='+('1000,4096,128,8,0' if name=='across-blocks' else '1000,0,128,8,0'),'-bennett-out='+str(out),'-disable-output',ll]);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr,'runs':[]};cases.append(row)
  if z.returncode:continue
  obj=out/'top/launch.bennett';c=run([REF,'check',obj]);row['check']=c.returncode==0;row['check_output']=c.stdout+c.stderr
  row['objects']=[{'path':str(x.relative_to(R)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(out.rglob('*.bennett'))]
  build=json.loads((out/'top/build.json').read_text());nt=len(build['budgets'])
  for arg,success in inputs:
   z=run([REF,'run-program',obj,'top','--args',','.join(map(str,[arg]+[1000]*nt)),'--budget',('100000,4096,128,8' if name=='across-blocks' else '100000,0,128,8')]);v=json.loads(z.stdout) if z.returncode==0 else {};status=v.get('status','');row['runs'].append({'arg':arg,'exit':z.returncode,'output':z.stdout+z.stderr,'ok':(status=='COMPLETED' and v.get('results')==[{'type':'i1','value':str((arg+1)&1 if name=='runtime-arg' else (1-arg if name in ['finite-kind','across-blocks'] else int(arg!=1)))}]) if success else (status=='FAILED' and 'trap' in (z.stdout+z.stderr).lower())})
 from general_dispatch import execute
 cases.extend(execute(a.major,d))
 report={'major':a.major,'cases':cases};(R/f'.tmp/production-dispatch-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not all(x.get('check') and all(r['ok'] for r in x['runs']) for x in cases)
if __name__=='__main__':raise SystemExit(main())
