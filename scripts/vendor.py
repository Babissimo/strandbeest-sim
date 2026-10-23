"""Fetches the pinned PyScript and Pyodide from the npm registry into site/vendor/.

Each tarball must match the sha512 integrity the registry publishes for it before anything is
written. A package already in place at its pinned version is left alone, so running this again
needs no network.

    uv run scripts/vendor.py
"""

import base64
import hashlib
import io
import json
import shutil
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

PYSCRIPT_VERSION = "0.7.31"
PYODIDE_VERSION = "314.0.2"
REGISTRY = "https://registry.npmjs.org"
VENDOR = Path(__file__).resolve().parents[1] / "site" / "vendor"
# The runtime files the page loads; Pyodide's other files are for Node or the REPL.
PYODIDE_FILES = (
    "pyodide.mjs",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)
STAMP = "VERSION"
TIMEOUT_S = 120


class VendorError(Exception):
    pass


def pyscript_path(member: str) -> str | None:
    return member.removeprefix("package/dist/") if member.startswith("package/dist/") else None


def pyodide_path(member: str) -> str | None:
    name = member.removeprefix("package/")
    return name if name in PYODIDE_FILES else None


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    folder: str
    # Maps a path in the tarball to its path in the folder, or None to leave it out.
    pick: Callable[[str], str | None]
    required: tuple[str, ...]


PACKAGES = (
    Package("@pyscript/core", PYSCRIPT_VERSION, "pyscript", pyscript_path, ("core.js", "core.css")),
    Package("pyodide", PYODIDE_VERSION, "pyodide", pyodide_path, PYODIDE_FILES),
)


def integrity(data: bytes) -> str:
    """The data's subresource integrity string, as npm writes it."""
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def check_integrity(data: bytes, expected: str) -> None:
    if not expected.startswith("sha512-"):
        raise VendorError(f"expected a sha512 integrity, got {expected!r}")
    if integrity(data) != expected:
        raise VendorError("the tarball does not match the registry's integrity")


def extract(data: bytes, pick: Callable[[str], str | None], dest: Path) -> list[str]:
    """Writes the picked regular files of a .tgz into dest; returns their paths there."""
    root = dest.resolve()
    written = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            name = pick(member.name)
            if name is None or not member.isfile():
                continue
            target = (root / name).resolve()
            if not target.is_relative_to(root) or target == root:
                raise VendorError(f"{member.name} would land outside {dest}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source:
                target.write_bytes(source.read())
            written.append(name)
    return written


def fetch(url: str) -> bytes:
    with urlopen(url, timeout=TIMEOUT_S) as response:
        return response.read()


def in_place(package: Package) -> bool:
    folder = VENDOR / package.folder
    stamp = folder / STAMP
    return (
        stamp.is_file()
        and stamp.read_text().strip() == f"{package.name}@{package.version}"
        and all((folder / name).is_file() for name in package.required)
    )


def vendor(package: Package) -> None:
    label = f"{package.name}@{package.version}"
    if in_place(package):
        print(f"{label} is already in site/vendor/{package.folder}/")
        return
    metadata = json.loads(fetch(f"{REGISTRY}/{quote(package.name, safe='@')}/{package.version}"))
    dist = metadata["dist"]
    if not dist["tarball"].startswith(REGISTRY + "/"):
        raise VendorError(f"{label}: the tarball is not on {REGISTRY}: {dist['tarball']}")
    data = fetch(dist["tarball"])
    check_integrity(data, dist["integrity"])

    # Unpack beside the old copy and swap at the end, so a failure leaves no half-written folder.
    staging = VENDOR / f".{package.folder}.partial"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        written = extract(data, package.pick, staging)
        missing = [name for name in package.required if name not in written]
        if missing:
            raise VendorError(f"{label}: the tarball lacks {', '.join(missing)}")
        (staging / STAMP).write_text(label + "\n")
        folder = VENDOR / package.folder
        shutil.rmtree(folder, ignore_errors=True)
        staging.rename(folder)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"{label}: {len(written)} files ({len(data) / 1e6:.1f} MB packed) in site/vendor/{package.folder}/")


def main() -> int:
    try:
        for package in PACKAGES:
            vendor(package)
    except (VendorError, OSError) as error:
        print(f"vendor.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
