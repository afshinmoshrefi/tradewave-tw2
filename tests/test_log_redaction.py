import gzip
import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "redact_log_credentials.py"
SPEC = importlib.util.spec_from_file_location("redact_log_credentials", SCRIPT)
redactor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redactor
SPEC.loader.exec_module(redactor)


RAW = (
    b'GET /login/api/long-lived-key?token=eyJheader.payload.signature '
    b'api_key=second-secret\n'
)


def test_dry_run_counts_without_modifying_or_printing_values(tmp_path, capsys):
    path = tmp_path / "service.log"
    path.write_bytes(RAW)
    assert redactor.main([str(path)]) == 0
    output = capsys.readouterr().out
    assert "DRY-RUN" in output and "replacements=3" in output
    assert "long-lived-key" not in output
    assert "payload" not in output
    assert path.read_bytes() == RAW


@pytest.mark.parametrize("compressed", [False, True])
def test_apply_is_atomic_and_idempotent_for_plain_and_gzip(tmp_path, compressed):
    path = tmp_path / ("service.log.gz" if compressed else "service.log")
    if compressed:
        with gzip.open(path, "wb") as handle:
            handle.write(RAW)
    else:
        path.write_bytes(RAW)

    assert redactor.main(["--apply", str(path)]) == 0
    data = gzip.open(path, "rb").read() if compressed else path.read_bytes()
    assert data == b"GET /login/api/***?token=*** api_key=***\n"
    assert sum(redactor.process(path, apply=False).values()) == 0


def test_directories_are_refused(tmp_path):
    with pytest.raises(ValueError, match="regular-file"):
        redactor.main([str(tmp_path)])
