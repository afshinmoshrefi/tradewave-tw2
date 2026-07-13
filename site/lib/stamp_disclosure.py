#!/usr/bin/env python3
"""
Pixel-disclosure stamper for TradeWave content figures.

WHY THIS EXISTS: per docs/marketing/CONTENT_PRODUCTION_HANDOFF.md Sec.2/5, every
published figure (a UI capture from tools/ui_capture/, or any other pre-existing
image) must carry the disclosure line IN ITS PIXELS, not just in a caption or
alt-text, because images get copied/re-hosted/screenshotted-of-a-screenshot and
travel without their captions. Brand charts from site/generate_insights_charts.py
(matplotlib) already bake their own footer natively at generation time - this
module is for everything else: UI captures out of tools/ui_capture/out/, and any
other pre-existing PNG that needs the line added after the fact.

Branding precedent: site/ticker_pages/generate_og_images.py is the existing
PIL-based renderer for TradeWave-branded images. This module deliberately reuses
its font-loading approach (DejaVu Bold/Regular with a graceful fallback list, since
Inter is not installed on this box - see FONT_CANDIDATES below) and its general
"thin divider + brand wordmark" visual language, so a stamped UI capture reads as
something the app itself rendered, not as a watermark bolted on by a separate tool.

Usage as a library:
    from site.lib.stamp_disclosure import stamp_disclosure
    out_path = stamp_disclosure('/path/to/capture.png')

Usage as a CLI:
    /home/flask/venv/bin/python3 site/lib/stamp_disclosure.py <in.png> [out.png]
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

# The exact disclosure line, per CONTENT_PRODUCTION_HANDOFF.md Sec.2. Do not
# reword this - it is a compliance string, not marketing copy. It already
# contains no em dash (house rule), so no_em_dash() is not needed here, but
# callers who pass a custom `text` are responsible for their own compliance.
DEFAULT_DISCLOSURE = (
    "Historical data. Not a recommendation. Past performance does not "
    "guarantee future results."
)

BRAND_TEXT = "TradeWave.AI"

# Font search order. generate_og_images.py hardcodes DejaVu paths directly
# (Inter is not installed on this box as of 2026-07-09 - confirmed by checking
# fc-list before writing this). We keep the same two DejaVu weights but widen
# the fallback list so this module fails soft (falls through every known path)
# rather than hard, before finally falling back to PIL's built-in bitmap font
# and, if even that constructor errors, failing fast with a clear message -
# per the "fail fast on unreadable input/missing font" requirement, a stamped
# image with a font that's silently wrong (e.g. PIL's tiny default bitmap font
# at a "36px" size that doesn't actually scale) is worse than a loud error,
# but running out of real fonts entirely on this box is not expected to happen.
FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/Inter/Inter-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/Inter/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
}

# --- Bar palette -----------------------------------------------------------
# Two variants, picked at stamp time by sampling the source image (see
# _detect_theme below) so the same script produces a correct bar for both
# dark-theme and light-theme captures without the caller having to say which.
#
# Dark variant: near-black, sampled+darkened from the capture's own bottom
# row (see WHY under _detect_theme) so the new bar blends into the app chrome
# it's extending rather than looking like a pasted-on strip of a different
# black. Text is muted light-gray, matching generate_og_images.py's
# TEXT_SECONDARY (156, 163, 175) family rather than pure white, so the
# disclosure reads as secondary/legal text, not a headline.
DARK_TEXT = (156, 163, 175)
DARK_BRAND = (129, 140, 248)  # a lighter tint of generate_og_images.py's ACCENT (99,102,241) - reads on near-black
DARK_FALLBACK_BG = (18, 15, 26)  # used only if bottom-row sampling is unavailable

# Light variant: a light-gray bar (not pure white, so it still reads as a
# distinct footer strip rather than blending invisibly into a white chart
# background) with dark-gray text.
LIGHT_TEXT = (75, 85, 99)      # matches generate_og_images.py's TEXT_SECONDARY tone family, dark end
LIGHT_BRAND = (79, 70, 229)    # a darker tint of ACCENT, readable on light backgrounds
LIGHT_BAR_BG = (237, 237, 240)


def _load_font(style, size):
    """Load a font by style ('bold'/'regular') at `size`, walking FONT_CANDIDATES.

    Fails fast (raises) only if every candidate path AND the PIL default font
    both fail - in practice this box always has DejaVu, so this is a safety
    net for a hypothetically stripped-down environment, not the expected path.
    """
    for path in FONT_CANDIDATES[style]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception as e:
        raise RuntimeError(
            "stamp_disclosure: no usable font found (tried %r and PIL's "
            "built-in default) - %s" % (FONT_CANDIDATES[style], e)
        )


def _sample_bottom_row_color(img):
    """Return the dominant RGB color of the image's bottom pixel row.

    WHY sample instead of hardcoding one dark and one light constant: UI
    captures come from tools/ui_capture/ in both themes, and even within a
    theme the exact background shade can drift as the app's CSS changes (e.g.
    a slightly different near-black between the opp table and the wave-viewer
    pane). Sampling the capture's OWN last row and blending a stamped bar from
    that color is what makes the appended bar look like a natural continuation
    of the image instead of a mismatched strip - the whole point of extending
    the canvas (see stamp_disclosure's docstring) rather than overlaying is
    defeated if the new bar is an obviously different shade of "dark."

    We use the bottom row specifically (not e.g. a corner pixel) because the
    bar is appended directly below it - whatever color is there is exactly
    what the new bar needs to visually continue from.
    """
    w, h = img.size
    # Sample a strided set of pixels across the bottom row rather than every
    # pixel - this is a footer color estimate, not a precise average, and
    # striding keeps this cheap even on a 3840px-wide capture.
    step = max(1, w // 40)
    samples = [img.getpixel((x, h - 1)) for x in range(0, w, step)]
    # Drop alpha if present (RGBA sources) - only used for RGB math below.
    samples = [tuple(s[:3]) for s in samples]
    r = sum(s[0] for s in samples) // len(samples)
    g = sum(s[1] for s in samples) // len(samples)
    b = sum(s[2] for s in samples) // len(samples)
    return (r, g, b)


def _luminance(rgb):
    """Perceptual luminance (0-255), standard Rec. 601 weights."""
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _darken(rgb, factor=0.72):
    """Scale an RGB tuple toward black by `factor` (< 1 darkens)."""
    return tuple(max(0, int(c * factor)) for c in rgb)


def _detect_theme(img):
    """Decide dark-bar vs light-bar mode from the image's own bottom row.

    WHY sample-based, not a caller-supplied flag: UI captures out of
    tools/ui_capture/ already come in both dark and light theme (see
    aapl_seasonal_dark.* vs aapl_seasonal_light.* in out/demo/), and this
    stamper is meant to run unattended in the content pipeline (Sec.5 of the
    handoff doc) without a human eyeballing each file to pick a mode. Reusing
    the same bottom-row sample this module already needs for bar-color
    blending (see _sample_bottom_row_color) to ALSO decide light-vs-dark is
    one measurement doing two jobs, and it can't drift out of sync with the
    actual image the way a hardcoded/guessed flag could.

    Returns (theme, sampled_rgb) where theme is 'dark' or 'light'.
    """
    sampled = _sample_bottom_row_color(img)
    theme = "light" if _luminance(sampled) >= 128 else "dark"
    return theme, sampled


def stamp_disclosure(in_path, out_path=None, text=DEFAULT_DISCLOSURE):
    """Append a branded disclosure footer bar to a PNG, in its pixels.

    Args:
        in_path: source PNG path. Must exist and be readable by PIL.
        out_path: destination path. If None, defaults to
            '<in_path without extension>-stamped.png'.
        text: disclosure text to render (defaults to the house-standard
            DEFAULT_DISCLOSURE line - do not change the default without
            updating docs/marketing/CONTENT_PRODUCTION_HANDOFF.md Sec.2, since
            that doc is the compliance source of truth for this exact string).

    Returns:
        out_path (str), the path actually written.

    WHY EXTEND THE CANVAS RATHER THAN OVERLAY ON TOP OF THE IMAGE:
    An overlay (semi-transparent strip drawn on top of existing pixels) always
    risks covering real chart content - the last row of a bar chart, a legend,
    an axis label near the bottom edge. UI captures from tools/ui_capture/ are
    tightly cropped to their content region (see docs/UI_CAPTURE_PIPELINE.md
    Sec.5/6 - crops are measured off real element bounding boxes, not padded),
    so there is no guaranteed "safe" empty margin at the bottom to overlay
    into. Extending the canvas height and painting the new footer bar into
    the NEW pixels only guarantees zero content loss, at the cost of a
    slightly taller image - a trade this pipeline always wants, since a
    disclosure that's illegible-because-it's-over-a-chart-line defeats the
    entire compliance purpose of stamping it into the pixels in the first
    place.
    """
    if not os.path.isfile(in_path):
        raise FileNotFoundError("stamp_disclosure: input not found: %s" % in_path)

    try:
        src = Image.open(in_path)
        src.load()  # force-read pixel data now, so a truncated/corrupt PNG fails here, not later
    except Exception as e:
        raise ValueError("stamp_disclosure: unreadable image %r: %s" % (in_path, e))

    src = src.convert("RGB")
    width, height = src.size

    theme, sampled_bg = _detect_theme(src)

    # --- Scale font size and bar height with image width ------------------
    # Spec target: ~28-34px font at 2678px wide (the standard UI-capture
    # width - see docs/UI_CAPTURE_PIPELINE.md's waveViewer crop, 2678px at
    # scale:2). Scale linearly off that reference point so narrower or wider
    # captures (e.g. 4x-scale captures, or a narrower crop) still get a
    # legible-but-proportionate footer instead of a fixed pixel size that's
    # too small on a 3840px appNoBanner crop or too large on a small crop.
    REFERENCE_WIDTH = 2678.0
    REFERENCE_FONT_SIZE = 30  # midpoint of the requested 28-34px range
    font_size = int(round(REFERENCE_FONT_SIZE * (width / REFERENCE_WIDTH)))
    font_size = max(16, min(font_size, 64))  # sane floor/ceiling for extreme widths

    brand_font_size = int(round(font_size * 1.05))  # brand wordmark reads slightly bolder/larger, matching og-image style

    pad_x = int(round(font_size * 1.3))  # left/right padding, scales with font
    bar_height = int(round(font_size * 2.6))  # slim bar: comfortably fits one text line + vertical padding

    disclosure_font = _load_font("regular", font_size)
    brand_font = _load_font("bold", brand_font_size)

    # --- Bar colors, by theme ----------------------------------------------
    if theme == "dark":
        # Darken the capture's own sampled bottom-row color so the bar reads
        # as a natural continuation of the UI's chrome, not a flat block of a
        # different near-black (see _sample_bottom_row_color's docstring for
        # why sampling instead of a hardcoded constant).
        bar_bg = _darken(sampled_bg, factor=0.72)
        text_color = DARK_TEXT
        brand_color = DARK_BRAND
    else:
        bar_bg = LIGHT_BAR_BG
        text_color = LIGHT_TEXT
        brand_color = LIGHT_BRAND

    # --- Build the extended canvas -----------------------------------------
    new_height = height + bar_height
    out_img = Image.new("RGB", (width, new_height), bar_bg)
    out_img.paste(src, (0, 0))
    draw = ImageDraw.Draw(out_img)

    bar_top = height
    text_center_y = bar_top + bar_height // 2

    # Disclosure text, left-aligned with padding, vertically centered in the bar.
    bbox = draw.textbbox((0, 0), text, font=disclosure_font)
    text_h = bbox[3] - bbox[1]
    disclosure_y = text_center_y - text_h // 2 - bbox[1]
    draw.text((pad_x, disclosure_y), text, fill=text_color, font=disclosure_font)

    # "TradeWave.AI" brand mark, right-aligned with matching padding, same
    # vertical center - mirrors generate_og_images.py's left-aligned brand
    # wordmark treatment, just right-aligned here since the disclosure text
    # already owns the left side of this slim bar.
    bbox = draw.textbbox((0, 0), BRAND_TEXT, font=brand_font)
    brand_w = bbox[2] - bbox[0]
    brand_h = bbox[3] - bbox[1]
    brand_x = width - pad_x - brand_w
    brand_y = text_center_y - brand_h // 2 - bbox[1]
    draw.text((brand_x, brand_y), BRAND_TEXT, fill=brand_color, font=brand_font)

    if out_path is None:
        root, _ext = os.path.splitext(in_path)
        out_path = root + "-stamped.png"

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_img.save(out_path, "PNG", optimize=True)

    # Keep ownership consistent with the rest of the dev-box content pipeline
    # (everything under site/ and tools/ui_capture/ runs and is owned as
    # flask:flask - see docs/UI_CAPTURE_PIPELINE.md Sec.1). Best-effort: this
    # is a convenience, not correctness, so a chown failure (e.g. script run
    # by a different user without permission) should not crash the stamp.
    try:
        import pwd
        import grp

        uid = pwd.getpwnam("flask").pw_uid
        gid = grp.getgrnam("flask").gr_gid
        os.chown(out_path, uid, gid)
        os.chmod(out_path, 0o640)  # match the rest of tools/ui_capture/out/ (owner rw, group r)
    except Exception:
        pass

    return out_path


def _main():
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: stamp_disclosure.py <in.png> [out.png]\n"
        )
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = stamp_disclosure(in_path, out_path)
    except Exception as e:
        sys.stderr.write("stamp_disclosure: FAIL: %s\n" % e)
        sys.exit(1)

    with Image.open(result) as im:
        print("stamped: %s (%dx%d)" % (result, im.width, im.height))


if __name__ == "__main__":
    _main()
