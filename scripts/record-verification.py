#!/usr/bin/env python3
"""Record actual fourth-pass gate and incomplete M1 acceptance audits."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tests'))
from contracts import PIN,dialect_text,drift

def read(name):return json.loads((R/'.tmp'/name).read_text())
assert (R/'.tmp/fourth-pre-push.exit').read_text().strip()=='0'
assert (R/'.tmp/fourth-pre-push.exit').stat().st_mtime_ns >= (R/'.tmp/fourth-verified-gate.log').stat().st_mtime_ns
assert not drift()
log=(R/'.tmp/fourth-verified-gate.log').read_text()
assert 'gate policy: 7 assertions passed' in log and 'contract policy: 5 assertions passed' in log
gate=read('corpus-gate.json');before=read('fourth-before-gate.json')
assert gate['dialect_commit']==PIN and not gate['accepted_contract_drift']
for major,h in gate['plugin_sha256'].items():
 assert hashlib.sha256((R/f'build/libbennett-plugin-{major}.so').read_bytes()).hexdigest()==h
previous=json.loads((R/'docs/verification.json').read_text())
result={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'code_head':subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip(),
 'dialect':'0.2.10','dialect_commit':PIN,'dialect_spec_sha256':hashlib.sha256(dialect_text().encode()).hexdigest(),'isa':'0.8',
 'contract_head':gate['contract_head'],'contract_head_drift':gate['contract_head_drift'],
 'contract_worktree_drift':gate['contract_worktree_drift'],'accepted_contract_drift':gate['accepted_contract_drift'],
 'plugin_sha256':gate['plugin_sha256'],'pre_push_exit':0,
 'before':{'code_head':'2d5f323','dialect_commit':before['dialect_commit'],'plugin_sha256':before['plugin_sha256'],'corpus_summary':before['summary'],'pre_push_exit':0,'reason':'Reproduced clean third-pass HEAD before fourth-pass implementation.'},
 'corpus_summary':gate['summary'],'corpus_scope':gate['scope'],
 'non_agreeing':[r for r in gate['cells'] if r['classification']!='agree'],
 'common_checks':{'gate_policy_assertions':7,'contract_policy_assertions':5},'checks':{},'scalars':{},'acceptance_audits':{},'milestone_1_complete':False,'production_launch_implemented':False,
 'spec_corpus_scalar_inventory':{'scalar_oracle_cases':[],'quantum_action_cases':sorted({r['case'] for r in gate['cells'] if r['case'].startswith('spec-')})},
 'objects_without_lift':{'arena-o1':'M3: TDL-4 arena and section 16.2 hidden arena pointer; bp-qql','entry-stack':'M2: section 8.5 replay/adoption helper closure and section 16.4 calls/memory; bp-311'},
 'remaining_M1':{'general_reference_audit_and_all_rule_keys':'bp-3w4','intrinsic_thunk_ordering_question':'bp-tr5','production_descriptors_CC_launches_host_stubs_records':'bp-2zv','rung1_scalar_examples_missing':8,'object_only_vectors_not_emitted':['entry-stack','arena-o1']},
 'existing_mechanical_deferrals':{'FP':'bp-7ni: section 13.1 helpers and native comparison linking','memory_bindings_calls':'bp-311: sections 8.5/16.2/16.4; eight scalar lifts and entry-stack'},
 'limits':['No full section 21 conformance claim: L4 compares keys across the plugin, not every materialised optimisation pipeline.','Rustc/Julia/full frontend-LTO gate coverage remains open.','No production accept verdict, CC launch object, host entry replacement, full records or certificates.','Standalone reference layout still starts at 4096; general comparison-link layout is unavailable.','General modular represented-address, composite/atomic and boundary/generation tier audit remains open.'],
 'historical_step_checks':previous.get('historical_step_checks',previous.get('step_checks',{})),
 'historical_step_check_provenance':'Previous passes, unchanged inc8/switch5 bytes, 256 inputs each; not re-run in fourth pass. add2 exhaustive timeout remains historical.'}
for major in (18,23):
 checks={family:read(f'{family}-{major}.json') for family in ['recognition','analysis-edges','reference-images','materialisation','region-keys','descriptors']}
 for family in ['recognition','analysis-edges','reference-images','materialisation','region-keys']:assert checks[family]['passed']==checks[family]['cases']
 assert checks['descriptors']['descriptor_inc8_equal'] and checks['descriptors']['production_unimplemented']
 result['checks'][str(major)]=checks
 audit=read(f'region-key-audit-{major}.json')
 assert audit['passed']<audit['cases'] and not audit['checks']['n-lower-widenable']
 result['acceptance_audits'][str(major)]={'all_published_materialised_keys':audit,'exit':1,'complete':False}
 scalar=read(f'scalars-{major}.json');assert len(scalar['objects'])==20 and scalar['passed']==12 and len(scalar['deferred'])==8 and scalar['c_inc8_equal']
 for row in scalar['objects']:
  if row.get('lowered'):
   assert row['fixture_equal'] and row['hash_fixture_equal'] and row['check'] and all(x['ok'] for x in row['runs'])
   row['symbols']=json.loads(row.pop('hashes'))['symbols'];row.pop('check_output',None)
 result['scalars'][str(major)]=scalar
result['example_byte_equality']=[{'name':row['name'],**{str(major):next(x for x in result['scalars'][str(major)]['objects'] if x['name']==row['name']).get('fixture_equal',False) for major in (18,23)}} for row in result['scalars']['18']['objects']]
result['example_byte_equality'] += [{'name':name,'18':False,'23':False,'reason':'No published LLVM lift source; not compiler-emitted.'} for name in ['entry-stack','arena-o1']]
result['new_deferrals']=[]
(R/'docs/verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('Recorded actual dual-major gate, 12 byte-exact scalar objects and eight unavailable lifts per major.')
