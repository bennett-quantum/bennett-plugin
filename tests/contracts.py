"""Read only published contract text at the pinned commit, never sibling code."""
import os,subprocess,tomllib,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','BROWSER']:os.environ.pop(key,None)
(ROOT/'.tmp').mkdir(exist_ok=True);os.environ['TMPDIR']=str(ROOT/'.tmp')
SIBLINGS=Path(os.environ.get('BENNETT_SIBLINGS') or ROOT.parent)
DIALECT=SIBLINGS/'bennett-dialect-spec'
PIN='95a4b8d06933018a07fef3516296a25fd582fcde'
def dialect_text():
 return subprocess.check_output(['git','-C',str(DIALECT),'show',PIN+':spec/Bennett-Dialect-Spec.md'],text=True)
def drift():
 # An unaccepted working draft is not a change to the accepted contract.
 registry=tomllib.loads((DIALECT/'SPEC_VERSIONS.toml').read_text())
 pin=tomllib.loads((ROOT/'SPEC_VERSIONS.toml').read_text())
 return (registry['dialect']!='0.2.13' or pin['dialect']!='0.2.13'
         or pin['specs']['bennett-dialect-spec']!='0.2.13'
         or pin['isa']!='0.8' or pin['specs']['bennett-isa-spec']!='0.8'
         or hashlib.sha256(dialect_text().encode()).hexdigest()!='803c2e5589fb26ddba322206a08e8759a38c23bd7eded5c31ed0ad99ba4bda15'
         or pin['commits']['bennett-dialect-spec']!=PIN)

def arith_path(major):
 pin=tomllib.loads((ROOT/'SPEC_VERSIONS.toml').read_text())['arith']
 root=os.environ.get('BENNETT_ARITH_PINNED_ROOT')
 path=Path(root)/f'llvm{major}/bennett-arith.bc' if root else Path(pin[f'llvm{major}_path'])
 assert hashlib.sha256(path.read_bytes()).hexdigest()==pin[f'llvm{major}_sha256'], f'LLVM {major}: arith pin mismatch: {path}'
 return path

def arith_manifest(major):
 # The bitcode digest is checked by arith_path; metadata comes from that same
 # immutable publication, even when only the .bc files have been relocated.
 import json
 arith_path(major)
 pin=tomllib.loads((ROOT/'SPEC_VERSIONS.toml').read_text())['arith']
 return json.loads(subprocess.check_output(['git','-C',str(SIBLINGS/'bennett-arith'),'show',f"{pin['commit']}:dist/llvm{major}/manifest.json"],text=True))
