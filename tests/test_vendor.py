"""scripts/vendor.py writes only checked files, and only inside the vendor folder."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "vendor", Path(__file__).resolve().parents[1] / "scripts" / "vendor.py"
)
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


def tarball(files: dict[str, bytes], mode: str = "w:gz") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def test_integrity_matches_npm() -> None:
    # npm's own integrity string for an empty file.
    assert vendor.integrity(b"") == (
        "sha512-z4PhNX7vuL3xVChQ1m2AB9Yg5AULVxXcg/SpIdNs6c5H0NE8XYXysP+DGNKHfuwvY7kxvUdBeoGlODJ6+SfaPg=="
    )


def test_wrong_integrity_is_refused() -> None:
    with pytest.raises(vendor.VendorError):
        vendor.check_integrity(b"tampered", vendor.integrity(b"original"))


def test_extracts_only_picked_files(tmp_path: Path) -> None:
    data = tarball({"package/dist/core.js": b"js", "package/src/core.js": b"src"})
    vendor.extract(data, vendor.pyscript_path, tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")] == ["core.js"]
    assert (tmp_path / "core.js").read_bytes() == b"js"


def test_refuses_paths_outside(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    data = tarball({"package/dist/../escaped.js": b"js"})
    with pytest.raises(vendor.VendorError):
        vendor.extract(data, vendor.pyscript_path, dest)
    assert not (tmp_path / "escaped.js").exists()


LOCK = {
    "packages": {
        "cffi": {"file_name": "cffi-2.0.0-cp314.whl", "sha256": "c" * 64, "depends": ["pycparser"]},
        "pycparser": {"file_name": "pycparser-3.0-py3.whl", "sha256": "p" * 64, "depends": []},
        "micropip": {"file_name": "micropip-0.11.1-py3.whl", "sha256": "m" * 64, "depends": []},
    }
}


def release(files: dict[str, bytes]) -> io.BytesIO:
    """A stand-in for Pyodide's release tarball, read as a stream."""
    return io.BytesIO(tarball({f"pyodide/{name}": data for name, data in files.items()}, "w:bz2"))


def test_lock_wheels_follow_dependencies() -> None:
    assert vendor.lock_wheels(LOCK, ("cffi", "micropip")) == {
        "cffi-2.0.0-cp314.whl": "c" * 64,
        "pycparser-3.0-py3.whl": "p" * 64,
        "micropip-0.11.1-py3.whl": "m" * 64,
    }


def test_lock_wheels_refuse_unknown_or_odd_names() -> None:
    with pytest.raises(vendor.VendorError):
        vendor.lock_wheels(LOCK, ("pymunk",))
    odd = {"packages": {"x": {"file_name": "../x.whl", "sha256": "0" * 64, "depends": []}}}
    with pytest.raises(vendor.VendorError):
        vendor.lock_wheels(odd, ("x",))


