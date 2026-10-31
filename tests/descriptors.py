#!/usr/bin/env python3
"""Descriptor built by C stores (§8.1): same reference object as §16 inc8."""
import argparse,json,re,shutil,subprocess
from contracts import ROOT as R,DIALECT,dialect_text

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--require-production',action='store_true',help='production smoke probe: an unimplemented diagnostic is failure');a=p.parse_args();d=R/f'.tmp/descriptors/{a.major}';d.mkdir(parents=True,exist_ok=True)
 # Use the published ABI header as a fixture, not a sibling implementation.
 header=subprocess.check_output(['git','-C',str(DIALECT),'show','023f5a7:spec/bennett_markers.h'],text=True);(d/'bennett_markers.h').write_text(header)
 # Field names are avoided so this tests the published positional ABI too.
 src=d/'in.c';src.write_text('''#include "bennett_markers.h"
unsigned char inc8(unsigned char x) { return (unsigned char)(x+1); }
void top(void) {
 void *x=__bennett_qalloc(0,8), *t=__bennett_qalloc(0,8), *f=__bennett_qalloc(0,4);
 struct Desc { struct { unsigned version,nparam,ndev,flags; void *tgt,*fault; } h;
 struct { unsigned kind,mode; void *q; unsigned long long value,size; } p[1]; } desc={{2,1,0,0,t,f},{{1,0,x,0,0}}};
 __bennett_oracle((void *)inc8,0,(const bennett_oracle_desc *)&desc);
 __bennett_qfree(f); __bennett_qfree(t); __bennett_qfree(x);
}
''')
 tool=f'/usr/lib/llvm-{a.major}/bin/';ll=d/'in.ll'
 subprocess.run([tool+'clang','-O1','-emit-llvm','-S',src,'-o',ll],check=True)
 cmd=[tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-descriptor-reference','-bennett-scalar-stack=7','-bennett-budget-default=5,0,7,1,0','-bennett-out='+str(d),'-disable-output',str(ll)]
 x=subprocess.run(cmd,capture_output=True,text=True);obj=d/'oracle-0/ref.bennett';fixture=re.search(r'```isa object=inc8\n(.*?)```',dialect_text(),re.S)[1].encode();ok=x.returncode==0 and obj.exists() and obj.read_bytes()==fixture
 # Production is acceptance: success and complete launch artefacts are required.
 prod=d/'production';shutil.rmtree(prod,ignore_errors=True);prod.mkdir()
 production=subprocess.run([('-bennett-out='+str(prod) if arg.startswith('-bennett-out=') else arg) for arg in cmd if arg!='-bennett-descriptor-reference'],capture_output=True,text=True)
 loud=production.returncode!=0 and 'unimplemented' in production.stderr
 required=['host.bc','device.bc','launches.json','top/launch.bennett','top/build.json','top/certificate.json','top/coverage.json','top/blockers.json','top/oracle-0/ref.bennett']
 complete=production.returncode==0 and all((prod/f).is_file() for f in required) and (prod/'top/oracle-0/ref.bennett').read_bytes()==fixture
 result={'major':a.major,'descriptor_inc8_equal':ok,'production_unimplemented':loud,'production_complete':complete,'production_exit':production.returncode,'production_artifacts':sorted(str(p.relative_to(prod)) for p in prod.rglob('*') if p.is_file()),'production_diagnostic':production.stderr,'diagnostic':x.stderr};(R/f'.tmp/descriptors-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return not(ok and complete)
if __name__=='__main__':raise SystemExit(main())
