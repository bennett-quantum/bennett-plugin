#!/usr/bin/env python3
"""§13 transport and published bitcode-edge tests, not a numerical library.

The synthetic definitions deliberately only implement bit operations. They prove
linkage/closure and carrier transport, never stand in for bennett-arith's arithmetic.
"""
import argparse, json, os, re, subprocess, shutil, hashlib, tomllib
from contracts import ROOT as R
from scalars import REF

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--production-cc',action='store_true',help='also execute the full-width real CC oracle launch (bp-7ni long-running probe)');a=p.parse_args()
 d=R/f'.tmp/softfloat/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 tool=f'/usr/lib/llvm-{a.major}/bin/';plugin=R/f'build/libbennett-plugin-{a.major}.so';rows=[]
 def run(argv,env=None,timeout=180):return subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=timeout,env=env)
 env=dict(os.environ);env['BENNETT_ARITH_BITCODE']=''
 def opt(body,name,flags,linked=None):
  src=d/(name+'.ll');src.write_text(body);dest=d/name
  e=dict(env)
  if linked:e['BENNETT_ARITH_BITCODE']=str(linked)
  z=run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10',*flags,src],e)
  return z,dest
 def check(name,ok,detail=''):rows.append(dict(name=name,ok=bool(ok),detail=detail))
 formats=[('half','f16',16),('bfloat','bf16',16),('float','f32',32),('double','f64',64),('x86_fp80','f80',80),('fp128','f128',128),('ppc_fp128','ppcf128',128)]
 for t,s,w in formats:
  body=f'''define {t} @f({t} %a, {t} %b, i128 %n) {{
 %x = sitofp i128 %n to {t}
 %v = fadd {t} %a, %x
 %k = fcmp une {t} %a, %b
 %r = select i1 %k, {t} %v, {t} %b
 ret {t} %r
}}'''
  z,_=opt(body,s,['-bennett-normalise-only','-S','-o','-'])
  check('carriers-'+s,z.returncode==0 and f'@__bennett_sf_sitofp_{s}(i128 %n)' in z.stdout and f'@__bennett_sf_cmp_{s}(i{w}' in z.stdout and not re.search(r'= (fadd|sitofp|fcmp) ',z.stdout),z.stderr)
 atomic=['fadd','fsub','fmax','fmin']+(['fmaximum','fminimum','fmaximumnum','fminimumnum'] if a.major==23 else [])
 for op in atomic:
  body=f'@g = internal global double 0.0\ndefine double @f(double %x) {{ %r = atomicrmw {op} ptr @g, double %x seq_cst\n ret double %r }}'
  z,_=opt(body,op,['-bennett-normalise-only','-S','-o','-'])
  helper={'fadd':'add','fsub':'sub','fmax':'maxnum','fmin':'minnum'}.get(op,op[1:])
  check('N9-'+op,z.returncode==0 and '@__bennett_sf_'+helper+'_f64' in z.stdout and 'atomicrmw' not in z.stdout,z.stderr)
 if a.major==23:
  body='define void @f(ptr initializes((0, 4)) %p) { store i32 0,ptr %p\n ret void }'
  z,_=opt(body,'N3-range-list',['-bennett-normalise-only','-S','-o','-'])
  check('N3-range-list-attribute',z.returncode==0 and 'initializes' not in z.stdout,z.stderr)
 # Each carrier-call family uses the prescribed result and operand widths.
 for op,argc in [('sqrt',1),('floor',1),('ceil',1),('trunc',1),('round',1),('roundeven',1),('rint',1),('nearbyint',1),('canonicalize',1),('minnum',2),('maxnum',2),('minimum',2),('maximum',2),('fma',3)]:
  args=', '.join('double %x' for _ in range(argc));types=', '.join('double' for _ in range(argc))
  body=f'declare double @llvm.{op}.f64({types})\ndefine double @f(double %x) {{ %r = call double @llvm.{op}.f64({args})\n ret double %r }}'
  z,_=opt(body,'intrinsic-'+op,['-bennett-normalise-only','-S','-o','-'])
  check('N32-'+op,z.returncode==0 and f'call i64 @__bennett_sf_{op}_f64' in z.stdout,z.stderr)
 for op in ['sitofp','uitofp']:
  for bits in [7,128,129,192]:
   body=f'define double @f(i{bits} %n) {{ %r = {op} i{bits} %n to double\n ret double %r }}'
   z,_=opt(body,f'{op}-{bits}',['-bennett-normalise-only','-S','-o','-'])
   # Wide function arguments are N22 limb ABI work; exercise wide loads here.
   if bits>128:
    body=f'define double @f(ptr %p) {{ %n = load i{bits}, ptr %p, align 8\n %r = {op} i{bits} %n to double\n ret double %r }}'
    z,_=opt(body,f'{op}-{bits}',['-bennett-normalise-only','-S','-o','-'])
   check(f'N32-{op}-{bits}',z.returncode==0 and f'@__bennett_sf_{op}_f64'+('_wide' if bits>128 else '') in z.stdout and not re.search(r'= (sitofp|uitofp) ',z.stdout),z.stderr)
 for pred in range(16):
  names=['false','oeq','ogt','oge','olt','ole','one','ord','uno','ueq','ugt','uge','ult','ule','une','true']
  body=f'define i1 @f(double %a,double %b) {{ %r = fcmp {names[pred]} double %a,%b\n ret i1 %r }}'
  z,_=opt(body,'predicate-'+str(pred),['-bennett-normalise-only','-S','-o','-'])
  check('predicate-'+str(pred),z.returncode==0 and f'i32 {pred})' in z.stdout,z.stderr)
 for mode,num in [('tonearest',0),('downward',1),('upward',2),('towardzero',3),('tonearestaway',4),('dynamic',None)]:
  body='declare double @llvm.experimental.constrained.fmuladd.f64(double,double,double,metadata,metadata)\ndefine double @f(double %a,double %b,double %c) { %r = call double @llvm.experimental.constrained.fmuladd.f64(double %a,double %b,double %c,metadata !"round.'+mode+'",metadata !"fpexcept.ignore")\n ret double %r }'
  z,_=opt(body,'round-'+mode,['-bennett-normalise-only','-S','-o','-'])
  check('constrained-unfused-'+mode,z.returncode==0 and '@__bennett_sf_mul_f64_rm' in z.stdout and '@__bennett_sf_add_f64_rm' in z.stdout and ('@__bennett_rt_fenv' in z.stdout if num is None else f'i32 {num})' in z.stdout),z.stderr)
 body='declare void @llvm.set.rounding(i32)\ndeclare i32 @llvm.get.rounding()\ndefine i32 @f() { call void @llvm.set.rounding(i32 1)\n %r = call i32 @llvm.get.rounding()\n ret i32 %r }'
 z,_=opt(body,'fenv',['-bennett-normalise-only','-S','-o','-'])
 check('fenv-state',z.returncode==0 and '@__bennett_rt_fenv' in z.stdout and 'call i32 @llvm.get.rounding' not in z.stdout,z.stderr)
 if a.major==18:
  body='declare i16 @llvm.convert.to.fp16.f64(double)\ndeclare double @llvm.convert.from.fp16.f64(i16)\ndefine double @f(double %x) { %h = call i16 @llvm.convert.to.fp16.f64(double %x)\n %r = call double @llvm.convert.from.fp16.f64(i16 %h)\n ret double %r }'
  z,_=opt(body,'fp16',['-bennett-normalise-only','-S','-o','-'])
  check('fp16-conversion',z.returncode==0 and '@__bennett_sf_fptrunc_f64_f16' in z.stdout and '@__bennett_sf_fpext_f16_f64' in z.stdout,z.stderr)
 # S2's private N9/N32 graph must not rewrite a host global's undef image.
 body='@g = internal global double undef\ndefine double @top() { %r = atomicrmw fadd ptr @g, double 1.0 seq_cst\n ret double %r }'
 z,_=opt(body,'host-image',['-bennett-analysis-only','-S','-o','-'])
 check('S2-host-image-preserved',z.returncode==0 and '@g = internal global double undef' in z.stdout,z.stderr)
 # Bind every predicate, integer extension and introduced helper in the S2 fixpoint.
 library='''define internal i1 @predicate(i64 %a, i64 %b, i32 %p) { %r = icmp eq i32 %p, 14
 ret i1 %r }
define i1 @__bennett_sf_cmp_f64(i64 %a, i64 %b, i32 %p) { %r = call i1 @predicate(i64 %a,i64 %b,i32 14)
 ret i1 %r }
define i64 @__bennett_sf_add_f64(i64 %a, i64 %b) { %r = xor i64 %a, %b
 ret i64 %r }
define i64 @__bennett_sf_sitofp_f64(i128 %a) { %r = trunc i128 %a to i64
 ret i64 %r }
'''
 lib=d/'arith.ll';lib.write_text(library);bc=d/'arith.bc';z=run([tool+'llvm-as',lib,'-o',bc]);assert z.returncode==0,z.stderr
 body='''define internal i1 @cmp(double %a, double %b) { %r = fcmp une double %a, %b
 ret i1 %r }
define i1 @top() { %v = call i1 @cmp(double 0.0,double 1.0)
 ret i1 %v }
'''
 rep=d/'analysis.json';z,_=opt(body,'analysis',['-bennett-analysis-only','-bennett-report='+str(rep),'-disable-output'],bc)
 data=json.loads(rep.read_text()) if z.returncode==0 else {};values=data.get('values',[])
 check('S2-comparison-closure',z.returncode==0 and any(v['function']=='top' and v['value']=='%v' and set(v['atoms'])=={'INT(0)','INT(1)'} and not v['top'] for v in values),z.stderr)
 # A linked FP atomic must transport helper effects, not perform integer arithmetic on bits.
 atomicbody='''@g = internal global double 0.0
define i64 @top() { %old = atomicrmw fmax ptr @g, double 1.0 seq_cst
 %v = load double, ptr @g
 %bits = bitcast double %v to i64
 ret i64 %bits }
'''
 atomiclib=d/'atomic.ll';atomiclib.write_text('define i64 @__bennett_sf_maxnum_f64(i64 %a,i64 %b) { ret i64 42 }')
 rep=d/'atomic-analysis.json';z,_=opt(atomicbody,'atomic-analysis',['-bennett-analysis-only','-bennett-report='+str(rep),'-disable-output'],atomiclib)
 data=json.loads(rep.read_text()) if z.returncode==0 else {}
 check('S2-FP-atomic',z.returncode==0 and any(v['value']=='%bits' and set(v['atoms'])=={'INT(0)','INT(42)'} and not v['top'] for v in data.get('values',[])),z.stderr)
 # Native comparison requires actual definitions (missing, corrupt and incomplete edges fail loudly).
 z,_=opt(body,'missing',['-bennett-comparison','-disable-output'])
 check('missing-entry',z.returncode!=0 and '§13.1 missing entry point __bennett_sf_cmp_f64' in z.stderr and 'BENNETT_ARITH_BITCODE' in z.stderr,z.stderr)
 z,_=opt(body,'bad-path',['-bennett-comparison','-disable-output'],d/'absent.bc')
 check('missing-bitcode-file',z.returncode!=0 and '§13.1 BENNETT_ARITH_BITCODE' in z.stderr,z.stderr)
 z,_=opt(body,'incomplete',['-bennett-comparison','-disable-output'],atomiclib)
 check('incomplete-bitcode',z.returncode!=0 and 'missing entry point __bennett_sf_cmp_f64' in z.stderr,z.stderr)
 comparison=d/'comparison.bc';z,_=opt(body,'comparison',['-bennett-comparison','-o',str(comparison)],bc)
 check('comparison-link',z.returncode==0,z.stderr)
 if z.returncode==0:
  e=dict(env,BENNETT_ARITH_BITCODE=str(bc))
  again=run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-comparison',comparison,'-disable-output'],e)
  check('comparison-relink-idempotent',again.returncode==0,again.stderr)
 if z.returncode==0:
  for level in (0,3):
   src=d/'main.c';src.write_text('extern _Bool top(void); int main(void) { return top()!=1; }')
   exe=d/f'compare-O{level}';z=run([tool+'clang',f'-O{level}',comparison,src,'-o',exe]);check(f'comparison-O{level}',z.returncode==0 and run([exe]).returncode==0,z.stderr)
 # Production L closure via a real descriptor and CC launch; helper body change changes the key.
 production='''define internal i1 @region(i64 %x) { %a = bitcast i64 %x to double
 %r = fcmp une double %a, 0.0
 ret i1 %r }
define void @top() {
 %d = alloca [64 x i8], align 8
 %q = call ptr @__bennett_qalloc(i64 0,i64 64)
 %t = call ptr @__bennett_qalloc(i64 0,i64 1)
 %f = call ptr @__bennett_qalloc(i64 0,i64 4)
 STORES
 call void @__bennett_oracle(ptr @region,ptr null,ptr %d)
 call void @__bennett_oracle(ptr @region,ptr null,ptr %d)
 call void @__bennett_qfree(ptr %f)
 call void @__bennett_qfree(ptr %t)
 call void @__bennett_qfree(ptr %q)
 ret void }
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_oracle(ptr,ptr,ptr)
'''
 fields=[(0,'i32','2'),(4,'i32','1'),(8,'i32','0'),(12,'i32','0'),(16,'ptr','%t'),(24,'ptr','%f'),(32,'i32','1'),(36,'i32','0'),(40,'ptr','%q'),(48,'i64','0'),(56,'i64','0')]
 production=production.replace('STORES','\n'.join(f'%p{j} = getelementptr i8, ptr %d, i64 {off}\n store {ty} {v}, ptr %p{j}' for j,(off,ty,v) in enumerate(fields)))
 out=d/'production';z,_=opt(production,'production-input',['-bennett-out='+str(out),'-bennett-budget-default=1000,0,256,16,0','-disable-output'],bc)
 check('production-link',z.returncode==0,z.stderr)
 if z.returncode==0:
  obj=out/'top/launch.bennett';z=run([REF,'check',obj]);check('production-check',z.returncode==0,z.stdout+z.stderr)
  z=run([REF,'run-program',obj,'top','--args','1000,1000','--budget','100000,0,256,16']);check('production-execute',z.returncode==0 and json.loads(z.stdout).get('status')=='COMPLETED',z.stdout+z.stderr)
  check('helper-transitive-closure','lproc @L3' in (out/'top/oracle-0/ref.bennett').read_text())
 # Direct CC FP arithmetic also consumes that library before SSA/CFG lowering.
 ccbody='''define i1 @top(i64 %x) { %q = call ptr @__bennett_qalloc(i64 0,i64 1)
 %a = bitcast i64 %x to double
 %r = fcmp une double %a,0.0
 call void @__bennett_qfree(ptr %q)
 ret i1 %r }
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
'''
 out=d/'cc';z,_=opt(ccbody,'cc-input',['-bennett-out='+str(out),'-disable-output'],bc)
 check('CC-link',z.returncode==0,z.stderr)
 if z.returncode==0:
  obj=out/'top/launch.bennett';z=run([REF,'check',obj]);check('CC-check',z.returncode==0,z.stdout+z.stderr)
  z=run([REF,'run-program',obj,'top','--args','0','--budget','100000,0,0,0'])
  check('CC-execute',z.returncode==0 and json.loads(z.stdout).get('results')==[{'type':'i1','value':'1'}],z.stdout+z.stderr)
 # N26 adapters execute both overlap directions and the zero-length/null cases.
 memory='declare void @__bennett_rt_memmove(ptr,ptr,i64)\ndeclare void @__bennett_rt_memset(ptr,i8,i64)\ndefine void @move(ptr %d,ptr %s,i64 %n) { call void @__bennett_rt_memmove(ptr %d,ptr %s,i64 %n)\n ret void }\ndefine void @fill(ptr %d,i8 %v,i64 %n) { call void @__bennett_rt_memset(ptr %d,i8 %v,i64 %n)\n ret void }'
 membc=d/'memory.bc';z,_=opt(memory,'memory-input',['-bennett-comparison','-o',str(membc)])
 check('comparison-memory-link',z.returncode==0,z.stderr)
 if z.returncode==0:
  main=d/'memory-main.c';main.write_text('#include <string.h>\nextern void move(void*,void*,unsigned long); extern void fill(void*,unsigned char,unsigned long); int main(void) { char s[9]="abcdefgh"; move(s+1,s,7); if(memcmp(s,"aabcdefg",8))return 1; move(s,s+1,7); if(memcmp(s,"abcdefg",7))return 2; fill(s,42,8); for(int i=0;i<8;i++)if(s[i]!=42)return 3; move(0,0,0); fill(0,0,0); return 0; }')
  exe=d/'memory-test';z=run([tool+'clang',membc,main,'-o',exe]);check('comparison-memory-overlap',z.returncode==0 and run([exe]).returncode==0,z.stderr)
 # Signaling comparison cannot silently use the quiet helper (published ABI question chn).
 body='declare i1 @llvm.experimental.constrained.fcmps.f64(double,double,metadata,metadata)\ndefine i1 @f(double %a,double %b) { %r = call i1 @llvm.experimental.constrained.fcmps.f64(double %a,double %b,metadata !"oeq",metadata !"fpexcept.strict")\n ret i1 %r }'
 z,_=opt(body,'signaling',['-bennett-normalise-only','-S','-o','-'])
 check('signaling-ABI-loud',z.returncode!=0 and 'bennett-arith-chn' in z.stderr,z.stderr)
 # The newly published numerical library is consumed solely via its pinned binary edge.
 pins=tomllib.loads((R/'SPEC_VERSIONS.toml').read_text())['arith'];published=__import__('pathlib').Path(pins[f'llvm{a.major}_path'])
 check('published-pin',hashlib.sha256(published.read_bytes()).hexdigest()==pins[f'llvm{a.major}_sha256'])
 manifest=json.loads((published.parent/'manifest.json').read_text());exports={x['name'] for x in manifest['exports']}
 check('published-required-exports',all('__bennett_sf_'+op+'_f64' in exports for op in ['sitofp','add','mul','div','cmp']))
 realenv=dict(os.environ);realenv.pop('BENNETT_ARITH_BITCODE',None)
 real=d/'real.ll';real.write_text('define i64 @real(i64 %x) { %a = sitofp i64 %x to double\n %b = fadd double %a, 1.0\n %r = bitcast double %b to i64\n ret i64 %r }')
 realbc=d/'real.bc';z=run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-comparison',real,'-o',realbc],realenv)
 check('published-comparison-link',z.returncode==0,z.stderr)
 if z.returncode==0:
  main=d/'real-main.c';main.write_text('#include <stdint.h>\nextern uint64_t real(uint64_t); int main(void) { return real(2)!=UINT64_C(0x4008000000000000) || real(0)!=UINT64_C(0x3ff0000000000000); }')
  for level in (0,3):
   exe=d/f'real-O{level}';z=run([tool+'clang',f'-O{level}',realbc,main,'-o',exe],realenv)
   check(f'published-comparison-O{level}',z.returncode==0 and run([exe],realenv).returncode==0,z.stderr)
 # Real published production: LLVM18's next producer is flattened aggregate rows.
 # Major-local probes are recorded separately from the byte-identical object suite.
 realout=R/f'.tmp/softfloat-production-probe/{a.major}';shutil.rmtree(realout,ignore_errors=True)
 z=run([tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-out='+str(realout),'-bennett-budget-default=1000000,65536,65536,128,4096','-disable-output',d/'production-input.ll'],realenv)
 if a.major==18:
  expected='§16.4 scalar row' in z.stderr and 'extractvalue { i64, i64 }' in z.stderr
  check('published-production-next-rule',z.returncode!=0 and expected and not list(realout.rglob('*.bennett')),z.stderr)
  rows[-1]['expected_unimplemented']=True
  rows[-1]['determining_sentence']='§16.4: insertvalue/extractvalue use lift.mov of the depth-first flattened field locations; aggregate call results are unpacked field by field (bp-1us).'
 else:
  check('published-production-link',z.returncode==0,z.stderr)
  if z.returncode==0:
   obj=realout/'top/oracle-0/ref.bennett';z=run([REF,'check',obj]);check('published-production-check',z.returncode==0,z.stdout+z.stderr)
   for value in [0,1,0x3ff0000000000000,0x7ff0000000000000,0x7ff8000000000000]:
    z=run([REF,'run-oracle',obj,'ref','--input',str(value),'--budget','1000000,65536,65536,128'])
    data=json.loads(z.stdout) if z.returncode==0 else {}
    check('published-production-numerical-'+str(value),z.returncode==0 and data.get('code')==0 and data.get('payload')==int(value!=0),z.stdout+z.stderr)
   # The direct CC path has a concrete, separately owned recursive producer.
   # This is a known refusal, never a claim of CC numerical conformance.
   ccdir=realout/'direct-cc'
   z,_=opt(ccbody,'published-cc-input',['-bennett-out='+str(ccdir),'-disable-output'],published)
   (d/'published-cc-diagnostic.txt').write_text(z.stderr)
   check('published-production-CC-next-rule',z.returncode!=0 and '§13.1 recursive CC soft-float closure' in z.stderr and '@bennett_sf_eval' in z.stderr and not list(ccdir.rglob('*.bennett')),'\n'.join(z.stderr.splitlines()[:3]))
   rows[-1]['expected_unimplemented']=True
   rows[-1]['determining_sentence']='§13.1: The entry points are defined by bennett-arith and are part of its bitcode the driver links; recursive CC materialisation of bennett_sf_eval is required (bp-7ni), with the integer/memory and multi-result rules of §17.4.'
   if a.production_cc:
    launch=realout/'top/launch.bennett'
    z=run([REF,'run-program',launch,'top','--args','1000000,1000000','--budget','1000000,65536,65536,128'],timeout=600)
    check('published-production-CC-execute',z.returncode==0 and json.loads(z.stdout).get('status')=='COMPLETED',z.stdout+z.stderr)
 # Missing production helpers are unavailability, never an unknown host call or a trap object.
 z,_=opt(production,'production-missing',['-bennett-out='+str(d/'missing-out'),'-disable-output'])
 check('production-missing',z.returncode!=0 and '§13.1 missing entry point __bennett_sf_cmp_f64' in z.stderr,z.stderr)
 result=dict(major=a.major,cases=len(rows),passed=sum(r['ok'] for r in rows),results=rows)
 (R/f'.tmp/softfloat-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result['passed']!=result['cases']
if __name__=='__main__':raise SystemExit(main())