def test_extracts_wanted_wheels_only(tmp_path: Path) -> None:
    files = {"pyodide/a.whl": b"a", "pyodide/b.whl": b"b", "pyodide/pyodide.asm.wasm": b"w"}
    # Only files in the release's pyodide/ folder count.
    stream = io.BytesIO(tarball({"a.whl": b"x", **files}, "w:bz2"))
    vendor.extract_wheels(stream, {"a.whl": vendor.sha256(b"a")}, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["a.whl"]
    assert (tmp_path / "a.whl").read_bytes() == b"a"


def test_wheel_with_wrong_hash_is_refused(tmp_path: Path) -> None:
    wanted = {"a.whl": vendor.sha256(b"a")}
    with pytest.raises(vendor.VendorError):
        vendor.extract_wheels(release({"a.whl": b"tampered"}), wanted, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_missing_wheel_is_reported(tmp_path: Path) -> None:
    wanted = {"a.whl": vendor.sha256(b"a"), "b.whl": vendor.sha256(b"b")}
    with pytest.raises(vendor.VendorError, match="b.whl"):
        vendor.extract_wheels(release({"a.whl": b"a"}), wanted, tmp_path)


def test_pypi_file_must_be_on_pypi() -> None:
    files = {
        "urls": [
            {
                "filename": "w.whl",
                "url": "https://files.pythonhosted.org/packages/w.whl",
                "digests": {"sha256": "0" * 64},
            },
            {
                "filename": "x.whl",
                "url": "https://elsewhere.example/x.whl",
                "digests": {"sha256": "0" * 64},
            },
        ]
    }
    assert vendor.pypi_file(files, "w.whl") == (
        "https://files.pythonhosted.org/packages/w.whl",
        "0" * 64,
    )
    for name in ("x.whl", "y.whl"):
        with pytest.raises(vendor.VendorError):
            vendor.pypi_file(files, name)


# The stand-in release: each package, its wheel, the wheel's contents and what it depends on.
RELEASE = [
    ("cffi", "cffi-2.0.0.whl", b"cffi", ["pycparser"]),
    ("pycparser", "pycparser-3.0.whl", b"pycparser", []),
    ("micropip", "micropip-0.11.1.whl", b"micropip", []),
]


@pytest.fixture
def sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """A vendor folder holding Pyodide, with PyPI and Pyodide's release played by stand-ins.

    Returns the release's wheels, for a test to tamper with.
    """
    monkeypatch.setattr(vendor, "VENDOR", tmp_path)
    (tmp_path / "pyodide").mkdir()
    lock = {
        name: {"file_name": file_name, "sha256": vendor.sha256(data), "depends": depends}
        for name, file_name, data, depends in RELEASE
    }
    (tmp_path / "pyodide" / "pyodide-lock.json").write_text(json.dumps({"packages": lock}))
    wheel_url = f"{vendor.PYPI_FILES}packages/{vendor.PYMUNK_WHEEL}"
    listing = {
        "filename": vendor.PYMUNK_WHEEL,
        "url": wheel_url,
        "digests": {"sha256": vendor.sha256(b"pymunk")},
    }
    pypi_json = f"{vendor.PYPI}/pymunk/{vendor.PYMUNK_VERSION}/json"
    replies = {pypi_json: json.dumps({"urls": [listing]}).encode(), wheel_url: b"pymunk"}
    files = {file_name: data for _, file_name, data, _ in RELEASE}
    monkeypatch.setattr(vendor, "fetch", lambda url: replies[url])
    monkeypatch.setattr(
        vendor, "urlopen", lambda url, timeout: {vendor.PYODIDE_RELEASE: release(files)}[url]
    )
    return files


def offline(*args: object, **kwargs: object) -> None:
    raise AssertionError("tried to download")


def test_wheels_land_beside_pyodide(
    sources: dict[str, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Left by an earlier version: every wheel replaced, the one no longer wanted gone.
    folder = tmp_path / "pyodide"
    for name in [vendor.PYMUNK_WHEEL, *sources, "pymunk-7.0.0-old.whl"]:
        (folder / name).write_bytes(b"old")
    (folder / vendor.WHEELS_STAMP).write_text("pymunk@7.0.0\n")
    vendor.vendor_wheels()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pyodide"]
    wheels = {p.name: p.read_bytes() for p in folder.glob("*.whl")}
    assert wheels == {vendor.PYMUNK_WHEEL: b"pymunk", **sources}
    # Once in place, they need no network.
    monkeypatch.setattr(vendor, "fetch", offline)
    monkeypatch.setattr(vendor, "urlopen", offline)
    vendor.vendor_wheels()


def contents(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def test_failure_leaves_the_folder_as_it_was(sources: dict[str, bytes], tmp_path: Path) -> None:
    sources["pycparser-3.0.whl"] = b"tampered"
    with pytest.raises(vendor.VendorError):
        vendor.vendor_wheels()
    assert contents(tmp_path) == ["pyodide", "pyodide/pyodide-lock.json"]


def test_pymunk_must_match_pypi(
    sources: dict[str, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = vendor.fetch
    monkeypatch.setattr(
        vendor, "fetch", lambda url: b"tampered" if url.endswith(".whl") else fetch(url)
    )
    with pytest.raises(vendor.VendorError, match="PyPI"):
        vendor.vendor_wheels()
    assert contents(tmp_path) == ["pyodide", "pyodide/pyodide-lock.json"]


def test_the_arena_loads_the_vendored_wheel() -> None:
    arena_mode = Path(__file__).resolve().parents[1] / "site" / "app" / "arena_mode.py"
    assert f'"./vendor/pyodide/{vendor.PYMUNK_WHEEL}"' in arena_mode.read_text()
