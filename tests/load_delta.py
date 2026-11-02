#!/usr/bin/env python3
"""PT6 loads update incrementally when an object's slots grow (bp-fj1); the result is the full pass's.

The hidden flag -bennett-analysis-check-delta recomputes every incremental load group in full and
aborts on any difference. This test runs it over every probe and fixture program and over
programs built to grow a loaded object round after round (stores of loaded values, partial
overlaps, strided stores, zero-filled heap images, a written constant image), and requires (a) no difference, (b) the
incremental path was actually taken where the program grows an object, and (c) the analysis
report is identical with and without the check.
"""
import argparse,json,re,subprocess,sys
from contracts import ROOT as R

def select_chain(base,offsets,ty='i8'):
 lines=[];prev=None
 for n,o in enumerate(offsets):
  lines.append(f' %q{n} = getelementptr {ty}, ptr {base}, i64 {o}')
  if prev is None: prev=f'%q{n}'
  else:
   lines.append(f' %r{n} = select i1 %c, ptr {prev}, ptr %q{n}');prev=f'%r{n}'
 return '\n'.join(lines),prev

def grow_global(slots=16):
 """A load of every slot feeds a store into one slot: the loaded set grows one value per round."""
 body,q=select_chain('@g',[8*n for n in range(slots)])
 stores='\n'.join(f' %s{n} = getelementptr i8, ptr @g, i64 {8*n}\n store i64 %a, ptr %s{n}' for n in (3,7,11))
 return f'''@g = internal global [{slots} x i64] zeroinitializer
define i64 @top(i1 %c) {{
{body}
 %v = load i64, ptr {q}
 %w = add i64 %v, 1
 %a = and i64 %w, 31
{stores}
 ret i64 %v
}}''','%v'

def grow_heap():
 """Zero-filled heap image, pointer stores into it, a partial (i32 of i64) load and a strided store."""
 body,q=select_chain('%b',[0,8,16,24,32])
 return f'''declare ptr @calloc(i64, i64)
@k = internal global i64 0
define i64 @top(i1 %c, i64 %i) {{
 %b = call ptr @calloc(i64 8, i64 8)
{body}
 %v = load i64, ptr {q}
 %h = load i32, ptr {q}
 %p = load ptr, ptr {q}
 %w = add i64 %v, 3
 %a = and i64 %w, 63
 %e = getelementptr i8, ptr %b, i64 16
 store i64 %a, ptr %e
 %f = getelementptr i8, ptr %b, i64 32
 store ptr @k, ptr %f
 %x = load i64, ptr %p
 %m = and i64 %i, 3
 %s = getelementptr i64, ptr %b, i64 %m
 store i64 %x, ptr %s
 %t = trunc i64 %a to i32
 %u = getelementptr i8, ptr %b, i64 40
 store i32 %t, ptr %u
 ret i64 %v
}}''','%v'

def grow_constant():
 """Stores reach a constant image through a merged pointer: its exact-byte loads lose and gain
 contributions as the written slots grow (the per-atom path), at byte and multi-byte widths."""
 body,q=select_chain('@s',[0,1,2,4,5])
 return f'''@s = internal constant [8 x i8] c"abcdefgh"
@h = internal global [8 x i8] zeroinitializer
define i32 @top(i1 %c, i1 %d) {{
{body}
 %b = load i8, ptr {q}
 %w = load i32, ptr {q}
 %x = load i16, ptr %q2
 %z = zext i8 %b to i32
 %y = add i32 %z, 1
 %t = trunc i32 %y to i8
 %k = and i8 %t, 7
 %dst = select i1 %d, ptr @h, ptr %q3
 store i8 %k, ptr %dst
 %e = getelementptr i8, ptr %dst, i64 1
 store i8 %b, ptr %e
 %r = add i32 %w, %y
 ret i32 %r
}}''','%w'

def run(m,src,check,tag):
 report=R/f'.tmp/load-delta/{m}/{tag}.json'
 argv=[f'/usr/lib/llvm-{m}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{m}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(src)]
 if check: argv.insert(4,'-bennett-analysis-check-delta')
 report.unlink(missing_ok=True)
 x=subprocess.run(argv,capture_output=True,text=True,timeout=600)
 data=report.read_text() if report.exists() else None
 return x.returncode,x.stderr,data

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--major',type=int,required=True);a=ap.parse_args();m=a.major
 out=R/f'.tmp/load-delta/{m}';out.mkdir(parents=True,exist_ok=True)
 results=[]
 def check(name,ok,detail=''):
  results.append({'case':name,'ok':bool(ok),'detail':detail if not ok else ''})
 programs=[]
 for name,(text,_) in {'grow-global':grow_global(),'grow-heap':grow_heap(),'grow-constant':grow_constant()}.items():
  path=out/f'{name}.ll';path.write_text(text);programs.append((name,path,True))
 for path in sorted((R/'tests/probes').glob('*.ll'))+sorted((R/'tests/fixtures').glob('*.ll')):
  programs.append((path.parent.name+'-'+path.stem,path,False))
 for name,path,grows in programs:
  rc0,err0,data0=run(m,path,False,name+'-plain')
  rc1,err1,data1=run(m,path,True,name+'-checked')
  check(name+'-no-difference','incremental PT6 differs' not in err1,err1[-400:])
  check(name+'-same-exit',rc0==rc1,{'plain':rc0,'checked':rc1,'err':err1[-300:]})
  # Reports name no flag, so a checked run must report exactly what the plain run reports.
  check(name+'-same-report',data0==data1,'reports differ')
  checked=re.search(r'checked (\d+) incremental load groups',err1)
  if grows:
   check(name+'-incremental-taken',rc1==0 and checked and int(checked.group(1))>0,err1[-400:])
 summary={'major':m,'cases':len(results),'passed':sum(r['ok'] for r in results)}
 (out/'result.json').write_text(json.dumps(summary|{'results':results},indent=1))
 print(json.dumps(summary|{'failed':[r for r in results if not r['ok']][:10]}))
 sys.exit(0 if summary['passed']==summary['cases'] else 1)
if __name__=='__main__':main()
