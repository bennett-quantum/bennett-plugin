"""Read only published contract text at the pinned commit, never sibling code."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','BROWSER']:os.environ.pop(key,None)
(ROOT/'.tmp').mkdir(exist_ok=True);os.environ['TMPDIR']=str(ROOT/'.tmp')
DIALECT=ROOT.parent/'bennett-dialect-spec'
PIN='95c3cd332f5f72c07fd5f2515f328deaa40c08b9'
def dialect_text():
 return subprocess.check_output(['git','-C',str(DIALECT),'show',PIN+':spec/Bennett-Dialect-Spec.md'],text=True)
def drift():
 return (DIALECT/'spec/Bennett-Dialect-Spec.md').read_text()!=dialect_text()
