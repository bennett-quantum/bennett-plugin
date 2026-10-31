#!/usr/bin/env python3
"""Record fifth-pass runs; production failure is not a passing M1 verdict."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tests'))
from contracts import PIN,dialect_text,drift
def read(name):return json.loads((R/'.tmp'/name).read_text())
assert (R/'.tmp/fifth-dry-run.exit').read_text().strip()=='0'
assert (R/'.tmp/fifth-dry-run.exit').stat().st_mtime_ns >= (R/'.tmp/fifth-dry-run.log').stat().st_mtime_ns
assert (R/'.tmp/fifth-before-corpus.exit').read_text().strip()=='0'
assert not drift()
log=(R/'.tmp/fifth-dry-run.log').read_text()
assert 'gate policy: 7 assertions passed' in log and 'contract policy: 5 assertions passed' in log
gate=read('corpus-gate.json');before=read('fifth-before-gate.json')
assert gate['dialect_commit']==before['dialect_commit']==PIN and not gate['accepted_contract_drift']
for major,h in gate['plugin_sha256'].items():
 assert hashlib.sha256((R/f'build/libbennett-plugin-{major}.so').read_bytes()).hexdigest()==h
result=json.loads(subprocess.check_output(['git','-C',str(R),'show','91a0d7d:docs/verification.json'],text=True))
previous_recorded_at=result['recorded_at']
result.update({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'code_head':subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip(),
 'dialect':'0.2.10','dialect_commit':PIN,'dialect_spec_sha256':hashlib.sha256(dialect_text().encode()).hexdigest(),'isa':'0.8',
 'contract_head':gate['contract_head'],'contract_head_drift':gate['contract_head_drift'],
 'contract_worktree_drift':gate['contract_worktree_drift'],'accepted_contract_drift':gate['accepted_contract_drift'],
 'plugin_sha256':gate['plugin_sha256'],'pre_push_exit':0,
 'before':{'code_head':'91a0d7d','dialect_commit':PIN,'plugin_sha256':before['plugin_sha256'],
   'corpus_summary':before['summary'],'corpus_exit':0,
   'initial_pre_push_exit':int((R/'.tmp/fifth-before.exit').read_text()),
   'reason':'Fresh unchanged-binary corpus passed. Initial pre-push encountered the newly strict binding assertions and exited 1 (TDD red); it did not reach the corpus suite.'},
 'corpus_summary':gate['summary'],'corpus_scope':gate['scope'],
 'non_agreeing':[r for r in gate['cells'] if r['classification']!='agree'],
 'checks':{},'scalars':{},'milestone_1_complete':False,'production_launch_implemented':False,'new_deferrals':[],
 'hook_verification':{'command':'git -C '+str(R)+' push --dry-run','exit':0,'gate_executed':True,'pushed':False,
   'fixes':['unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE','resolve installed hook symlink before git root discovery'],
   'red_exit':128,'first_dry_run_exit':1,'first_dry_run_error':'fatal: this operation must be run in a work tree',
   'first_dry_run_cause':'Unsetting alone leaves root discovery inside .git/hooks.'},
 'acceptance_audit_provenance':{'all_published_materialised_keys':'Historical fourth-pass runs recorded at '+previous_recorded_at+'; not rerun in fifth pass. Analysis/key implementation unchanged.',
   'production_scalar':'Fresh --require-production smoke probes on both majors: exit 1, no production artefacts.'},
 'historical_step_check_provenance':'Earlier passes; unchanged inc8/switch5 bytes, 256 inputs each. Not rerun in fifth pass; add2 exhaustive timeout remains historical.'})
result['remaining_M1']['rung1_scalar_examples_missing']=4
result['existing_mechanical_deferrals']['memory_bindings_calls']='bp-311: sections 8.5/16.2/16.4; four remaining scalar lifts and entry-stack'
for major in (18,23):
 checks={family:read(f'{family}-{major}.json') for family in ['recognition','analysis-edges','reference-images','materialisation','region-keys','descriptors']}
 for family in ['recognition','analysis-edges','reference-images','materialisation','region-keys']:assert checks[family]['passed']==checks[family]['cases']
 descriptor=checks['descriptors']
 assert descriptor['descriptor_inc8_equal'] and descriptor['production_exit']==1
 assert descriptor['production_unimplemented'] and not descriptor['production_artifacts']
 result['checks'][str(major)]=checks
 scalar=read(f'scalars-{major}.json')
 assert len(scalar['objects'])==20 and scalar['passed']==16 and len(scalar['deferred'])==4 and scalar['c_inc8_equal']
 assert sum(len(row.get('runs',[])) for row in scalar['objects'])==40
 for row in scalar['objects']:
  if row.get('lowered'):
   assert row['fixture_equal'] and row['hash_fixture_equal'] and row['check'] and all(x['ok'] for x in row['runs'])
   row['symbols']=json.loads(row.pop('hashes'))['symbols'];row.pop('check_output',None)
 result['scalars'][str(major)]=scalar
result['example_byte_equality']=[{'name':row['name'],**{str(major):next(x for x in result['scalars'][str(major)]['objects'] if x['name']==row['name']).get('fixture_equal',False) for major in (18,23)}} for row in result['scalars']['18']['objects']]
result['example_byte_equality'] += [{'name':name,'18':False,'23':False,'reason':'No published LLVM lift source; not compiler-emitted.'} for name in ['entry-stack','arena-o1']]
result['fifth_pass']={'bindings':{'red':{'18':'0/4; exit 1','23':'0/4; exit 1'},'green':{'18':'4/4; five vectors','23':'4/4; five vectors'}},
 'production_scalar':{'18':'red; exit 1','23':'red; exit 1','bead':'bp-2zv',
   'root_cause':'BennettPass still rejects CC/marker event lowering; host replacement and launch records are not implemented.',
   'determining_requirements':['dialect 0.2.10 section 17.4: marker calls lower to region calls and qreg.* instructions with the handle register environment of section 6.5',
     'dialect 0.2.10 section 19.9: host module with device entries replaced by launch stubs; ISA objects, certificate, coverage and build record',
     'ISA 0.8 section 10: A run executes a device CC entry.'],
   'published_cc_launch_golden':False,
   'golden_note':'Section 17.4 makes CC/R lowering plugin-defined. inc8 is a published reference oracle/lproc object, not a CC launch object; this does not waive production obligations.'}}
(R/'docs/verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('Recorded dual-major dry-run hook/gate, 16 exact objects and 40 vectors per major; production remains red.')
