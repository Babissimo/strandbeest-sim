"""site/pyscript.toml and the GA worker's site/worker.toml load the vendored runtime and copy in
every module they import."""

import ast
import tomllib
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"
CONFIG = tomllib.loads((SITE / "pyscript.toml").read_text())
WORKER = tomllib.loads((SITE / "worker.toml").read_text())


def test_runtime_is_vendored() -> None:
    assert CONFIG["interpreter"] == "./vendor/pyodide/pyodide.mjs"
    assert WORKER["interpreter"] == CONFIG["interpreter"]


def app_modules_imported(script: Path) -> set[str]:
    """The app/ modules a script imports, directly or through one another, as config keys."""
    found: set[Path] = set()
    waiting = [script]
    while waiting:
        for node in ast.walk(ast.parse(waiting.pop().read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                parts = name.split(".")
                if parts[0] != "app" or len(parts) < 2:
                    continue
                module = SITE / "app" / f"{parts[1]}.py"
                if module.is_file() and module not in found:
                    found.add(module)
                    waiting.append(module)
    return {"./" + path.relative_to(SITE).as_posix() for path in found}


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


def test_worker_maps_what_it_imports() -> None:
    worker = SITE / "app" / "ga_worker.py"
    expected = page_files("beest", "*") | {"./app/__init__.py"} | app_modules_imported(worker)
    assert "./app/job.py" in expected
    files = WORKER["files"]
    assert set(files) == expected
    assert all(source == target for source, target in files.items())


def test_js_modules_map_every_script() -> None:
    # Each .js in app/ loads before the page's Python, named after its file.
    expected = {path: Path(path).stem for path in page_files("app", "*.js")}
    assert "./app/editor.js" in expected
    assert CONFIG["js_modules"]["main"] == expected
    assert "js_modules" not in WORKER
