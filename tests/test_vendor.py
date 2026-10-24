"""scripts/vendor.py writes only checked files, and only inside the vendor folder."""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "vendor", Path(__file__).resolve().parents[1] / "scripts" / "vendor.py"
)
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


def tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
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
