from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_deploy_installs_webinar_cron_on_each_web_target():
    deploy = (ROOT / "ops" / "deploy.sh").read_text(encoding="utf-8")
    assert 'bash "$repo/ops/install_webinar_cron.sh"' in deploy


def test_webinar_cron_refreshes_hourly_and_replaces_old_entry():
    installer = (ROOT / "ops" / "install_webinar_cron.sh").read_text(encoding="utf-8")
    assert "ENTRY='0 * * * * " in installer
    assert "grep -Fv \"$MARKER\"" in installer


def test_deploy_verifier_checks_cron_feed_and_conditional_footer():
    verifier = (ROOT / "ops" / "verify_deploy.sh").read_text(encoding="utf-8")
    assert "webinar schedule refresh cron installed" in verifier
    assert "footer-webinars-link" in verifier
    assert "/webinars/webinars.json" in verifier
