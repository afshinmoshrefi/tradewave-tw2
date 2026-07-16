"""Deployment ownership contracts for the generated developer portal."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER = ROOT / "ops" / "assemble_developer_portal.sh"


def test_portal_generators_run_as_repo_owner_not_root():
    script = ASSEMBLER.read_text(encoding="utf-8")

    assert "GENERATOR_USER=flask" in script
    assert 'chown -R "$GENERATOR_USER:$GENERATOR_USER" "$path"' in script
    assert "sudo \\" in script
    assert "--preserve-env=" in script
    assert '-u "$GENERATOR_USER" -- "$PY" "$script"' in script
    assert script.index('chown -R "$GENERATOR_USER:$GENERATOR_USER"') < script.index(
        "run_gen api_marketing/generate.py"
    )
