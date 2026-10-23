"""The arena's physics engine (pymunk, on Pyodide's own cffi), loaded once for every tab.

It loads the first time a tab asks for it, so the page starts without waiting; whoever asks while
it loads waits for that same load, and an ask after a failed load tries again.
"""
from __future__ import annotations

import asyncio

# Where scripts/vendor.py puts pymunk; Pyodide finds cffi beside itself through its lock file.
WHEEL = "./vendor/pyodide/pymunk-7.3.1-cp314-cp314-pyemscripten_2026_0_wasm32.whl"

_loading: asyncio.Future | None = None


async def engine():
    """beest.arena, once pymunk has loaded; raises when it cannot load."""
    global _loading
    if _loading is None:
        _loading = asyncio.ensure_future(_load())
    loading = _loading
    try:
        # Shielded, so a waiter that gives up does not end the load for the others.
        return await asyncio.shield(loading)
    except Exception:
        if _loading is loading:
            _loading = None
        raise


async def _load():
    import pyodide_js
    # A wheel that fails to load is logged, and the import below then fails.
    await pyodide_js.loadPackage(["cffi", WHEEL])
    from beest import arena
    return arena
