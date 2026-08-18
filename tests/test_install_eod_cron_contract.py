from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "ops" / "install_eod_cron.sh"


def test_eod_cron_uses_the_effective_runtime_model_for_each_environment():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "dev)" in source
    assert "RELEASE_ROOT='/home/flask/.tw2-app-current'" in source
    assert "staging|prod)" in source
    assert "RELEASE_ROOT='/home/flask'" in source
    assert "cd $RELEASE_ROOT/data_updater" in source
    assert "TW2_ENV must be dev, staging, or prod" in source
