#!/usr/bin/env python3
"""Render the 12 paid-nurture text sources into MailerLite-ready HTML.

The text files remain the copy source of truth. Run this script after editing any
Navigator, Analyst, or Strategist nurture email:

    python ops/render_paid_nurture_emails.py
    python ops/render_paid_nurture_emails.py --check

Only Python's standard library is used so the renderer is safe to run in local,
CI, and deployment environments without installing another package.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EMAIL_ROOT = REPO_ROOT / "docs" / "marketing" / "emails"
TIERS = ("navigator", "analyst", "strategist")
EMAIL_NUMBERS = range(1, 5)
UNSUBSCRIBE_TOKEN = "{$unsubscribe}"

TIER_COLORS = {
    "navigator": "#0f766e",
    "analyst": "#6d28d9",
    "strategist": "#b45309",
}

LINK_RE = re.compile(
    r"mailto:[^\s<>]+|https?://[^\s<>]+|"
    r"(?<![\w@])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")

# Paid onboarding should teach customers to use what they selected. Trial,
# checkout, price-comparison, and downsell language belongs in other journeys.
BANNED_COPY = {
    "trial language": re.compile(r"\btrial\b", re.IGNORECASE),
    "checkout language": re.compile(r"\bcheckout\b", re.IGNORECASE),
    "charge language": re.compile(
        r"\b(?:charged?|billing|renewal|no charge)\b", re.IGNORECASE
    ),
    "pricing language": re.compile(
        r"\$\s*\d|\bper month\b|\bbilled yearly\b|\bmonthly price\b|"
        r"\b(?:lower[- ]priced|price comparison)\b",
        re.IGNORECASE,
    ),
    "downsell language": re.compile(
        r"\b(?:downgrad(?:e|ed|ing)|smaller plan|free explorer|plan check|"
        r"whether you need|pay less|pay more|pay extra|change plans|"
        r"navigator may be enough|explorer may be enough)\b",
        re.IGNORECASE,
    ),
    "unsupported reminder-state language": re.compile(
        r"\b(?:main portfolio|checked box|checked state|checkbox)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class EmailSource:
    path: Path
    tier: str
    subject: str
    preview: str
    send_day: int
    brand: str
    title: str
    groups: tuple[tuple[str, ...], ...]
    source_text: str


def _group_nonblank_lines(lines: list[str]) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    current: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if line:
            current.append(line)
        elif current:
            groups.append(tuple(current))
            current = []
    if current:
        groups.append(tuple(current))
    return groups


def parse_source(path: Path, tier: str) -> EmailSource:
    source_text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = source_text.splitlines()
    if len(lines) < 7:
        raise ValueError(f"{path}: source is too short")

    metadata: dict[str, str] = {}
    for expected, line in zip(("Subject", "Preview", "Send day"), lines[:3]):
        prefix = f"{expected}:"
        if not line.startswith(prefix):
            raise ValueError(f"{path}: expected {prefix!r} on metadata line")
        metadata[expected] = line[len(prefix) :].strip()

    if source_text.count(UNSUBSCRIBE_TOKEN) != 1:
        raise ValueError(
            f"{path}: source must contain exactly one {UNSUBSCRIBE_TOKEN}"
        )

    groups = _group_nonblank_lines(lines[3:])
    if len(groups) < 3 or len(groups[0]) != 1 or len(groups[1]) != 1:
        raise ValueError(f"{path}: expected brand, title, and body blocks")

    brand = groups[0][0]
    title = groups[1][0]
    if brand != f"TRADEWAVE {tier.upper()}":
        raise ValueError(f"{path}: unexpected brand line {brand!r}")

    try:
        send_day = int(metadata["Send day"])
    except ValueError as exc:
        raise ValueError(f"{path}: Send day must be an integer") from exc

    return EmailSource(
        path=path,
        tier=tier,
        subject=metadata["Subject"],
        preview=metadata["Preview"],
        send_day=send_day,
        brand=brand,
        title=title,
        groups=tuple(groups[2:]),
        source_text=source_text,
    )


def _trim_link_punctuation(value: str) -> tuple[str, str]:
    trailing = ""
    while value and value[-1] in ".,;":
        trailing = value[-1] + trailing
        value = value[:-1]
    return value, trailing


def format_inline(text: str, accent: str) -> str:
    """Escape text and linkify URLs/email addresses without changing targets."""

    parts: list[str] = []
    cursor = 0
    for match in LINK_RE.finditer(text):
        parts.append(html.escape(text[cursor : match.start()]))
        raw_value, trailing = _trim_link_punctuation(match.group(0))
        if raw_value.lower().startswith("mailto:"):
            href = raw_value
            display = raw_value[7:].split("?", 1)[0]
        elif "@" in raw_value and not raw_value.lower().startswith(("http://", "https://")):
            href = f"mailto:{raw_value}"
            display = raw_value
        else:
            href = raw_value
            display = raw_value
        parts.append(
            '<a href="{}" style="color:{};font-weight:700;text-decoration:underline;">{}</a>'.format(
                html.escape(href, quote=True),
                accent,
                html.escape(display),
            )
        )
        parts.append(html.escape(trailing))
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    rendered = "".join(parts)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)


def _standalone_link(text: str) -> str | None:
    match = LINK_RE.fullmatch(text.strip())
    return match.group(0) if match else None


def _looks_like_heading(text: str) -> bool:
    if LINK_RE.search(text) or text.endswith((".", "?", "!", ",", ";")):
        return False
    if text.lower().endswith("team") or text.startswith("TradeWave —"):
        return False
    letters = "".join(character for character in text if character.isalpha())
    if letters and letters.upper() == letters:
        return True
    return len(text.split()) <= 8 and bool(text) and text[0].isupper()


def _render_button(label: str, url: str, accent: str) -> str:
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:26px 0 30px 0;">
  <tr>
    <td bgcolor="{accent}" style="border-radius:8px;text-align:center;">
      <a href="{html.escape(url, quote=True)}" style="display:inline-block;padding:14px 22px;color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:700;line-height:20px;text-decoration:none;border-radius:8px;">{html.escape(label)}</a>
    </td>
  </tr>
</table>""".strip()


