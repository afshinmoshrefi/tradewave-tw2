# TW-TASK-0009: SMN production on subscription models - target workflow and migration plan

- Status: in-progress (generation dashboard verified on Dev; private Claude comparison finished with five reviewed previews and one held article; server ChatGPT authentication and scheduler cutover pending; production migration remains proposed)
- Confidence: production steps read from SMN `main` `548231e` code and the production timer list (read-only); not yet verified on the production host config (`/etc/SMN/secrets.env` values not read)
- Priority: P1. The owner's goal is to move production off per-call API billing. Dev is the test bed for this.
- First observed / last updated: 2026-09-26T18:34Z
- Executor/session/claim time: Claude Code (Opus 5.5), owner session on .180, 2026-09-24T21:45Z - original design; Codex `smn-dashboard-generation-20260926` owns current Dev work.
- Authorization: original production plan was documentation only; the owner subsequently authorized the Dev provider switch, dashboard and bounded Claude comparison. Production migration still requires separate authorization.

## September26 Current Handoff

Owner explicitly requested ChatGPT models with Astra **high**, not xhigh, and a reversible Claude/ChatGPT selector. SMN main and live Dev source are now `77bf3468809f22a690f4d4543779b6b39f00bd7c`, installed at `/opt/smn-daily/releases/77bf3468809f22a690f4d4543779b6b39f00bd7c` on primary Dev .180, with `/opt/smn-daily/current` pointing there. The dashboard changes advanced through `3f78e502ab00f90a06c78707e29a24f45e316472` and `ea90f9b0ee0e9a5bda4e18fb97eec13938fd852a`; prior script source was `b559a86483cb89adcc452b69cd4703626132b1ac`. The activation lock is released. This does not change production.

- `smn-daily profile chatgpt` selects Astra high writing, Sol medium research/review and Luna low image checks. `smn-daily profile claude` restores Opus 5.5 medium, Sonnet 5 low and Haiku 4.5 low. **Current selection is Claude**, saved through the Dev dashboard for the comparison. Selection applies to new editions; an incomplete date stays bound to its original roles. `smn-daily profile` displays the selection; `smn-daily run` executes the New York date through the fixed script.
- All stages, including visual checks and failed attempts, share the 40-job limit. Completed receipts are reused; overlapping script runs are rejected. Fresh-source discovery uses a bounded research-role web job, then code captures two primary pages with URLs, dates and hashes. One alternate-source discovery is allowed when pages fail. Research must cite captured primary sources. Direct HTTPS connections pin checked public IPs while retaining TLS hostname verification.
- Subscription-only adapters preserve API-variable stripping and reject unsupported model/effort choices. Claude's WebSearch may internally use its Haiku helper and StructuredOutput; that is allowed only for the discovery stage and recorded separately. Article writing/review remain tool-less with exact configured models. No engine mathematics changed.
- Verification: 44 focused Linux tests passed. A private retained September25 F article passed Astra high writing, Sol medium independent review, source/structure checks, desktop/mobile layouts and Luna low visual inspection with no repair. Sol web discovery and fresh captured-page research passed separately. Claude WebSearch executed through the saved subscription; its saved successful output was revalidated after accounting for the internal helper/StructuredOutput. No full new six-article edition or percentage cost saving has been verified.
- Evidence: Windows `C:/Users/afshin/Documents/smn-provider-verification-20260926` (article/receipts and discovery); Dev `/var/tmp/smn-switch-source-verified`, `/var/tmp/smn-switch-claude-discovery`, `/var/tmp/smn-switch-tests-20260926`. The installed command skipped the completed September25 receipt without generating anything; September26 returned `waiting_for_production` with zero model jobs. Compact operational result: `/var/lib/tradewave/smn-daily/last-run.json`.
- **Remaining:** the updated server CLI `/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex` sees no valid ChatGPT account even though the old CLI prints a cached login status. Windows ChatGPT authentication works. A fresh official device sign-in was requested; credentials were not copied. Verify `subscription_writer.account_snapshot` after sign-in before relying on unattended ChatGPT execution. Then install/enable the committed `blog/systemd/smn-subscription-daily.{service,timer}` and replace the old Codex heartbeat's article orchestration with compact status monitoring to prevent duplicate work. Neither scheduler was changed in this implementation. Do not silently fall back to Claude or API.
- Installed `/usr/local/bin/smn-daily` sets the dedicated CLI paths and uses `/opt/smn-daily/bin/git` to run Git as flask; CLIs use their existing root subscription sessions. The source checkout is flask-owned. Rollback of this new standalone controller is to stop using its command and remove the `current` symlink only after verifying it still targets this release. No previous controller pointer existed; previous publishing/dashboard code, articles and scheduler remain intact. Future source updates must keep this controller current with SMN main before publication (publisher rejects source drift).

## Goal

### September26 dashboard generation and cost reporting claim

