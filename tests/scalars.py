#!/usr/bin/env python3
"""Compare independently generated scalar objects with published object fixtures."""
import argparse,json,os,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
SPEC=R.parent/'bennett-dialect-spec/spec/Bennett-Dialect-Spec.md'
REF=R.parent/'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'
def run(cmd):return subprocess.run(list(map(str,cmd)),text=True,capture_output=True,timeout=60)
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--step-check',action='store_true');a=p.parse_args()
 spec=SPEC.read_text();objects=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',spec,re.S))
 maps=dict(re.findall(r'```text linkmap=([^\n ]+)\n(.*?)```',spec,re.S))
 runs=dict(re.findall(r'```text run=([^\n ]+)\n(.*?)```',spec,re.S))
 results=[]
 for tag,body in re.findall(r'```llvm (lift=[^\n]+)\n(.*?)```',spec,re.S):
  fields=dict(re.findall(r'([\w]+)=([^ ]+)',tag));name=fields['lift']
  # Scalar fixtures only; memory/effects/FP/indirectbr are scheduled mechanics.
  if name not in ['oracle-empty-output','oracle-empty-fault','oracle-discard-return','pointer-as270','gep-index-obj','gep-index-const','inc8','add2','switch5']:continue
  dest=R/f'.tmp/scalars/{a.major}/{name}';dest.mkdir(parents=True,exist_ok=True)
  src=dest/'input.ll';src.write_text(body+('\ndeclare void @__bennett_nz_fault(i64)\n' if '@__bennett_nz_fault' in body else ''))
  stack=re.search(r'stack (?:max |max=|)(\d+)',maps.get(name,''))
  if not stack:stack=re.search(r'stack\s+(\d+)',maps.get(name,''))
  cells=int(stack[1]) if stack else 32
  cmd=[f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.6','-bennett-oracle='+fields['region'][1:],'-bennett-scalar-shape='+fields['desc'],'-bennett-scalar-stack='+str(cells),'-bennett-out='+str(dest),'-disable-output',str(src)]
  x=run(cmd);row={'name':name,'lowered':x.returncode==0}
  if x.returncode:row['error']=x.stderr[-1500:];results.append(row);continue
  obj=dest/'ref.bennett';check=run([REF,'check',obj]);row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
  hashes=run([REF,'hash',obj]);row['hashes']=hashes.stdout.strip()
  row['fixture_equal']=obj.read_text().strip()==objects[name].strip()
  executions=[]
  for line in runs.get(name,'').splitlines():
   expected=re.search(r'budget=([^ ]+) -> code=(\d+) payload=(\d+) steps=(\d+)',line)
   if not expected:continue
   budget,code,payload,steps=expected.groups();inp=re.search(r'input=([^ ]*)',line)[1]
   argv=[REF,'run-oracle',obj,'ref','--input',inp,'--budget',budget]
   for v in re.findall(r'arg=([^ ]+)',line):argv+=['--arg',v]
   z=run(argv);text=z.stdout+z.stderr
   try:
    data=json.loads(z.stdout);ok=all(str(data[k])==v for k,v in [('code',code),('payload',payload),('steps',steps)])
   except (ValueError,KeyError):ok=False
   executions.append({'input':inp,'budget':budget,'ok':bool(ok),'output':text.strip()})
  if a.step_check and name in ['inc8','add2','switch5']:
   budgets={'inc8':'5,0,7,1','add2':'6,0,9,1','switch5':'18,0,32,1'}
   z=run([REF,'step-check',obj,'ref','--exhaustive','--max-bits','16','--budget',budgets[name]])
   executions.append({'step_check':True,'ok':z.returncode==0,'output':z.stdout+z.stderr})
  row['runs']=executions;results.append(row)
 report={'major':a.major,'objects':results,'passed':sum(x.get('check',False) and x.get('fixture_equal',False) and all(y['ok'] for y in x.get('runs',[])) for x in results)}
 (R/f'.tmp/scalars-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 return report['passed']!=len(results)
if __name__=='__main__':raise SystemExit(main())
