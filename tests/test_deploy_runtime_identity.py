from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deploy_rejects_competing_runtime_and_checks_live_process_cwd():
    source = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")

    assert "systemctl show \"$UNIT\" -p WorkingDirectory --value" in source
    assert "/home/flask/\\.tw2-(app-current|releases)" in source
    assert 'readlink -f "/proc/$pid/cwd"' in source
    assert "assert_live_runtime \"$APP\" tradewave-appserver" in source
    assert "assert_live_runtime \"$WEB\" tradewave-web" in source


def test_deploy_binds_verification_to_source_and_bundle_hashes():
    deploy = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
    verify = (ROOT / "ops" / "verify_deploy.sh").read_text(encoding="utf-8")

    assert 'TW2_EXPECTED_SHA="$EXPECTED_SHA"' in deploy
    assert 'TW2_EXPECTED_BUNDLE_SHA256="$BUNDLE_SHA256"' in deploy
    assert "sudo -u flask git -C /home/flask rev-parse HEAD" in verify
    assert "/home/flask/web-react/build/.tradewave-source-sha" in verify
    assert "sha256sum '$react_js_path'" in verify
    assert "React index references the verified main bundle" in verify
