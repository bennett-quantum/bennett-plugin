#!/usr/bin/env python3
"""Scalar publication must obtain every version from the negotiated producer."""

import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ScalarContract(unittest.TestCase):
    def test_versioned_publication_has_no_independent_isa_literal(self):
        source = (ROOT / "src/Scalar.cpp").read_text()
        # The R-only profile currently has no public quantum-reference entry;
        # enforce this boundary invariant before another profile reaches it.
        literals = re.findall(r'isa=0\.[0-9]+|(?:abi|object|launch|sched|cert|coverage|target)(?:=|\\"\s*:\s*\\")0\.[0-9]+', source)
        self.assertEqual(literals, [], "scalar header, signatures and hash envelopes must share producerISA()")


if __name__ == "__main__":
    unittest.main()
