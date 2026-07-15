"""Reproducibility and input-safety checks for the offline wheel inventory."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
_SCRIPT = Path(__file__).resolve().parents[1] / "mcp_offline_wheels.py"
_SPEC = importlib.util.spec_from_file_location("mcp_offline_wheels", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
wheels = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = wheels
_SPEC.loader.exec_module(wheels)


@pytest.fixture(autouse=True)
def _trust_current_test_owner(monkeypatch):
    if os.name != "nt":
        monkeypatch.setattr(wheels, "TRUSTED_WHEELHOUSE_UID", os.geteuid())
        monkeypatch.setattr(wheels, "TRUSTED_WHEELHOUSE_GID", os.getegid())


def _record_hash(value: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b"=")
    return "sha256=" + digest.decode("ascii")


def _wheel_bytes(
    *,
    name: str = "demo-pkg",
    version: str = "1.2.3",
    tag: str = "py3-none-any",
    payload: bytes = b"VALUE = 7\n",
    extra_files: dict[str, bytes] | None = None,
    record_mutator=None,
    duplicate: tuple[str, bytes] | None = None,
) -> bytes:
    escaped_name = name.replace("-", "_")
    dist_info = f"{escaped_name}-{version}.dist-info"
    files = {
        "demo_pkg/__init__.py": payload,
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: unit-test\n"
            "Root-Is-Purelib: true\n"
            f"Tag: {tag}\n\n"
        ).encode(),
    }
    files.update(extra_files or {})
    record_name = f"{dist_info}/RECORD"
    rows = [
        [path, _record_hash(value), str(len(value))] for path, value in files.items()
    ]
    rows.append([record_name, "", ""])
    if record_mutator is not None:
        record_mutator(rows)
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    files[record_name] = output.getvalue().encode()

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        for path, value in files.items():
            info = zipfile.ZipInfo(path, (2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, value)
        if duplicate is not None:
            info = zipfile.ZipInfo(duplicate[0], (2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, duplicate[1])
    return archive_bytes.getvalue()


def _write_lock(
    path: Path, wheel_bytes: bytes, *, name="demo-pkg", version="1.2.3"
) -> None:
    digest = hashlib.sha256(wheel_bytes).hexdigest()
    path.write_text(
        f"{name}=={version} --hash=sha256:{digest}\n",
        encoding="utf-8",
    )


def _stage(
    tmp_path: Path,
    wheel_bytes: bytes,
    *,
    filename="demo_pkg-1.2.3-py3-none-any.whl",
    destination_name="wheelhouse",
):
    source = tmp_path / f"source-{destination_name}"
    source.mkdir()
    (source / filename).write_bytes(wheel_bytes)
    lock = tmp_path / f"{destination_name}.lock"
    _write_lock(lock, wheel_bytes)
    destination_parent = tmp_path / f"owned-{destination_name}"
    destination_parent.mkdir(mode=0o700)
    destination = destination_parent / destination_name
    manifest = wheels.stage_wheels(
        lock=str(lock.resolve()),
        source=str(source.resolve()),
        destination=str(destination.resolve()),
        python_version="3.13",
        architecture="x86_64",
        glibc="2.39",
        expected_owner_uid=getattr(os, "geteuid", lambda: 0)(),
    )
    return manifest, destination, lock, source


def _installed_tree(
    tmp_path: Path,
    *,
    name="demo-pkg",
    version="1.2.3",
    console_scripts: dict[str, str] | None = None,
):
    dist_info_name = f"{name.replace('-', '_')}-{version}.dist-info"
    extra_files = {}
    if console_scripts:
        extra_files["demo_pkg/cli.py"] = b"def main():\n    return 0\n"
        entries = "[console_scripts]\n" + "".join(
            f"{script}={target}\n" for script, target in console_scripts.items()
        )
        extra_files[f"{dist_info_name}/entry_points.txt"] = entries.encode("utf-8")
    wheel_bytes = _wheel_bytes(
        name=name,
        version=version,
        extra_files=extra_files,
    )
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    wheel = wheelhouse / f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    wheel.write_bytes(wheel_bytes)
    if os.name != "nt":
        wheel.chmod(0o444)
        wheelhouse.chmod(0o555)
    lock = tmp_path / "installed.lock"
    _write_lock(lock, wheel_bytes, name=name, version=version)

    root = tmp_path / "site-packages"
    root.mkdir()
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith(".dist-info/RECORD"):
                continue
            destination = root / Path(info.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
    dist_info = root / dist_info_name
    (dist_info / "INSTALLER").write_bytes(b"pip\n")
    (dist_info / "REQUESTED").write_bytes(b"")
    if console_scripts:
        scripts = root / "bin"
        scripts.mkdir()
        for script, target in console_scripts.items():
            module, callable_name = target.split(":", 1)
            (scripts / script).write_bytes(
                wheels._console_script_bytes(module, callable_name)
            )

    record_relative = f"{dist_info.name}/RECORD"
    rows = []
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = path.relative_to(root).as_posix()
        value = path.read_bytes()
        record_path = f"../../{relative}" if relative.startswith("bin/") else relative
        rows.append([record_path, _record_hash(value), str(len(value))])
    rows.append([record_relative, "", ""])
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    (dist_info / "RECORD").write_text(output.getvalue(), encoding="utf-8", newline="")
    return root, lock, dist_info, wheelhouse


def _append_installed_record_row(
    dist_info: Path, record_path: str, payload: bytes
) -> None:
    record = dist_info / "RECORD"
    rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    rows.insert(-1, [record_path, _record_hash(payload), str(len(payload))])
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    record.write_text(output.getvalue(), encoding="utf-8", newline="")


def _rewrite_installed_record_claim(
    dist_info: Path, record_path: str, payload: bytes
) -> None:
    record = dist_info / "RECORD"
    rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    found = False
    for row in rows:
        if row[0] == record_path:
            row[1:] = [_record_hash(payload), str(len(payload))]
            found = True
    assert found
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    record.write_text(output.getvalue(), encoding="utf-8", newline="")


def _replace_locked_wheel(
    wheelhouse: Path,
    lock: Path,
    wheel_bytes: bytes,
    *,
    authorize: bool,
) -> Path:
    wheel = next(wheelhouse.glob("*.whl"))
    if os.name != "nt":
        wheel.chmod(0o644)
    wheel.write_bytes(wheel_bytes)
    if os.name != "nt":
        wheel.chmod(0o444)
    if authorize:
        _write_lock(lock, wheel_bytes)
    return wheel


def test_parse_lock_accepts_pip_tools_continuations(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "# generated by pip-tools\n"
        f"demo-pkg==1.2.3 \\\n    --hash=sha256:{'a' * 64} \\\n    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )

    parsed, digest = wheels.parse_lock(str(lock.resolve()))

    assert set(parsed) == {"demo-pkg"}
    assert parsed["demo-pkg"].version == "1.2.3"
    assert parsed["demo-pkg"].hashes == frozenset({"a" * 64, "b" * 64})
    assert digest == hashlib.sha256(lock.read_bytes()).hexdigest()


def test_validate_lock_cli_emits_minimal_canonical_manifest(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "# generated\n"
        f"demo-pkg==1.2.3 --hash=sha256:{'a' * 64} "
        f"--hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )
    expected = {
        "kind": "dependency-lock",
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "package_count": 1,
        "schema": wheels.SCHEMA_VERSION,
    }

    assert wheels.validate_lock(lock=str(lock.resolve())) == expected
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(_SCRIPT),
            "validate-lock",
            "--lock",
            str(lock.resolve()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == wheels._canonical_json(expected).decode("ascii") + "\n"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"demo-pkg>=1.2.3 --hash=sha256:" + b"a" * 64 + b"\n", "exact pin"),
        (
            b"demo-pkg==1.2.3 --hash=sha256:"
            + b"a" * 64
            + b"\ndemo_pkg==1.2.3 --hash=sha256:"
            + b"b" * 64
            + b"\n",
            "duplicate locked project",
        ),
        (b"demo-pkg==1.2.3 --hash=sha512:" + b"a" * 64 + b"\n", "unsupported"),
        (b"demo-pkg==1.2.3\n", "no hashes"),
        (b"\xff\n", "not UTF-8"),
    ],
)
def test_validate_lock_cli_rejects_unsafe_grammar(tmp_path, raw, message):
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(raw)

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(_SCRIPT),
            "validate-lock",
            "--lock",
            str(lock.resolve()),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert message in completed.stderr
    assert completed.stdout == ""


def test_stage_preserves_exact_wheel_and_emits_deterministic_manifest(tmp_path):
    wheel = _wheel_bytes()
    first, first_destination, _lock, _source = _stage(
        tmp_path, wheel, destination_name="first"
    )
    second, second_destination, _lock2, _source2 = _stage(
        tmp_path, wheel, destination_name="second"
    )

    assert first == second
    assert first["wheel_count"] == 1
    assert first["wheels"][0]["normalized_name"] == "demo-pkg"
    assert first["wheels"][0]["sha256"] == hashlib.sha256(wheel).hexdigest()
    assert (first_destination / "demo_pkg-1.2.3-py3-none-any.whl").read_bytes() == wheel
    assert (
        second_destination / "demo_pkg-1.2.3-py3-none-any.whl"
    ).read_bytes() == wheel
    unsigned = dict(first)
    manifest_hash = unsigned.pop("wheel_manifest_sha256")
    assert manifest_hash == hashlib.sha256(wheels._canonical_json(unsigned)).hexdigest()
    if os.name == "posix":
        assert stat.S_IMODE(first_destination.stat().st_mode) == 0o555
        assert stat.S_IMODE(next(first_destination.iterdir()).stat().st_mode) == 0o444


def test_stage_rejects_preexisting_destination_without_replacing_it(tmp_path):
    wheel = _wheel_bytes()
    source = tmp_path / "source"
    source.mkdir()
    (source / "demo_pkg-1.2.3-py3-none-any.whl").write_bytes(wheel)
    lock = tmp_path / "runtime.lock"
    _write_lock(lock, wheel)
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o700)
    destination = parent / "wheelhouse"
    destination.mkdir()
    before = destination.stat()

    with pytest.raises(wheels.BundleError, match="must not preexist"):
        wheels.stage_wheels(
            lock=str(lock.resolve()),
            source=str(source.resolve()),
            destination=str(destination.resolve()),
            python_version="3.13",
            architecture="x86_64",
            glibc="2.39",
            expected_owner_uid=getattr(os, "geteuid", lambda: 0)(),
        )

    after = destination.stat()
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)


def test_stage_rejects_archive_not_authorized_by_lock(tmp_path):
    good = _wheel_bytes()
    bad = _wheel_bytes(payload=b"VALUE = 8\n")
    source = tmp_path / "source"
    source.mkdir()
    (source / "demo_pkg-1.2.3-py3-none-any.whl").write_bytes(bad)
    lock = tmp_path / "runtime.lock"
    _write_lock(lock, good)
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o700)
    with pytest.raises(wheels.BundleError, match="not authorized"):
        wheels.stage_wheels(
            lock=str(lock.resolve()),
            source=str(source.resolve()),
            destination=str((parent / "wheelhouse").resolve()),
            python_version="3.13",
            architecture="x86_64",
            glibc="2.39",
            expected_owner_uid=getattr(os, "geteuid", lambda: 0)(),
        )
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "wheel, message",
    [
        (
            lambda: _wheel_bytes(extra_files={"../escape.py": b"bad"}),
            "unsafe wheel member path",
        ),
        (
            lambda: _wheel_bytes(duplicate=("DEMO_PKG/__init__.py", b"bad")),
            "duplicate/colliding",
        ),
        (
            lambda: _wheel_bytes(record_mutator=lambda rows: rows.pop(0)),
            "allowlist mismatch",
        ),
        (
            lambda: _wheel_bytes(name="wrong-name"),
            "filename project does not match lock|METADATA identity",
        ),
    ],
)
def test_stage_rejects_malformed_wheel_structures(tmp_path, wheel, message):
    value = wheel()
    with pytest.raises(wheels.BundleError, match=message):
        _stage(tmp_path, value)


def test_stage_rejects_incompatible_wheel_tag(tmp_path):
    wheel = _wheel_bytes(tag="cp312-cp312-win_amd64")
    with pytest.raises(wheels.BundleError, match="incompatible"):
        _stage(
            tmp_path,
            wheel,
            filename="demo_pkg-1.2.3-cp312-cp312-win_amd64.whl",
        )


def test_stage_rejects_unexpected_file_and_symlink(tmp_path):
    wheel = _wheel_bytes()
    source = tmp_path / "source"
    source.mkdir()
    wheel_path = source / "demo_pkg-1.2.3-py3-none-any.whl"
    wheel_path.write_bytes(wheel)
    (source / "download.log").write_text("unexpected", encoding="utf-8")
    lock = tmp_path / "runtime.lock"
    _write_lock(lock, wheel)
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o700)
    with pytest.raises(wheels.BundleError, match="exactly one file"):
        wheels.stage_wheels(
            lock=str(lock.resolve()),
            source=str(source.resolve()),
            destination=str((parent / "wheelhouse").resolve()),
            python_version="3.13",
            architecture="x86_64",
            glibc="2.39",
            expected_owner_uid=getattr(os, "geteuid", lambda: 0)(),
        )

    (source / "download.log").unlink()
    if hasattr(os, "symlink"):
        original = tmp_path / "original.whl"
        original.write_bytes(wheel)
        wheel_path.unlink()
        try:
            wheel_path.symlink_to(original)
        except OSError:
            pytest.skip("symlinks unavailable")
        with pytest.raises(wheels.BundleError, match="safe regular file"):
            wheels.stage_wheels(
                lock=str(lock.resolve()),
                source=str(source.resolve()),
                destination=str((parent / "wheelhouse2").resolve()),
                python_version="3.13",
                architecture="x86_64",
                glibc="2.39",
                expected_owner_uid=getattr(os, "geteuid", lambda: 0)(),
            )


def test_stage_enforces_member_resource_bound(tmp_path, monkeypatch):
    wheel = _wheel_bytes(payload=b"12345")
    monkeypatch.setattr(wheels, "MAX_MEMBER_BYTES", 4)
    with pytest.raises(wheels.BundleError, match="member exceeds"):
        _stage(tmp_path, wheel)


def test_stage_enforces_total_member_resource_bound(tmp_path, monkeypatch):
    wheel = _wheel_bytes()
    monkeypatch.setattr(wheels, "MAX_TOTAL_MEMBERS", 3)
    with pytest.raises(wheels.BundleError, match="wheel-set member-count"):
        _stage(tmp_path, wheel)


def test_verify_install_accepts_exact_record_allowlist_and_is_deterministic(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    first = wheels.verify_install(
        lock=str(lock.resolve()),
        site_packages=str(root.resolve()),
        wheelhouse=str(wheelhouse.resolve()),
    )
    second = wheels.verify_install(
        lock=str(lock.resolve()),
        site_packages=str(root.resolve()),
        wheelhouse=str(wheelhouse.resolve()),
    )
    assert first == second
    assert first["distribution_count"] == 1
    assert first["file_count"] == 6
    assert first["distributions"] == [
        {"name": "demo-pkg", "normalized_name": "demo-pkg", "version": "1.2.3"}
    ]
    unsigned = dict(first)
    inventory_hash = unsigned.pop("inventory_sha256")
    assert (
        inventory_hash == hashlib.sha256(wheels._canonical_json(unsigned)).hexdigest()
    )


def test_verify_install_maps_exact_pip_target_console_script_scheme(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(
        tmp_path,
        console_scripts={"demo-cli": "demo_pkg.cli:main"},
    )

    result = wheels.verify_install(
        lock=str(lock.resolve()),
        site_packages=str(root.resolve()),
        wheelhouse=str(wheelhouse.resolve()),
    )
    assert result["file_count"] == 9


@pytest.mark.parametrize(
    "record_path",
    [
        "../bin/demo-cli",
        "../../../bin/demo-cli",
        "../../sbin/demo-cli",
        "../../bin/subdir/demo-cli",
        "../../bin//demo-cli",
        "../../bin/./demo-cli",
        "../../bin/demo-cli/",
        "../../bin/.hidden",
        "../../bin/demo\\evil",
        "../../bin/e\u0301",
        "../../bin/demo\x00evil",
        "/bin/demo-cli",
        "C:/bin/demo-cli",
    ],
)
def test_verify_install_rejects_non_scheme_traversal_rows(tmp_path, record_path):
    root, lock, dist_info, wheelhouse = _installed_tree(tmp_path)
    _append_installed_record_row(dist_info, record_path, b"declared-only")

    with pytest.raises(wheels.BundleError, match="unsafe installed RECORD path"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_verify_install_rejects_unrecorded_console_script(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    script = root / "bin" / "unexpected"
    script.parent.mkdir()
    script.write_bytes(b"#!/bin/sh\nexit 0\n")

    with pytest.raises(wheels.BundleError, match=r"extra=\['bin/unexpected'\]"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_verify_install_rejects_recorded_console_script_symlink(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable")
    root, lock, _dist_info, wheelhouse = _installed_tree(
        tmp_path,
        console_scripts={"demo-cli": "demo_pkg.cli:main"},
    )
    script = root / "bin" / "demo-cli"
    script.unlink()
    try:
        script.symlink_to(root / "demo_pkg" / "__init__.py")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(wheels.BundleError, match="non-regular"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


@pytest.mark.skipif(
    os.name == "nt", reason="pip console-script scheme is POSIX-specific"
)
def test_real_pip_target_console_script_install_verifies(tmp_path):
    if importlib.util.find_spec("pip") is None:
        pytest.skip("pip is unavailable")
    install_python = Path(wheels.INSTALL_SCRIPT_PYTHON)
    if not install_python.is_file():
        pytest.skip("fixed production Python is unavailable")
    dist_info = "demo_pkg-1.2.3.dist-info"
    wheel_bytes = _wheel_bytes(
        extra_files={
            "demo_pkg/cli.py": b"def main():\n    return 0\n",
            f"{dist_info}/entry_points.txt": (
                b"[console_scripts]\ndemo-cli=demo_pkg.cli:main\n"
            ),
        }
    )
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "demo_pkg-1.2.3-py3-none-any.whl"
    wheel.write_bytes(wheel_bytes)
    wheel.chmod(0o444)
    wheelhouse.chmod(0o555)
    lock = tmp_path / "requirements.lock"
    _write_lock(lock, wheel_bytes)
    target = tmp_path / "target"
    completed = subprocess.run(
        [
            str(install_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-compile",
            "--only-binary=:all:",
            "--target",
            str(target),
            "--find-links",
            str(wheelhouse),
            "-r",
            str(lock),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_CACHE_DIR": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr
    installed_record = target / dist_info / "RECORD"
    assert "../../bin/demo-cli" in installed_record.read_text(encoding="utf-8")
    assert (target / "bin" / "demo-cli").is_file()
    result = wheels.verify_install(
        lock=str(lock.resolve()),
        site_packages=str(target.resolve()),
        wheelhouse=str(wheelhouse.resolve()),
    )
    assert result["distribution_count"] == 1


def test_verify_install_rejects_tamper_and_unrecorded_extra(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    (root / "demo_pkg" / "__init__.py").write_bytes(b"TAMPERED\n")
    with pytest.raises(wheels.BundleError, match="differs from"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )

    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path / "extra")
    (root / "demo_pkg" / "extra.py").write_bytes(b"extra\n")
    with pytest.raises(wheels.BundleError, match="allowlist mismatch"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_rewritten_installed_record_cannot_authorize_tampered_wheel_member(tmp_path):
    root, lock, dist_info, wheelhouse = _installed_tree(tmp_path)
    payload = b"ATTACKER REPLACEMENT\n"
    (root / "demo_pkg" / "__init__.py").write_bytes(payload)
    _rewrite_installed_record_claim(dist_info, "demo_pkg/__init__.py", payload)

    with pytest.raises(wheels.BundleError, match="locked wheelhouse"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


@pytest.mark.parametrize("generated", ["INSTALLER", "REQUESTED"])
def test_rewritten_record_cannot_authorize_generated_metadata_tamper(
    tmp_path, generated
):
    root, lock, dist_info, wheelhouse = _installed_tree(tmp_path)
    payload = b"attacker\n"
    (dist_info / generated).write_bytes(payload)
    _rewrite_installed_record_claim(dist_info, f"{dist_info.name}/{generated}", payload)

    with pytest.raises(wheels.BundleError, match="locked wheelhouse"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_rewritten_record_cannot_authorize_console_script_tamper(tmp_path):
    root, lock, dist_info, wheelhouse = _installed_tree(
        tmp_path,
        console_scripts={"demo-cli": "demo_pkg.cli:main"},
    )
    payload = b"#!/bin/sh\nexec attacker\n"
    (root / "bin" / "demo-cli").write_bytes(payload)
    _rewrite_installed_record_claim(dist_info, "../../bin/demo-cli", payload)

    with pytest.raises(wheels.BundleError, match="locked wheelhouse"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_locked_wheel_rejects_inherited_entry_point_defaults(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    malicious = _wheel_bytes(
        extra_files={
            "demo_pkg-1.2.3.dist-info/entry_points.txt": (
                b"[DEFAULT]\nevil=demo_pkg:main\n[console_scripts]\n"
            )
        }
    )
    _replace_locked_wheel(wheelhouse, lock, malicious, authorize=True)

    with pytest.raises(wheels.BundleError, match="unsupported defaults"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


@pytest.mark.parametrize(
    ("extra_path", "message"),
    [
        ("demo_pkg-1.2.3.data/purelib/evil.py", "unsupported .data"),
        ("demo_pkg-1.2.3.dist-info/INSTALLER", "pip-reserved"),
        ("../escape.py", "unsafe wheel member"),
    ],
)
def test_locked_wheel_rejects_unsupported_or_reserved_members(
    tmp_path, extra_path, message
):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    malicious = _wheel_bytes(extra_files={extra_path: b"malicious\n"})
    _replace_locked_wheel(wheelhouse, lock, malicious, authorize=True)

    with pytest.raises(wheels.BundleError, match=message):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


@pytest.mark.parametrize(
    "stdlib_path",
    [
        "json.py",
        "email/__init__.py",
        "sitecustomize/__init__.py",
        "usercustomize/__init__.py",
    ],
)
def test_locked_wheel_rejects_top_level_stdlib_shadow(tmp_path, stdlib_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    malicious = _wheel_bytes(extra_files={stdlib_path: b"SHADOW = True\n"})
    _replace_locked_wheel(wheelhouse, lock, malicious, authorize=True)

    with pytest.raises(wheels.BundleError, match="stdlib shadow"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_wheelhouse_substitution_or_byte_tamper_is_not_authorized(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    substitution = _wheel_bytes(payload=b"SUBSTITUTED = True\n")
    _replace_locked_wheel(wheelhouse, lock, substitution, authorize=False)

    with pytest.raises(wheels.BundleError, match="SHA-256 is not authorized"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


@pytest.mark.parametrize(
    "relative",
    [
        "bad.pth",
        "sitecustomize.py",
        "usercustomize.py",
        "sitecustomize/__init__.py",
        "usercustomize/__init__.py",
        "pkg/cache.pyc",
    ],
)
def test_verify_install_rejects_startup_and_bytecode_files(tmp_path, relative):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    path = root / Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"bad")
    with pytest.raises(wheels.BundleError, match="forbidden startup/cache"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_verify_install_rejects_hardlinked_file(tmp_path):
    if not hasattr(os, "link"):
        pytest.skip("hard links unavailable")
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    source = root / "demo_pkg" / "__init__.py"
    try:
        os.link(source, tmp_path / "second-link")
    except OSError:
        pytest.skip("hard links unavailable")
    with pytest.raises(wheels.BundleError, match="single-link|multi-link"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_verify_install_rejects_fifo_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs unavailable")
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    fifo = root / "demo_pkg" / "special"
    os.mkfifo(fifo)
    with pytest.raises(wheels.BundleError, match="non-regular"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_verify_install_enforces_installed_node_bound(tmp_path, monkeypatch):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    monkeypatch.setattr(wheels, "MAX_INSTALLED_NODES", 3)
    with pytest.raises(wheels.BundleError, match="node-count"):
        wheels.verify_install(
            lock=str(lock.resolve()),
            site_packages=str(root.resolve()),
            wheelhouse=str(wheelhouse.resolve()),
        )


def test_cli_is_stdlib_only_and_prints_canonical_json_for_verify_install(tmp_path):
    root, lock, _dist_info, wheelhouse = _installed_tree(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(_SCRIPT),
            "verify-install",
            "--lock",
            str(lock.resolve()),
            "--site-packages",
            str(root.resolve()),
            "--wheelhouse",
            str(wheelhouse.resolve()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(completed.stdout)
    assert parsed["kind"] == "installed-tree"
    assert (
        completed.stdout
        == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )


def test_cli_is_stdlib_only_and_prints_canonical_json_for_stage(tmp_path):
    wheel = _wheel_bytes()
    source = tmp_path / "source"
    source.mkdir()
    filename = "demo_pkg-1.2.3-py3-none-any.whl"
    (source / filename).write_bytes(wheel)
    lock = tmp_path / "runtime.lock"
    _write_lock(lock, wheel)
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o700)
    destination = parent / "wheelhouse"

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            str(_SCRIPT),
            "stage",
            "--lock",
            str(lock.resolve()),
            "--source",
            str(source.resolve()),
            "--destination",
            str(destination.resolve()),
            "--python-version",
            "3.13",
            "--architecture",
            "x86_64",
            "--glibc",
            "2.39",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    parsed = json.loads(completed.stdout)
    assert parsed["kind"] == "wheelhouse"
    assert (destination / filename).read_bytes() == wheel
    assert (
        completed.stdout
        == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )
