# TW-TASK-0009: SMN production on subscription models - target workflow and migration plan

- Status: proposed (design only; no code, schedule or production change)
- Confidence: production steps read from SMN `main` `548231e` code and the production timer list (read-only); not yet verified on the production host config (`/etc/SMN/secrets.env` values not read)
- Priority: P1. The owner's goal is to move production off per-call API billing. Dev is the test bed for this.
- First observed / last updated: 2026-09-24T21:45Z
- Executor/session/claim time: Claude Code (Opus 5.5), owner session on .180, 2026-09-24T21:45Z - design only
- Authorization: documentation only. The owner asked Claude to design the production workflow and the Dev-to-production migration.

## Goal

The Dev editions have been an experiment. Dev reads production's picks and TradeWave studies, writes independently, and lets the owner compare the old and new styles. The real goal is **production**:

1. Production writes articles through a **subscription** login (Claude or ChatGPT now; possibly Grok later), not per-call API billing.
2. The high-end model **only writes the article**. Every other step uses code, or the cheapest model that can do it.
3. A **script workflow** runs the steps in a fixed order. No AI agent directs the run: the Dev heartbeat spent 13.5M-19.6M input tokens a day re-reading its own history (TW-TASK-0006 usage evidence).
4. A **cheap hero-image check** catches bad heroes (for example the recent COSTCO hero had misspelled text). Phase 1 only reports the result. Later, a failed check regenerates the image.

## Production today (SMN `main` 548231e, read-only)

| Time (UTC) | Step | Code | AI used |
|---|---|---|---|
| 02:00 | Pick ideas: TradeWave pattern scan, filters, ranking | `select_news_articles.py` | Tavily search API; ranking LLM (`RANKING_LLM`: Claude / gpt-5-mini / grok-3 / grok-3-mini) |
| 03:00 | Queue 6 articles into Redis | `daily_article_queue.py` -> `blog_queue.py` | none |
| 03:00-03:10 | Worker, per article (`article_processor.py` -> `article_workflow.generate_news_article`) | | |
| | 1. TradeWave charts | `generate_tradewave_charts` | none (code) |
| | 2. Hero image | `article_hero_image.hero_image_workflow` | gpt-5-nano writes the image prompt; premium image API (`PREMIUM_IMAGE_PROVIDER`: stability / openai gpt-image-1 / flux), SDXL fallback |
| | 3. Research | `research_tavily` | Tavily search API + gpt-5-nano / gpt-5-mini synthesis |
| | 4. Prompt | `build_article_prompt` | none (code) |
| | 5. Write | `write_article` -> `AI_tools.send_openai_prompt` | `SMN_ARTICLE_MODEL` (default `gpt-6-astra`; memory says GPT-5.1 earlier; production env value not read) |
| | 6. SEO title | `article_title.generate_unique_seo_title` | OpenAI (gpt-5-mini) |
| | 7. Citation gate, price finalize (EODHD) | `citation_gate`, `article_post_process` | none (code) |
| | 8. Publish | `publish_article` | none |
| 05:30 | Audit | `smn-audit-daily.timer` | (not inspected) |
| ~07:00 | Reader email | email scripts | (not inspected) |

Every AI step is billed per call. Deadline: articles must be live before the ~07:00 email.

## Dev experiment today (Codex, TW-TASK-0005)

A Windows-PC heartbeat (Astra xhigh agent) at 07:00 ET: capture production's 6 picks and engine studies -> research and `sources.json` -> `subscription_daily.py` (6 writer + 6 reviewer `codex exec` jobs, **all Astra xhigh** per the September23 receipts) -> layout screenshots, inspected by the agent -> `subscription_primary_publish.py` to .180. Heroes reuse production's image; Dev makes no image call. Stronger than production on structure: strict article schema, TradeWave values unchanged, source word caps, independent review, native charts, price path, receipts.

## Target production workflow

One script, `smn_daily.py` (name TBD), run by a timer at about 03:00 UTC after selection. Each step is idempotent and writes a receipt, so a rerun resumes. Code steps cost no tokens. Model steps are short, stateless, tool-less jobs: the script gives each job its input, so no job needs web or file tools.

