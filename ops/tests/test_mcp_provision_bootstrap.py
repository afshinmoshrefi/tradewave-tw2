"""Adversarial tests for the isolated root provisioning bootstrap."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import os
import re
import stat
import struct
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_candidate_mcp_provision_bootstrap",
    ROOT / "ops" / "mcp_provision_bootstrap.py",
)
bootstrap = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bootstrap)


def _act_as_current_owner(monkeypatch):
    monkeypatch.setattr(bootstrap, "ROOT_UID", getattr(os, "getuid", lambda: 0)())
    monkeypatch.setattr(bootstrap, "ROOT_GID", getattr(os, "getgid", lambda: 0)())


def _record_digest(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _record_row(path: Path, site_packages: Path) -> tuple[str, str, str]:
    return (
        path.relative_to(site_packages).as_posix(),
        _record_digest(path),
        str(path.stat().st_size),
    )


def _write_distribution(
    site_packages: Path, *, name: str, version: str, import_name: str
) -> None:
    package = site_packages / import_name
    package.mkdir()
    module = package / "__init__.py"
    module.write_text(f"VERSION = {version!r}\n", encoding="utf-8")

    stem = name.replace("-", "_")
    dist_info = site_packages / f"{stem}-{version}.dist-info"
    dist_info.mkdir()
    metadata = dist_info / "METADATA"
    metadata.write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n",
        encoding="utf-8",
    )
    record = dist_info / "RECORD"
    with record.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(_record_row(module, site_packages))
        writer.writerow(_record_row(metadata, site_packages))
        writer.writerow((record.relative_to(site_packages).as_posix(), "", ""))


def _synthetic_provision_venv(tmp_path: Path, monkeypatch):
    _act_as_current_owner(monkeypatch)
    venv = tmp_path / "provision-venv"
    site_packages = venv / "lib" / "python3.13" / "site-packages"
    site_packages.mkdir(parents=True)
    _write_distribution(site_packages, name="pip", version="26.1.2", import_name="pip")
    scripts = site_packages / "bin"
    scripts.mkdir()
    pip_script = scripts / "pip"
    pip_script.write_text("#!/usr/bin/python3.13\n", encoding="utf-8")
    pip_record = site_packages / "pip-26.1.2.dist-info" / "RECORD"
    with pip_record.open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerow(
            ("../../bin/pip", _record_digest(pip_script), str(pip_script.stat().st_size))
        )
    _write_distribution(
        site_packages,
        name="psycopg2-binary",
        version="2.9.12",
        import_name="psycopg2",
    )
    versions, lock_hashes, _raw = bootstrap._parse_lock(
        ROOT / "requirements-mcp-provision.lock"
    )
    return venv, site_packages, versions, lock_hashes


def _validate_fixture(tmp_path: Path, monkeypatch):
    venv, site_packages, versions, lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )
    manifest = bootstrap._validate_site_packages(
        site_packages=site_packages,
        venv=venv,
        versions=versions,
        lock_hashes=lock_hashes,
    )
    assert len(manifest) == 64
    return venv, site_packages, versions, lock_hashes


def test_provision_lock_is_exact_hashed_allowlist():
    versions, hashes, raw = bootstrap._parse_lock(
        ROOT / "requirements-mcp-provision.lock"
    )

    assert versions == {"pip": "26.1.2", "psycopg2-binary": "2.9.12"}
    assert all(hashes.values())
    assert hashlib.sha256(raw).hexdigest() == (
        "6bbea01c38a0c35671ce952983347b0eea625ecc143fa43c74eb9be2241fc48a"
    )


def test_exact_record_inventory_accepts_only_the_two_locked_distributions(
    tmp_path, monkeypatch
):
    _validate_fixture(tmp_path, monkeypatch)


def test_pip_target_console_script_record_maps_only_to_sealed_target_bin(
    tmp_path, monkeypatch
):
    venv, site_packages, _versions, _lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )

    target, relative = bootstrap._record_target(
        "../../bin/pip", site_packages=site_packages, venv=venv
    )

    assert target == (site_packages / "bin" / "pip").resolve(strict=True)
    assert relative == "lib/python3.13/site-packages/bin/pip"


@pytest.mark.parametrize(
    "raw_name",
    (
        "../../../bin/pip",
        "../../bin/../pip",
        "../../bin/.pip",
        "../../bin/pip/extra",
        "pip/../bin/pip",
        "pip//__init__.py",
        ".",
    ),
)
def test_noncanonical_or_broader_record_escape_spellings_fail_closed(
    tmp_path, monkeypatch, raw_name
):
    venv, site_packages, _versions, _lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )

    with pytest.raises(bootstrap.BootstrapError, match="unsafe RECORD path"):
        bootstrap._record_target(raw_name, site_packages=site_packages, venv=venv)


@pytest.mark.parametrize(
    ("relative", "contents", "message"),
    [
        ("unrecorded.py", "VALUE = 1\n", "exact RECORD allowlist"),
        ("poison.pth", "import os\n", "startup customization"),
        ("sitecustomize.py", "VALUE = 1\n", "startup customization"),
        ("usercustomize.py", "VALUE = 1\n", "startup customization"),
    ],
)
def test_site_packages_poison_files_fail_closed(
    tmp_path, monkeypatch, relative, contents, message
):
    venv, site_packages, versions, lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )
    (site_packages / relative).write_text(contents, encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError, match=message):
        bootstrap._validate_site_packages(
            site_packages=site_packages,
            venv=venv,
            versions=versions,
            lock_hashes=lock_hashes,
        )


def test_site_packages_symlink_fails_closed(tmp_path, monkeypatch):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable")
    venv, site_packages, versions, lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )
    try:
        (site_packages / "poison-link").symlink_to(
            site_packages / "pip" / "__init__.py"
        )
    except OSError:
        pytest.skip("test user cannot create symlinks")

    with pytest.raises(bootstrap.BootstrapError, match="contains a symlink"):
        bootstrap._validate_site_packages(
            site_packages=site_packages,
            venv=venv,
            versions=versions,
            lock_hashes=lock_hashes,
        )


def test_recorded_file_byte_tamper_fails_closed(tmp_path, monkeypatch):
    venv, site_packages, versions, lock_hashes = _synthetic_provision_venv(
        tmp_path, monkeypatch
    )
    with (site_packages / "psycopg2" / "__init__.py").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write("# tamper\n")

    with pytest.raises(bootstrap.BootstrapError, match="RECORD hash mismatch"):
        bootstrap._validate_site_packages(
            site_packages=site_packages,
            venv=venv,
            versions=versions,
            lock_hashes=lock_hashes,
        )


def _independent_bundle_digest(bundle: Path) -> str:
    entries: list[tuple[bytes, Path, os.stat_result]] = [(b".", bundle, bundle.lstat())]

    def collect(directory: Path, prefix: bytes) -> None:
        for entry in os.scandir(directory):
            name = os.fsencode(entry.name)
            relative = name if not prefix else prefix + b"/" + name
            if relative == b".sealed":
                continue
            path = directory / entry.name
            metadata = path.lstat()
            entries.append((relative, path, metadata))
            if stat.S_ISDIR(metadata.st_mode):
                collect(path, relative)

    collect(bundle, b"")
    digest = hashlib.sha256(b"TW_MCP_BUNDLE_CONTENT_V1\0")
    for relative, path, metadata in sorted(entries, key=lambda value: value[0]):
        kind = (
            b"D"
            if stat.S_ISDIR(metadata.st_mode)
            else b"F" if stat.S_ISREG(metadata.st_mode) else b"L"
        )
        digest.update(kind)
        digest.update(struct.pack(">I", stat.S_IMODE(metadata.st_mode)))
        digest.update(struct.pack(">Q", len(relative)))
        digest.update(relative)
        if kind == b"F":
            value = path.read_bytes()
            digest.update(struct.pack(">Q", len(value)))
            digest.update(hashlib.sha256(value).digest())
        elif kind == b"L":
            target = os.readlink(os.fsencode(path))
            if not isinstance(target, bytes):
                target = os.fsencode(target)
            digest.update(struct.pack(">Q", len(target)))
            digest.update(target)
    return digest.hexdigest()


def test_bundle_digest_parity_and_root_owned_source_tamper_rejection(
    tmp_path, monkeypatch
):
    _act_as_current_owner(monkeypatch)
    bundle = tmp_path / "bundle"
    source = bundle / "src" / "apiserver"
    artifacts = bundle / "artifacts"
    source.mkdir(parents=True)
    artifacts.mkdir()
    db = source / "db.py"
    db.write_text("VALUE = 1\n", encoding="utf-8")
    (artifacts / "provision.py").write_text("pass\n", encoding="utf-8")
    if hasattr(os, "symlink"):
        try:
            (bundle / "python-link").symlink_to("/usr/bin/python3.13")
        except OSError:
            pass

    content_digest = bootstrap._bundle_content_sha256(bundle)
    assert content_digest == _independent_bundle_digest(bundle)
    inventory = {
        "provision_lock_sha256": "1" * 64,
        "provision_manifest_sha256": "2" * 64,
        "provision_tree_sha256": "3" * 64,
    }
    seal = bundle / ".sealed"
    seal.write_text(
        "\n".join(
            [
                *(f"{key}={value}" for key, value in inventory.items()),
                f"bundle_content_sha256={content_digest}",
                "",
            ]
        ),
        encoding="ascii",
    )
    bootstrap._verify_seal(seal, inventory, bundle=bundle)

    db.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError, match="root import boundary"):
        bootstrap._verify_seal(seal, inventory, bundle=bundle)


def test_run_contract_has_no_candidate_source_root():
    source = (ROOT / "ops" / "mcp_provision_bootstrap.py").read_text(encoding="utf-8")
    run = bootstrap._parser().parse_args(
        [
            "run",
            "--bundle",
            "/release",
            "--lock",
            "/release/artifacts/provision.lock",
            "--provisioner",
            "/release/artifacts/provision-mcp-key.py",
            "--",
            "--check-service",
        ]
    )
    assert not hasattr(run, "source_root")
    assert run.provisioner_arguments == ["--", "--check-service"]
    assert "--source-root" not in source
    assert 'bundle / "src"' not in source


def test_run_exposes_only_verified_site_packages_and_stdlib(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    artifacts = bundle / "artifacts"
    site_packages = bundle / "provision-venv" / "lib" / "python3.13" / "site-packages"
    artifacts.mkdir(parents=True)
    site_packages.mkdir(parents=True)
    provisioner = artifacts / "provision-mcp-key.py"
    provisioner.write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(
        bootstrap,
        "_prepare",
        lambda **_kwargs: (bundle, artifacts / "provision.lock", {}, site_packages),
    )
    monkeypatch.setattr(
        bootstrap, "_canonical_absolute", lambda value, _label: Path(value)
    )
    monkeypatch.setattr(bootstrap, "_assert_exact_path", lambda *_args: None)
    monkeypatch.setattr(
        bootstrap, "_assert_secure_node", lambda *_args, **_kwargs: None
    )
    captured = {}

    def run_path(path, *, run_name):
        captured["path"] = path
        captured["run_name"] = run_name
        captured["argv"] = list(sys.argv)
        captured["sys_path"] = list(sys.path)

    monkeypatch.setattr(bootstrap.runpy, "run_path", run_path)
    monkeypatch.setattr(
        sys, "path", ["candidate-source", *bootstrap.SYSTEM_STDLIB_PATH]
    )
    arguments = bootstrap._parser().parse_args(
        [
            "run",
            "--bundle",
            str(bundle),
            "--lock",
            str(artifacts / "provision.lock"),
            "--provisioner",
            str(provisioner),
            "--",
            "--check-service",
        ]
    )
    bootstrap._command_run(arguments)
    assert captured["argv"] == [str(provisioner), "--check-service"]
    assert captured["sys_path"] == [*bootstrap.SYSTEM_STDLIB_PATH, str(site_packages)]
    assert "candidate-source" not in captured["sys_path"]


def test_run_forwards_abort_unchanged_and_surfaces_success(
    tmp_path, monkeypatch, capsys
):
    bundle = tmp_path / "bundle"
    artifacts = bundle / "artifacts"
    site_packages = bundle / "provision-venv" / "lib" / "python3.13" / "site-packages"
    artifacts.mkdir(parents=True)
    site_packages.mkdir(parents=True)
    provisioner = artifacts / "provision-mcp-key.py"
    provisioner.write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(
        bootstrap,
        "_prepare",
        lambda **_kwargs: (bundle, artifacts / "provision.lock", {}, site_packages),
    )
    monkeypatch.setattr(
        bootstrap, "_canonical_absolute", lambda value, _label: Path(value)
    )
    monkeypatch.setattr(bootstrap, "_assert_exact_path", lambda *_args: None)
    monkeypatch.setattr(
        bootstrap, "_assert_secure_node", lambda *_args, **_kwargs: None
    )

    def run_path(path, *, run_name):
        assert path == str(provisioner)
        assert run_name == "__main__"
        assert sys.argv == [str(provisioner), "--abort"]
        print("PASS: pending MCP service-key rotation reconciled for rollback")

    monkeypatch.setattr(bootstrap.runpy, "run_path", run_path)
    monkeypatch.setattr(sys, "path", [*bootstrap.SYSTEM_STDLIB_PATH])
    monkeypatch.setattr(sys, "argv", ["pytest"])
    arguments = bootstrap._parser().parse_args(
        [
            "run",
            "--bundle",
            str(bundle),
            "--lock",
            str(artifacts / "provision.lock"),
            "--provisioner",
            str(provisioner),
            "--",
            "--abort",
        ]
    )
    assert bootstrap._command_run(arguments) == 0
    assert "reconciled for rollback" in capsys.readouterr().out


def test_active_controller_recovery_restores_then_reconciles_credentials_before_marker():
    deploy = (ROOT / "ops" / "deploy_mcp_release.sh").read_text(encoding="utf-8")
    recovery = deploy[
        deploy.index('  if [ "$mode" = active ] || [ "$mode" = recovering ]; then'):
        deploy.index('  if [ "$mode" = finalizing ]; then')
    ]
    active = recovery[
        recovery.index('    if [ "$mode" = active ]; then'):
        recovery.index(
            '    if [ "$entry_kind" = legacy ] || [ "$gateway_kind" = legacy ]; then'
        )
    ]
    reconcile = '''      if [ "$entry_kind" = sealed ]; then
        check_release_service_key
      else
        abort_mcp_key_rotation "$candidate_bundle"
      fi'''
    assert reconcile in active
    assert active.index("journal_action restore >/dev/null") < active.index(reconcile)
    assert active.index(reconcile) < recovery.index("journal_action mark-recovered")
    assert active.count('abort_mcp_key_rotation "$candidate_bundle"') == 1
    assert deploy.count('abort_mcp_key_rotation "$candidate_bundle"') == 1
    assert 'run_release_provisioner "${1:-$CANDIDATE_BUNDLE}" --abort' in deploy
