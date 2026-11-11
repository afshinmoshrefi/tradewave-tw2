# TW-TASK-0027: Expand the Learn section for search traffic

- Status: verified on dev
- Confidence: n/a (feature)
- Priority: P2, organic search acquisition; Learn had six short platform guides
- First observed / last updated: 2026-11-11
- Executor/session/claim time: Claude, learn-seo-expansion-20261111, 2026-11-11T19:30Z
- Authorization: Afshin asked to expand the Learn section extensively so it drives search traffic, and to add two TradeWaveAI YouTube videos ("Learn TRADEWAVE in 4 MINUTES" and "80% wins still losing"). Routine dev activation included; staging/production excluded.

## Goal, Scope and Acceptance

- Add searchable, accurate Learn guides on seasonal trading concepts, metrics and risk, not only product walkthroughs.
- Embed the two videos: `7ZQoj2e93oo` ("Find Your First Wave - Start Here", 4:00, the four-minute tour) and `3STPilmV3aU` ("Risk Reward Ratio vs Win Rate: Which Matters More?", the 80%-winners-still-lose video). Identified from the channel by title, length and description.
- Keep Michael Sacchitello's creator credit on the six guides he created; credit new articles to TradeWave Research.
- Structured data: Article (per-article author), VideoObject, FAQPage, BreadcrumbList; Blog on the index.

## Implementation and Handoff

- `site/generate_learn.py`: resolves content/templates/config from its own checkout (dev follows `.tw2-app-current`; previously hardcoded `/home/flask/site`, so dev rendered stale content); `TW_LEARN_OUTPUT_DIR` override for tests; CATEGORIES (Start Here, Seasonal Trading Basics, Reading the Numbers, Risk and Trade Management, Platform Guides, Reference); frontmatter `category`, `updated`, `video`, `faq`; per-article author; unknown `related:` slugs fail the run.
- `site/templates/learn_article.html`: privacy-enhanced YouTube embed (youtube-nocookie.com is already in the site CSP frame-src), VideoObject and FAQPage JSON-LD, visible FAQ, category breadcrumb, research byline, CTA to `/signup` (`data-cta-id="learn_article_try_free"`), educational disclaimer, duplicate footer Learn link replaced with Insights.
- `site/templates/learn_index.html`: SEO title/description, section navigation, "Watch and Learn" video row, grouped category sections; Michael's credit scoped to Platform Guides.
- 19 new articles in `site/content/learn/` (about 20,000 words). Figures come from `docs/TRADEWAVE_METHODOLOGY_AND_FEATURES_KB.md` and the two video descriptions; worked arithmetic examples were recomputed.
- `tests/test_learn_generator.py`: renders into a temp dir; checks structured data, internal links, nocookie embeds, FAQ markup, creator credit scope and section order.
- Activation: static generator only. Run `site/generate_learn.py` then `site/generate_seo_files.py` from the active checkout. No service restart, migration, dependency or React build.
- Rollback: point `.tw2-app-current` back to the recorded previous root and rerun `generate_learn.py` and `generate_seo_files.py` from it.

## Environment Verification

Dev: verified 2026-11-11 by Claude. Main and live dev are both 2a48ad7890a2b9cc628325e43d92fe9b2a17568c (tree dec9670b); `.tw2-app-current` -> /home/tradewave-worktrees/learn-seo-expansion-dev-20261111 (previous /home/tradewave-worktrees/mcp-chart-styles-final-20261020). Backend code identical to the prior live tree (diff limited to site/, tests/, docs/), so no service was restarted; running processes keep the old, content-identical cwd until their next restart. Ran generate_learn.py (25 articles) and generate_seo_files.py (sitemap 61 URLs). Browser smoke on https://tw2-dev.trxstat.com/learn/: 25 cards in 6 sections, four-minute video embed plays, FAQ opens, Article/VideoObject/FAQPage/BreadcrumbList JSON-LD, no horizontal overflow at 375px. Evidence: /var/lib/tradewave/release-state/learn-seo-expansion-20261111/ (activation-before.json, learn-before.tgz, dev-verification.json). Rollback: point .tw2-app-current back to the previous root, rerun both generators (or untar learn-before.tgz into /var/www/tradewave). Staging: not checked. Production: not checked.

Owner action: the "80% wins still losing" video (3STPilmV3aU) has embedding disabled on YouTube, so it renders as a thumbnail linking to YouTube (`embeddable: false`). If Afshin enables "Allow embedding" in YouTube Studio, remove that line to embed it inline.

## History

- 2026-11-11: Claimed; plan, articles, generator/template changes and tests written in task worktree.
- 2026-11-11: First activation showed Video unavailable for 3STPilmV3aU (embedding disabled by owner); added embeddable: false thumbnail fallback (2a48ad78). Verified on dev, main advanced without force, lock released.
