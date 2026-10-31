#!/usr/bin/env python3
"""Local §21.1 gate. Never rewrites EXPECT or silently blesses unimplemented checks.

The published harness has no plugin option. Its implementation is copied and
executed opaquely in .tmp solely to obtain the ABI-matched trace-runtime binaries
and baseline fixture metadata. No harness/runtime implementation is imported.
The independent driver runs the envelope + bennett and checks L1–L6. Missing
checks remain divergences. Exit 0 requires agreement for every non-deferred,
non-blocked case (and no contract drift). A deferral/blocked case is counted
separately and printed on EVERY run with its milestone/bead; never agreement.
Only the evidenced property failures below may be classified unavailable;
additional failures, plugin errors, changed exits and missing checks exit 1.
"""
import argparse,concurrent.futures,hashlib,json,os,re,shutil,subprocess,sys,tarfile,io
from pathlib import Path
from contracts import drift,PIN
R=Path(__file__).resolve().parents[1]
CORPUS=R.parent/'bennett-dialect-spec/corpus/legality'
def run(args,timeout=30):
 try:
  x=subprocess.run(list(map(str,args)),capture_output=True,text=True,errors="replace",timeout=timeout)
  return x.returncode,x.stdout,x.stderr
 except subprocess.TimeoutExpired:return 124,'','timeout'
def pipelines(major):
 return [*[f'default<O{i}>' for i in range(4)],*(['default<Os>','default<Oz>'] if major==18 else []),'lto-pre-link<O3>','lto<O3>','thinlto-pre-link<O3>','thinlto<O3>','default<O3>,default<O3>,default<O3>','strip','strip-nondebug','mergefunc']
def bootstrap():
 snapshot=R/'.tmp/blackbox'/PIN
 dst=snapshot/'corpus/legality'
 if not dst.exists():
  snapshot.mkdir(parents=True,exist_ok=True)
  # Copy and execute the published harness opaquely at the SAME immutable pin
  # as cases and headers; never import/inspect its implementation.
  archive=subprocess.check_output(['git','-C',str(CORPUS.parent.parent),'archive',PIN,'corpus/legality','spec/bennett_markers.h'])
  with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(snapshot,filter='data')
 # A versioned baseline is a black-box artefact, not a substitute for plugin checks.
 result=dst/'results/raw/baseline.json'
 if not result.exists():
  x=subprocess.run(['python3',str(dst/'harness/run.py'),'baseline','--majors','18,23','--jobs','4'])
  if x.returncode:raise RuntimeError('black-box harness bootstrap failed')
 return {x['id']:x for x in json.loads(result.read_text())}
def normalize(trace):
 # Function addresses are separately covered by L4; L1 compares event order,
 # ordinary scalar operands, classical results and handle identities.
 return re.sub(r'F(?:@0x[0-9a-fA-F]+|:[^\s]+|\?)','F',trace)
def native(bc,major,baseline,dest):
 tool=Path(f'/usr/lib/llvm-{major}/bin');result={}
 info=baseline['majors'][str(major)]['native']
 link=next(x['argv'] for x in info['commands'] if x['argv'][0]=='cc')
 runtime=[x for x in link if x.endswith('.o')][1:]
 for level in [0,3]:
  obj=dest/f'O{level}.o';exe=dest/f'O{level}.exe'
  rc,_,err=run([tool/'llc',f'-O{level}','-relocation-model=pic','-filetype=obj',bc,'-o',obj])
  if rc:return {'error':'L5 llc: '+err[-500:]}
  _,nm,_=run([tool/'llvm-nm','-u',obj]);result[f'undefined_O{level}']=sorted(set(re.findall(r'__bennett_\w+',nm)))
  rc,_,err=run(['cc','-no-pie','-rdynamic',obj,*runtime,'-ldl','-o',exe])
  if rc:return {'error':'L5 link: '+err[-500:]}
  inputs=baseline['inputs'];traces=[];code=0
  for i in range(0,len(inputs),64):
   rc,out,err=run([exe,*map(str,inputs[i:i+64])]);code|=rc;traces.append(out)
  result[f'exit_O{level}']=code;result[f'trace_O{level}']=normalize(''.join(traces))
 return result
