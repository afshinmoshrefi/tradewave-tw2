"""SEO + social + AI-discoverability for the TradeWave developer portal.

Two parts:
  - head_tags(canonical_url, title, description, og_type): per-page <head> block with a
    canonical link, Open Graph + Twitter Card tags, and sitewide JSON-LD (Organization +
    WebSite). Each portal generator inserts this into its page shell.
  - build_sitemap() / build_robots() / build_llms(): the site-level discovery files
    (sitemap.xml, robots.txt, llms.txt) written into the portal docroot.

All URLs are env-driven via portal_urls (dev -> developers-dev.trxstat.com; prod ->
developers.tradewave.ai). No em-dashes in any emitted copy.
"""
import portal_urls

PORTAL = portal_urls.PORTAL_URL          # https://developers.tradewave.ai (prod) / -dev (dev)
DOCS = portal_urls.DOCS_URL
LEARN = portal_urls.LEARN_URL
API_BASE = portal_urls.API_BASE
MCP_URL = portal_urls.MCP_URL
CONSOLE = portal_urls.CONSOLE_URL
MAIN = portal_urls.MAIN_URL
OG_IMAGE = PORTAL + "/og-developers.png"   # generated brand card (see build_og_image note)

_ORG_JSONLD = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "TradeWave",
    "url": MAIN,
    "logo": MAIN + "/_static/logo.png",
    "sameAs": [MAIN],
}


def _ld(obj):
    import json
    return '<script type="application/ld+json">%s</script>' % json.dumps(obj, separators=(",", ":"))


def head_tags(canonical_url, title, description, og_type="website", jsonld=None):
    """Return the SEO/social/JSON-LD <head> block for one page. title/description are the
    human strings (no site suffix needed - we add og:site_name separately)."""
    desc = (description or "").replace('"', "&quot;")
    ttl = (title or "").replace('"', "&quot;")
    blocks = [
        '<link rel="canonical" href="%s">' % canonical_url,
        '<meta property="og:type" content="%s">' % og_type,
        '<meta property="og:site_name" content="TradeWave Developers">',
        '<meta property="og:title" content="%s">' % ttl,
        '<meta property="og:description" content="%s">' % desc,
        '<meta property="og:url" content="%s">' % canonical_url,
        '<meta property="og:image" content="%s">' % OG_IMAGE,
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="%s">' % ttl,
        '<meta name="twitter:description" content="%s">' % desc,
        '<meta name="twitter:image" content="%s">' % OG_IMAGE,
        _ld(_ORG_JSONLD),
        _ld({
            "@context": "https://schema.org", "@type": "WebSite",
            "name": "TradeWave Developers", "url": PORTAL,
        }),
    ]
    if jsonld:
        blocks.append(_ld(jsonld))
    return "\n  ".join(blocks)


def api_jsonld():
    """JSON-LD describing the API product itself (for the marketing/docs landing)."""
    return {
        "@context": "https://schema.org",
        "@type": "WebAPI",
        "name": "TradeWave Data API",
        "description": ("Seasonal-edge and ML trading signals as a REST API and MCP server. "
                        "Signals only (percentages and a normalized 0-100 index, never raw prices), "
                        "broker-agnostic, with a public forward-tested track record."),
        "url": DOCS,
        "documentation": DOCS,
        "provider": _ORG_JSONLD,
    }


# --- site-level discovery files -------------------------------------------------

def build_sitemap(urls):
    """urls = list of (loc, changefreq, priority). loc is absolute."""
    items = []
    for loc, freq, prio in urls:
        items.append(
            "  <url>\n    <loc>%s</loc>\n    <changefreq>%s</changefreq>\n"
            "    <priority>%s</priority>\n  </url>" % (loc, freq, prio))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(items) + "\n</urlset>\n")


def build_robots():
    return ("User-agent: *\nAllow: /\n\n"
            "# AI agents and crawlers welcome - this is a public developer surface.\n"
            "Sitemap: %s/sitemap.xml\n" % PORTAL)


def build_llms():
    """llms.txt - a concise, link-rich map for LLMs / AI agents (llmstxt.org convention).
    Fitting for an MCP product: it tells an agent exactly how to use TradeWave."""
    base = """# TradeWave Developers

> Seasonal-edge and ML trading signals for developers and AI agents. Signals only
> (percentages and a normalized 0-100 seasonal index, never raw prices); broker-agnostic;
> with a public, time-stamped, forward-tested daily-pick track record.

TradeWave exposes the same seasonal + ML signals two ways: a REST API and a hosted MCP
server. REST authentication is a single API key (Authorization: Bearer tw_live_...); the
MCP server also accepts an OAuth sign-in with a TradeWave account (how ChatGPT and
Claude.ai connect - no API key). ML scoring is available on every tier, metered per day.
Every response is educational and carries a disclaimer; nothing here is personalized
investment advice.

## Start here
- Quickstart: {docs}/quickstart.html
- Authentication: {docs}/authentication.html
- API reference: {docs}/api-reference.html
- Interactive playground: {portal}/playground/
- Get an API key (free): {console}

## For AI agents (MCP)
- MCP endpoint (streamable-http; ChatGPT/Claude.ai sign in via OAuth, dev tools use a Bearer API key): {mcp}
- MCP setup (ChatGPT, Claude, Cursor): {portal}/mcp.html
- Flagship tools: find_best_opportunities, analyze_symbol, explain_pick, morning_briefing, whats_seasonal_now, compare_opportunities
- Discovery manifest: {portal}/.well-known/mcp.json

## Learn
- What is a seasonal edge / reading a SignalCard: {learn}/what-is-a-seasonal-edge.html
- Build a cross-market screener: {learn}/cross-market-screener.html
- Using the ML win-probability model: {learn}/ml-win-probability.html
- The verifiable track record: {learn}/verifiable-track-record.html

## Reference
- OpenAPI spec: {docs}/openapi.yaml
- Postman collection: {docs}/tradewave.postman_collection.json
- Pricing: {portal}/pricing.html
""".format(docs=DOCS, portal=PORTAL, console=CONSOLE, mcp=MCP_URL, learn=LEARN)

    # Append the agent-era argument (why consume instead of compute + how an agent integrates),
    # authored + honesty-critiqued, stored in llms_agent_append.md. Its hardcoded prod URLs are
    # rewritten to the env-driven hosts so dev/staging/prod each emit their own.
    import os
    extra_path = os.path.join(os.path.dirname(__file__), "llms_agent_append.md")
    try:
        with open(extra_path, encoding="utf-8") as f:
            extra = f.read()
    except OSError:
        extra = ""
    if extra:
        extra = (extra
                 .replace("https://api.tradewave.ai/v1", API_BASE)
                 .replace("https://mcp.tradewave.ai", MCP_URL)
                 .replace("https://developers.tradewave.ai/docs/openapi.yaml", DOCS + "/openapi.yaml")
                 .replace("https://developers.tradewave.ai/.well-known/mcp.json", PORTAL + "/.well-known/mcp.json")
                 .replace("https://developers.tradewave.ai/mcp.html", PORTAL + "/mcp.html")
                 .replace("https://tradewave.ai/account/api/keys", CONSOLE))
        base = base + "\n" + extra
    return base
