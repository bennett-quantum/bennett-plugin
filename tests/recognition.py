#!/usr/bin/env python3
"""DA/DB/DC regression tests: published examples, never checker implementation."""
import argparse, json, os, re, subprocess, tempfile
from pathlib import Path
from contracts import dialect_text
R = Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--major',type=int,required=True); p.add_argument('--case',action='append'); a=p.parse_args()
 tool=Path(f'/usr/lib/llvm-{a.major}/bin/opt'); plugin=R/f'build/libbennett-plugin-{a.major}.so'
 spec=dialect_text()
 decls=re.search(r'```llvm markers-ir\n(.*?)```',spec,re.S)[1]
 cases=[]
 for attrs,body in re.findall(r'```llvm ([^\n]*)\n(.*?)```',spec,re.S):
  fields=dict(re.findall(r'(\w+)=([^ ]+)',attrs))
  name=fields.get('example','')
  if name.startswith(('recog-','attr-','handle-','region-','pt')) or name in ['version-flag','julia-jlplt','effect-lie']:
   if a.case and name not in a.case:continue
   if 'majors' in fields and str(a.major) not in fields['majors'].split(','):continue
   if not fields.get('verdict','').startswith(('accept','reject','blocked')): continue
   used=set(re.findall(r'@(__bennett_\w+)',body)); declared=set(re.findall(r'(?:declare|define) [^@\n]+@([^ (]+)',body))
   body+='\n'+'\n'.join(l for l in decls.splitlines() if re.search(r'@([^ (]+)',l)[1] in used-declared)
   cases.append((name,body,fields['verdict']))
 failures=[]
 with tempfile.TemporaryDirectory(dir=R/'.tmp') as t:
  for name,body,want in cases:
   f=Path(t)/(name+'.ll'); f.write_text(body); report=Path(t)/'report.json'
   cmd=[str(tool),'-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-closed-unit','-bennett-report='+str(report),'-disable-output',str(f)]
   try:x=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=60)
   except subprocess.TimeoutExpired:
    failures.append((name,want,124,'timeout'));continue
   ok=(x.returncode==0) if not want.startswith('reject:') else x.returncode!=0 and want.split(':')[1] in x.stderr
   if ok and x.returncode==0 and report.exists():
    data=json.loads(report.read_text())
    if name=='pt6-byte-width':ok=any(v['value']=='%n' and v['atoms']==['INT(257)'] and not v['top'] for v in data['values'])
    if name in ['pt5-range','pt5-range-load']:ok=any(v['value']=='%w' and set(v['atoms'])=={'INT(1)','INT(3)'} and not v['top'] for v in data['values'])
    if name=='pt2-wrap':ok=any(v['value']=='%p' and v['atoms']==['PTR(@tab,0,0)'] and not v['top'] for v in data['values']) and [c['name'] for c in data['regions'][0]['candidates']]==['body']
    if name in ['pt6-zero-stack','pt6-zero-heap','pt8-zero-copy']:
     ok=all(any(v['value']==val and set(v['atoms'])==atoms and not v['top'] for v in data['values']) for val,atoms in [('%raw',{'INT(0)','INT(1)'}),('%width',{'INT(1)','INT(3)'})])
    for n,val,atoms in [('pt3-pack257','%bits',{'INT(257)'}),('pt3-pack256','%b',{'INT(256)'}),('pt3-unpack','%b',{'INT(3)'}),('pt10-lane-zero','%width',{'INT(1)','INT(2)','INT(4)'})]:
     if name==n:ok=any(v['value']==val and set(v['atoms'])==atoms and not v['top'] for v in data['values'])
    if name=='pt6-subrange':ok=any(v['value']=='%n' and v['top'] for v in data['values'])
   if not ok: failures.append((name,want,x.returncode,x.stderr[-1500:]))
 result={'major':a.major,'cases':len(cases),'passed':len(cases)-len(failures),'failures':failures}
 (R/f'.tmp/recognition-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 return bool(failures)
if __name__=='__main__': raise SystemExit(main())