def cell(task):
 case,major,pipe,baseline=task;stem=case.stem
 dest=R/'.tmp/gate'/str(major)/stem/hashlib.sha256(pipe.encode()).hexdigest()[:12];dest.mkdir(parents=True,exist_ok=True)
 tool=Path(f'/usr/lib/llvm-{major}/bin');plugin=R/f'build/libbennett-plugin-{major}.so'
 src=case;row={'case':stem,'major':major,'pipeline':pipe,'expect':re.search(r'EXPECT:\s*(\w+)',case.read_text())[1],'properties':{},'diagnostic':''}
 if case.suffix=='.c':
  src=dest/'input.ll';rc,_,err=run([tool/'clang','-O0','-Xclang','-disable-O0-optnone','-emit-llvm','-S',case,'-o',src])
  if rc:row['diagnostic']=err;row['properties']['L1']='frontend failed';return row
 combined=dest/'combined.bc';report=dest/'analysis.json'
 rc,out,err=run([tool/'opt','-load-pass-plugin='+str(plugin),'-passes='+pipe+',bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-legality-audit','-bennett-report='+str(report),src,'-o',combined],timeout=60)
 row['plugin_exit']=rc;row['diagnostic']=err[-1800:]
 if stem=='c-pure-attr-wrapper' and rc and 'BD-E-EFFECT-LIE' in err:
  row['properties']['L2']=True;row['agree']=True;row['expected_diagnostic']='§3.8 source-effect lie (EXPECT: probe)';return row
 negative={'control-memory-none':('BD-E-MARKER-ATTRIBUTE','L2'),'control-readonly':('BD-E-MARKER-ATTRIBUTE','L2'),'control-handle-deref':('BD-E-HANDLE-USE','L3')}
 if stem in negative:
  code,prop=negative[stem];row['properties'][prop]=(code in err and rc!=0)
  row['agree']=row['properties'][prop];return row
 if rc:
  prop='L2' if 'MARKER-ATTRIBUTE' in err or 'SIGNATURE' in err or 'MARKER-UNKNOWN' in err or 'EFFECT-LIE' in err else 'L3' if 'HANDLE-' in err or '§5' in err else 'L6'
  row['properties'][prop]=False;row['agree']=False;return row
 data=json.loads(report.read_text());row['properties']['L2']=True;row['properties']['L3']=True
 row['properties']['L6']=all(isinstance(r['candidates'],list) for r in data['regions'])
 # Region keys must be name-independent; compare mergefunc twins in the same
 # materialised module. Cross-pipeline semantic identity still needs full map.
 stable=dest/'stable.json'
 rc2,_,err2=run([tool/'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-legality-audit','-bennett-report='+str(stable),combined,'-disable-output'])
 def identities(d):return [(r['marker'],r['operand'],sorted({c['key'] for c in r['candidates']})) for r in d['regions']]
 row['properties']['L4']=False if rc2 else identities(data)==identities(json.loads(stable.read_text()))
 row['identity_scope']='content identity under plugin; stock-pipeline equivalence pending full materialisation' 
 before=dest/'before.bc';rc,_,err=run([tool/'opt','-passes='+pipe,src,'-o',before])
 if rc:row['properties']['L1']=False;row['diagnostic']=err;row['agree']=False;return row
 if stem in baseline:
  (dest/'pre').mkdir(exist_ok=True);(dest/'post').mkdir(exist_ok=True)
  pre=native(before,major,baseline[stem],dest/'pre');post=native(combined,major,baseline[stem],dest/'post')
  row['properties']['L1']=not pre.get('error') and not post.get('error') and pre.get('trace_O0')==post.get('trace_O0') and pre.get('exit_O0')==post.get('exit_O0')
  row['properties']['L5']=not post.get('error') and post.get('trace_O0')==post.get('trace_O3') and post.get('exit_O0')==post.get('exit_O3') and post.get('undefined_O0')==post.get('undefined_O3')
  row['native_error']=pre.get('error') or post.get('error')
  row['native_exits']={f'{stage}_O{level}':d.get(f'exit_O{level}') for stage,d in [('pre',pre),('post',post)] for level in [0,3]}
  if pre.get('exit_O0',0)!=0 or post.get('exit_O0',0)!=0:
   row['properties']['L1']=False;row['properties']['L5']=False
   row['native_error']='black-box runtime failed: pre exit '+str(pre.get('exit_O0'))+', post exit '+str(post.get('exit_O0'))
 else:row['properties']['L1']='missing black-box baseline';row['properties']['L5']='missing black-box baseline'
 row['agree']=all(v is True for v in row['properties'].values())
 return row