Codex session `smn-dashboard-generation-20260926`, claimed 2026-09-26T17:45Z. Owner authorized updating the Dev dashboard first, then running a Claude comparison today and showing receipt-based usage and cost in the dashboard. SMN main/live Dev is `3f78e502ab00f90a06c78707e29a24f45e316472`; source pointer `/opt/smn-daily/current` targets its versioned release. The existing `/etc/systemd/system/pub_dashboard.service` is retained; `/etc/systemd/system/pub_dashboard.service.d/20-generation.conf` sets `WorkingDirectory=/opt/smn-daily/current/blog`, `SMN_DAILY_STATE_ROOT=/var/lib/tradewave/smn-daily`, and `PYTHONDONTWRITEBYTECODE=1`. The service stays on private LAN port 7172 with its original auth configuration; public dashboard routing/SSO was not enabled. Git branch/worktree for the application: `codex/smn-dashboard-generation-20260926`, `TradeWave Main Orchestrator/smn-provider-switch-20260926`. Shared record branch/worktree: `codex/smn-provider-switch-record-20260926`, `smn-provider-switch-record-20260926`.

The Generation panel persists Claude or ChatGPT/Codex subscription selection for **new** editions. Claude API and OpenAI API appear as unavailable until real adapters are configured; neither maps silently to subscription execution. The dashboard lists discovered daily/comparison runs and receipt-derived token usage and CLI-reported list-price API-equivalent USD by article/job, stage and model. Missing usage is visible. It is not a subscription invoice, and coordination/batch overhead is separate or unknown. JSON and job CSV export plus reviewed article previews use the existing dashboard auth; profile writes require the dashboard header and same-origin check. Preview serves only a finalized, bound, visually passed article and whitelisted assets under a sandbox CSP. No arbitrary prompts, logs or source paths are exposed.

The initial dashboard source `3f78e502` passed 69 Linux tests, a rendered browser save/reload of Claude selection, and live `GET /api/generation/settings`, `/api/generation/runs`, and `/api/generation/runs/2026-09-25?kind=daily` contracts. The Friday September25 cost table showed `$3.4645` reported API-equivalent usage. The follow-up `ea90f9b` passed 10 focused Linux cost/dashboard tests; the final mobile table repair `77bf346` passed three focused Linux dashboard tests and JavaScript syntax checking. A narrow browser layout check found a 250px container with an 861px horizontally scrolling table and readable one-line headers; the rendered report retained its exact totals and preview links. The screenshot tool returned a blank capture while the Codex tab was not foreground, so the geometry and rendered DOM are the mobile evidence. Main, active source pointer and fetched release HEAD all match `77bf346`; the release tree is clean, `pub_dashboard` is active from `/opt/smn-daily/current/blog`, and the Dev lock was released.

The saved Claude subscription login (`claude.ai` Pro) was verified. The private comparison `2026-09-26-claude` used September25 production subjects with publication disabled and exited at 2026-09-26T18:24:53Z. F, VIX, CPRT, XLF and APH passed editorial, layout, hero and visual checks and have gated dashboard previews. AAPL was held before writing because its engine full-sample evidence did not match; no AAPL preview was approved. Metadata says `ready_to_publish` in `private_preview` mode for the five completed articles, while `publication_status` is `held` for the six-subject set. **No publication receipt or landing job exists; the Friday live edition and Monday publication path were untouched.** The original VIX hold was archived under `recovery/`, and the active root `HOLD.json` is absent after its successful resumption.

The run used 38 of the 40 allowed model jobs, including six retries or repair attempts. CLI receipts covered all 38 jobs and summed to **$4.6627624 reported list-price API-equivalent USD**; the six retries accounted for $1.0331816. Per-article equivalents: F $1.1476148, CPRT $0.9675012, XLF $0.8011754, VIX $0.7881688, APH $0.6936306, and held AAPL $0.2646716. These are receipt estimates, not the subscription invoice or cash charged. Coordination usage has partial scope and is separate from article totals; external tool fees are not independently itemized. No new image API call was made. The dashboard reports the complete/held state with five preview links and no obsolete VIX hold reason. Production, scheduler cutover, paid API use, paywall and unrelated article work remain outside this Dev checkpoint.

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
- 2026-09-24T22:00Z, Claude: owner said "build it, for Dev first". Phase 1 built on SMN branch `claude/smn-claude-writer-20260925` (`ae43fda`, not on main): `smn_daily.py` script workflow, `smn_models.json` role settings (claude/codex per role), `smn_research.py` (tool-less research from production's saved news; code checks URLs, verbatim quotes, values, and the sign of reported changes), `smn_visual.py` (tool-less Haiku screenshot, hero-text and landing checks), inline-image Claude jobs. 609 tests; only the 4 pre-existing `test_editorial_comparison` errors. End-to-end replay of September23 HPQ (no publication): 9 jobs in about 5 minutes (research x2, write, repair, review, repair, re-review, visual, hero). Findings: (a) my first number check rejected a correct -16 because the quote says "16%", and the retry flipped the value to +16. Fixed by comparing absolute values and requiring the sign to match "fell/rose". (b) The Sonnet-low re-review saw the +16 sign problem but rated it minor and passed. A code check now blocks it before writing. (c) The hero check flagged the September24 COSTCO hero ("MARKELL" instead of "WHOLESALE"); the owner confirmed it is bad. Research from production's saved news is narrower than Codex's live web research (it missed Cintas's own FY26 release). Codex review requested before main.

