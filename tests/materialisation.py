#!/usr/bin/env python3
"""Compare scalar N-rule output with published normalise-out instruction lists."""
import argparse,json,re,subprocess
from contracts import ROOT as R,dialect_text

def instructions(text):
 result={}
 for name,body in re.findall(r'define [^@\n]*@([^ (]+)[^{]*\{(.*?)^}',text,re.S|re.M):
  result[name]=[re.sub(r'\s+',' ',l.strip()) for l in body.splitlines() if l.strip() and not l.strip().endswith(':') and not l.lstrip().startswith(';')]
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();spec=dialect_text();pairs={tag:dict(re.findall(r'```llvm normalise-'+tag+r'=([^\n ]+)[^\n]*\n(.*?)```',spec,re.S)) for tag in ['in','out']};rows=[]
 for name in ['n-flags','n-shift','n-query','n-atomic-nand']:
  d=R/f'.tmp/materialisation/{a.major}/{name}';d.mkdir(parents=True,exist_ok=True);src=d/'in.ll';src.write_text(pairs['in'][name]);out=d/'out.ll'
  cmd=[f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.7','-bennett-normalise-only','-S',str(src),'-o',str(out)]
  x=subprocess.run(cmd,capture_output=True,text=True);actual=out.read_text() if x.returncode==0 else '';want=instructions(pairs['out'][name]);got=instructions(actual);ok=x.returncode==0 and got==want
  if name=='n-flags':ok=ok and all(s not in '\n'.join(l for l in actual.splitlines() if not l.startswith('declare')) for s in [' noundef',' nonnull','willreturn','mustprogress','memory(argmem:'])
  rows.append({'case':name,'ok':ok,'error':x.stderr.strip() if x.returncode else '' if ok else {'want':want,'got':got}})
 result={'major':a.major,'cases':len(rows),'passed':sum(x['ok'] for x in rows),'results':rows};(R/f'.tmp/materialisation-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return any(not x['ok'] for x in rows)
if __name__=='__main__':raise SystemExit(main())
