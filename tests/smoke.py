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
