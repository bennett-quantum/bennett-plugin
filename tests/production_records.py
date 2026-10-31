#!/usr/bin/env python3
"""Check artifact bindings/complete instruction coverage; no certificate-proof claim."""
import argparse,hashlib,json,re
from contracts import ROOT as R

def main():
 p=argparse.ArgumentParser();p.add_argument('--major',required=True,type=int);a=p.parse_args();report={'major':a.major,'cases':[]}
 for name in ['0','7','255','published','abi']:
  root=R/f'.tmp/production/{a.major}/{name}/out';entry='abi' if name=='abi' else 'top';d=root/entry
  row={'name':name,'ok':False};report['cases'].append(row)
  if not (d/'launch-record.json').exists():row['error']='missing launch-record.json';continue
  record=json.loads((d/'launch-record.json').read_text());row['artifact_hashes']=all((root/path).stat().st_size==v['bytes'] and hashlib.sha256((root/path).read_bytes()).hexdigest()==v['sha256'] for path,v in record['artifacts'].items())
  assert record['certificate_acceptance']=='metadata_only' # deliberately not executable acceptance
  obj=(d/'launch.bennett').read_text();symbols=json.loads(obj.split('section symbols\n')[1].split('\n')[0]);hashes={v['name']:v['interface_hash'] for v in symbols.values()}
  expected=[];symbol=block=None;ordinal=0
  for line in obj.split('section functions\n')[1].split('\n\nsection ')[0].splitlines():
   if re.match(r'(fn cc|oracle|lproc|action) @',line):symbol=re.search(r'@([^ (]+)',line)[1];continue
   if line.startswith('^'):block=line[1:].split('(')[0];ordinal=0;continue
   if not line or line.startswith('regs '):continue
   expected.append([hashes[symbol],block,ordinal]);ordinal+=1
  cov=json.loads((d/'all-coverage.json').read_text())['entries'];row['coverage_complete']=expected==[x['point'] for x in cov]
  row['coverage_sources']=all(x['source'].startswith('dialect-0.2.10:') for x in cov)
  row['metadata_hashes']={f:hashlib.sha256((d/f).read_bytes()).hexdigest() for f in ['build.json','certificate.json','coverage.json']}
  row['ok']=all(row[k] for k in ['artifact_hashes','coverage_complete','coverage_sources'])
 (R/f'.tmp/production-records-{a.major}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not all(x['ok'] for x in report['cases'])
if __name__=='__main__':raise SystemExit(main())
