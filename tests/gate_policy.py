#!/usr/bin/env python3
"""An allowlisted unavailable check cannot hide a new property failure."""
from corpus_gate import classify, summarize

def row(name,props,**kw):return dict(case=name,major=18,properties=props,agree=all(v is True for v in props.values()),**kw)
base={'L1':False,'L2':True,'L3':True,'L4':True,'L5':False,'L6':True}
b=row('spec-sem2-adj',base,native_exits={'pre_O0':87,'pre_O3':87,'post_O0':87,'post_O3':87})
assert classify(b)=='blocked-upstream: bp-c2i (upstream b-dialect-spec-566)'
assert classify(row('spec-sem2-compute',dict(base,L3=False),native_exits=b['native_exits']))=='diverge'
assert classify(row('spec-sem2-adj',base,native_exits=dict(b['native_exits'],post_O3=1)))=='diverge'
assert classify(row('fp-rot-fastmath-reassoc',dict(base,L1=True)))=='deferred: M2 (§13 FP materialisation; PLAN M2)'
assert classify(row('fp-rot-fastmath-reassoc',dict(base,L1=True,L4=False)))=='diverge'
assert classify(row('ordinary',{'L5':False}))=='diverge'
s=summarize([b,row('ordinary',{'L1':True})]);assert s['cases_blocked']==1 and s['cases_agree']==1 and s['cases_diverge']==0
print('gate policy: 7 assertions passed')
