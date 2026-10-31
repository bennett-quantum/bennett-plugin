#!/usr/bin/env python3
"""Record sixth-pass actual runs without promoting partial launches to M1 acceptance."""
import datetime,hashlib,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tests'))
from contracts import PIN,dialect_text,drift
def read(name):return json.loads((R/'.tmp'/name).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert (R/'.tmp/sixth-final-gate.exit').read_text().strip()=='0'
assert (R/'.tmp/sixth-final-gate.exit').stat().st_mtime_ns >= (R/'.tmp/sixth-final-gate.log').stat().st_mtime_ns
assert not drift()
gate=read('corpus-gate.json');before=read('sixth-before-gate.json')
assert gate['dialect_commit']==before['dialect_commit']==PIN and not gate['accepted_contract_drift']
assert all(digest(R/f'build/libbennett-plugin-{major}.so')==h for major,h in gate['plugin_sha256'].items())
result=json.loads(subprocess.check_output(['git','-C',str(R),'show','a2bce18:docs/verification.json'],text=True))
result['historical_fifth_pass_recorded_at']=result['recorded_at']
result.update({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'code_head':subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip(),
 'plugin_sha256':gate['plugin_sha256'],'pre_push_exit':0,'corpus_summary':gate['summary'],
 'contract_head':gate['contract_head'],'contract_head_drift':gate['contract_head_drift'],
 'contract_worktree_drift':gate['contract_worktree_drift'],'accepted_contract_drift':gate['accepted_contract_drift'],
 'non_agreeing':[r for r in gate['cells'] if r['classification']!='agree'],
 'before':{'code_head':'a2bce18','corpus_summary':before['summary'],'plugin_sha256':before['plugin_sha256'],
   'corpus_exit':0,'production_exit':{'18':1,'23':1},'provenance':'Fresh unchanged-binary corpus plus strict production probes. No fresh unchanged-code full pre-push claim.'},
 'production_launch_implemented':'partial','production_scalar_inc8_launch_implemented':True,
 'milestone_1_complete':False,'new_deferrals':[],
 'acceptance_audit_provenance':{'all_published_materialised_keys':'Historical fourth-pass all-fixture key audit retained; not rerun or claimed complete in sixth pass.',
   'production_scalar':'Fresh strict production, independent ISA check/run-program, native mock protocol and integer ABI tests on both majors. Full gate with stable plugin hashes exit 0.'}})
result['checks']={};result['scalars']={}
for major in (18,23):
 checks={name:read(f'{name}-{major}.json') for name in ['recognition','analysis-edges','reference-images','materialisation','region-keys','descriptors','production']}
 for name in ['recognition','analysis-edges','reference-images','materialisation','region-keys']:
  assert checks[name]['passed']==checks[name]['cases']
 assert checks['descriptors']['descriptor_inc8_equal'] and checks['descriptors']['production_complete'] and checks['descriptors']['production_exit']==0
 prod=checks['production'];assert prod['passed']==3 and prod['published_oracle_inc8']['ok'] and prod['native_abi']['ok']
 for row in prod['cases']:
  assert row['ok'] and row['host_protocol'] and all(r['ok'] for r in row['runs'])
  row.pop('check_output',None)
 result['checks'][str(major)]=checks
 scalars=read(f'scalars-{major}.json');assert scalars['passed']==16 and len(scalars['objects'])==20 and len(scalars['deferred'])==4 and scalars['c_inc8_equal']
 assert sum(len(row.get('runs',[])) for row in scalars['objects'])==40
 for row in scalars['objects']:
  if row.get('lowered'):
   assert row['fixture_equal'] and row['hash_fixture_equal'] and row['check'] and all(r['ok'] for r in row['runs'])
   row['symbols']=json.loads(row.pop('hashes'))['symbols'];row.pop('check_output',None)
 result['scalars'][str(major)]=scalars
# Published reference-byte evidence and generated CC-byte evidence are separate.
fixtures=dict(re.findall(r'```isa object=([^\n ]+)\n(.*?)```',dialect_text(),re.S))
paths=[(name,f'.tmp/scalars/{{major}}/{name}/ref.bennett',name) for name in ['inc8','binding-out-byte','binding-clock-read','binding-block-byte','binding-console-byte']]
paths += [('descriptor-reference inc8','.tmp/descriptors/{major}/oracle-0/ref.bennett','inc8'),
 ('production C descriptor reference','.tmp/descriptors/{major}/production/top/oracle-0/ref.bennett','inc8'),
 ('production C descriptor CC','.tmp/descriptors/{major}/production/top/launch.bennett',None)]
for x in [0,7,255]:
 paths += [(f'production measured-{x} reference',f'.tmp/production/{{major}}/{x}/out/top/oracle-0/ref.bennett','inc8'),
  (f'production measured-{x} CC',f'.tmp/production/{{major}}/{x}/out/top/launch.bennett',None)]
paths += [('production published-oracle-inc8 reference','.tmp/production/{major}/published/out/top/oracle-0/ref.bennett','inc8'),
 ('production published-oracle-inc8 CC','.tmp/production/{major}/published/out/top/launch.bennett',None),
 ('production integer-ABI CC','.tmp/production/{major}/abi/out/abi/launch.bennett',None)]
byte_table=[]
for name,pattern,golden in paths:
 row={'name':name,'published_golden':golden,'majors':{}}
 for major in (18,23):
  path=R/pattern.format(major=major);data=path.read_bytes()
  row['majors'][str(major)]={'path':str(path.relative_to(R)),'sha256':digest(path),'bytes':len(data),'published_byte_equal':data==fixtures[golden].encode() if golden else None}
  if golden:assert row['majors'][str(major)]['published_byte_equal']
  else:
   ref=R.parent/'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'
   checked=subprocess.run([ref,'check',path],capture_output=True,text=True,timeout=60)
   assert checked.returncode==0,checked.stderr
   row['majors'][str(major)]['independent_check']=json.loads(checked.stdout)
   if name in ['production C descriptor CC','production integer-ABI CC']:
    abi=name=='production integer-ABI CC'
    execution=subprocess.run([ref,'run-program',path,'abi' if abi else 'top','--args','11' if abi else '5','--budget','10000,0,0,0' if abi else '10000,0,7,1'],capture_output=True,text=True,timeout=60)
    assert execution.returncode==0,execution.stderr
    v=json.loads(execution.stdout);assert v['status']==('COMPLETED' if abi else 'FAILED') and v['run_state']=='CLOSED'
    if abi:assert v['results']==[{'type':'i8','value':'11'}]
    else:assert v['fault']==4
    row['majors'][str(major)]['independent_run']=v
 row['cross_major_byte_equal']=(R/pattern.format(major=18)).read_bytes()==(R/pattern.format(major=23)).read_bytes()
 assert row['cross_major_byte_equal']
 byte_table.append(row)
result['sixth_pass']={'commits':['bc14d48','563ca6a'],'gate_exit':0,'gate_command':'env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR='+str(R/'.tmp')+' '+str(R/'scripts/pre-push'),
 'initial_gate_exit':1,'initial_gate_valid':False,'initial_gate_cause':'Plugin digest changed during corpus after ABI rebuild; final gate rerun in full against stable binaries.',
 'red_probes':{str(m):(R/f'.tmp/sixth-red-{m}.log').read_text() for m in (18,23)},
 'byte_equality':byte_table,'published_cc_golden':False,'golden_bead':'bp-95o',
 'host_target':'BENNETT_TARGET contains runtime target JCS; no environment service outside launch ABI',
 'host_runtime_witness':'Native compiled mock checks published ABI protocol and arguments/result and captured embedded bytes; actual ISA objects are independently executed by run-program. Not a linked launch-library acceptance claim.',
 'certificate_status':'Hash-bound metadata only; empty regions, no checked executable claims or target/schedule binding. Required completion remains bp-2zv.',
 'remaining_bead':'bp-2zv','remaining_sub_items':[
  'Scalar OUT/MEM_IN/device descriptors, multiple distinct shapes/regions and finite dispatch/general handle/CC environments (dialect 8.2,8.3,6.5,17.4).',
  'Full budget-table selection/identity overlays and frozen componentwise capacity maxima (dialect 9.2).',
  'Target/schedule-bound checked executable certificate claims and full record/coverage acceptance (dialect 19.9; ISA 9.2,12).',
  'Paired published production CC byte fixture (bp-95o; dialect 17.4 plugin-defined lowering).']}
result['remaining_M1']['production_descriptors_CC_launches_host_stubs_records']='bp-2zv: scalar IN/ARG launches/stubs implemented; full production acceptance sub-items in sixth_pass'
result['limits']=[x for x in result['limits'] if not x.startswith('No production accept verdict')]
result['limits'].append('Partial production scalar launch implementation: no full descriptor dispatch/budget-table or checked executable certificate acceptance; bp-2zv remains open. No paired published CC golden (bp-95o).')
(R/'docs/verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('Recorded actual dual-major gate, exact references, executable scalar launches, and explicit incomplete production acceptance.')
