#!/usr/bin/env python3
"""Build/load interface and exact pre-link no-op on both majors."""
import os,subprocess,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','BROWSER']:os.environ.pop(key,None)
os.environ['TMPDIR']=str(R/'.tmp')
for major in [18,23]:
 with tempfile.TemporaryDirectory(dir=R/'.tmp') as tmp:
  src=Path(tmp)/'prelink.ll';src.write_text('define void @__bennett_qfree(ptr %h) { ret void }\n')
  tool=f'/usr/lib/llvm-{major}/bin/opt';plugin=str(R/f'build/libbennett-plugin-{major}.so')
  def run(*args):return subprocess.run([tool,*args],text=True,capture_output=True,check=True).stdout
  before=run('-S',str(src),'-o','-')
  after=run('-load-pass-plugin='+plugin,'-passes=bennett','-bennett-pre-link','-bennett-dialect=wrong','-S',str(src),'-o','-')
  assert before==after,major
  bad=subprocess.run([tool,'-load-pass-plugin='+plugin,'-passes=bennett','-bennett-dialect=0.2.6','-disable-output',str(src)],text=True,capture_output=True)
  assert bad.returncode!=0 and 'BD-E-MARKER-DEFINED' in bad.stderr
  print(f'LLVM {major}: pre-link inert; post-link plugin loaded and diagnosed reserved definition')
  src.write_text('''
@g1 = internal constant i8 1
@g2 = internal constant i8 2
declare void @__bennett_oracle(ptr, ptr, ptr)
define internal i8 @one() { ret i8 5 }
define internal i8 @renamed() { ret i8 5 }
define internal i8 @read1() { %v = load i8, ptr @g1
ret i8 %v }
define internal i8 @read2() { %v = load i8, ptr @g2
ret i8 %v }
define void @top() {
 call void @__bennett_oracle(ptr @one, ptr null, ptr null)
 call void @__bennett_oracle(ptr @renamed, ptr null, ptr null)
 call void @__bennett_oracle(ptr @read1, ptr null, ptr null)
 call void @__bennett_oracle(ptr @read2, ptr null, ptr null)
 ret void
}
''')
  report=Path(tmp)/'keys.json'
  run('-load-pass-plugin='+plugin,'-passes=bennett','-bennett-dialect=0.2.6','-bennett-analysis-only','-bennett-report='+str(report),str(src),'-disable-output')
  import json
  keys=[x['candidates'][0]['key'] for x in json.loads(report.read_text())['regions']]
  assert keys[0]==keys[1], 'source symbol changed region identity'
  assert keys[2]!=keys[3], 'referenced global image missing from region identity'
  print(f'LLVM {major}: content keys ignore function names and retain global images')
  # Every ABI 0.2 prototype is checked through the actual C frontend. Wrappers
  # use parameter names from the published header, not a duplicate signature map.
  import re
  from contracts import DIALECT,PIN,dialect_text
  header=subprocess.check_output(['git','-C',str(DIALECT),'show',PIN+':spec/bennett_markers.h'],text=True)
  hp=Path(tmp)/'markers.h';hp.write_text(header)
  prototypes=header.split('/* BEGIN PROTOTYPES */')[1].split('/* END PROTOTYPES */')[0]
  wrappers=[]
  for result,name,params in re.findall(r'([^;\n]+?)\s+(__bennett_\w+)\(([^)]*)\) BENNETT_NOEXCEPT;',prototypes):
   arguments=[re.search(r'(\w+)$',x.strip())[1] for x in params.split(',')]
   wrappers.append(result+' test'+name+'('+params+') { '+('' if result.strip()=='void' else 'return ')+name+'('+','.join(arguments)+'); }')
  assert len(wrappers)==23
  c=Path(tmp)/'markers.c';c.write_text('#include "markers.h"\n'+'\n'.join(wrappers))
  ir=Path(tmp)/'markers.ll'
  subprocess.run([f'/usr/lib/llvm-{major}/bin/clang','-O0','-emit-llvm','-S',str(c),'-o',str(ir)],check=True)
  run('-load-pass-plugin='+plugin,'-passes=bennett','-bennett-dialect=0.2.6','-bennett-analysis-only','-bennett-closed-unit',str(ir),'-disable-output')
  signatures=re.search(r'```llvm markers-ir\n(.*?)```',dialect_text(),re.S)[1]
  for _,name,params in re.findall(r'declare (\w+) @(__bennett_\w+)\(([^)]*)\)',signatures):
   types=[x.strip().split()[0] for x in params.split(',')]
   actual=[t+' '+('null' if t=='ptr' else '0.0' if t=='double' else '0') for t in types]
   src.write_text('declare i7 @'+name+'('+','.join(types)+')\ndefine void @test() { call i7 @'+name+'('+','.join(actual)+')\nret void }\n')
   bad=subprocess.run([tool,'-load-pass-plugin='+plugin,'-passes=bennett','-bennett-dialect=0.2.6','-disable-output',str(src)],text=True,capture_output=True)
   assert bad.returncode!=0 and 'BD-E-MARKER-SIGNATURE' in bad.stderr,(major,name,bad.stderr)
  print(f'LLVM {major}: all 23 C marker signatures accepted; 23 malformed signatures diagnosed')
