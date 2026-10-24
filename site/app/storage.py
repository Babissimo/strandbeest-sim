"""The browser's storage for this site, which may be blocked or full.

Each viewer's browser keeps its own copy; nothing reaches other viewers.
"""
from __future__ import annotations

from pyscript import window


def recall(key: str) -> str | None:
    """What the browser keeps under `key`; None when it keeps nothing or storage is blocked."""
    try:
        value = window.localStorage.getItem(key)
    except Exception:
        return None
    # A missing key gives JavaScript's null, which is not None.
    return value if isinstance(value, str) else None


def keep(key: str, value: str | None) -> bool:
    """Keeps `value` under `key`, or with None forgets it; False when storage is blocked or
    full. An older value that could not be replaced is forgotten if it can be."""
    try:
        if value is not None:
            window.localStorage.setItem(key, value)
            return True
    except Exception:
        pass
    try:
        window.localStorage.removeItem(key)
    except Exception:
        return False
    return value is None
