"""Regression checks for the scorecard's MailerLite subscription contract."""

from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "site"
    / "templates"
    / "scorecard.html"
)


def test_scorecard_signup_verifies_mailerlite_response():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "mode: 'no-cors'" not in source
    assert "response.json()" in source
    assert "data.success !== true" in source
    assert "Could not subscribe right now" in source


def test_scorecard_signup_uses_form_managed_group():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "forms/193536028893512718/subscribe" in source
    assert "groups[]" not in source
