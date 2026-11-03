#!/usr/bin/env python3
"""An accepted pin can coexist with a later unaccepted worktree draft."""
import tempfile
from pathlib import Path
import contracts as c
from unittest.mock import patch
assert not c.drift(), 'accepted contract differs from pinned release'
original=c.DIALECT
text=c.dialect_text()
with tempfile.TemporaryDirectory(dir=c.ROOT/'.tmp') as d:
 c.DIALECT=Path(d)
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.13"\nisa="0.8"\n')
 (c.DIALECT/'spec').mkdir()
 (c.DIALECT/'spec/Bennett-Dialect-Spec.md').write_text('# unaccepted draft 0.2.14\n')
 c.dialect_text=lambda:text
 assert not c.drift(), 'unaccepted draft invalidated accepted release'
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.14"\nisa="0.8"\n')
 assert c.drift(), 'new accepted release was hidden'
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.13"\nisa="0.8"\n')
 pin=c.tomllib.loads((c.ROOT/'SPEC_VERSIONS.toml').read_text());pin['dialect']='0.2.14'
 with patch.object(c.tomllib,'loads',side_effect=[{'dialect':'0.2.14'},pin]):
  assert c.drift(), 'version-only repin hid stale pinned content'
 c.dialect_text=lambda:text+'changed'
 assert c.drift(), 'pinned byte corruption was hidden'
c.DIALECT=original
print('contract policy: 5 assertions passed')

# Relocated publications must retain the pin, including rejection of corruption.
import os
with tempfile.TemporaryDirectory(dir=c.ROOT/'.tmp') as d:
 with patch.dict(os.environ, {'BENNETT_ARITH_PINNED_ROOT':d}):
  for major in (18,23):
   path=Path(d)/f'llvm{major}/bennett-arith.bc';path.parent.mkdir();path.write_bytes(b'corrupt')
   try:c.arith_path(major)
   except AssertionError:pass
   else:raise AssertionError('relocation bypassed the digest pin')
print('arith relocation: corrupt publications rejected on both majors')

# The default path must enforce the same digest as a relocated publication.
with tempfile.TemporaryDirectory(dir=c.ROOT/'.tmp') as d:
 pins=c.tomllib.loads((c.ROOT/'SPEC_VERSIONS.toml').read_text())
 for major in (18,23):
  path=Path(d)/f'corrupt-{major}.bc';path.write_bytes(b'corrupt')
  pins['arith'][f'llvm{major}_path']=str(path)
 with patch.dict(os.environ, {}, clear=False), patch.object(c.tomllib,'loads',return_value=pins):
  os.environ.pop('BENNETT_ARITH_PINNED_ROOT',None)
  for major in (18,23):
   try:c.arith_path(major)
   except AssertionError:pass
   else:raise AssertionError('default path bypassed the digest pin')
print('arith default paths: corrupt publications rejected on both majors')

# M2 publication: the configured bitcode and immutable manifests retain the pin.
# Honour an explicit relocation throughout; sibling working files can advance
# independently while a gate uses its immutable, digest-checked publication.
for major in (18,23):
 c.arith_path(major)
 manifest=c.arith_manifest(major)
 pins=c.tomllib.loads((c.ROOT/'SPEC_VERSIONS.toml').read_text())['arith']
 assert manifest['bitcode_sha256']==pins[f'llvm{major}_sha256']
 assert len(manifest['exports'])==1134, (major,len(manifest['exports']))
 names={row['name'] for row in manifest['exports']}
 assert {'__bennett_sf_add_ppcf128','__bennett_sf_sin_f128'} <= names
print('arith M2: configured hashes and 1134-export immutable manifests verified on both majors')
