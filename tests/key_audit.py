#!/usr/bin/env python3
"""Audit all published keys; unequal keys are obligations, never passing keys.

The full raw audit must remain red until every producer agrees. This accounting
check requires each remaining witness to have a live bead quoting its accepted
contract sentence. It does not change corpus deferrals or conformance verdicts.
"""
import argparse,json,subprocess,sys
from contracts import ROOT as R,dialect_text
p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args()
path=R/f'.tmp/region-key-audit-{a.major}.json';path.unlink(missing_ok=True)
x=subprocess.run([sys.executable,str(R/'tests/region_keys.py'),'--major',str(a.major),'--all-fixtures'],capture_output=True,text=True)
raw=json.loads(path.read_text());spec=dialect_text();beads=[json.loads(l) for l in (R/'.beads/issues.jsonl').read_text().splitlines()]
assert x.returncode==int(raw['passed']!=raw['cases']),x.stderr
owners={}
for bead in beads:
 meta=bead.get('metadata',{})
 if isinstance(meta,str):meta=json.loads(meta)
 if bead['status']=='closed':continue
 for witness in meta.get('region_key_witnesses',[]):
  assert witness not in owners,(witness,owners.get(witness),bead['id'])
  sentences=meta.get('determining_sentences',[])
  assert sentences and all(sentence in spec for sentence in sentences),(bead['id'],'missing accepted determining sentence')
  reason=meta.get('audit_remainder_reason','')
  assert reason.strip(),(bead['id'],'missing concrete remainder reason')
  owners[witness]=(bead['id'],reason)
remaining=[];unaccounted=[]
for row in raw['published_closures']:
 if not row['ok']:
  obligation=owners.get(row['fixture']);remaining.append(dict(witness=row['fixture'],bead=obligation[0] if obligation else None,reason=obligation[1] if obligation else None))
  if not obligation:unaccounted.append(row['fixture'])
# The four local identity checks must never be filed away as producer gaps.
assert all(raw['closure_checks'].values()),raw['closure_checks']
assert all(raw['checks'][name] for name in ['flags','freeze','rstep_preserved','host_preserved'])
result=dict(major=a.major,cases=raw['cases'],matched=raw['passed'],unmatched=raw['cases']-raw['passed'],accounted=len(remaining)-len(unaccounted),unaccounted=unaccounted,remaining=remaining)
(R/f'.tmp/key-audit-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(bool(unaccounted))
