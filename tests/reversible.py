#!/usr/bin/env python3
"""Pinned §19.2 R mode: executable successful paths with an ISA-7 verdict."""
import argparse, hashlib, json, shutil, subprocess
from contracts import ROOT as R, SIBLINGS, arith_path
from production import REF

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();m=a.major
 tool=f'/usr/lib/llvm-{m}/bin/';plugin=R/f'build/libbennett-plugin-{m}.so';rows=[]
 def run(args,code=0):
  z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=180)
  assert z.returncode==code,(args,z.returncode,z.stdout,z.stderr)
  return z
 for case,expected,status in [('r-console','68690a','0'),('r-start-exit','780a','3')]:
  d=R/f'.tmp/reversible/{m}/{case}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
  source=R/f'tests/probes/{case}.ll'
  base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','--bennett-tier=reversible','--bennett-entry=main',source]
  run([*base,'-bennett-analysis-only','-bennett-report='+str(d/'recognised.json'),'-disable-output'])
  recognised=json.loads((d/'recognised.json').read_text());assert 'R' in next(f['tiers'] for f in recognised['functions'] if f['name']=='main'),recognised
  run([*base,'-bennett-budget-default=100000,131072,4096,32,65536','-bennett-out='+str(d/'out'),'-disable-output'],3)
  for f in ['host.bc','device.bc']:run([tool+'opt','-passes=verify',d/'out'/f,'-disable-output'])
  obj=d/'out/main/launch.bennett';run([REF,'check',obj]);run([REF,'hash',obj])
  assert json.loads((d/'out/main/blockers.json').read_text())[0]['code']=='BD-B-ISA7'
  replies=d/'argv.json';replies.write_text(json.dumps([dict(service='bennett.argv',payload='00'*20,reply='00'*20)]))
  executions=[]
  for reverse in [False,True]:
   argv=[REF,'run-program',obj,'main','--budget','1000000,131072,4096,32','--replies',replies]+(['--reverse'] if reverse else [])
   value=json.loads(run(argv).stdout)
   assert value['results']==[dict(type='i32',value=status)] and not value['faults'],value
   assert b''.join(bytes.fromhex(e['bytes']) for e in value['tape']).hex()==expected,value
   if reverse:assert value['equals_entry'] and value['memory_equals_entry'] and value['console_hex']=='',value
   else:assert value['console_hex']==expected,value
   executions.append(value)
  rows.append(dict(case=case,ok=True,source_sha256=sha(source),recognised_sha256=sha(d/'recognised.json'),materialised_sha256=sha(d/'out/device.bc'),materialised_verified=True,object_sha256=sha(obj),runs=executions))
 result=dict(major=m,cases=len(rows),passed=len(rows),results=rows)
 (R/f'.tmp/reversible-{m}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
