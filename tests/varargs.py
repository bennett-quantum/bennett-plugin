#!/usr/bin/env python3
"""N23 (§14.3): variadic definitions take a va block, calls spill into one, and va_start builds the
target's va_list so that the front end's inline va_arg takes its memory path (bp-cbg).

Run on the published n-varargs witness and its published native values, and on real clang output."""
import argparse,re,subprocess
from contracts import ROOT as R,dialect_text
def run(args):
 z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=300);assert z.returncode==0,(args,z.stderr[-1500:]);return z.stdout
HARNESS='''
@fmt = private constant [6 x i8] c"%lld\\0A\\00"
declare i32 @printf(ptr, ...)
define i32 @main() {
@CALLS@  ret i32 0
}
'''
TARGET='target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"\ntarget triple = "x86_64-unknown-linux-gnu"\n'
C=r'''
#include <stdarg.h>
long long weighted(int n, ...) {
  va_list ap;va_start(ap,n);long long sum=0;
  for(int i=0;i<n;i++) {
    if(i&1) sum+=(i+1)*va_arg(ap,long long);
    else sum+=(i+1)*va_arg(ap,int);
  }
  va_end(ap);return sum;
}
long long copied(int n, ...) {
  va_list ap,again;va_start(ap,n);va_copy(again,ap);long long a=0,b=0;
  for(int i=0;i<n;i++) a+=va_arg(ap,int);
  for(int i=0;i<n;i++) b+=2*va_arg(again,int);
  va_end(again);va_end(ap);return a+b;
}
typedef long long (*fn)(int, ...);
__attribute__((noinline)) long long through(fn f,long long x) {return f(3,(int)x,x*2,(int)x+1);}
long long top_a(long long x){return weighted(4,(int)x,x+1,(int)x+2,x+3);}
long long top_b(long long x){return copied(3,(int)x,(int)x+1,(int)x+2);}
long long top_c(long long x){return through(x&1?weighted:weighted,x);}
long long top_d(long long x){return weighted(0)+x;}
'''
def weighted(values):return sum((i+1)*v for i,v in enumerate(values))
EXPECT={'top_a':lambda x:weighted([x,x+1,x+2,x+3]),'top_b':lambda x:3*(3*x+3),'top_c':lambda x:weighted([x,x*2,x+1]),'top_d':lambda x:x}
def materialise(major,src,out):
 tool=f'/usr/lib/llvm-{major}/bin/'
 run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-normalise-only','-S',src,'-o',out])
 run([tool+'opt','-passes=verify','-disable-output',out])
 return out.read_text()
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();tool=f'/usr/lib/llvm-{a.major}/bin/'
 d=R/f'.tmp/varargs/{a.major}';d.mkdir(parents=True,exist_ok=True);checks=0
 # Published witness.
 text=dialect_text();source=re.search(r'```llvm normalise-in=n-varargs\n(.*?)```',text,re.S)[1]
 native=re.findall(r'top\((-?\d+)\) = (-?\d+)',re.search(r'```text native=n-varargs\n(.*?)```',text,re.S)[1])
 calls=''.join(f'  %r{n} = call i32 @top(i32 {x})\n  %w{n} = sext i32 %r{n} to i64\n  call i32 (ptr, ...) @printf(ptr @fmt, i64 %w{n})\n' for n,(x,_) in enumerate(native))
 src=d/'witness.ll';src.write_text(TARGET+source+HARNESS.replace('@CALLS@',calls));out=d/'witness-out.ll'
 body=materialise(a.major,src,out)
 assert re.search(r'define internal i32 @sum\(i32 %n, ptr %nz\.va\)',body),re.findall(r'define[^\n]*@sum[^\n]*',body)
 for name in ('%nz.vfo.sum.0','%nz.vov.sum.0','%nz.vrs.sum.0','%nz.vb.r','%nz.vb1.r','%nz.vb2.r'):assert name in body,(name,'missing')
 assert 'va_start' not in body and 'va_end' not in body,'a va intrinsic survived'
 got=run([tool+'lli',out]).split();assert got==[v for _,v in native],(got,native);checks+=1
 # Clang's real inline va_arg, va_copy, calls through a variadic function pointer, no variadic args.
 xs=[0,1,7,1000,-5]
 harness=''.join(f'  printf("%lld\\n",{name}({x}LL));\n' for name in EXPECT for x in xs)
 c=d/'real.c';c.write_text('int printf(const char *,...);\n'+C+'int main(void){\n'+harness+'  return 0;\n}\n')
 ll=d/'real.ll';run([tool+'clang','-O2','-S','-emit-llvm','--target=x86_64-unknown-linux-gnu','-fno-builtin-printf',c,'-o',ll])
 want=[str(EXPECT[name](x)) for name in EXPECT for x in xs]
 assert run([tool+'lli',ll]).split()==want,'source disagrees with the model'
 out=d/'real-out.ll';body=materialise(a.major,ll,out)
 for name in ('weighted','copied'):
  definition=re.search(r'define [^\n]*@'+name+r'\(([^)]*)\)',body);assert definition and '...' not in definition[1] and 'nz.va' in definition[1],(name,definition and definition[0])
 assert 'va_start' not in body and 'va_end' not in body and 'va_copy' not in body,'a va intrinsic survived'
 got=run([tool+'lli',out]).split();assert got==want,('materialised',got,want);checks+=len(want)
 print(f'varargs LLVM {a.major}: {checks} checks')
if __name__=='__main__':raise SystemExit(main())
