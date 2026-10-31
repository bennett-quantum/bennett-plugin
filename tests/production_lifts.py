#!/usr/bin/env python3
"""Published memory/call lifts through real descriptors and CC launch objects."""
import argparse, json, re, shutil
from contracts import ROOT as R, dialect_text
from scalars import run, REF

def execute(major, names):
 text=dialect_text();objects=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',text,re.S));maps=dict(re.findall(r'```text linkmap=([^\n ]+)\n(.*?)```',text,re.S))
 rows=[]
 for tag,body in re.findall(r'```llvm (lift=[^\n]+)\n(.*?)```',text,re.S):
  fields=dict(re.findall(r'(\w+)=([^ ]+)',tag));name=fields['lift']
  if name not in names:continue
  d=R/f'.tmp/production-lifts/{major}/{name}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
  desc=fields['desc'];bindings=re.findall(r'(IN|MEM_IN|ARG)\((\d+)(?:,zext)?\)',desc)
  widths=[int(n) for k,n in bindings];dev=re.search(r'ENTROPY\((\d+)\)',desc);target=int(re.search(r'tgt=(\d+)',desc)[1]);np=len(bindings)
  stores=[(0,'i32','2'),(4,'i32',str(np)),(8,'i32',str(int(bool(dev)))),(12,'i32','0'),(16,'ptr','%t'),(24,'ptr','%fault')];alloc=[];free=[]
  for j,(kind,n) in enumerate(bindings):
   n=int(n);base=32+32*j;code={'IN':1,'ARG':2,'MEM_IN':3}[kind];q='null';size=0;value=16 if kind=='ARG' else 0
   if kind!='ARG':
    q=f'%q{j}';bits=n if kind=='IN' else 8*(1<<n);size=(1<<n) if kind=='MEM_IN' else 0
    alloc.append(f'{q} = call ptr @__bennett_qalloc(i64 0, i64 {bits})');free.append(f'call void @__bennett_qfree(ptr {q})')
   stores.extend([(base,'i32',str(code)),(base+4,'i32','0'),(base+8,'ptr',q),(base+16,'i64',str(value)),(base+24,'i64',str(size))])
  if dev:
   alloc.append(f'%e = call ptr @__bennett_qalloc(i64 0, i64 {8*(1<<int(dev[1]))})');free.append('call void @__bennett_qfree(ptr %e)');base=32+32*np
   stores.extend([(base,'i32','1'),(base+4,'i32','0'),(base+8,'ptr','%e'),(base+16,'i64',dev[1])])
  for fn,sig in {'__bennett_nz_fault':'void @__bennett_nz_fault(i64)','__bennett_nz_alloc':'ptr @__bennett_nz_alloc(i64)','__bennett_nz_free':'void @__bennett_nz_free(ptr)'}.items():
   if '@'+fn in body and not re.search(r'(?:define|declare) [^\n]*@'+fn+r'\(',body):body+='\ndeclare '+sig+'\n'
  for j,(fn,addr) in enumerate(re.findall(r'function @([^ ]+) A=0x([a-fA-F0-9]+)',maps.get(name,''))):
   body=re.sub(r'(define [^\n]*@'+re.escape(fn)+r'\([^\n]*?\)) \{',r'\1 !bennett.address !'+str(900+j)+' {',body);body+='\n!'+str(900+j)+' = !{i64 '+str(int(addr,16))+'}\n'
  body+='\ndefine void @top() {\n%desc = alloca ['+str(32+32*np+24*bool(dev))+' x i8], align 8\n'
  body+='\n'.join(alloc)+f'\n%t = call ptr @__bennett_qalloc(i64 0, i64 {target})\n%fault = call ptr @__bennett_qalloc(i64 0, i64 4)\n'
  body+='\n'.join(f'%p{i} = getelementptr i8, ptr %desc, i64 {off}\nstore {ty} {v}, ptr %p{i}' for i,(off,ty,v) in enumerate(stores))
  body+='\n'+f'call void @__bennett_oracle(ptr {fields["region"]}, ptr null, ptr %desc)\n'*2+'call void @__bennett_qfree(ptr %fault)\ncall void @__bennett_qfree(ptr %t)\n'+'\n'.join(free)+'\nret void\n}\ndeclare ptr @__bennett_qalloc(i64, i64)\ndeclare void @__bennett_qfree(ptr)\ndeclare void @__bennett_oracle(ptr, ptr, ptr)\n'
  source=d/'input.ll';source.write_text(body);out=d/'out'
  layout=json.loads(objects[name].split('section layout\n')[1]);stack=1<<layout['S_cells'];heap=layout['heap_limit_max']
  z=run([f'/usr/lib/llvm-{major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10',f'-bennett-budget-default=10000,{heap},{stack},16,0','-bennett-out='+str(out),'-disable-output',source]);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr};rows.append(row)
  if z.returncode:continue
  row['reference_exact']=(out/'top/oracle-0/ref.bennett').read_bytes()==objects[name].encode()
  obj=out/'top/launch.bennett';z=run([REF,'check',obj]);row['check']=z.returncode==0;row['check_output']=z.stdout+z.stderr
  z=run([REF,'run-program',obj,'top','--args','10000,10000','--budget',f'100000,{heap},{stack},16']);row['execution']=z.stdout+z.stderr;row['run']=z.returncode==0 and json.loads(z.stdout).get('status')=='COMPLETED'
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',required=True,type=int);p.add_argument('--case',action='append');a=p.parse_args();rows=execute(a.major,a.case or ['entry-replay-byte','rung4-mini','rung8-mini','listsum']);report={'major':a.major,'cases':rows};(R/f'.tmp/production-lifts-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not rows or not all(r.get('reference_exact') and r.get('check') and r.get('run') for r in rows)
if __name__=='__main__':raise SystemExit(main())
