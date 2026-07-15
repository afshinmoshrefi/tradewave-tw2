"""Release-VM proof for the immutable API gateway's /home isolation.

This test intentionally uses PID1 to exercise the exact mount-namespace
precedence relied on by the production unit: all of /home/flask is hidden, then
one live, read-only ledger file is bind-mounted into a private runtime path.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import uuid

import pytest


LEDGER = pathlib.Path("/home/flask/site/data/featured_history.json")
SYSTEMD_RUN = pathlib.Path("/usr/bin/systemd-run")
SYSTEM_PYTHON = pathlib.Path("/usr/bin/python3.13")


pytestmark = pytest.mark.skipif(
    sys.platform != "linux"
    or os.geteuid() != 0
    or not SYSTEMD_RUN.exists()
    or not SYSTEM_PYTHON.exists()
    or not LEDGER.is_file(),
    reason="requires the root release VM with systemd and the live featured ledger",
)


def test_gateway_can_read_only_the_explicit_home_flask_ledger() -> None:
    token = str(uuid.uuid4())
    runtime = f"tradewave-gateway-policy-{token}"
    unit = f"{runtime}.service"
    target = f"/run/{runtime}/featured_history.json"
    probe = """
import os

target = os.environ["TW2_FEATURED_HISTORY_FILE"]
with open(target, "rb", buffering=0) as handle:
    if not handle.read(1):
        raise SystemExit("bound ledger is empty or unreadable")
for operation in (
    lambda: os.listdir("/home/flask"),
    lambda: open("/home/flask/config.py", "rb", buffering=0),
):
    try:
        value = operation()
    except (PermissionError, FileNotFoundError):
        continue
    if hasattr(value, "close"):
        value.close()
    raise SystemExit("gateway namespace exposed another /home/flask path")
"""
    command = [
        os.fspath(SYSTEMD_RUN),
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        "--service-type=exec",
        f"--unit={unit}",
        "--property=DynamicUser=yes",
        f"--property=RuntimeDirectory={runtime}",
        "--property=RuntimeDirectoryMode=0700",
        "--property=ProtectSystem=strict",
        "--property=ProtectHome=read-only",
        "--property=InaccessiblePaths=/home/flask",
        f"--property=BindReadOnlyPaths={LEDGER}:{target}",
        "--property=NoNewPrivileges=yes",
        "--property=PrivateDevices=yes",
        "--property=ProtectKernelTunables=yes",
        "--property=ProtectKernelModules=yes",
        "--property=ProtectControlGroups=yes",
        "--property=CapabilityBoundingSet=",
        "--property=AmbientCapabilities=",
        "--setenv=HOME=/nonexistent",
        "--setenv=PATH=/usr/bin:/bin",
        "--setenv=LANG=C.UTF-8",
        "--setenv=LC_ALL=C.UTF-8",
        f"--setenv=TW2_FEATURED_HISTORY_FILE={target}",
        os.fspath(SYSTEM_PYTHON),
        "-I",
        "-B",
        "-S",
        "-c",
        probe,
    ]
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert not pathlib.Path(f"/run/{runtime}").exists()
