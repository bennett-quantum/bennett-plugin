"""Read only published contract text at the pinned commit, never sibling code."""
import os,subprocess,tomllib,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','BROWSER']:os.environ.pop(key,None)
(ROOT/'.tmp').mkdir(exist_ok=True);os.environ['TMPDIR']=str(ROOT/'.tmp')
DIALECT=ROOT.parent/'bennett-dialect-spec'
PIN='023f5a771a814270634db3be9cfde88ded69f975'
def dialect_text():
 return subprocess.check_output(['git','-C',str(DIALECT),'show',PIN+':spec/Bennett-Dialect-Spec.md'],text=True)
def drift():
 # An unaccepted working draft is not a change to the accepted contract.
 registry=tomllib.loads((DIALECT/'SPEC_VERSIONS.toml').read_text())
 pin=tomllib.loads((ROOT/'SPEC_VERSIONS.toml').read_text())
 return (registry['dialect']!='0.2.10' or pin['dialect']!='0.2.10'
         or pin['specs']['bennett-dialect-spec']!='0.2.10'
         or pin['isa']!='0.8' or pin['specs']['bennett-isa-spec']!='0.8'
         or hashlib.sha256(dialect_text().encode()).hexdigest()!='d4f3c1a88391cc147f8c8fa4f80f82852e3ebe6f880610fc16cd5151f33d7206'
         or pin['commits']['bennett-dialect-spec']!=PIN)
