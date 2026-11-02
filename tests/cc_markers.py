#!/usr/bin/env python3
"""§17.4/§18.3 CC lowering of gate2, gate3 and qprep, and dynamic wire indices (bp-vsa).

Every expected value comes from an independent Python model of §18.3: a basis-state model for
the permutation gates and a state vector for the published Grover translation unit (§16.7)."""
import argparse,json,math,re,shutil,subprocess
from contracts import ROOT as R,dialect_text,SIBLINGS
from production import REF
HEADER=SIBLINGS/'bennett-dialect-spec/spec'
PROGRAM=r'''
#include <stdint.h>
#include "bennett_markers.h"
static const uint8_t image[40]={0x01,0x80,0xff,0x00,0x5a,0xa5,0x10,0x08,0x33,0xcc,0x0f,0xf0,0x01,0x02,0x04,0x08,
                                0x80,0x40,0x20,0x10,0x7e,0x81,0x00,0x00,0xde,0xad,0xbe,0xef,0xfe,0xed,0xfa,0xce,
                                0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88};
static uint64_t read_all(bennett_q q,uint64_t n) {
  uint64_t sum=0;
  for(uint64_t i=0;i<n;i++) sum+=(uint64_t)__bennett_measure(q,i)*(i+1);
  return sum;
}
/* x sets a's four wires; the gates below act within and across two registers, and b's measured
   bits come back with a's, then both registers are cleaned by re-applying what was measured. */
uint64_t perm(uint64_t x) {
  bennett_q a=__bennett_qalloc(BENNETT_CLASS_ANY,4), b=__bennett_qalloc(BENNETT_CLASS_ANY,4);
  for(volatile uint64_t i=0;i<4;i++) if((x>>i)&1) __bennett_gate(BENNETT_GATE_X,a,i);
  __bennett_gate2(BENNETT_GATE2_CX,a,0,b,1);
  __bennett_gate2(BENNETT_GATE2_SWAP,a,1,b,2);
  __bennett_gate3(BENNETT_GATE3_CCX,a,2,a,3,b,3);
  __bennett_gate3(BENNETT_GATE3_CCX,a,0,b,2,b,0);
  __bennett_gate2(BENNETT_GATE2_CX,a,0,a,3);
  uint64_t r=0;
  for(uint64_t i=0;i<4;i++) r|=(uint64_t)__bennett_measure(a,i)<<i;
  for(uint64_t i=0;i<4;i++) r|=(uint64_t)__bennett_measure(b,i)<<(i+4);
  for(volatile uint64_t i=0;i<4;i++) if((r>>i)&1) __bennett_gate(BENNETT_GATE_X,a,i);
  for(volatile uint64_t i=0;i<4;i++) if((r>>(i+4))&1) __bennett_gate(BENNETT_GATE_X,b,i);
  __bennett_qfree(a);__bennett_qfree(b);
  return r;
}
/* CZ is a phase: H CZ H on the target flips it iff the control is 1. */
uint64_t phase(uint64_t c) {
  bennett_q a=__bennett_qalloc(BENNETT_CLASS_ANY,2);
  if(c&1) __bennett_gate(BENNETT_GATE_X,a,0);
  __bennett_gate(BENNETT_GATE_H,a,1);
  __bennett_gate2(BENNETT_GATE2_CZ,a,0,a,1);
  __bennett_gate(BENNETT_GATE_H,a,1);
  uint64_t r=__bennett_measure(a,1);
  if(c&1) __bennett_gate(BENNETT_GATE_X,a,0);
  if(r) __bennett_gate(BENNETT_GATE_X,a,1);
  __bennett_qfree(a);
  return r;
}
/* Constant source: 40 bytes are two 128-bit chunks and a byte tail; two XORs clean the register. */
uint64_t prep_const(void) {
  bennett_q q=__bennett_qalloc(BENNETT_CLASS_ANY,328);
  __bennett_qprep(q,image,40);
  uint64_t r=read_all(q,320);
  __bennett_qprep(q,image,40);
  __bennett_qfree(q);
  return r;
}
/* A source known only at run time. */
uint64_t prep_dynamic(uint64_t x) {
  volatile uint8_t bytes[20];
  for(int i=0;i<20;i++) bytes[i]=(uint8_t)(x*(uint64_t)(i+3));
  bennett_q q=__bennett_qalloc(BENNETT_CLASS_ANY,160);
  __bennett_qprep(q,(const void *)bytes,20);
  uint64_t r=read_all(q,160);
  __bennett_qprep(q,(const void *)bytes,20);
  __bennett_qfree(q);
  return r;
}
/* One unpaired qprep leaves the register dirty: the qfree must fail, not pass quietly. */
uint64_t prep_dirty(void) {
  bennett_q q=__bennett_qalloc(BENNETT_CLASS_ANY,328);
  __bennett_qprep(q,image,40);
  __bennett_qfree(q);
  return 0;
}
'''
IMAGE=bytes([0x01,0x80,0xff,0x00,0x5a,0xa5,0x10,0x08,0x33,0xcc,0x0f,0xf0,0x01,0x02,0x04,0x08,0x80,0x40,0x20,0x10,0x7e,0x81,0,0,0xde,0xad,0xbe,0xef,0xfe,0xed,0xfa,0xce,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88])
def model_perm(x):
 a=[(x>>i)&1 for i in range(4)];b=[0]*4
 b[1]^=a[0]
 a[1],b[2]=b[2],a[1]
 b[3]^=a[2]&a[3]
 b[0]^=a[0]&b[2]
 a[3]^=a[0]
 return sum(v<<i for i,v in enumerate(a))|sum(v<<(i+4) for i,v in enumerate(b))
