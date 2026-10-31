#!/usr/bin/env python3
"""§7.3 scalar materialised closure identity, preserving the original H module."""
import argparse,json,re,subprocess
from contracts import ROOT as R,dialect_text
p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);p.add_argument('--all-fixtures',action='store_true',help='audit every published normalise fixture; fails until all keys agree');a=p.parse_args()
d=R/f'.tmp/region-keys/{a.major}';d.mkdir(parents=True,exist_ok=True)
source=d/'in.ll';out=d/'host.ll';report=d/'report.json'
source.write_text('''declare void @__bennett_oracle(ptr,ptr,ptr)
define internal i8 @flags(i8 %x) { %v = add nsw i8 %x, 1
 ret i8 %v }
define internal i8 @plain(i8 %x) { %v = add i8 %x, 1
 ret i8 %v }
define internal i8 @frozen(i8 %x) { %v = freeze i8 %x
 ret i8 %v }
define internal i8 @identity(i8 %x) { ret i8 %x }
define internal i8 @charged(i8 %x) { ret i8 %x, !bennett.rstep !0 }
define void @top() {
 call void @__bennett_oracle(ptr @flags,ptr null,ptr null)
 call void @__bennett_oracle(ptr @plain,ptr null,ptr null)
 call void @__bennett_oracle(ptr @frozen,ptr null,ptr null)
 call void @__bennett_oracle(ptr @identity,ptr null,ptr null)
 call void @__bennett_oracle(ptr @charged,ptr null,ptr null)
 ret void }
!0 = !{}
''')
x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-S',str(source),'-o',str(out)],capture_output=True,text=True)
keys=[r['candidates'][0]['key'] for r in json.loads(report.read_text())['regions']] if x.returncode==0 else []
checks={'flags':len(keys)==5 and keys[0]==keys[1],'freeze':len(keys)==5 and keys[2]==keys[3],
        'rstep_preserved':len(keys)==5 and keys[3]!=keys[4],
        'host_preserved':x.returncode==0 and 'add nsw' in out.read_text() and 'freeze i8' in out.read_text()}
# Compare source closures against independently published materialised closures.
# An absent transform is a failure; equality of two raw source keys is no witness.
spec=dialect_text()
pairs={tag:dict(re.findall(r'```llvm normalise-'+tag+r'=([^\n ]+)[^\n]*\n(.*?)```',spec,re.S)) for tag in ['in','out']}
fixtures=['n-flags','n-shift','n-undef','n-defined-zero','n-dynamic-lane','n-narrow-lane',
          'n-trap','n-memintrinsics','n-atomic','n-atomic-wrap',
          *(['n-atomic-usub'] if a.major==23 else [])]
if a.all_fixtures:
 fixtures=[name for name in pairs['in'] if name!='n-atomic-usub' or a.major==23]
details=[]
for name in fixtures:
 entry=re.search(r'define [^@\n]*@([^ (]+)',pairs['in'][name])[1]
 observed=[];errors=[]
 for tag in ['in','out']:
  path=d/f'{name}-{tag}.ll';rep=d/f'{name}-{tag}.json'
  path.write_text(pairs[tag][name]+f'\ndeclare void @__bennett_oracle(ptr,ptr,ptr)\ndefine void @__key_probe() {{\n call void @__bennett_oracle(ptr @{entry},ptr null,ptr null)\n ret void\n}}\n')
  rep.unlink(missing_ok=True)
  try:
   z=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(rep),'-disable-output',str(path)],capture_output=True,text=True,timeout=20)
  except subprocess.TimeoutExpired:
   z=subprocess.CompletedProcess([],124,'','key audit timed out after 20 seconds')
  observed.append(json.loads(rep.read_text())['regions'][0]['candidates'][0]['key'] if z.returncode==0 else None)
  errors.append(z.stderr if z.returncode else '')
 context=re.search(r'```llvm normalise-in='+re.escape(name)+r'([^\n]*)',spec)[1].strip()
 unsupported_context=bool(re.search(r'(rmode|platform)=',context))
 checks[name]=not unsupported_context and None not in observed and observed[0]==observed[1]
 details.append({'fixture':name,'keys':observed,'errors':errors,'ok':checks[name],
                 'context':context,'context_implemented':not unsupported_context})
result={'major':a.major,'checks':checks,'cases':len(checks),'passed':sum(checks.values()),'diagnostic':x.stderr,'published_closures':details}
(R/f'.tmp/{"region-key-audit" if a.all_fixtures else "region-keys"}-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
raise SystemExit(not all(checks.values()))
