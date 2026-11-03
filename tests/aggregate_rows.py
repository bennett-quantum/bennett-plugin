#!/usr/bin/env python3
"""§16.4 aggregate field rows plus N22/N25 ABI, independently executed."""
import argparse,json,shutil,subprocess,hashlib
from contracts import ROOT as R
from scalars import REF
from production_environments import descriptor,DECL

CASES={'aggregate-fields':lambda x:(x&0xffffff)+9,
       'aggregate-call-result':lambda x:(x+3)&((1<<64)-1),
       'aggregate-wide-return':lambda x:(x+(9 if x==0 else 10))&((1<<64)-1)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
 tool=f'/usr/lib/llvm-{a.major}/bin/';plugin=R/f'build/libbennett-plugin-{a.major}.so';rows=[]
 def run(cmd):return subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=90)
 for name,expected in CASES.items():
  d=R/f'.tmp/aggregate-rows/{a.major}/{name}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
  src=R/f'tests/probes/{name}.ll';report=d/'recognised.json';material=d/'materialised.ll'
  base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.13',src]
  z=run([*base,'-bennett-analysis-only','-bennett-report='+str(report),'-disable-output']);assert z.returncode==0,z.stderr
  z=run([*base,'-bennett-normalise-only','-S','-o',material]);assert z.returncode==0,z.stderr
  text=material.read_text();assert 'extractvalue' in text or name=='aggregate-wide-return',text
  if name=='aggregate-wide-return':assert 'ptr %nz.ret' in text and 'define internal void @make' in text,text
  out=d/'out';z=run([*base,'-bennett-oracle=top','-bennett-scalar-shape=IN(64,zext);tgt=64','-bennett-scalar-stack=65536','-bennett-scalar-heap=65536','-bennett-out='+str(out),'-disable-output']);assert z.returncode==0,z.stderr
  z=run([tool+'opt','-passes=verify','-disable-output',out/'materialised.bc']);assert z.returncode==0,z.stderr
  obj=out/'ref.bennett';z=run([REF,'check',obj]);assert z.returncode==0,z.stdout+z.stderr
  body=obj.read_text();assert 'lift.mov' in body
  if name!='aggregate-wide-return':assert 'lift.lshr' in body and 'lift.trunc' in body
  vectors=[]
  for x in (0,1,7,0x1234567,(1<<64)-1):
   z=run([REF,'run-oracle',obj,'ref','--input',str(x),'--budget','1000000,65536,65536,128']);data=json.loads(z.stdout) if z.returncode==0 else {}
   assert data.get('code')==0 and data.get('payload')==expected(x),(name,x,z.stdout,z.stderr)
   vectors.append(dict(input=x,payload=data['payload'],steps=data['steps']))
  # A real descriptor launch observes the low byte, then uncomputes the
  # complete target and releases it. This executes the new L rows under CC.
  fields=[(0,'i32','2'),(4,'i32','1'),(8,'i32','0'),(12,'i32','0'),(16,'ptr','%q'),(24,'ptr','%fault'),(32,'i32','2'),(36,'i32','0'),(40,'ptr','null'),(48,'i64','7'),(56,'i64','0')]
  host='define i64 @top() {\n%desc = alloca [64 x i8], align 8\n%q = call ptr @__bennett_qalloc(i64 0,i64 64)\n%fault = call ptr @__bennett_qalloc(i64 0,i64 4)\n'+descriptor(fields)+'\ncall void @__bennett_oracle(ptr @region,ptr null,ptr %desc)\n'
  for n in range(8):host+=f'%m{n} = call i1 @__bennett_measure(ptr %q,i64 {n})\n%z{n} = zext i1 %m{n} to i64\n%s{n} = shl i64 %z{n}, {n}\n'
  for n in range(1,8):host+=f'%r{n} = or i64 '+('%s0' if n==1 else f'%r{n-1}')+f', %s{n}\n'
  host+='call void @__bennett_oracle(ptr @region,ptr null,ptr %desc)\ncall void @__bennett_qfree(ptr %fault)\ncall void @__bennett_qfree(ptr %q)\nret i64 %r7\n}\n'+DECL+'\ndeclare i1 @__bennett_measure(ptr,i64)\n'
  cc=d/'production.ll';cc.write_text(src.read_text().replace('define i64 @top(', 'define internal i64 @region(')+'\n'+host)
  cc_out=d/'production';z=run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.13','-bennett-budget-default=1000000,65536,65536,128,4096','-bennett-out='+str(cc_out),'-disable-output',cc]);assert z.returncode==0,z.stderr
  launch=cc_out/'top/launch.bennett';z=run([REF,'check',launch]);assert z.returncode==0,z.stdout+z.stderr
  tokens=json.loads((cc_out/'top/build.json').read_text())['budgets']
  cc_ref=REF.parent.parent/'release/bennett-isa-ref'
  z=run([cc_ref,'run-program',launch,'top','--args',','.join(str(t['steps']) for t in tokens),'--budget','10000000,65536,65536,128']);data=json.loads(z.stdout) if z.returncode==0 else {}
  assert data.get('status')=='COMPLETED' and data.get('results')==[dict(type='i64',value=str(expected(7)))],(name,z.stdout,z.stderr)
  rows.append(dict(case=name,ok=True,recognised=str(report.relative_to(R)),materialised=str(material.relative_to(R)),vectors=vectors,cc_result=data,recognised_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),materialised_sha256=hashlib.sha256(material.read_bytes()).hexdigest(),materialised_bitcode_sha256=hashlib.sha256((out/'materialised.bc').read_bytes()).hexdigest(),materialised_verified=True))
 result=dict(major=a.major,cases=len(rows),passed=len(rows),results=rows)
 (R/f'.tmp/aggregate-rows-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':raise SystemExit(main())