| # | Step | Who | Role -> default model |
|---|---|---|---|
| 1 | Select ideas (existing, 02:00) | code + LLM | `rank` -> cheap (Haiku 4.5 / gpt-5-mini) |
| 2 | TradeWave studies and charts, EODHD prices | code | - |
| 3 | Fetch news (Tavily search, existing) | code (search API) | - |
| 4 | Build `sources.json` entry: pick sources, excerpts, chart records, brief | LLM, tool-less | `research` -> Sonnet 5 low (or gpt-5-mini) |
| 5 | Validate sources: URLs load, dates, record values found in excerpts | code | - |
| 6 | **Write article** | LLM | `write` -> **Opus 5.5 medium** or **Astra xhigh** (owner chooses after comparison) |
| 7 | Mechanical checks (schema, word caps, TradeWave values, prices) | code | - |
| 8 | One repair only if 7 fails | LLM | `write` |
| 9 | Independent review | LLM | `review` -> Sonnet 5 low |
| 10 | Hero image: prompt, then render | LLM + image API | `hero_prompt` -> Haiku; image stays API (below) |
| 11 | **Hero check** (new): list the visible text, flag spelling and garbling | LLM vision, tool-less | `hero_check` -> Haiku 4.5 |
| 12 | SEO title | LLM | `title` -> Haiku |
| 13 | Render, layout/overflow check (Playwright code) | code | - |
| 14 | Publish, live check, receipt | code | - |
| 15 | Failure: retry transient steps up to 3 times; else hold the article and alert the owner | code | - |

**Provider layer.** Each role maps to one `provider/model/effort` in one config file. Adapters with the same job/receipt contract:
- `codex` - `codex exec`, ChatGPT subscription (exists: `subscription_writer.py`).
- `claude` - `claude -p`, Claude subscription (exists: `claude_subscription_writer.py`, SMN branch `claude/smn-claude-writer-20260925`).
- `grok` - future; add when xAI offers a supported subscription CLI.
- `api` - today's API calls, kept only as an explicit, owner-approved fallback.
Receipts record provider, model, effort, billing source and `api_fallback`. The `generation` metadata on each article comes from them (already built on the Claude branch).

**Hero image.** Neither subscription CLI offers a supported unattended image-generation path today. The render stays an API call (a small cost per article). Only the hero prompt and the new check move to cheap models. Check phases:
- Phase A: the check only records `hero-check.json` and alerts; nothing changes.
- Phase B (owner: "not right now"): on a spelling or garble failure, regenerate once with a "no text" instruction; after a second failure, use the fallback image.
For images, a Haiku job uses `claude -p --input-format stream-json` with the image as a base64 content block, so it needs no file tools.

## Migration plan

| Phase | Where | What | Exit gate |
|---|---|---|---|
| 0 (now) | Dev | Claude one-day edition September25 (TW-TASK-0005) | live_verified |
| 1 | Dev .180 (server, not the Windows PC) | Build `smn_daily.py` and the role config; run it daily in place of the heartbeat; hero check in report-only mode on production's heroes | 5 clean days; cost per article measured; no agent manager |
| 2 | Dev | Writer comparison on the same picks: Opus 5.5 medium vs Astra xhigh (owner blind read) | Owner picks the writer |
| 3 | Production, shadow | Install the subscription CLI login on production. Run the new pipeline at 03:00 into a private folder; the API pipeline still publishes. Compare daily | 5 days finished before 06:00 with no hold; owner approves the style |
| 4 | Production, cutover | New pipeline publishes. If it has not finished by 06:00, the old API pipeline runs (if the owner approves the fallback). Deploy through `smn_deploy.sh` (snapshot plus one-command rollback) | 2 weeks stable |
| 5 | Production | Retire the API writer path; turn on hero regeneration (Phase B); add Grok when available | - |

Production stays untouched until Phase 3, and Phase 3 needs explicit owner authorization.

## Risks and open questions

1. **Subscription terms and limits.** Confirm that each provider's plan allows scheduled, unattended use for a commercial site. The owner is on Claude Pro, and 6 articles with review is about 20 short jobs. A larger plan may be needed for headroom. Not verified.
2. **Limit or outage on a production morning.** Options: fall back to the API, or delay the day. This is an owner decision.
3. **Login on a server.** The subscription CLI must be logged in on the production host, and the login can expire. The script must check the login at 02:30 and alert early.
4. **Style change.** Production articles will change from the old API style to the new edition style (schema, native charts, review). URLs, SEO and emails must keep working. This needs a checklist before Phase 3.
5. **Codex's open points** (TW-TASK-0006): bounded recovery and a total job budget. Both are part of step 15 and the role config.

## History

- 2026-09-24T21:45Z, Claude: design proposed at the owner's request. Next: Codex review of this plan in TW-TASK-0006; owner decisions on risks 1-2; then Phase 1 build on Dev.