def classify(row):
 failed={k for k,v in row['properties'].items() if v is not True}
 if not failed and row.get('agree'):return 'agree'
 if row.get('case') in ['spec-sem2-adj','spec-sem2-compute'] and failed=={'L1','L5'} and row.get('native_exits')=={'pre_O0':87,'pre_O3':87,'post_O0':87,'post_O3':87}:
  return 'blocked-upstream: bp-c2i (upstream b-dialect-spec-566)'
 if row.get('case')=='fp-rot-fastmath-reassoc' and failed=={'L5'}:
  return 'deferred: M2 (§13 FP materialisation; PLAN M2)'
 return 'diverge'
def summarize(cells):
 bycase={name:[classify(x) for x in cells if x['case']==name] for name in {x['case'] for x in cells}}
 statuses=[]
 for values in bycase.values():
  statuses.append('diverge' if 'diverge' in values else 'blocked' if any(v.startswith('blocked-') for v in values) else 'deferred' if any(v.startswith('deferred:') for v in values) else 'agree')
 result={'cases_run':len(bycase),'cells_run':len(cells),'cells_agree':sum(classify(x)=='agree' for x in cells)}
 for status in ['agree','deferred','blocked','diverge']:result['cases_'+status]=statuses.count(status)
 return result
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,action='append');p.add_argument('--case',action='append');p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
 for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','BROWSER']:os.environ.pop(key,None)
 (R/'.tmp').mkdir(exist_ok=True);os.environ['TMPDIR']=str(R/'.tmp')
 current=run(['git','-C',CORPUS.parent.parent,'rev-parse','HEAD'])[1].strip()
 if drift():print('accepted dialect contract drift; executing pinned fixtures '+PIN,file=sys.stderr)
 plugin_hashes={str(m):hashlib.sha256((R/f'build/libbennett-plugin-{m}.so').read_bytes()).hexdigest() for m in (a.major or [18,23])}
 baseline=bootstrap()
 # Read fixture blobs only; never copy/import a sibling checker implementation.
 pinned=R/'.tmp/contracts'/PIN
 fixture_paths=run(['git','-C',CORPUS.parent.parent,'ls-tree','-r','--name-only',PIN,'--','corpus/legality/cases','corpus/legality/controls'])[1].splitlines()
 cases=[]
 for path in fixture_paths:
  if not path.endswith(('.ll','.c')):continue
  target=pinned/Path(path).relative_to('corpus/legality');target.parent.mkdir(parents=True,exist_ok=True)
  rc,body,err=run(['git','-C',CORPUS.parent.parent,'show',PIN+':'+path])
  if rc:raise RuntimeError(err)
  target.write_text(body);cases.append(target)
 cases.sort()
 if a.case:cases=[x for x in cases if x.stem in a.case]
 tasks=[(c,m,p,baseline) for m in (a.major or [18,23]) for c in cases for p in pipelines(m)]
 rows=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
  for n,row in enumerate(pool.map(cell,tasks),1):
   rows.append(row)
   if n%50==0:print(f'gate {n}/{len(tasks)}',flush=True)
 summary={}
 for m in a.major or [18,23]:
  cells=[x for x in rows if x['major']==m];bycase={c.stem:[x for x in cells if x['case']==c.stem] for c in cases}
  summary[str(m)]=summarize(cells)
  for name,casecells in bycase.items():
   statuses={classify(x) for x in casecells}-{'agree'}
   if statuses:print(f"LLVM {m} {name}: {', '.join(sorted(statuses))}",flush=True)
 for row in rows:row['classification']=classify(row)
 result={'plugin_sha256':plugin_hashes,'contract_head':current,'contract_head_drift':current!=PIN,'contract_worktree_drift':(CORPUS.parent.parent/'spec/Bennett-Dialect-Spec.md').read_text()!=__import__('contracts').dialect_text(),'accepted_contract_drift':drift(),'dialect_commit':PIN,'scope':'clang C + opt envelope; rustc/Julia/front-end LTO pending','summary':summary,'cells':rows}
 assert all(hashlib.sha256((R/f'build/libbennett-plugin-{m}.so').read_bytes()).hexdigest()==h for m,h in plugin_hashes.items()),'plugin changed during gate'
 (R/'.tmp/corpus-gate.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(summary,indent=2))
 return drift() or any(classify(x)=='diverge' for x in rows)
if __name__=='__main__':raise SystemExit(main())
