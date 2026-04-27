"""
CLI shim — python storytelling_bot.py <args> → package CLI.
Also handles python -m storytelling_bot by fixing sys.path first.
"""
import sys
import importlib
from pathlib import Path

# Ensure the real package (src/) is found before this file
_src = str(Path(__file__).parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# If this module is already cached under the wrong name, remove it
# so that sub-imports like storytelling_bot.schema resolve to the package.
if "storytelling_bot" in sys.modules and not hasattr(sys.modules["storytelling_bot"], "__path__"):
    del sys.modules["storytelling_bot"]

if __name__ == "__main__":
    # Re-import the real package main
    import runpy
    runpy.run_module("storytelling_bot.__main__", run_name="__main__", alter_sys=True)
