#!/usr/bin/env python3
"""Fail the gate if any object in the previous receipt changes or disappears."""
import hashlib,json,runpy
from contracts import ROOT as R
paths=runpy.run_path(str(R/'scripts/record-verification.py'))['object_paths']
baseline=json.loads((R/'docs/verification.json').read_text())['latest_pass']['object_pairs']['rows']
for major in (18,23):
 current=dict(paths(R/'.tmp',major,json.loads((R/f'.tmp/scalars-{major}.json').read_text())))
 for old in baseline:
  assert old['object'] in current, f"LLVM {major}: prior object missing: {old['object']}"
  assert hashlib.sha256(current[old['object']].read_bytes()).hexdigest()==old['sha256'],f"LLVM {major}: prior object changed: {old['object']}"
print(f'prior objects: {len(baseline)} hashes preserved on both majors')
