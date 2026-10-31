#!/usr/bin/env python3
"""An accepted pin can coexist with a later unaccepted worktree draft."""
import tempfile
from pathlib import Path
import contracts as c
assert not c.drift(), 'accepted contract differs from pinned release'
original=c.DIALECT
text=c.dialect_text()
with tempfile.TemporaryDirectory(dir=c.ROOT/'.tmp') as d:
 c.DIALECT=Path(d)
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.10"\nisa="0.8"\n')
 (c.DIALECT/'spec').mkdir()
 (c.DIALECT/'spec/Bennett-Dialect-Spec.md').write_text('# unaccepted draft 0.2.11\n')
 c.dialect_text=lambda:text
 assert not c.drift(), 'unaccepted draft invalidated accepted release'
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.11"\nisa="0.8"\n')
 assert c.drift(), 'new accepted release was hidden'
 (c.DIALECT/'SPEC_VERSIONS.toml').write_text('dialect="0.2.10"\nisa="0.8"\n')
 c.dialect_text=lambda:text+'changed'
 assert c.drift(), 'pinned byte corruption was hidden'
c.DIALECT=original
print('contract policy: 4 assertions passed')
