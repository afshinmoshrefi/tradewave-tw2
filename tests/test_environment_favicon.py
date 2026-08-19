import hashlib
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "site" / "static"
HELPER = ROOT / "ops" / "lib" / "tradewave_favicon.sh"

EXPECTED = {
    "dev": "favicon-white.png",
    "staging": "favicon-black.png",
    "prod": "favicon-colour.png",
}

APPROVED_BLACK_SHA256 = (
    "3ddd7ff36144ae91b48a2a1250b5cb9558e8dee559054a02a3f496ad8ca01ee8"
)


def _png_size(path: Path) -> Tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def _bash() -> Optional[str]:
    found = shutil.which("bash")
    if found:
        return found
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    return str(git_bash) if git_bash.exists() else None


@pytest.mark.parametrize("environment,filename", EXPECTED.items())
def test_environment_maps_to_square_png(environment: str, filename: str) -> None:
    path = STATIC / filename
    width, height = _png_size(path)
    assert width == height == 250


def test_staging_black_asset_matches_the_approved_artwork() -> None:
    digest = hashlib.sha256((STATIC / EXPECTED["staging"]).read_bytes()).hexdigest()
    assert digest == APPROVED_BLACK_SHA256


@pytest.mark.parametrize("environment,filename", EXPECTED.items())
def test_shell_helper_selects_the_environment_asset(
    environment: str, filename: str
) -> None:
    bash = _bash()
    if bash is None:
        pytest.skip("bash is required to exercise the deployment helper")

    command = (
        f'source "{HELPER.as_posix()}"; '
        f'tw_favicon_source "{environment}" "{STATIC.as_posix()}"'
    )
    completed = subprocess.run(
        [bash, "-lc", command],
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(completed.stdout.strip()).name == filename


def test_shell_helper_publishes_the_staging_asset(tmp_path: Path) -> None:
    bash = _bash()
    if bash is None:
        pytest.skip("bash is required to exercise the deployment helper")

    destination = tmp_path / "favicon.png"
    command = (
        f'source "{HELPER.as_posix()}"; '
        f'tw_publish_environment_favicon "staging" "{STATIC.as_posix()}" '
        f'"{destination.as_posix()}"'
    )
    subprocess.run(
        [bash, "-lc", command],
        check=True,
        capture_output=True,
        text=True,
    )
    assert destination.read_bytes() == (STATIC / EXPECTED["staging"]).read_bytes()


def test_shell_helper_rejects_an_unknown_environment() -> None:
    bash = _bash()
    if bash is None:
        pytest.skip("bash is required to exercise the deployment helper")

    command = (
        f'source "{HELPER.as_posix()}"; '
        f'tw_favicon_source "stage" "{STATIC.as_posix()}"'
    )
    completed = subprocess.run(
        [bash, "-lc", command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "unsupported TW2_ENV" in completed.stderr
