#!/usr/bin/env python3
"""Validate a TradeWave release manifest without exposing stored evidence values."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - exercised on an unprepared host
    raise SystemExit(
        "ERROR: jsonschema is unavailable; install the committed requirements.txt first"
    ) from exc


PROMOTION_STATUSES = {
    "staging_preflight",
    "staging_deployed",
    "awaiting_prod_approval",
    "prod_preflight",
    "prod_deployed",
}


def composite_release_hash(manifest: dict[str, Any]) -> str:
    """Return the canonical identity hash bound at approval boundaries."""
    artifacts = manifest.get("artifacts") or {}
    frontend = sorted(artifacts.get("frontend") or [], key=lambda item: item["path"])
    payload = {
        "release_sha": (manifest.get("git") or {}).get("release_sha"),
        "backend_fingerprint": artifacts.get("backend_fingerprint"),
        "frontend": frontend,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _state(manifest: dict[str, Any], group: str, name: str) -> str | None:
    return ((manifest.get(group) or {}).get(name) or {}).get("state")


def semantic_errors(manifest: dict[str, Any]) -> list[str]:
    """Check cross-field invariants JSON Schema cannot express."""
    errors: list[str] = []
    git = manifest.get("git") or {}
    artifacts = manifest.get("artifacts") or {}
    approvals = manifest.get("approvals") or {}
    environments = manifest.get("environments") or {}
    release_sha = git.get("release_sha")
    identity_hash = artifacts.get("manifest_sha256")
    status = manifest.get("status")
    target = manifest.get("requested_target")

    if identity_hash and identity_hash != composite_release_hash(manifest):
        errors.append("artifacts.manifest_sha256 does not match canonical release identity")

    for field in ("main_locked_sha",):
        value = git.get(field)
        if value is not None and value != release_sha:
            errors.append(f"git.{field} does not equal git.release_sha")

    if status in PROMOTION_STATUSES or (
        status == "complete" and target in {"staging", "prod"}
    ):
        if release_sha is None:
            errors.append("promotion status requires git.release_sha")
        if git.get("main_locked_sha") != release_sha:
            errors.append("promotion status requires main_locked_sha == release_sha")
        if git.get("remote_main_sha") != release_sha:
            errors.append("promotion status requires remote_main_sha == release_sha")

    for name, approval in approvals.items():
        if approval.get("state") != "approved":
            continue
        if approval.get("release_sha") != release_sha:
            errors.append(f"approvals.{name}.release_sha does not equal git.release_sha")
        if not identity_hash or approval.get("artifact_sha256") != identity_hash:
            errors.append(
                f"approvals.{name}.artifact_sha256 does not equal artifacts.manifest_sha256"
            )

    for name, environment in environments.items():
        value = environment.get("release_sha")
        if value is not None and value != release_sha:
            errors.append(f"environments.{name}.release_sha does not equal git.release_sha")

    for index, artifact in enumerate(artifacts.get("frontend") or []):
        if artifact.get("source_sha") != release_sha:
            errors.append(
                f"artifacts.frontend[{index}].source_sha does not equal git.release_sha"
            )

    if _state(manifest, "approvals", "staging") == "approved":
        if _state(manifest, "approvals", "dev") != "approved":
            errors.append("staging approval requires dev approval")
        if _state(manifest, "environments", "staging") != "verified":
            errors.append("staging approval requires verified staging")

    if _state(manifest, "approvals", "production") == "approved":
        if _state(manifest, "approvals", "staging") != "approved":
            errors.append("production approval requires staging approval")
        if _state(manifest, "approvals", "production_snapshots") != "approved":
            errors.append("production approval requires current production snapshots")

    if status in {"prod_preflight", "prod_deployed"}:
        if _state(manifest, "approvals", "production") != "approved":
            errors.append(f"{status} requires production approval")

    if status == "awaiting_prod_approval":
        if _state(manifest, "environments", "staging") != "verified":
            errors.append("awaiting_prod_approval requires verified staging")

    if status == "complete":
        if target in {"dev", "staging", "prod"}:
            if _state(manifest, "environments", target) != "verified":
                errors.append(f"complete {target} release requires verified {target}")
        if target == "staging" and _state(manifest, "approvals", "dev") != "approved":
            errors.append("complete staging release requires dev approval")
        if target == "prod" and _state(manifest, "approvals", "production") != "approved":
            errors.append("complete production release requires production approval")

    return errors


def validate_manifest(
    manifest: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = []
    for error in sorted(
        validator.iter_errors(manifest),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"schema violation at {path} (rule={error.validator})")
    if not errors:
        errors.extend(semantic_errors(manifest))
    return errors


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("release_manifest.schema.json"),
    )
    args = parser.parse_args(argv)

    try:
        manifest = _load_json(args.manifest)
        schema = _load_json(args.schema)
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        print(f"INVALID release manifest input: {type(exc).__name__}", file=sys.stderr)
        return 2

    errors = validate_manifest(manifest, schema)
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1

    release_id = manifest.get("release_id", "unknown")
    release_sha = (manifest.get("git") or {}).get("release_sha") or "pending"
    print(f"VALID release manifest: {release_id} sha={release_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
