#!/usr/bin/env python3
"""Descriptor built by C stores (§8.1): same reference object as §16 inc8."""
import argparse,json,subprocess
from contracts import ROOT as R,DIALECT

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();d=R/f'.tmp/descriptors/{a.major}';d.mkdir(parents=True,exist_ok=True)
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
 cmd=[tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-descriptor-reference','-bennett-scalar-stack=7','-bennett-out='+str(d),'-disable-output',str(ll)]
 x=subprocess.run(cmd,capture_output=True,text=True);obj=d/'oracle-0/ref.bennett';fixture=R/f'.tmp/scalars/{a.major}/inc8/ref.bennett';ok=x.returncode==0 and obj.exists() and obj.read_bytes()==fixture.read_bytes()
 # Production must still fail loudly until CC launch/object emission exists.
 production=subprocess.run([arg for arg in cmd if arg!='-bennett-descriptor-reference'],capture_output=True,text=True)
 loud=production.returncode!=0 and 'unimplemented' in production.stderr
 result={'major':a.major,'descriptor_inc8_equal':ok,'production_unimplemented':loud,'diagnostic':x.stderr};(R/f'.tmp/descriptors-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return not(ok and loud)
if __name__=='__main__':raise SystemExit(main())
