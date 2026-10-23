"""Serves site/ on this machine with the headers the page needs.

    uv run scripts/serve.py            # http://127.0.0.1:8000
    uv run scripts/serve.py --port 8080

The two isolation headers make the page cross-origin isolated, so it may use SharedArrayBuffer;
site/_headers sends the same pair when the site is hosted. no-store makes every reload fetch the
current files.
"""

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"
HOST = "127.0.0.1"
PORT = 8000
HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cache-Control": "no-store",
}
# Browsers refuse a module script or streamed WebAssembly served under the wrong type.
TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".zip": "application/zip",
    ".toml": "application/toml",
    ".py": "text/plain; charset=utf-8",
    ".whl": "application/octet-stream",
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
}


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def end_headers(self) -> None:
        for name, value in HEADERS.items():
            self.send_header(name, value)
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--directory", type=Path, default=SITE, help="folder to serve (site/)")
    args = parser.parse_args()
    if args.directory == SITE and not (SITE / "vendor" / "pyodide" / "pyodide.mjs").is_file():
        print("serve.py: site/vendor/ is missing; run `uv run scripts/vendor.py` first", file=sys.stderr)
    server = ThreadingHTTPServer((HOST, args.port), partial(Handler, directory=args.directory))
    print(f"Serving {args.directory} at http://{HOST}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
