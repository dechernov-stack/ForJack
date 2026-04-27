"""
Ensure src/storytelling_bot package takes priority over root-level shim.
This must run before any test imports.
"""
import sys
from pathlib import Path

_root = str(Path(__file__).parent)
_src = str(Path(__file__).parent / "src")

# Remove '' (CWD) and root dir so the shim file doesn't shadow the package
for _p in ("", _root):
    while _p in sys.path:
        sys.path.remove(_p)

# Insert src/ at front so the real package wins
if _src not in sys.path:
    sys.path.insert(0, _src)