def bits_sum(data,n):
 return sum(((data[i//8]>>(i%8))&1)*(i+1) for i in range(n))
def model_dynamic(x):
 return bits_sum(bytes((x*(i+3))&255 for i in range(20)),160)
# The published minidb (§16.7) over the image the gate also uses.
GROVER_IMAGE=bytes.fromhex('0007000a0165030704c8052a06630796')
def minidb(rowid):
 img=GROVER_IMAGE;n=img[1];lo,hi=0,n
 while lo<hi:
  mid=(lo+hi)//2;key,value=img[2+2*mid],img[3+2*mid]
  if key==rowid:return (value&1)==0 if img[0]&1==0 else value>=100
  if key<rowid:lo=mid+1
  else:hi=mid
 return False
def grover_probabilities():
 # H on 3 wires, a phase flip on marked rows (the |-> target), diffusion: 2|s><s|-I up to a phase.
 amps=[1/math.sqrt(8)]*8
 amps=[-v if minidb(i) else v for i,v in enumerate(amps)]
 mean=sum(amps)/8
 return [2*mean-v for v in amps]
def grover_outcome(draws):
 # ISA §14.2 draws, wires 0, 1, 2 in that order: the outcome is 0 iff the draw is below P(0).
 amps=grover_probabilities();live=list(range(8));result=0
 for wire,draw in enumerate(draws):
  zero=sum(amps[i]**2 for i in live if not (i>>wire)&1);total=sum(amps[i]**2 for i in live)
  bit=0 if draw<zero/total else 1
  result|=bit<<wire;live=[i for i in live if ((i>>wire)&1)==bit]
 return result
def run(args,check=True):
 z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=600)
 if check:assert z.returncode==0,(args,z.stdout[-2000:],z.stderr[-2000:])
 return z
def build(major,d,sources,budget):
 tool=f'/usr/lib/llvm-{major}/bin/';bcs=[]
 for name,text in sources.items():
  src=d/f'{name}.c';src.write_text(text);bc=d/f'{name}.bc';bcs.append(bc)
  run([tool+'clang','-O2','-flto','-emit-llvm','-I',HEADER,'-c',src,'-o',bc])
 run([tool+'llvm-link',*bcs,'-o',d/'p.bc'])
 run([tool+'opt','-passes=lto<O3>','-S',d/'p.bc','-o',d/'post.ll'])
 run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10',f'-bennett-budget-default={budget}','-bennett-out='+str(d/'out'),'-disable-output',d/'post.ll'])
def invocation(obj,entry,args=None):
 found=re.search(r'section layout\n(.*)',obj.read_text())
 if found:
  layout=json.loads(found[1]);budget=f"10000000,{layout['heap_limit_max']},{1<<layout['S_cells']},8"
 else:budget='10000000,0,0,0' # A memoryless launch (§5.4).
 # A launch takes its entry arguments, then one step allowance per budget token (§9).
 tokens=len(json.loads((obj.parent/'build.json').read_text())['budgets'])
 values=([] if args is None else [str(args)])+['100000']*tokens
 return [REF,'run-program',obj,entry,'--budget',budget]+(['--args',','.join(values)] if values else [])
def value(obj,entry,args=None,draws=None):
 cmd=invocation(obj,entry,args)
 if draws is not None:cmd+=['--draws',','.join(map(repr,draws))]
 return json.loads(run(cmd).stdout)
def result(data):
 assert data['status']=='COMPLETED',data
 return int(data['results'][0]['value'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();checks=0
 d=R/f'.tmp/cc-markers/{a.major}/program';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 build(a.major,d,{'program':PROGRAM},'400,4096,512,8,0')
 for entry in ['perm','phase','prep_const','prep_dynamic','prep_dirty']:
  run([REF,'check',d/f'out/{entry}/launch.bennett'])
 for x in range(16):
  got=result(value(d/'out/perm/launch.bennett','perm',x));assert got==model_perm(x),('perm',x,got,model_perm(x));checks+=1
 for c in (0,1):
  # H CZ H is X^c on the target: deterministic, so any draw must give it.
  for draw in (0.25,0.75):
   got=result(value(d/'out/phase/launch.bennett','phase',c,[draw]));assert got==c,('phase',c,draw,got);checks+=1
 got=result(value(d/'out/prep_const/launch.bennett','prep_const'));assert got==bits_sum(IMAGE,320),('prep_const',got,bits_sum(IMAGE,320));checks+=1
 for x in (0,1,3,0x5b,0xff):
  got=result(value(d/'out/prep_dynamic/launch.bennett','prep_dynamic',x));assert got==model_dynamic(x),('prep_dynamic',x,got,model_dynamic(x));checks+=1
 z=run(invocation(d/'out/prep_dirty/launch.bennett','prep_dirty'),check=False)
 dirty=json.loads(z.stdout);assert dirty['status']=='FAILED' and dirty['fault']==4,('dirty free passed',dirty);checks+=1 # T-CLEAN, §18.3.
 # §16.7's published translation unit, run on an image fixed in a wrapper: one Grover iteration.
 text=dialect_text();db=re.search(r'```c example=rung4-minidb verdict=accept\n(.*?)```',text,re.S)[1];tu=re.search(r'```c example=rung4-grover-tu verdict=accept\n(.*?)```',text,re.S)[1]
 # First the unmodified pair, as the consumer gate builds it, then the same text fixed on an image.
 d=R/f'.tmp/cc-markers/{a.major}/published';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 build(a.major,d,{'db':db,'tu':tu},'400,0,512,8,0')
 launches=json.loads((d/'out/launches.json').read_text());assert [l['entry'] for l in launches]==['grover_once'],launches
 run([REF,'check',d/'out/grover_once/launch.bennett']);checks+=1
 fixed=tu+'static const uint8_t image[16]={'+','.join(map(str,GROVER_IMAGE))+'};\nuint64_t grover_fixed(void){return grover_once(image);}\n'
 fixed=fixed.replace('uint32_t grover_once(','static inline __attribute__((always_inline)) uint32_t grover_once(')
 d=R/f'.tmp/cc-markers/{a.major}/grover';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 build(a.major,d,{'db':db,'tu':fixed},'400,0,512,8,0')
 obj=d/'out/grover_fixed/launch.bennett';run([REF,'check',obj])
 marked=[i for i in range(8) if minidb(i)]
 assert marked,'the published image marks nothing'
 for draws in ([0.5,0.5,0.5],[0.0,0.0,0.0],[0.99,0.99,0.99],[0.1,0.9,0.5],[0.9,0.1,0.5],[0.4,0.6,0.2]):
  got=result(value(obj,'grover_fixed',draws=draws));want=grover_outcome(draws);assert got==want,('grover',draws,got,want);checks+=1
 print(f'cc markers LLVM {a.major}: {checks} checks; grover marked {marked}')
if __name__=='__main__':raise SystemExit(main())
