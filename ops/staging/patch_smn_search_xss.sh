#!/usr/bin/env bash
# Idempotent patch for the SMN search.html stored-XSS.
# Original file at /var/www/smn/search.html came from TW1 prod and inlines
# article.title / article.dek into innerHTML with no escaping. We inject
# a small escapeHtml() helper and wrap the two interpolations.
#
# Safe to re-run — first run patches, subsequent runs see the marker and skip.

set -euo pipefail

TARGET=/var/www/smn/search.html
[[ -f "$TARGET" ]] || { echo "no $TARGET — nothing to patch"; exit 0; }

if grep -q "function escapeHtml" "$TARGET"; then
    echo "already patched"
    exit 0
fi

cp -a "$TARGET" "${TARGET}.preXSSpatch"

# 1. Insert escapeHtml() helper just before filteredArticles.map
python3 - <<'PY'
from pathlib import Path
import re
p = Path("/var/www/smn/search.html")
s = p.read_text(encoding='utf-8')
helper = """
        function escapeHtml(v) {
            if (v == null) return '';
            return String(v)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
"""
# Insert helper just before the first reference to filteredArticles
s2 = re.sub(r"(?P<lead>\n\s*)(container\.innerHTML\s*=\s*filteredArticles)",
            lambda m: m.group('lead') + helper.strip() + m.group('lead') + m.group(2),
            s, count=1)
# Wrap title + dek
s2 = s2.replace("${article.title || 'Untitled'}", "${escapeHtml(article.title || 'Untitled')}")
s2 = s2.replace("${article.dek || ''}", "${escapeHtml(article.dek || '')}")
# Wrap symbol/heroUrl/url for defense-in-depth
s2 = s2.replace('<img src="${heroUrl}" alt="${article.symbol}">',
                '<img src="${escapeHtml(heroUrl)}" alt="${escapeHtml(article.symbol)}">')
s2 = s2.replace('<a href="${article.url}" class="result-item">',
                '<a href="${escapeHtml(article.url)}" class="result-item">')
if s == s2:
    raise SystemExit("patch produced no changes — file format may have shifted, aborting")
p.write_text(s2, encoding='utf-8')
print("patched", p)
PY

chown www-data:www-data "$TARGET"
chmod 644 "$TARGET"
echo "search.html patched + backup at ${TARGET}.preXSSpatch"