def _render_group(group: tuple[str, ...], accent: str) -> str:
    # Some sources keep account/help lines directly above the unsubscribe line
    # without blank separators. Remove only the unsubscribe line so those links
    # remain in the rendered message.
    group = tuple(line for line in group if UNSUBSCRIBE_TOKEN not in line)
    if not group:
        return ""

    if len(group) == 2:
        destination = _standalone_link(group[1])
        if destination:
            label = group[0].rstrip(":").strip()
            is_bare_email = "@" in destination and not destination.lower().startswith(
                ("http://", "https://", "mailto:")
            )
            if (
                "/account" in destination
                or is_bare_email
                or destination.lower().startswith("mailto:")
                and label.lower() == "email"
            ):
                return (
                    '<p style="margin:20px 0;color:#475569;font-family:Arial,Helvetica,sans-serif;'
                    'font-size:15px;line-height:24px;">'
                    f"{format_inline(group[0], accent)} "
                    f"{format_inline(group[1], accent)}</p>"
                )
            return _render_button(label, destination, accent)

    if all(line.startswith("- ") for line in group):
        rows = []
        for line in group:
            rows.append(
                "<tr>"
                f'<td valign="top" style="width:18px;padding:4px 0;color:{accent};font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:24px;">&#8226;</td>'
                '<td valign="top" style="padding:4px 0;color:#334155;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:25px;">'
                f"{format_inline(line[2:].strip(), accent)}</td>"
                "</tr>"
            )
        return (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="margin:8px 0 22px 0;">'
            + "".join(rows)
            + "</table>"
        )

    if len(group) == 1:
        text = group[0]
        if text == "---":
            return (
                '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
                'style="margin:28px 0;"><tr><td style="height:1px;background:#e2e8f0;line-height:1px;font-size:1px;">&nbsp;</td></tr></table>'
            )
        numbered = NUMBERED_RE.match(text)
        if numbered:
            number, remainder = numbered.groups()
            letters = "".join(character for character in remainder if character.isalpha())
            if letters and letters.upper() == letters:
                return (
                    f'<h2 style="margin:28px 0 10px 0;color:#0f172a;font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:26px;">'
                    f'<span style="color:{accent};">{number}.</span> {html.escape(remainder.title())}</h2>'
                )
            return (
                '<p style="margin:12px 0;color:#334155;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:26px;">'
                f'<strong style="color:{accent};">{number}.</strong> {format_inline(remainder, accent)}</p>'
            )

        destination = _standalone_link(text)
        if destination:
            return (
                '<p style="margin:18px 0;color:#475569;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:24px;">'
                f"{format_inline(text, accent)}</p>"
            )

        if _looks_like_heading(text):
            return (
                f'<h2 style="margin:30px 0 10px 0;color:{accent};font-family:Arial,Helvetica,sans-serif;font-size:17px;line-height:24px;letter-spacing:0.03em;">'
                f"{html.escape(text)}</h2>"
            )

    rendered_lines = "<br>".join(format_inline(line, accent) for line in group)
    return (
        '<p style="margin:0 0 18px 0;color:#334155;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:26px;">'
        f"{rendered_lines}</p>"
    )


