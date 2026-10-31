#!/usr/bin/env python3
"""§9.2's published H16 -> H32 witness, token binding and every step prefix."""
import argparse, copy, hashlib, json, re, shutil
from contracts import ROOT as R, dialect_text
from scalars import run, REF


def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
 text=dialect_text()
 def block(kind,name):return re.search(r'```'+kind+'='+name+r'[^\n]*\n(.*?)```',text,re.S)[1]
 runtime=block('llvm example','budget-stage-runtime');table=json.loads(block('json budget-table','budget-stage'));want=json.loads(block('text state','budget-stage'))
 d=R/f'.tmp/budget-stage/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 # Use the existing measured CC wrapper; only the region and budget source differ.
 wrapper=(R/f'.tmp/production/{a.major}/7/input.ll').read_text()
 wrapper=re.sub(r'define [^\n]*@inc8\(.*?^}', '',wrapper,flags=re.S|re.M)
 wrapper=wrapper.replace('@inc8','@f')
 source=d/'input.ll';source.write_text(wrapper+'\n'+runtime)
 rows=[]
 def lower(name,t,src=source):
  dest=d/name;dest.mkdir();tf=dest/'table.json';tf.write_text(json.dumps(t,sort_keys=True,separators=(',',':')))
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budgets='+str(tf),'-bennett-out='+str(dest/'out'),'-disable-output',src])
  row={'name':name,'lowered':z.returncode==0,'diagnostic':z.stderr};rows.append(row)
  if z.returncode:return None
  row['build']=json.loads((dest/'out/top/build.json').read_text());obj=dest/'out/top/oracle-0/ref.bennett';launch=dest/'out/top/launch.bennett'
  row['check']=all(run([REF,'check',x]).returncode==0 for x in (obj,launch));row['sha256']=hashlib.sha256(obj.read_bytes()).hexdigest()
  return row,obj,launch
 def oracle(obj,budget):
  z=run([REF,'run-oracle',obj,'ref','--input','7','--budget',budget]);assert z.returncode==0,z.stderr
  return json.loads(z.stdout)
 baseline=copy.deepcopy(table);baseline['entries']=[{'identity':'0'*64,'sstack':'32'}]
 base=lower('baseline',baseline);final=lower('identity-once',table)
 if base and final:
  br,bo,_=base;fr,fo,fl=final
  bs=br['build']['budget_table']['shapes'][0];fs=fr['build']['budget_table']['shapes'][0]
  br['reference_exact']=bo.read_bytes()==(R/'tests/fixtures/budget-stage-16.bennett').read_bytes()
  fr['reference_exact']=fo.read_bytes()==(R/'tests/fixtures/budget-stage-32.bennett').read_bytes()
  br['ok']=br['reference_exact'] and bs['selection_identity']==bs['identity']==want['selection_identity'] and oracle(bo,'10000,64,512,16')==want['baseline_run']
  fr['ok']=fr['reference_exact'] and fs['selection_identity']==want['selection_identity'] and fs['identity']==want['identity'] and {k:int(v) for k,v in fs['resolved'].items()}==want['resolved'] and {k:int(v) for k,v in fr['build']['budget_table']['capacities'].items()}==want['capacities'] and oracle(fo,'10000,64,512,16')==want['run']
  n24=d/'n24.ll';n24.write_text(wrapper+'\n'+re.sub(r'define i8 @f\(.*?^}',block('llvm normalise-in','n-budget-stage').strip(),runtime,count=1,flags=re.S|re.M))
  nr=lower('n24-source',table,n24)
  if nr:nr[0]['ok']=nr[1].read_bytes()==fo.read_bytes()
  # No fixed point: a final-hash entry must never replace the H16 overlay.
  trap=copy.deepcopy(table);trap['entries'].append({'identity':want['identity'],'sstack':'16'})
  no_rematch=lower('no-rematch',trap)
  if no_rematch:no_rematch[0]['ok']=no_rematch[1].read_bytes()==fo.read_bytes()
  steps=copy.deepcopy(table);steps['entries']=[{'identity':want['selection_identity'],'steps':'0'},{'identity':'0'*64,'sstack':'32'}]
  st=lower('steps-only',steps)
  if st:st[0]['ok']=st[1].read_bytes()==bo.read_bytes() and oracle(st[1],'0,64,512,16')==want['steps_only_run']
  # Every one of the 316 executed-row budget boundaries is checked independently.
  prefixes=[oracle(fo,f'{n},64,512,16') for n in range(1,317)]
  fr['prefix_vectors']=len(prefixes);fr['prefixes_ok']=all(v==({'code':1,'payload':0,'steps':n} if n<316 else want['run']) for n,v in enumerate(prefixes,1));fr['ok'] &= fr['prefixes_ok']
  # The actual CC launch token binds H32 and resolved limits; measurement sees 7.
  token=fr['build']['budgets'];fr['tokens_final']=all(b['identity']==want['identity'] and b['selection_identity']==want['selection_identity'] and b['sstack']=='32' for b in token);fr['ok'] &= fr['tokens_final']
  z=run([REF,'run-program',fl,'top','--args','11,10000,10000','--budget','100000,64,512,16']);fr['launch_output']=z.stdout+z.stderr
  fr['ok'] &= z.returncode==0 and json.loads(z.stdout).get('results')==[{'type':'i32','value':'18'}]
 # Proof refusal must not grant ordinary source memory a backing-only path.
 proof_cases=[]
 for name,bad in {
  'changed-bookkeeping':runtime.replace('store i64 %sp, ptr %slot','store i64 999, ptr %slot'),
  'out-of-frame':runtime.replace('%nz.fp.f, i64 0','%nz.fp.f, i64 24'),
  'after-pop':runtime.replace('  %v = load i8, ptr %p, align 1\n  call void @__bennett_rt_ss_pop(ptr %nz.fp.f)','  call void @__bennett_rt_ss_pop(ptr %nz.fp.f)\n  %v = load i8, ptr %p, align 1'),
  'external-state-writer':runtime+'\ndefine void @other() { store i64 8, ptr @ss_sp\n ret void }\n',
 }.items():
  src=d/(name+'.ll');src.write_text(bad)
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-oracle=f','-bennett-scalar-shape=IN(8,zext);tgt=8','-bennett-out='+str(d/name),'-disable-output',src])
  proof_cases.append({'name':name,'ok':z.returncode!=0 and 'linked runtime logical-frame validation' in z.stderr,'diagnostic':z.stderr})
 report={'major':a.major,'cases':rows,'proof_cases':proof_cases};(R/f'.tmp/budget-stage-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 return not all(r['ok'] for r in proof_cases) or not rows or not all(r.get('check') and r.get('ok') for r in rows)
if __name__=='__main__':raise SystemExit(main())
