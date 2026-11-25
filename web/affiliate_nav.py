"""The ONE sub-navigation shown on every partner-program admin page
(TW-TASK-0039, fix-0039).

Plain HTML with fixed /admin/... paths and no template syntax, so the same
string drops into the string templates of affiliate_admin / affiliate_ops_admin
/ affiliate_help_admin / affiliate_comms_admin / affiliate_owner_admin, into
the page templates inside web/app.py, and (as the Jinja global
`affiliate_subnav`) into the Flask-Admin list pages through
templates/admin/affiliate_list.html. No imports: safe to load from anywhere.

Paths are Flask-Admin endpoints registered in web/app.py; a test checks that
every one of them resolves.
"""

# (path, label, group). Groups only add a little space between related links.
NAV_ITEMS = (
    ("/admin/affiliate_home/", "Partner program", "home"),
    ("/admin/affiliate_applications/", "Applications", "people"),
    ("/admin/affiliate/", "Partners", "people"),
    ("/admin/affiliate_help/", "Questions", "people"),
    ("/admin/affiliate_messages/", "Messages", "people"),
    ("/admin/affiliate_tax_forms/", "Tax forms", "money"),
    ("/admin/affiliate_compute/", "Compute", "money"),
    ("/admin/affiliate_bulk_payouts/", "Bulk payouts", "money"),
    ("/admin/affiliatepayout/", "Payout ledger", "money"),
    ("/admin/affiliatecommissionline/", "Commission lines", "money"),
    ("/admin/affiliate_tax_report/", "Year-end tax report", "money"),
    ("/admin/affiliate_terms/", "Terms", "setup"),
    ("/admin/promo_campaigns/", "Campaigns", "setup"),
    ("/admin/affiliate_creatives/", "Creative library", "setup"),
    ("/admin/affiliate_help_kb/", "Knowledge base", "setup"),
    ("/admin/affiliate_guide/", "How it works", "setup"),
)

_STYLE = (
    "<style>"
    ".twp-nav{display:flex;flex-wrap:wrap;gap:6px 6px;align-items:center;margin:0 0 14px;padding:8px 10px;"
    "background:#fff;border:1px solid #e3e6ee;border-radius:10px;font:13px/1.4 -apple-system,Segoe UI,Roboto,Arial,sans-serif;}"
    ".twp-nav a{display:inline-block;margin:0;padding:4px 10px;border-radius:16px;color:#3a32a8;text-decoration:none;white-space:nowrap;}"
    ".twp-nav a:hover{background:#eef2ff;}"
    ".twp-nav a.twp-home{background:#4f46e5;color:#fff;font-weight:700;}"
    ".twp-nav a.twp-back{color:#555;}"
    ".twp-nav .twp-sep{width:1px;height:16px;background:#d9dcea;margin:0 2px;}"
    "@media (max-width:640px){.twp-nav{padding:6px;gap:4px;}.twp-nav a{padding:6px 9px;}.twp-nav .twp-sep{display:none;}}"
    "</style>"
)


def build() -> str:
    parts = [_STYLE, '<div class="twp-nav" role="navigation" aria-label="Partner program">',
             '<a class="twp-back" href="/admin">&larr; Admin</a>']
    last = None
    for path, label, group in NAV_ITEMS:
        if last is not None and group != last:
            parts.append('<span class="twp-sep" aria-hidden="true"></span>')
        last = group
        parts.append('<a%s href="%s">%s</a>' % (' class="twp-home"' if group == "home" else "", path, label))
    parts.append("</div>")
    return "".join(parts)


NAV_HTML = build()