def render_email(source: EmailSource) -> str:
    accent = TIER_COLORS[source.tier]
    blocks = "\n".join(
        block for group in source.groups if (block := _render_group(group, accent))
    )
    preview = html.escape(source.preview)
    subject = html.escape(source.subject)
    title = html.escape(source.title)
    tier_label = html.escape(source.tier.upper())

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{subject}</title>
  <style>
    html, body {{ margin:0 !important; padding:0 !important; width:100% !important; }}
    table {{ border-collapse:collapse !important; }}
    img {{ border:0; height:auto; line-height:100%; outline:none; text-decoration:none; }}
    @media only screen and (max-width:680px) {{
      .email-shell {{ width:100% !important; }}
      .email-pad {{ padding:28px 22px !important; }}
      .email-header {{ padding:20px 22px !important; }}
      .email-title {{ font-size:28px !important; line-height:35px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#eef2f7;word-spacing:normal;">
  <div style="display:none;font-size:1px;color:#eef2f7;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{preview}&#8204;&#8203;&#847;&nbsp;&#847;&nbsp;&#847;&nbsp;</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#eef2f7">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" class="email-shell" style="width:640px;max-width:640px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
          <tr>
            <td class="email-header" bgcolor="#0f172a" style="padding:22px 40px;border-top:5px solid {accent};">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:18px;font-weight:800;letter-spacing:0.08em;">TRADEWAVE</td>
                  <td align="right"><span style="display:inline-block;padding:6px 10px;border:1px solid {accent};border-radius:999px;color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:700;letter-spacing:0.08em;">{tier_label}</span></td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td class="email-pad" style="padding:40px 46px 34px 46px;">
              <h1 class="email-title" style="margin:0 0 24px 0;color:#0f172a;font-family:Arial,Helvetica,sans-serif;font-size:32px;line-height:40px;font-weight:800;letter-spacing:-0.02em;">{title}</h1>
{blocks}
            </td>
          </tr>
          <tr>
            <td bgcolor="#f8fafc" style="padding:22px 40px;border-top:1px solid #e2e8f0;text-align:center;">
              <p style="margin:0 0 8px 0;color:#64748b;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;">TradeWave &mdash; seasonal market research that shows its work.</p>
              <p style="margin:0;color:#64748b;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;"><a href="{UNSUBSCRIBE_TOKEN}" style="color:#64748b;text-decoration:underline;">Unsubscribe</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _source_links(source_text: str) -> set[str]:
    links: set[str] = set()
    for match in LINK_RE.finditer(source_text):
        value, _ = _trim_link_punctuation(match.group(0))
        links.add(value)
    return links


def validate_render(source: EmailSource, rendered: str) -> None:
    errors: list[str] = []
    if rendered.count(UNSUBSCRIBE_TOKEN) != 1:
        errors.append(f"rendered HTML must contain exactly one {UNSUBSCRIBE_TOKEN}")

    unescaped = html.unescape(rendered)
    rendered_hrefs = set(re.findall(r'href="([^"]+)"', unescaped, flags=re.IGNORECASE))
    for link in sorted(_source_links(source.source_text)):
        if link not in unescaped:
            errors.append(f"missing source link: {link}")
            continue
        expected_href = (
            link
            if link.lower().startswith(("http://", "https://", "mailto:"))
            else f"mailto:{link}"
        )
        if expected_href not in rendered_hrefs:
            errors.append(f"source link is not clickable: {link}")

    visible_text = re.sub(r"<style\b[^>]*>.*?</style>", " ", rendered, flags=re.I | re.S)
    visible_text = re.sub(r"<[^>]+>", " ", visible_text)
    visible_text = html.unescape(visible_text)
    for label, pattern in BANNED_COPY.items():
        match = pattern.search(visible_text)
        if match:
            errors.append(f"{label}: {match.group(0)!r}")

    if "<!doctype html>" not in rendered.lower():
        errors.append("missing HTML doctype")
    if source.subject not in unescaped:
        errors.append("subject missing from HTML title")
    if source.preview not in unescaped:
        errors.append("preview missing from preheader")

    if errors:
        details = "; ".join(errors)
        raise ValueError(f"{source.path}: {details}")


def render_all(check: bool) -> int:
    changed: list[Path] = []
    stale: list[Path] = []
    validated = 0

    for tier in TIERS:
        for number in EMAIL_NUMBERS:
            source_path = EMAIL_ROOT / tier / f"email-{number}.txt"
            output_path = source_path.with_suffix(".html")
            source = parse_source(source_path, tier)
            rendered = render_email(source)
            validate_render(source, rendered)
            validated += 1

            current = output_path.read_text(encoding="utf-8") if output_path.exists() else None
            if current == rendered:
                continue
            if check:
                stale.append(output_path)
                continue
            with output_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
            changed.append(output_path)

    if check and stale:
        print("Paid-nurture HTML is stale:")
        for path in stale:
            print(f"  {path.relative_to(REPO_ROOT)}")
        print("Run: python ops/render_paid_nurture_emails.py")
        return 1

    action = "validated" if check else "rendered"
    print(f"{action.capitalize()} {validated} paid-nurture emails.")
    if changed:
        print(f"Updated {len(changed)} HTML files:")
        for path in changed:
            print(f"  {path.relative_to(REPO_ROOT)}")
    elif not check:
        print("All HTML files were already current.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate sources and fail if generated HTML differs from disk",
    )
    args = parser.parse_args()
    try:
        return render_all(check=args.check)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
