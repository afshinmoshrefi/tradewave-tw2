from pathlib import Path
import sys

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_LIB = REPO_ROOT / "site" / "lib"
if str(SITE_LIB) not in sys.path:
    sys.path.insert(0, str(SITE_LIB))

import daily_pick_social_card as card


PICK = {
    "featured_date": "2026-07-23",
    "symbol": "SAPH",
    "date": "2026-07-23",
    "end_date": "2026-08-21",
    "daysOut": 29,
    "direction": "long",
    "avg_profit": 5.8,
    "sharpe_ratio": 1.34,
    "years": "10",
    "win_prob": 0.85,
}


def test_generates_x_large_image_card(tmp_path):
    output = card.generate_daily_pick_card(PICK, tmp_path)

    assert output == tmp_path / "assets/social/daily-pick-2026-07-23-saph.png"
    assert output.stat().st_size < 5 * 1024 * 1024
    with Image.open(output) as image:
        assert image.size == (1200, 630)
        assert image.mode == "RGB"


def test_social_metadata_is_unique_per_pick_date():
    metadata = card.social_metadata(PICK, "https://tradewave.ai/")

    assert metadata["title"] == "TradeWave AI Pick: $SAPH"
    assert metadata["page_url"] == (
        "https://tradewave.ai/scorecard.html?pick=2026-07-23"
    )
    assert metadata["image_url"].endswith(
        "/assets/social/daily-pick-2026-07-23-saph.png"
    )
    assert "85% estimated win probability" in metadata["description"]


def test_refreshes_only_marked_scorecard_metadata(tmp_path):
    scorecard = tmp_path / "scorecard.html"
    scorecard.write_text(
        "<html><head>\n"
        + card.SOCIAL_META_START
        + "\n<meta name=\"twitter:card\" content=\"summary\">\n"
        + card.SOCIAL_META_END
        + "\n</head><body>ledger stays</body></html>",
        encoding="utf-8",
    )

    metadata = card.refresh_scorecard_social_meta(
        PICK, tmp_path, "https://tradewave.ai/"
    )

    refreshed = scorecard.read_text(encoding="utf-8")
    assert '<meta name="twitter:card" content="summary_large_image">' in refreshed
    assert metadata["image_url"] in refreshed
    assert "ledger stays" in refreshed
