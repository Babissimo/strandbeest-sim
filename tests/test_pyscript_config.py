"""site/pyscript.toml loads the vendored runtime and copies in every module the page imports."""

import tomllib
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"
CONFIG = tomllib.loads((SITE / "pyscript.toml").read_text())


def test_runtime_is_vendored() -> None:
    assert CONFIG["interpreter"] == "./vendor/pyodide/pyodide.mjs"


def page_files(folder: str, pattern: str) -> set[str]:
    # Caches and hidden files or folders (.DS_Store, .ipynb_checkpoints) are not the page's.
    found = set()
    for path in (SITE / folder).rglob(pattern):
        parts = path.relative_to(SITE).parts
        if path.is_file() and not any(p == "__pycache__" or p.startswith(".") for p in parts):
            found.add("./" + "/".join(parts))
    return found


def test_files_map_every_module() -> None:
    # Everything in beest/ (data files too) and every .py in app/.
    expected = page_files("beest", "*") | page_files("app", "*.py")
    files = CONFIG["files"]
    assert set(files) == expected
    assert all(source == target for source, target in files.items())
