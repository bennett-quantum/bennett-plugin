#!/usr/bin/env python3
"""Accepted contracts and publications are checked against immutable gate pins."""
import os
import tempfile
from pathlib import Path
import contracts as c
from unittest.mock import patch
assert not c.drift(), 'accepted contract differs from pinned release'
text = c.dialect_text()
pins = c.tomllib.loads((c.ROOT / 'SPEC_VERSIONS.toml').read_text())
with tempfile.TemporaryDirectory() as d:
 root = Path(d)
 source = (c.ROOT / 'SPEC_VERSIONS.toml').read_text()
 for old, new in ((pins['dialect'], 'invalid-version'),
                  (pins['dialect_sha256'], '0' * 64),
                  (pins['commits']['bennett-dialect-spec'], '0' * 40)):
  (root / 'SPEC_VERSIONS.toml').write_text(source.replace(old, new))
  with patch.object(c, 'ROOT', root):
   assert c.drift(), f'contract metadata corruption hidden: {old}'
with patch.object(c, 'dialect_text', return_value=text + 'changed'):
 assert c.drift(), 'pinned byte corruption was hidden'
print('contract policy: accepted registry, version, commit and content verified')

# Legacy live/relocation settings cannot redirect arithmetic away from gate.toml.
with tempfile.TemporaryDirectory() as d:
 expected = {major: c.arith_path(major) for major in (18, 23)}
 with patch.dict(os.environ, {'BENNETT_ARITH_PINNED_ROOT': d}):
  for major in (18,23):
   path=Path(d)/f'llvm{major}/bennett-arith.bc';path.parent.mkdir();path.write_bytes(b'corrupt')
   assert c.arith_path(major) == expected[major], 'environment bypassed gate pin'
print('arith paths: legacy environment cannot redirect either major')

# Corruption at the resolved path is still rejected; shared caches stay read-only.
with tempfile.TemporaryDirectory() as d:
 root = Path(d)
 for major in (18,23):
  path=root/f'dist/llvm{major}/bennett-arith.bc';path.parent.mkdir(parents=True);path.write_bytes(b'corrupt')
 with patch.object(c, 'sibling', return_value=root):
  for major in (18,23):
   try:c.arith_path(major)
   except AssertionError:pass
   else:raise AssertionError('corrupt pinned bitcode accepted')
print('arith hashes: corrupt publications rejected on both majors')

# M2 publication: the configured bitcode and immutable manifests retain the pin.
# Sibling working files can advance independently of the pinned publication.
for major in (18,23):
 c.arith_path(major)
 manifest=c.arith_manifest(major)
 pins=c.tomllib.loads((c.ROOT/'SPEC_VERSIONS.toml').read_text())['arith']
 assert manifest['bitcode_sha256']==pins[f'llvm{major}_sha256']
 assert len(manifest['exports'])==1134, (major,len(manifest['exports']))
 names={row['name'] for row in manifest['exports']}
 assert {'__bennett_sf_add_ppcf128','__bennett_sf_sin_f128'} <= names
print('arith M2: configured hashes and 1134-export immutable manifests verified on both majors')
