"""
Make the `latency` package importable regardless of the physical directory name.

The repo root IS the `latency` package (has __init__.py + agents/, core/, etc.).
When the directory is named something other than `latency` (e.g. `kinzie`),
Python can't find it by the package name. This conftest creates the mapping.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def _register_latency_package() -> None:
    if "latency" in sys.modules:
        return

    pkg = types.ModuleType("latency")
    pkg.__path__ = [str(_REPO_ROOT)]  # type: ignore[assignment]
    pkg.__file__ = str(_REPO_ROOT / "__init__.py")
    pkg.__package__ = "latency"
    pkg.__spec__ = None  # type: ignore[assignment]

    init = _REPO_ROOT / "__init__.py"
    if init.exists():
        exec(compile(init.read_text(), str(init), "exec"), vars(pkg))

    sys.modules["latency"] = pkg


_register_latency_package()

# Also add repo root for any legacy direct imports (e.g. `import core`)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
