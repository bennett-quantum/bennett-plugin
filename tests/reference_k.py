#!/usr/bin/env python3
"""§5.1's K is the only bound of the reference analysis (advisor ruling on b-dialect-spec-5u3).

Offsets are never closed before K offsets of one provenance, and no object collapses for its slot
count, unless the non-reference flag -bennett-analysis-early-chain-close asks for it.
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
def solve(major,name,body,early=False):
 dest=R/f'.tmp/reference-k/{major}/{name}';dest.mkdir(parents=True,exist_ok=True)
 src=dest/'in.ll';src.write_text('target datalayout = "e-p:64:64"\n'+body+'\n');report=dest/'report.json'
 argv=[f'/usr/lib/llvm-{major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(src)]
 if early:argv.insert(4,'-bennett-analysis-early-chain-close')
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
 # Reference: K offsets stay exact; one more takes the orbit. The boundary is §5.1's own.
 body,last=unknown_extent(4096);data,_=solve(m,'unknown-4096',body);v=value(data,last)
 check('unknown-extent-K-exact',not v['top'] and len(v['atoms'])==4096,{'top':v['top'],'atoms':len(v['atoms'])})
 body,last=unknown_extent(4097);data,_=solve(m,'unknown-4097',body);v=value(data,last)
 check('unknown-extent-K+1-closes',v['top'] and len(v['atoms'])<8,{'top':v['top'],'atoms':v['atoms'][:8]})
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
 # The flag is the only way to the earlier closure, and it says so.
 body,last=unknown_extent(40);data,err=solve(m,'early-unknown-40',body,early=True);v=value(data,last)
 check('flag-closes-early',v['top'] and len(v['atoms'])<8,{'top':v['top'],'atoms':v['atoms'][:8]})
 check('flag-labelled','NOT the reference analysis' in err,err[:200])
 data,_=solve(m,'early-slots-80',many_slots(80),early=True);v=value(data,'%v')
 check('flag-collapses',v['top'],v)
 _,err=solve(m,'default-silent',unknown_extent(4)[0]);check('default-unlabelled','NOT the reference analysis' not in err,err[:200])
 result={'major':m,'cases':len(results),'passed':sum(r['ok'] for r in results),'results':results}
 (R/f'.tmp/reference-k-{m}.json').write_text(json.dumps(result,indent=1))
 print(json.dumps({k:result[k] for k in ('major','cases','passed')}|{'failed':[r for r in results if not r['ok']]}))
 sys.exit(0 if result['passed']==result['cases'] else 1)
if __name__=='__main__':main()
