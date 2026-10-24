"""scripts/serve.py sends the isolation headers and the types the runtime needs."""

from pathlib import Path
from urllib.request import ProxyHandler, build_opener

direct = build_opener(ProxyHandler({}))

TYPES = {
    "core.mjs": "text/javascript",
    "core.js": "text/javascript",
    "pyodide.asm.wasm": "application/wasm",
    "pyscript.toml": "application/toml",
    "main.py": "text/plain",
    "pyodide-lock.json": "application/json",
    "python_stdlib.zip": "application/zip",
    "pymunk.whl": "application/octet-stream",
}


def test_headers(serve_folder, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    with serve_folder(tmp_path) as url, direct.open(url + "/") as response:
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers.get_content_type() == "text/html"


def test_types(serve_folder, tmp_path: Path) -> None:
    for name in TYPES:
        (tmp_path / name).write_bytes(b"")
    with serve_folder(tmp_path) as url:
        for name, expected in TYPES.items():
            with direct.open(f"{url}/{name}") as response:
                assert response.headers.get_content_type() == expected, name
