"""Nonsecret Tara runtime fingerprint shared by health checks and deploy gates."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tara_runtime_policy import public_policy, validate_policy


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
PROMPT_VERSION = "tara-prompt-policy-2026-08-04"


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _combined_hash(paths):
    digest = hashlib.sha256()
    for path in sorted(Path(item) for item in paths):
        digest.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _release_sha():
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT}",
                "-C",
                str(REPO_ROOT),
                "rev-parse",
                "HEAD",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def frontend_bundle_hash(frontend_dir=None):
    if not frontend_dir:
        return "not-supplied"
    root = Path(frontend_dir).resolve()
    matches = sorted((root / "static" / "js").glob("main.*.js"))
    if len(matches) != 1:
        raise RuntimeError("expected exactly one compiled main JavaScript bundle")
    return _sha256_file(matches[0])


def runtime_fingerprint(frontend_dir=None):
    """Return only release, source, model-policy, and nonsecret config facts."""

    validate_policy()
    policy = public_policy()
    prompt_hash = _combined_hash(
        [
            APP_DIR / "chatbot.py",
            APP_DIR / "chatbot_knowledge.txt",
            APP_DIR / "tara_prompt_context.py",
        ]
    )
    planner_hash = _sha256_file(APP_DIR / "tara_answer_planner.py")
    policy_hash = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    nonsecret_config = {
        "calendar_day_windows": True,
        "entry_date_is_day_one": True,
        "legacy_canary_supported": False,
        "model_policy_hash": policy_hash,
        "prompt_version": PROMPT_VERSION,
    }
    config_hash = hashlib.sha256(
        json.dumps(nonsecret_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    fields = {
        "release_sha": _release_sha(),
        **policy,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "planner_hash": planner_hash,
        "nonsecret_config_hash": config_hash,
        "frontend_bundle_hash": frontend_bundle_hash(frontend_dir),
    }
    fields["fingerprint"] = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return fields
