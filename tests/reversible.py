#!/usr/bin/env python3
"""Pinned §19.2 R mode: executable successful paths with an ISA-7 verdict."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
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
 for case,expected,status in [('r-console','68690a','0'),('r-start-exit','780a','3'),('r-callback','78','0'),('r-asm','78','0')]:
  d=R/f'.tmp/reversible/{m}/{case}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
  source=R/f'tests/probes/{case}.ll'
  base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.13','--bennett-tier=reversible','--bennett-entry=main',source]
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
  if case=='r-asm':
   replies.write_text(json.dumps([dict(service='bennett.argv',payload='00'*20,reply='01000000'+'00'*16)]))
   value=json.loads(run([REF,'run-program',obj,'main','--budget','1000000,131072,4096,32','--replies',replies]).stdout)
   assert value['status']=='FAILED' and value['console_hex']=='',value
   assert 'unlisted-op' in (d/'out/main/build.json').read_text()
   assert any(e['source']=='dialect-0.2.13:N31' and 'unlisted-op' in e['reason'] for e in json.loads((d/'out/main/coverage.json').read_text())['entries'])
   replies.write_text(json.dumps([dict(service='bennett.argv',payload='00'*20,reply='00'*20)]))
  rows.append(dict(case=case,ok=True,source_sha256=sha(source),recognised_sha256=sha(d/'recognised.json'),materialised_sha256=sha(d/'out/device.bc'),materialised_verified=True,object_sha256=sha(obj),runs=executions))
 # §17.6: budget checks precede each source effect and the final return.
 for limit,prefix in [(0,''),(1,'78'),(2,'78')]:
  d=R/f'.tmp/reversible/{m}/budget-{limit}';d.mkdir(parents=True,exist_ok=True)
  source=R/'tests/probes/r-budget.ll'
  run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.13','--bennett-tier=reversible','--bennett-entry=main',source,f'-bennett-budget-default={limit},131072,4096,32,65536','-bennett-out='+str(d/'out'),'-disable-output'],3)
  obj=d/'out/main/launch.bennett';run([REF,'check',obj])
  value=json.loads(run([REF,'run-program',obj,'main','--budget','1000000,131072,4096,32','--replies',replies]).stdout)
  assert value['console_hex']==prefix,value
  assert value['status']==('COMPLETED' if limit==2 else 'FAILED'),value
  rows.append(dict(case=f'budget-{limit}',ok=True,object_sha256=sha(obj),result=value,typed_fault_implemented=False))
 # Full ordinary musl program: both majors must pass vector intrinsic lowering
 # and emit checked R artifacts. Typed budget faults remain the ISA-7 blocker.
 d=R/f'.tmp/reversible/{m}/r-hello';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 runtime_root=Path(os.environ['BENNETT_ALLOCATOR_PINNED_ROOT']) if os.environ.get('BENNETT_ALLOCATOR_PINNED_ROOT') else SIBLINGS/'bennett-runtimes/dist'
 runtime=runtime_root/f'llvm{m}/bennett-runtimes.bc'
 expected={18:'4ca7fb401658e145c611aa4b3817d1b5fe1623c4d973c04be8b80a0b5893633f',23:'bbdef17b6cbb05636ab97276a651705b115f6c5ec9622fb5ff391ba197f0179e'}
 assert sha(runtime)==expected[m], 'runtime publication changed'
 sysroot=runtime.parent/'musl-sysroot';arith=arith_path(m);source=R/'tests/probes/r-hello.c'
 run([tool+'clang','--target=x86_64-unknown-linux-musl','--sysroot='+str(sysroot),'-nostdinc','-isystem',sysroot/'include','-O2','-flto','-emit-llvm','-c',source,'-o',d/'input.bc'])
 run([tool+'llvm-link',d/'input.bc',runtime,arith,'--only-needed','-o',d/'linked.bc'])
 run([tool+'opt','-passes=lto<O3>',d/'linked.bc','-o',d/'postlink.bc'])
 base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.13','--bennett-tier=reversible','--bennett-entry=main',d/'postlink.bc']
 started=time.monotonic();run([*base,'-bennett-analysis-only','-bennett-report='+str(d/'recognised.json'),'-disable-output']);seconds=time.monotonic()-started
 assert seconds<20, seconds
 z=run([*base,'-bennett-report='+str(d/'production-recognised.json'),'-bennett-out='+str(d/'out'),'-disable-output'],3)
 (d/'production.stderr').write_text(z.stderr)
 row=dict(case='r-hello',ok=True,production_complete=False,source_sha256=sha(source),runtime_sha256=sha(runtime),arith_sha256=sha(arith),postlink_sha256=sha(d/'postlink.bc'),recognised_sha256=sha(d/'recognised.json'),analysis_seconds=seconds,analysis_rounds=json.loads((d/'recognised.json').read_text())['analysis_rounds'],diagnostic=z.stderr)
 for file in ['device.bc','host.bc']:run([tool+'opt','-passes=verify',d/'out'/file,'-disable-output'])
 obj=d/'out/main/launch.bennett';release_ref=REF.parent.parent/'release/bennett-isa-ref'
 run([release_ref,'check',obj]);run([release_ref,'hash',obj])
 assert json.loads((d/'out/main/blockers.json').read_text())[0]['code']=='BD-B-ISA7'
 row.update(expected_blocked='BD-B-ISA7',materialised_verified=True,materialised_sha256=sha(d/'out/device.bc'),object_sha256=sha(obj),checker_sha256=sha(release_ref))
 rows.append(row)
 result=dict(major=m,cases=len(rows),passed=len(rows),results=rows)
 (R/f'.tmp/reversible-{m}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
