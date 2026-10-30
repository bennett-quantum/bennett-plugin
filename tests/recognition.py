#!/usr/bin/env python3
"""DA/DB/DC regression tests: published examples, never checker implementation."""
import argparse, json, os, re, subprocess, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--major',type=int,required=True); a=p.parse_args()
 tool=Path(f'/usr/lib/llvm-{a.major}/bin/opt'); plugin=R/f'build/libbennett-plugin-{a.major}.so'
 spec=(R.parent/'bennett-dialect-spec/spec/Bennett-Dialect-Spec.md').read_text()
 decls=re.search(r'```llvm markers-ir\n(.*?)```',spec,re.S)[1]
 cases=[]
 for attrs,body in re.findall(r'```llvm ([^\n]*)\n(.*?)```',spec,re.S):
  fields=dict(re.findall(r'(\w+)=([^ ]+)',attrs))
  name=fields.get('example','')
  if name.startswith('recog-') or name in ['pt12-root-return','pt-variable-index','pt6-byte-width','pt6-subrange','version-flag']:
   if not fields.get('verdict','').startswith(('accept','reject','blocked')): continue
   used=set(re.findall(r'@(__bennett_\w+)',body)); declared=set(re.findall(r'(?:declare|define) [^@\n]+@([^ (]+)',body))
   body+='\n'+'\n'.join(l for l in decls.splitlines() if re.search(r'@([^ (]+)',l)[1] in used-declared)
   cases.append((name,body,fields['verdict']))
 failures=[]
 with tempfile.TemporaryDirectory(dir=R/'.tmp') as t:
  for name,body,want in cases:
   f=Path(t)/(name+'.ll'); f.write_text(body); report=Path(t)/'report.json'
   cmd=[str(tool),'-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.6','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(f)]
   x=subprocess.run(cmd,capture_output=True,text=True)
   ok=(x.returncode==0) if not want.startswith('reject:') else x.returncode!=0 and want.split(':')[1] in x.stderr
   if not ok: failures.append((name,want,x.returncode,x.stderr[-1500:]))
 print(json.dumps({'major':a.major,'cases':len(cases),'passed':len(cases)-len(failures),'failures':failures},indent=2))
 return bool(failures)
if __name__=='__main__': raise SystemExit(main())
