"""Put the repository root on sys.path for the suite.

The tests live in `tests/` (software-development-standards §7.3) while the code they exercise is a set of
single modules at the repository root — `logger`, `review_harness`, `portfolio` and the rest. pytest
prepends the test file's own directory, not the rootdir, so `from logger import logger` worked only while
the suite sat in the root and stopped working the moment it moved.

The alternative is packaging the application so the modules are importable by name, which is a larger
change than enrolling it in CI and is not what this is for.
"""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
