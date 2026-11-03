#!/usr/bin/env python3
"""§5.1's K bounds INT atoms only (accepted 5u3 interpretation; advisor R16).

Pointer offsets have no cardinality cutoff and objects never collapse for their slot count.
The NON-REFERENCE flag -bennett-analysis-early-chain-close enables experimental widening.
"""
import argparse,json,subprocess,sys
from contracts import ROOT as R
def chain(count,offset):
 """A select chain over `count` GEPs of %b, so that %p<count-1> holds them all."""
 lines=[f' %g0 = getelementptr i8, ptr %b, i64 {offset(0)}']
 prev='%g0'
 for n in range(1,count):
  lines.append(f' %g{n} = getelementptr i8, ptr %b, i64 {offset(n)}')
  lines.append(f' %p{n} = select i1 %c, ptr {prev}, ptr %g{n}')
  prev=f'%p{n}'
 return '\n'.join(lines),prev
def unknown_extent(count):
 body,last=chain(count,lambda n:n*8)
 return f'''declare ptr @malloc(i64)
define ptr @top(i1 %c, i64 %n) {{
 %b = call ptr @malloc(i64 %n)
{body}
 ret ptr {last}
}}''',last
def past_extent(count):
 body,last=chain(count,lambda n:1000+n*8)
 return f'''@g = internal global [2 x i64] zeroinitializer
define ptr @top(i1 %c) {{
 %b = getelementptr i8, ptr @g, i64 0
{body}
 ret ptr {last}
}}''',last
def many_slots(count):
 stores='\n'.join(f' %s{n} = getelementptr i8, ptr %b, i64 {n*8}\n store i64 {n+100}, ptr %s{n}' for n in range(count))
 return f'''declare ptr @malloc(i64)
define i64 @top(i64 %n) {{
 %b = call ptr @malloc(i64 %n)
{stores}
 %v = load i64, ptr %s0
 ret i64 %v
}}'''
def constant_calls(count):
 """Council sol B1: PT9 unions in-bounds constant addresses into one internal parameter."""
 image='\\01'*8192
 calls='\n'.join(f' call i8 @sink(ptr getelementptr inbounds ([8192 x i8], ptr @bytes, i64 0, i64 {n}))' for n in range(count))
 return f'''@bytes = internal constant [8192 x i8] c"{image}"
declare void @__bennett_adj(ptr, ptr, ptr)
define internal i8 @sink(ptr %p) {{
 ; Expose the parameter's exact address set in the instruction-only report.
 %address = getelementptr i8, ptr %p, i64 0
 %v = load i8, ptr %p
 ret i8 %v
}}
define internal void @action(ptr %env) {{
{calls}
 ret void
}}
define void @top() {{
 call void @__bennett_adj(ptr @action, ptr null, ptr null)
 ret void
}}'''
INTEGER_ORBIT='''@g = internal global [8 x i64] zeroinitializer
define internal i64 @cycle() {
entry:
 %base = ptrtoint ptr @g to i64
 br label %loop
loop:
 %n = phi i64 [ %base, %entry ], [ %sum, %loop ]
 %sum = add i64 %n, 8
 br label %loop
}
define i64 @top() {
 %r = call i64 @cycle()
 ret i64 %r
}'''
UNDEFINED_REACH='''declare void @ext(ptr)
@x = internal global ptr null
@y = internal global i64 5
@z = internal global i64 5
define i64 @top() {
 call void @ext(ptr @x)
 store ptr @y, ptr @x
 %reached = load i64, ptr @y
 %apart = load i64, ptr @z
 %sum = add i64 %reached, %apart
 ret i64 %sum
}'''
CALL_CYCLE='''define i32 @walk(i32 %depth) {
entry:
 %again = icmp ne i32 %depth, 0
 br i1 %again, label %deeper, label %leaf
deeper:
 %r = call i32 @walk(i32 0)
 %next = add i32 %r, 1
 br label %leaf
leaf:
 %out = phi i32 [ %next, %deeper ], [ 0, %entry ]
 ret i32 %out
}'''
LANE_ORBIT='''define <2 x i16> @top() {
entry: br label %loop
loop:
 %v = phi <2 x i16> [ <i16 0, i16 16>, %entry ], [ %next, %loop ]
 %next = add <2 x i16> %v, <i16 16, i16 16>
 %c = extractelement <2 x i16> %next, i64 0
 %t = icmp eq i16 %c, 0
 br i1 %t, label %out, label %loop
out:
 ret <2 x i16> %v
}'''
PT5_SETS='''@g = internal global [8 x i64] zeroinitializer
@h = internal global [8 x i64] zeroinitializer
define i64 @top(i1 %c) {
 %p = select i1 %c, ptr @g, ptr @h
 %i = ptrtoint ptr %p to i64
 %n = select i1 %c, i64 8, i64 16
 %d = add i64 %i, %n
 %j = ptrtoint ptr @g to i64
 %diff = sub i64 %i, %j
 %neg = sub i64 100, %j
 %r = add i64 %d, %diff
 %s = add i64 %r, %neg
 ret i64 %s
}'''
def solve(major,name,body,early=False,check_delta=False):
 dest=R/f'.tmp/reference-k/{major}/{name}';dest.mkdir(parents=True,exist_ok=True)
 src=dest/'in.ll';src.write_text('target datalayout = "e-p:64:64"\n'+body+'\n');report=dest/'report.json'
 argv=[f'/usr/lib/llvm-{major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(src)]
 if early:argv.insert(4,'-bennett-analysis-early-chain-close')
 if check_delta:argv.insert(4,'-bennett-analysis-check-delta')
 x=subprocess.run(argv,capture_output=True,text=True,timeout=600)
 if x.returncode:raise AssertionError(f'{name}: {x.stderr[-800:]}')
 return json.loads(report.read_text()),x.stderr
def value(data,name,function='top'):
 found=[v for v in data['values'] if v['function']==function and v['value']==name]
 if len(found)!=1:raise AssertionError(f'{name}: {len(found)} records')
 return found[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();m=a.major;results=[]
 def check(name,ok,detail=''):results.append({'case':name,'ok':bool(ok),'detail':str(detail)[:400]})
 # Reference: 40 offsets of an object of no literal extent are exact, without top.
 body,last=unknown_extent(40);data,_=solve(m,'unknown-40',body);v=value(data,last)
 check('unknown-extent-40-exact',not v['top'] and len(v['atoms'])==40 and all(x.endswith(',0)') for x in v['atoms']),v)
 # K applies only to INT atoms: both finite pointer unions stay exact (bp-ipp).
 body,last=unknown_extent(4096);data,_=solve(m,'unknown-4096',body);v=value(data,last)
 check('unknown-extent-K-exact',not v['top'] and set(v['atoms'])=={f'PTR(%b,{n*8},0)' for n in range(4096)},{'top':v['top'],'atoms':len(v['atoms'])})
 body,last=unknown_extent(4097);data,_=solve(m,'unknown-4097',body);v=value(data,last)
 check('unknown-extent-K+1-exact',not v['top'] and set(v['atoms'])=={f'PTR(%b,{n*8},0)' for n in range(4097)},{'top':v['top'],'atoms':len(v['atoms'])})
 # The in-bounds constant-byte witness must be accepted with INT(1), with no EXT/top
 # residue at either side of 4096. Also exercise the incremental/full PT6 comparison.
 for count in (4096,4097):
  data,_=solve(m,f'constant-calls-{count}',constant_calls(count),check_delta=True)
  v=value(data,'%address','sink')
  check(f'constant-calls-{count}-exact-offsets',not v['top'] and set(v['atoms'])=={f'PTR(@bytes,{n},0)' for n in range(count)},{'top':v['top'],'atoms':len(v['atoms'])})
  v=value(data,'%v','sink')
  check(f'constant-calls-{count}-load-one',not v['top'] and v['atoms']==['INT(1)'],v)
  check(f'constant-calls-{count}-accepted',any(f['name']=='action' and f['tiers']==['CC'] for f in data['functions']) and 'non_reference' not in data,data['functions'])
 # Reference: eight addresses outside the object stay explicit beside PT2's unknown address.
 body,last=past_extent(8);data,_=solve(m,'past-8',body);v=value(data,last)
 explicit=[x for x in v['atoms'] if x.startswith('PTR(@g,') and x.endswith(',0)')]
 check('past-extent-8-exact',len(explicit)==8,v)
 # Reference: 80 written slots of one object do not collapse it; a load reads its own slot.
 data,_=solve(m,'slots-80',many_slots(80));v=value(data,'%v')
 check('slots-80-no-collapse',not v['top'] and 'INT(100)' in v['atoms'] and 'INT(101)' not in v['atoms'],v)
 # An additive cycle of step 8 is exactly the class of its step: PT5 leaves no reason for (X,*).
 data,_=solve(m,'integer-orbit',INTEGER_ORBIT);v=value(data,'%n','cycle')
 check('integer-orbit-residue',v['top'] and 'PTR(@g,0,8)' in v['atoms'] and 'PTR(@g,0,-1)' not in v['atoms'],v)
 # PT12 reaches through memory, also over an edge a later step creates; an unreached object stays exact.
 data,_=solve(m,'pt12-reach',UNDEFINED_REACH)
 check('pt12-reaches-later-edge',value(data,'%reached')['top'] and not value(data,'%apart')['top'] and value(data,'%apart')['atoms']==['INT(5)'],[value(data,'%reached'),value(data,'%apart')])
 # An additive cycle through a call's return is solved directly; a vector lane's orbit within K is whole and exact.
 data,_=solve(m,'call-cycle',CALL_CYCLE);v=value(data,'%r','walk')
 check('call-cycle-top',v['top'] and data['analysis_rounds']<100,{'rounds':data['analysis_rounds'],'v':v})
 data,_=solve(m,'lane-orbit',LANE_ORBIT);v=value(data,'%v','top')
 check('lane-orbit-exact',data['analysis_rounds']<100 and not v['top'],{'rounds':data['analysis_rounds'],'top':v['top']})
 # PT5 on address sets: one displaced image per INT, a conservative one for address minus address and INT minus address.
 data,_=solve(m,'pt5-sets',PT5_SETS)
 v=value(data,'%d');check('pt5-displaced-exact',set(v['atoms'])=={'PTR(@g,8,0)','PTR(@g,16,0)','PTR(@h,8,0)','PTR(@h,16,0)'},v)
 v=value(data,'%diff');check('pt5-address-difference',v['top'] and 'PTR(@g,0,-1)' in v['atoms'] and 'PTR(@h,0,-1)' in v['atoms'],v)
 v=value(data,'%neg');check('pt5-int-minus-address',v['top'] and 'PTR(@g,0,-1)' in v['atoms'],v)
 # The flag is the only way to this NON-REFERENCE widening, and it says so.
 body,last=unknown_extent(40);data,err=solve(m,'early-unknown-40',body,early=True);v=value(data,last)
 check('flag-closes-early',v['top'] and len(v['atoms'])<8,{'top':v['top'],'atoms':v['atoms'][:8]})
 check('flag-labelled','NON-REFERENCE' in err and data.get('non_reference')=='-bennett-analysis-early-chain-close',err[:200])
 data,_=solve(m,'early-slots-80',many_slots(80),early=True);v=value(data,'%v')
 check('flag-collapses',v['top'],v)
 _,err=solve(m,'default-silent',unknown_extent(4)[0]);check('default-unlabelled','NOT the reference analysis' not in err,err[:200])
 result={'major':m,'cases':len(results),'passed':sum(r['ok'] for r in results),'results':results}
 (R/f'.tmp/reference-k-{m}.json').write_text(json.dumps(result,indent=1))
 print(json.dumps({k:result[k] for k in ('major','cases','passed')}|{'failed':[r for r in results if not r['ok']]}))
 sys.exit(0 if result['passed']==result['cases'] else 1)
if __name__=='__main__':main()
