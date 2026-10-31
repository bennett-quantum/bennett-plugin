#!/usr/bin/env python3
"""§7.3 scalar materialised closure identity, preserving the original H module."""
import argparse,json,subprocess
from contracts import ROOT as R
p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
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
define void @top() {
 call void @__bennett_oracle(ptr @flags,ptr null,ptr null)
 call void @__bennett_oracle(ptr @plain,ptr null,ptr null)
 call void @__bennett_oracle(ptr @frozen,ptr null,ptr null)
 call void @__bennett_oracle(ptr @identity,ptr null,ptr null)
 ret void }
''')
x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-S',str(source),'-o',str(out)],capture_output=True,text=True)
keys=[r['candidates'][0]['key'] for r in json.loads(report.read_text())['regions']] if x.returncode==0 else []
checks={'flags':len(keys)==4 and keys[0]==keys[1],'freeze':len(keys)==4 and keys[2]==keys[3],'host_preserved':x.returncode==0 and 'add nsw' in out.read_text() and 'freeze i8' in out.read_text()}
result={'major':a.major,'checks':checks,'passed':sum(checks.values()),'diagnostic':x.stderr}
(R/f'.tmp/region-keys-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
raise SystemExit(not all(checks.values()))