## September26 provider-switch implementation claim

Codex, 2026-09-26: owner explicitly requests a ChatGPT version of Claude's economical script workflow, Astra writer at **high** (not xhigh), and the ability to switch between Claude and ChatGPT generation. Claim: selectable provider profiles, subscription adapters, all-stage budget enforcement, safe resume/provenance, focused tests and Dev-only operational integration. SMN branch `codex/smn-provider-switch-20260926`, Windows worktree `TradeWave Main Orchestrator/smn-provider-switch-20260926`. Preserve Claude's configured roles and all financial/content/visual/publication gates. No production writes, campaigns or paid API fallback. Routine implementation delegated to a Sol agent; parent owns integration and runtime verification. The owner instruction is the authority for Astra High; no peer agreement is invented. Existing dashboard/SSO and flat-year production fixes remain separate. Next: inspect adapter/runtime capabilities and implement the smallest working switch, then verify both profiles and a bounded retained-input smoke.

## September28 Phase 3 production shadow installed (owner instruction)

Claude, 2026-09-28T15:45Z: the owner said "prod shadow ... create the shadow on production now and turn it on". This skips the Phase 1-2 exit gates by owner decision. The shadow writes and checks on production and **never publishes**; the API pipeline still publishes. Live code in `/home/flask` was not changed (so `smn_deploy.sh` was not used).

- Code: SMN branch `claude/smn-prod-shadow-20260928` (`a19ed79`, not pushed, copied to prod as a git bundle) at `/opt/smn-shadow/SMN`. It is built on the other Claude thread's unpushed fixes `59ddc87` (capture only daily articles, 1-6 allowed), `69eb390` (drop stale sources), `db896e1` (millions/billions quote match). New: `32e6b1a` `SMN_CAPTURE_LOCAL=1` reads production locally; `a19ed79` a research/source failure holds only that article, not the edition, and discovery is told nasdaq.com blocks the fetcher.
- Runtime: `smn-shadow.timer` at 04:30 and 06:00 UTC -> `smn-shadow.service` (oneshot, flock, Nice 15, idle I/O) -> `/opt/smn-shadow/run.sh` -> `smn_daily.py --profile claude --max-jobs 40` (no `--publish`). Evidence: `/var/lib/tradewave/smn-daily/prod-shadow/<date>/`. Node v20.19.4 tarball at `/opt/smn-shadow/node`, Playwright 1.63 at `/opt/smn-playwright` (+ apt Chromium deps, 71 new packages, none upgraded). Existing prod Claude CLI login (2.1.282) works.
- Engine access: prod key `/root/.ssh/smn_shadow_engine` is authorized on the engine host 194.113.195.141 with `restrict,command="/usr/local/bin/smn_engine_export_forced"`; it can run only a pinned copy of `tradewave_engine_export.py` (`/usr/local/lib/smn-shadow/`). If the exporter changes in SMN, recopy it.
- Prod host limits: 1 CPU, 961 MB RAM. Jobs run one at a time.
- First run (2026-09-28, 5 daily articles): capture and engine export passed; held at primary discovery for MCD (nasdaq.com timeouts, SEC exhibits without a visible date). Same nasdaq/SEC results from Dev, so not a prod network issue. Fixed by `a19ed79`; resumed.
- Weekly Claude meter was 90% during the Dev run on the same day; a limit hit holds the shadow day and does not affect production.
- Off switch: `systemctl disable --now smn-shadow.timer` on prod.
- Live production bug seen by the other thread: QQQ failed today at `research_tavily` (HTTP 400, `*` wildcard in `include_domains` with topic `news`), so prod made 5 articles, not 6. Not fixed here.

Next: 5 shadow days; owner compares styles. Codex review of `a19ed79` and the forced-command engine key requested.
- 2026-09-28T16:35Z, Claude: shadow branch rebased onto SMN main `11baa39`, now `51e039d` on prod. Two research false holds fixed (owner: "figure this out - it has to be part of the overall check"): (1) XLK quotes were exact, but the release wraps mid-sentence and uses no-break spaces; the verbatim check collapses whitespace on both sides. (2) MCD SEC exhibits carry no printed date; the date check also accepts EDGAR's filing-index "Filing Date" (the wrong-date 10-Q, 08-04 claimed vs 08-07 filed, is still held). New `daily-check.json`: every captured article must pass; any held article fails the day (exit 3). Zero-cost replay on the real Sept 28 evidence: XLK 0 problems (was 2), MCD 2 accepted pages (was 1). Full suite: same 17 pre-existing import/env errors before and after; 2 new tests pass. Prod safety drop-in: CPUWeight=10, MemoryHigh=450M, MemoryMax=600M, MemorySwapMax=300M. First run measured ldavg-1 max 0.20, memory max 34%. Codex review requested.
