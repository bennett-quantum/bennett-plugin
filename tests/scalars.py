#!/usr/bin/env python3
"""Compare independently generated scalar objects with published object fixtures."""
import argparse,json,os,re,subprocess
from pathlib import Path
from contracts import dialect_text,SIBLINGS
R=Path(__file__).resolve().parents[1]
SPEC=SIBLINGS/'bennett-dialect-spec/spec/Bennett-Dialect-Spec.md'
REF=SIBLINGS/'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'
def run(cmd):
 try:return subprocess.run(list(map(str,cmd)),text=True,capture_output=True,timeout=60)
 except subprocess.TimeoutExpired:return subprocess.CompletedProcess(cmd,124,'','timeout after 60 seconds')
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--step-check',action='store_true');p.add_argument('--case',action='append');a=p.parse_args()
 spec=dialect_text();objects=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',spec,re.S))
 maps=dict(re.findall(r'```text linkmap=([^\n ]+)\n(.*?)```',spec,re.S))
 stated_hashes=dict(re.findall(r'```text hash=([^\n ]+)\n(.*?)```',spec,re.S))
 runs=dict(re.findall(r'```text run=([^\n ]+)\n(.*?)```',spec,re.S))
 results=[]
 for tag,body in re.findall(r'```llvm (lift=[^\n]+)\n(.*?)```',spec,re.S):
  fields={k:v.strip(chr(34)) for k,v in re.findall(r'([\w]+)=([^ ]+)',tag)};name=fields['lift']
  if a.case and name not in a.case:continue
  # Enumerate every published lift, including explicitly unavailable mechanics.
  supported=name in ['binding-out-byte','binding-clock-read','binding-block-byte','binding-console-byte','oracle-empty-output','oracle-empty-fault','oracle-discard-return','pointer-as270','gep-index-obj','gep-index-const','inc8','add2','switch5','fp-aggregate','atomic-nand','indirectbr-two-blocks','entry-replay-byte','rung4-mini','rung8-mini','listsum']
  dest=R/f'.tmp/scalars/{a.major}/{name}';dest.mkdir(parents=True,exist_ok=True)
  primitives={'__bennett_nz_fault':'void @__bennett_nz_fault(i64)','__bennett_nz_alloc':'ptr @__bennett_nz_alloc(i64)','__bennett_nz_free':'void @__bennett_nz_free(ptr)'}
  for n,sig in primitives.items():
   if '@'+n in body and not re.search(r'(?:define|declare) [^\n]*@'+n+r'\(',body):body+='\ndeclare '+sig+'\n'
  # Published comparison-link addresses are driver input, never inferred from names.
  for j,(fn,addr) in enumerate(re.findall(r'function @([^ ]+) A=0x([a-fA-F0-9]+)',maps.get(name,''))):
   body=re.sub(r'(define [^\n]*@'+re.escape(fn)+r'\([^\n]*?\)) \{',r'\1 !bennett.address !'+str(900+j)+' {',body)
   body+='\n!'+str(900+j)+' = !{i64 '+str(int(addr,16))+'}\n'
  src=dest/'input.ll';src.write_text(body)
  stack=re.search(r'stack (?:max |max=|)(\d+)',maps.get(name,''))
  if not stack:stack=re.search(r'stack\s+(\d+)',maps.get(name,''))
  cells=int(stack[1]) if stack else 32
  cmd=[f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle='+fields['region'][1:],'-bennett-scalar-shape='+re.sub(r'MEM_IN\((\d+)\)',lambda m:'MEM_IN('+str(1<<int(m[1]))+')',fields['desc']),'-bennett-scalar-stack='+str(cells),'-bennett-scalar-heap='+str(int(re.search(r'heap_limit_max=(\d+)',maps.get(name,''))[1]) if re.search(r'heap_limit_max=(\d+)',maps.get(name,'')) else 0),'-bennett-out='+str(dest),'-disable-output',str(src)]
  (dest/'ref.bennett').unlink(missing_ok=True)
  x=run(cmd);row={'name':name,'lowered':x.returncode==0}
  if x.returncode:
   row['error']=x.stderr[-1500:]
   row['deferred']=not supported and 'unimplemented:' in x.stderr and 'milestone 2' in x.stderr
   results.append(row);continue
  obj=dest/'ref.bennett';check=run([REF,'check',obj]);row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
  hashes=run([REF,'hash',obj]);row['hashes']=hashes.stdout.strip()
  row['fixture_equal']=obj.read_bytes()==objects[name].encode()
  actual=json.loads(hashes.stdout) if hashes.returncode==0 else {}
  row['hash_fixture_equal']=all(actual.get('symbols',{}).get(n,{}).get('interface_hash')==h for n,h in re.findall(r'^([^ ]+) ([a-f0-9]{64})$',stated_hashes.get(name,''),re.M))
  row['object_hash']=actual.get('object_hash')
  executions=[]
  for line in runs.get(name,'').splitlines():
   expected=re.search(r'budget=([^ ]+) -> code=(\d+) payload=(\d+) steps=(\d+)',line)
   if not expected:continue
   budget,code,payload,steps=expected.groups();inp=re.search(r'input=([^ ]*)',line)[1]
   argv=[REF,'run-oracle',obj,'ref','--input',inp,'--budget',budget]
   for v in re.findall(r'arg=([^ ]+)',line):argv+=['--arg',v]
   for v in re.findall(r'mem=([^ ]+)',line):argv+=['--mem',v.replace(':','=',1)]
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
 cdir=R/f'.tmp/scalars/{a.major}/c-inc8';cdir.mkdir(parents=True,exist_ok=True)
 csrc=cdir/'inc8.c';csrc.write_text('unsigned char inc8(unsigned char x) { return (unsigned char)(x + 1); }\n')
 cll=cdir/'inc8.ll';cc=run([f'/usr/lib/llvm-{a.major}/bin/clang','-O3','-emit-llvm','-S',csrc,'-o',cll])
 lower=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=default<O3>,bennett','-bennett-dialect=0.2.10','-bennett-oracle=inc8','-bennett-scalar-shape=IN(8,zext);tgt=8','-bennett-scalar-stack=7','-bennett-out='+str(cdir),'-disable-output',cll]) if cc.returncode==0 else cc
 c_ok=lower.returncode==0 and (cdir/'ref.bennett').read_bytes()==objects['inc8'].encode()
 report={'major':a.major,'c_inc8_equal':c_ok,'objects':results,'deferred':[x['name'] for x in results if x.get('deferred')], 'passed':sum(x.get('check',False) and x.get('fixture_equal',False) and x.get('hash_fixture_equal',False) and all(y['ok'] for y in x.get('runs',[])) for x in results)}
 (R/f'.tmp/scalars-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 return report['passed']+len(report['deferred'])!=len(results) or not c_ok
if __name__=='__main__':raise SystemExit(main())
