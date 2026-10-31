#!/usr/bin/env python3
"""Production CC launch acceptance, independent ISA check and launch execution."""
import argparse,hashlib,json,os,re,shutil,subprocess
from contracts import ROOT as R,DIALECT,dialect_text
REF=R.parent/'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'
def run(args):return subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=60)
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',required=True,type=int);a=p.parse_args();d=R/f'.tmp/production/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 (d/'bennett_markers.h').write_text(subprocess.check_output(['git','-C',str(DIALECT),'show','023f5a7:spec/bennett_markers.h'],text=True))
 fixture=re.search(r'```isa object=inc8\n(.*?)```',dialect_text(),re.S)[1].encode()
 report={'major':a.major,'cases':[]}
 for x in (0,7,255):
  dest=d/str(x);dest.mkdir();src=dest/'input.c'
  prep=''.join(f'__bennett_gate(1,x,{i});' for i in range(8) if (x>>i)&1)
  measures=''.join(f'r |= (unsigned)__bennett_measure(t,{i}) << {i};' for i in range(8))
  src.write_text('''#include "../bennett_markers.h"
unsigned char inc8(unsigned char x) { return (unsigned char)(x+1); }
unsigned top(unsigned arg) {
 void *x=__bennett_qalloc(0,8), *t=__bennett_qalloc(0,8), *f=__bennett_qalloc(0,4);
 struct Desc { struct { unsigned version,nparam,ndev,flags; void *tgt,*fault; } h;
 struct { unsigned kind,mode; void *q; unsigned long long value,size; } p[1]; } desc={{2,1,0,0,t,f},{{1,0,x,0,0}}};
 PREP
 __bennett_oracle((void *)inc8,0,(const bennett_oracle_desc *)&desc);
 unsigned r=0; MEASURE
 __bennett_oracle((void *)inc8,0,(const bennett_oracle_desc *)&desc);
 PREP
 __bennett_qfree(f); __bennett_qfree(t); __bennett_qfree(x);
 return r+arg;
}
'''.replace('PREP',prep).replace('MEASURE',measures))
  tool=f'/usr/lib/llvm-{a.major}/bin/';ll=dest/'input.ll';cc=run([tool+'clang','-O1','-emit-llvm','-S',src,'-o',ll]);assert cc.returncode==0,cc.stderr
  objdir=dest/'out';lower=run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-scalar-stack=7','-bennett-budget-default=5,0,7,1,0','-bennett-out='+str(objdir),'-disable-output',ll]);row={'input':x,'lower_exit':lower.returncode,'diagnostic':lower.stderr};report['cases'].append(row)
  if lower.returncode:continue
  obj=objdir/'top/launch.bennett';check=run([REF,'check',obj]);row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
  if check.returncode:continue
  hashes=json.loads(check.stdout);row['object_hash']=hashes['object_hash'];row['symbols']=hashes['symbols'];row['reference_exact']=(objdir/'top/oracle-0/ref.bennett').read_bytes()==fixture
  executions=[]
  for steps,expected in [(5,(x+1)&255),(4,0)]:
   z=run([REF,'run-program',obj,'top','--args',f'11,{steps},{steps}','--budget','10000,0,7,1']);v=json.loads(z.stdout) if z.returncode==0 else {};executions.append({'steps':steps,'exit':z.returncode,'diagnostic':z.stderr,'result':v,'ok':v.get('status')=='COMPLETED' and v.get('run_state')=='CLOSED' and v.get('results')==[{'type':'i32','value':str(expected+11)}]})
  row['runs']=executions
  # Stub IR is independently verified and contains no marker references.
  host=run([tool+'opt','-passes=verify','-S',objdir/'host.bc','-o','-']);row['host_verified']=host.returncode==0
  top=re.search(r'define [^\n]*@top\(.*?^}',host.stdout,re.S|re.M)[0]
  row['host_replaced']='@__bennett_' not in top and all('@'+n in top for n in ['bennett_load','bennett_budget','bennett_run','bennett_wait','bennett_run_close','bennett_unload'])
  build=json.loads((objdir/'top/build.json').read_text());cert=json.loads((objdir/'top/certificate.json').read_text());cov=json.loads((objdir/'top/coverage.json').read_text())
  row['record_bindings']=build['object_hash']==hashes['object_hash']==cert['bindings']['object_hash'] and cert['bindings']['closure_hash']==hashes['symbols']['top']['closure_hash'] and cert['producer']['version'].endswith(hashlib.sha256((objdir/'top/build.json').read_bytes().rstrip(b'\n')).hexdigest())
  row['coverage_points']=len(cov['entries'])>0 and all(e['point'][0]==hashes['symbols']['top']['interface_hash'] for e in cov['entries'])
  native=dest/'host-test'
  cc=run([tool+'clang',objdir/'host.bc',R/'tests/launch_runtime.c','-I'+str(R.parent/'bennett-isa-spec/include'),f'-DEXPECTED={((x+1)&255)+11}','-o',native])
  if cc.returncode==0:
   os.environ['BENNETT_TARGET']='{}';os.environ['CAPTURE_OBJECT']=str(dest/'embedded.bennett');execution=run([native]);row['host_protocol']=execution.returncode==0 and (dest/'embedded.bennett').read_bytes()==obj.read_bytes();row['host_output']=execution.stdout+execution.stderr
  else:row['host_protocol']=False;row['host_output']=cc.stderr
  row['ok']=all(row.get(k) for k in ['check','reference_exact','host_verified','host_replaced','record_bindings','coverage_points','host_protocol']) and all(z['ok'] for z in executions)
 # The accepted LLVM fixture includes an explicit budget record and packed
 # vector stores; compile it unmodified with only its published declarations.
 body=re.search(r'```llvm example=oracle-inc8[^\n]*\n(.*?)```',dialect_text(),re.S)[1]
 decls=re.search(r'```llvm markers-ir\n(.*?)```',dialect_text(),re.S)[1]
 used=set(re.findall(r'@(__bennett_\w+)',body));body+='\n'+'\n'.join(l for l in decls.splitlines() if re.search(r'@([^ (]+)',l)[1] in used)
 published=d/'published';published.mkdir();(published/'input.ll').write_text(body)
 z=run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budget-default=5,0,7,1,0','-bennett-out='+str(published/'out'),'-disable-output',published/'input.ll'])
 pub={'exit':z.returncode,'diagnostic':z.stderr};report['published_oracle_inc8']=pub
 if z.returncode==0:
  obj=published/'out/top/launch.bennett';check=run([REF,'check',obj]);execution=run([REF,'run-program',obj,'top','--args','5,5','--budget','10000,0,7,1']);pub['check']=check.returncode==0;pub['check_output']=check.stdout+check.stderr;pub['run']=json.loads(execution.stdout) if execution.returncode==0 else execution.stderr;pub['reference_exact']=(published/'out/top/oracle-0/ref.bennett').read_bytes()==fixture
  pub['ok']=pub['check'] and pub['reference_exact'] and execution.returncode==0 and pub['run']['status']=='COMPLETED' and pub['run']['run_state']=='CLOSED'
 # Replacing a function body must preserve the native integer calling ABI.
 abi=d/'abi';abi.mkdir();(abi/'input.ll').write_text('''define signext i8 @abi(i8 signext %arg) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %q)
 ret i8 %arg
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
''')
 z=run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-out='+str(abi/'out'),'-disable-output',abi/'input.ll'])
 abi_result={'exit':z.returncode,'diagnostic':z.stderr};report['native_abi']=abi_result
 if z.returncode==0:
  host=run([tool+'opt','-passes=verify','-S',abi/'out/host.bc','-o','-']);abi_result['ok']=host.returncode==0 and 'define signext i8 @abi(i8 signext %arg)' in host.stdout
 report['passed']=sum(r.get('ok',False) for r in report['cases']);(R/f'.tmp/production-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report['passed']!=len(report['cases']) or not pub.get('ok') or not abi_result.get('ok')
if __name__=='__main__':raise SystemExit(main())
