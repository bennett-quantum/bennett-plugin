#!/usr/bin/env python3
"""N27 semantics, runtime closure, and wide-slot transport against Python integers."""
import argparse,ctypes,json,os,random,re,subprocess
from contracts import ROOT as R
from scalars import REF
p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
d=R/f'.tmp/integer-intrinsics/{a.major}';d.mkdir(parents=True,exist_ok=True);tool=f'/usr/lib/llvm-{a.major}/bin/';rows=[]
def run(args):
 z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=180);assert z.returncode==0,z.stderr;return z
widths=[1,7,8,16,24,32,64,65,80,128,129,192,256,257,512]
base=['smax','smin','umax','umin','abs','ctpop','ctlz','cttz','bitreverse','fshl','fshr','uadd.sat','usub.sat','sadd.sat','ssub.sat','sshl.sat','ushl.sat','uadd.with.overflow','usub.with.overflow','sadd.with.overflow','ssub.with.overflow','umul.with.overflow','smul.with.overflow','smul.fix','umul.fix','smul.fix.sat','umul.fix.sat','sdiv.fix','udiv.fix','sdiv.fix.sat','udiv.fix.sat']
source=[];cases=[]
for n in widths:
 ops=base+(['bswap'] if n%16==0 else [])+(['scmp','ucmp','pdep','pext','clmul'] if a.major==23 else [])
 for op in ops:
  if n==1 and '.fix' in op:continue
  t=f'i{n}';over=op.endswith('.overflow');ret='{'+t+',i1}' if over else 'i8' if op in ['scmp','ucmp'] else t
  unary=op in ['abs','ctpop','ctlz','cttz','bitreverse','bswap'];types=[t] if unary else [t,t]
  if op in ['abs','ctlz','cttz']:types+=['i1']
  if op in ['fshl','fshr']:types+=[t]
  if '.fix' in op:types+=['i32']
  suffix=f'i8.i{n}' if op in ['scmp','ucmp'] else t
  source.append(f'declare {ret} @llvm.{op}.{suffix}('+','.join(types)+')')
  call=[t+' %a']
  if not unary:call+=[t+' %b']
  if op in ['abs','ctlz','cttz']:call+=['i1 false']
  if op in ['fshl','fshr']:call+=[t+' %c']
  if '.fix' in op:call+=['i32 '+str(n//2)]
  name=f'f{n}_'+op.replace('.','_');cases.append((n,op,name))
  body=f'define i8 @{name}(ptr %p,ptr %q,ptr %s,ptr %out) {{ %a = load {t},ptr %p,align 1\n %b = load {t},ptr %q,align 1\n %c = load {t},ptr %s,align 1\n %v = call {ret} @llvm.{op}.{suffix}('+','.join(call)+')\n'
  if over:body+=f' %value = extractvalue {ret} %v,0\n %flag = extractvalue {ret} %v,1\n store {t} %value,ptr %out,align 1\n %r = zext i1 %flag to i8\n ret i8 %r }}'
  elif op in ['scmp','ucmp']:body+=' store i8 %v,ptr %out,align 1\n ret i8 0 }'
  else:body+=f' store {t} %v,ptr %out,align 1\n ret i8 0 }}'
  source.append(body)
src=d/'in.ll';src.write_text('\n'.join(source));out=d/'out.ll'
run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-normalise-only','-S',src,'-o',out])
assert not re.search(r'call .*@llvm\.',out.read_text()),'intrinsic call residue'
runtime=d/'stack.c';runtime.write_text('#include <stdint.h>\n#include <unistd.h>\nstatic unsigned char s[1048576];static uint64_t sp;void *__bennett_rt_ss_push(uint64_t n,uint64_t a){sp=(sp+a-1)&-a;void*p=s+sp;sp+=n;return p;}void __bennett_rt_ss_pop(void*p){sp=(unsigned char*)p-s;}void __bennett_nz_fault(uint64_t n){_exit((int)n);}')
so=d/'n27.so';run([tool+'clang','-shared','-fPIC','-O0',out,runtime,'-o',so]);lib=ctypes.CDLL(str(so));rng=random.Random(9027)
def buf(x,n):return ctypes.create_string_buffer(x.to_bytes((n+7)//8,'little'),8*((n+63)//64))
def signed(x,n):return x-(1<<n) if x>>(n-1) else x
def quotient(x,y):return abs(x)//abs(y)*(-1 if (x<0)!=(y<0) else 1)
for n,op,name in cases:
 mask=(1<<n)-1;lo=-(1<<(n-1));hi=(1<<(n-1))-1
 vectors=[(0,1),(mask,1),(1<<(n-1),mask),(hi,hi),(mask,mask),(0,0)]+[(rng.getrandbits(n),rng.getrandbits(n)) for _ in range(5)]
 fn=getattr(lib,name);fn.argtypes=[ctypes.c_void_p]*4;fn.restype=ctypes.c_uint8
 for x,y in vectors:
  sx,sy=signed(x,n),signed(y,n);flag=0;z=y
  if '.fix' in op and 'div' in op and not y:continue
  if op=='abs':v=abs(sx)
  elif op in ['smax','smin','umax','umin']:v=(max if op.endswith('max') else min)(*((sx,sy) if op[0]=='s' else (x,y)))
  elif op=='ctpop':v=x.bit_count()
  elif op=='ctlz':v=n-x.bit_length()
  elif op=='cttz':v=(x&-x).bit_length()-1 if x else n
  elif op=='bitreverse':v=int(f'{x:0{n}b}'[::-1],2)
  elif op=='bswap':v=int.from_bytes(x.to_bytes(n//8,'little'),'big')
  elif op in ['scmp','ucmp']:
   xx,yy=(sx,sy) if op=='scmp' else (x,y);v=((xx>yy)-(xx<yy))&255
  elif op in ['fshl','fshr']:
   shift=z%n;v=(((x<<n)|y)<<shift>>n) if op=='fshl' else (((x<<n)|y)>>shift)
  elif op in ['pdep','pext']:
   v=0;j=0
   for k in range(n):
    if y>>k&1:
     if op=='pdep':v|=(x>>j&1)<<k
     else:v|=(x>>k&1)<<j
     j+=1
  elif op=='clmul':
   v=0
   for k in range(n):
    if y>>k&1:v^=x<<k
  else:
   sign=op[0]=='s';xx,yy=(sx,sy) if sign else (x,y);lower,upper=(lo,hi) if sign else (0,mask)
   if 'shl' in op:v=xx<<y if y<n else (upper+1 if xx>0 else lower-1 if xx<0 else 0)
   elif 'mul' in op:v=xx*yy
   elif 'div' in op:v=quotient(xx<<(n//2),yy)
   elif 'add' in op:v=xx+yy
   else:v=xx-yy
   if '.fix' in op and 'mul' in op:v>>=n//2
   if op.endswith('.overflow'):flag=int(v<lower or v>upper)
   if op.endswith('.sat'):v=max(lower,min(upper,v))
  output=buf(0,n);gotflag=fn(buf(x,n),buf(y,n),buf(z,n),output);actual=int.from_bytes(output.raw[:(1 if op in ['scmp','ucmp'] else (n+7)//8)],'little')
  want=v&(255 if op in ['scmp','ucmp'] else mask);assert (actual,gotflag)==(want,flag),(n,op,x,y,actual,want,gotflag,flag)
 rows.append(f'{n}/{op}')
# Defined-zero count, modular funnel, partial limbs, scalar flags and division faults
# above all use real plugin definitions. Fault rows execute in isolated children.
for n in [7,65,129,192,257,512]:
 for op in ['sdiv.fix','udiv.fix','sdiv.fix.sat','udiv.fix.sat']:
  pid=os.fork()
  if pid==0:getattr(lib,f'f{n}_'+op.replace('.','_'))(buf(1,n),buf(0,n),buf(0,n),buf(0,n));os._exit(0)
  assert os.waitstatus_to_exitcode(os.waitpid(pid,0)[1])==5,(n,op)
 rows.append(f'{n}/fault5')
# Production must contain and execute the count-slot body, overflow and saturation.
prod=d/'production.ll';prod.write_text('''declare i192 @llvm.ctlz.i192(i192,i1)
declare i192 @llvm.uadd.sat.i192(i192,i192)
declare {i192,i1} @llvm.uadd.with.overflow.i192(i192,i192)
define internal i1 @n27prod(ptr %p) { %a = load i192,ptr %p,align 1
 %n = call i192 @llvm.ctlz.i192(i192 %a,i1 false)
 %s = call i192 @llvm.uadd.sat.i192(i192 %a,i192 1)
 %pair = call {i192,i1} @llvm.uadd.with.overflow.i192(i192 %a,i192 1)
 %flag = extractvalue {i192,i1} %pair,1
 %c = icmp eq i192 %n,191
 %v = icmp eq i192 %s,2
 %both = and i1 %c,%v
 %no = xor i1 %flag,true
 %r = and i1 %both,%no
 ret i1 %r }
!llvm.module.flags = !{!0}
!0 = !{i32 1, !"bennett.sstack", i64 256}''')
obj=d/'production';run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle=n27prod','-bennett-scalar-shape=MEM_IN(32);tgt=1','-bennett-scalar-stack=4096','-bennett-scalar-heap=4096','-bennett-out='+str(obj),'-disable-output',prod])
run([REF,'check',obj/'ref.bennett'])
for x in [0,1,(1<<192)-1]:
 data=json.loads(run([REF,'run-oracle',obj/'ref.bennett','ref','--input','','--mem','m0='+x.to_bytes(32,'little').hex(),'--budget','1000000,4096,4096,256']).stdout)
 assert data['code']==0 and data['payload']==int(x==1),data
rows.append('production-count-slot-overflow-saturation')
result=dict(major=a.major,cases=len(rows),passed=len(rows),results=rows);(R/f'.tmp/integer-intrinsics-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
