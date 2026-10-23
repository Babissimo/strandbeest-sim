"""site/_headers, which Cloudflare applies, sends what scripts/serve.py sends."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("serve", ROOT / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)

ISOLATION = ("Cross-Origin-Opener-Policy", "Cross-Origin-Embedder-Policy")
# Cloudflare sends no Content-Type for extensions missing from its own table.
UNTYPED = (".py", ".whl")


def rules() -> dict[str, dict[str, str]]:
    """site/_headers as {path pattern: {header: value}}."""
    parsed: dict[str, dict[str, str]] = {}
    pattern = ""
    for line in (ROOT / "site" / "_headers").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # As Cloudflare reads it, a line starting with / is a path and the rest are its headers.
        if line.startswith("/"):
            pattern = line
            parsed.setdefault(pattern, {})
        else:
            name, value = line.split(":", 1)
            parsed[pattern][name.strip()] = value.strip()
    return parsed


def test_isolation_headers() -> None:
    every_path = rules()["/*"]
    for name in ISOLATION:
        assert every_path[name] == serve.HEADERS[name], name


def test_types_cloudflare_lacks() -> None:
    parsed = rules()
    for extension in UNTYPED:
        assert parsed.get(f"/*{extension}", {}).get("Content-Type") == serve.TYPES[extension], (
            extension
        )
