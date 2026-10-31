#!/usr/bin/env python3
"""Staged selector precedence, unmatched maxima, explicit precedence and no rematch."""
import argparse,hashlib,json,shutil
from production import run, REF
from contracts import ROOT as R

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',required=True,type=int);a=p.parse_args()
 d=R/f'.tmp/production-budgets/{a.major}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
 src=R/f'.tmp/production/{a.major}/7/input.ll';assert src.exists(),'run production.py first'
 defaults={'steps':'5','heap':'0','stack':'7','depth':'1','sstack':'0'}
 table={'version':'0.2','defaults':defaults,'entries':[{'symbol':'inc?','steps':'4'},{'symbol':'*','steps':'3'},{'identity':'0'*64,'heap':'8','stack':'32'}]}
 cases=[]
 def lower(name,t,source=src):
  dest=d/name;dest.mkdir();tablefile=dest/'table.json';tablefile.write_text(json.dumps(t,sort_keys=True,separators=(',',':')))
  z=run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-budgets='+str(tablefile),'-bennett-out='+str(dest/'out'),'-disable-output',source]);row={'name':name,'exit':z.returncode,'diagnostic':z.stderr};cases.append(row)
  if z.returncode:return None
  row['build']=json.loads((dest/'out/top/build.json').read_text());obj=dest/'out/top/launch.bennett';c=run([REF,'check',obj]);row['check']=c.returncode==0;row['sha256']=hashlib.sha256(obj.read_bytes()).hexdigest()
  b=row['build']['budgets'];steps=[x['steps'] for x in b]
  z=run([REF,'run-program',obj,'top','--args',','.join((['11'] if source==src else [])+steps),'--budget','10000,0,32,2']);v=json.loads(z.stdout) if z.returncode==0 else {};row['execution']={'output':z.stdout+z.stderr,'ok':v.get('status')=='COMPLETED' and (source!=src or v.get('results')==[{'type':'i32','value':str(19 if steps[0]=='5' else 11)}])};return row
 baseline=lower('baseline',table)
 if baseline:
  b=baseline['build']['budget_table'];shape=b['shapes'][0];h=shape['selection_identity'];baseline['ok']=shape['resolved']['steps']=='4' and b['capacities']['heap']=='8' and b['capacities']['stack']=='32'
  table['entries'].insert(0,{'identity':h,'steps':'5'})
  over=lower('identity-once',table)
  if over:
   q=over['build']['budget_table']['shapes'][0];over['ok']=q['selection_identity']==h and q['identity']==shape['identity'] and q['resolved']['steps']=='5'
  # A region key beats earlier symbol entries, component by component.
  table['entries'].append({'region_key':shape['region_key'],'steps':'2','depth':'2'})
  key=lower('key-priority',table)
  if key:key['ok']=key['build']['budget_table']['shapes'][0]['baseline']['steps']=='2' and key['build']['budget_table']['shapes'][0]['resolved']['steps']=='5' and key['build']['budget_table']['shapes'][0]['resolved']['depth']=='2'
 explicit=lower('explicit-precedence',table,R/f'.tmp/production/{a.major}/published/input.ll')
 if explicit:explicit['ok']=all(b['steps']=='5' for b in explicit['build']['budgets']) and explicit['build']['budget_table']['capacities']['steps']=='5'
 report={'major':a.major,'cases':cases};(R/f'.tmp/production-budgets-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not cases or not all(c.get('ok') and c.get('check') and c.get('execution',{}).get('ok') for c in cases)
if __name__=='__main__':raise SystemExit(main())
