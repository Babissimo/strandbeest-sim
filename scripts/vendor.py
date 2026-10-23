"""Fetches the pinned PyScript and Pyodide from the npm registry into site/vendor/, and the
arena's wheels beside Pyodide.

Each npm tarball must match the sha512 integrity the registry publishes for it before anything is
written. The arena's pymunk comes from PyPI and must match PyPI's sha256. The npm package leaves
out Pyodide's own wheels, so cffi (which pymunk runs on, with its dependencies) and micropip come
from Pyodide's release tarball on GitHub; each must match the sha256 in pyodide-lock.json and is
saved under the name the lock gives it, which is where Pyodide looks for it. Anything already in
place at its pinned version is left alone, so running this again needs no network.

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
from http.client import HTTPException
from pathlib import Path
from typing import BinaryIO
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

PYMUNK_VERSION = "7.3.1"
PYPI = "https://pypi.org/pypi"
PYPI_FILES = "https://files.pythonhosted.org/"
# pymunk built for Pyodide 314's platform.
PYMUNK_WHEEL = f"pymunk-{PYMUNK_VERSION}-cp314-cp314-pyemscripten_2026_0_wasm32.whl"
# Pyodide's builds of what pymunk runs on, and of micropip, which installs wheels in the page.
PYODIDE_WHEELS = ("cffi", "micropip")
# Every wheel in pyodide-lock.json, 426 MB in all; reading stops once the wanted ones are found.
PYODIDE_RELEASE = (
    f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}/"
    f"pyodide-{PYODIDE_VERSION}.tar.bz2"
)
WHEELS_STAMP = "WHEELS"


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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lock_wheels(lock: dict, names: tuple[str, ...]) -> dict[str, str]:
    """The wheels of these packages in pyodide-lock.json and all they depend on: name to sha256."""
    wheels: dict[str, str] = {}
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        entry = lock["packages"].get(name)
        if entry is None:
            raise VendorError(f"pyodide-lock.json has no package {name!r}")
        file_name = entry["file_name"]
        # The name becomes a path in site/vendor/pyodide/.
        if Path(file_name).name != file_name or not file_name.endswith(".whl"):
            raise VendorError(f"pyodide-lock.json gives {name!r} an odd file name: {file_name!r}")
        wheels[file_name] = entry["sha256"]
        for dependency in entry["depends"]:
            add(dependency)

    for name in names:
        add(name)
    return wheels


def extract_wheels(stream: BinaryIO, wanted: dict[str, str], dest: Path) -> None:
    """Writes the wanted wheels (name to sha256) from a Pyodide release tarball into dest.

    The tarball is read as it arrives and only as far as the last wanted wheel. Nothing is
    written unless every wheel is there and matches.
    """
    found: dict[str, bytes] = {}
    with tarfile.open(fileobj=stream, mode="r|bz2") as tar:
        for member in tar:
            name = member.name.removeprefix("pyodide/")
            if name == member.name or name not in wanted or not member.isfile():
                continue
            with tar.extractfile(member) as source:
                data = source.read()
            if sha256(data) != wanted[name]:
                raise VendorError(f"{name} in Pyodide's release does not match pyodide-lock.json")
            found[name] = data
            if len(found) == len(wanted):
                break
    missing = [name for name in wanted if name not in found]
    if missing:
        raise VendorError(f"Pyodide's release lacks {', '.join(missing)}")
    for name, data in found.items():
        (dest / name).write_bytes(data)


def pypi_file(release: dict, file_name: str) -> tuple[str, str]:
    """The URL and sha256 that PyPI's JSON for a release gives one of its files."""
    for entry in release["urls"]:
        if entry["filename"] == file_name:
            if not entry["url"].startswith(PYPI_FILES):
                raise VendorError(f"{file_name} is not on {PYPI_FILES}: {entry['url']}")
            return entry["url"], entry["digests"]["sha256"]
    raise VendorError(f"PyPI lists no {file_name}")


def vendor_wheels() -> None:
    """Puts pymunk and Pyodide's cffi and micropip in site/vendor/pyodide/ for the arena."""
    folder = VENDOR / "pyodide"
    wanted = lock_wheels(json.loads((folder / "pyodide-lock.json").read_text()), PYODIDE_WHEELS)
    names = [PYMUNK_WHEEL, *wanted]
    label = f"pymunk@{PYMUNK_VERSION} and pyodide@{PYODIDE_VERSION}'s {', '.join(PYODIDE_WHEELS)}"
    stamp = folder / WHEELS_STAMP
    if (
        stamp.is_file()
        and stamp.read_text().strip() == label
        and all((folder / name).is_file() for name in names)
    ):
        print(f"{label} are already in site/vendor/pyodide/")
        return
    url, digest = pypi_file(json.loads(fetch(f"{PYPI}/pymunk/{PYMUNK_VERSION}/json")), PYMUNK_WHEEL)
    pymunk = fetch(url)
    if sha256(pymunk) != digest:
        raise VendorError(f"{PYMUNK_WHEEL} does not match PyPI's sha256")

    # Every wheel is fetched and checked before any goes into the folder.
    staging = VENDOR / ".wheels.partial"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        (staging / PYMUNK_WHEEL).write_bytes(pymunk)
        with urlopen(PYODIDE_RELEASE, timeout=TIMEOUT_S) as response:
            extract_wheels(response, wanted, staging)
        for name in names:
            (staging / name).replace(folder / name)
        for old in folder.glob("*.whl"):
            if old.name not in names:
                old.unlink()
        stamp.write_text(label + "\n")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"{label}: {len(names)} wheels in site/vendor/pyodide/")


def main() -> int:
    try:
        for package in PACKAGES:
            vendor(package)
        vendor_wheels()
    # A download cut short raises HTTPException; a garbled JSON reply, ValueError.
    except (VendorError, OSError, tarfile.TarError, HTTPException, ValueError) as error:
        print(f"vendor.py: {error}", file=sys.stderr)
        return 1
    except KeyError as missing:
        print(f"vendor.py: the metadata lacks {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
