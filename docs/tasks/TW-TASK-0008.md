# TW-TASK-0008: SMN publishing dashboard (pins, order, publish/unpublish, schedule, hero) and portfolio fixes

- Status: verified on dev
- Confidence: reproduced (live tests on SMN dev, 52 unit tests)
- Priority: P2. Owner-requested editorial control of the SMN home page and publication; fixes two defects in the portfolio Publish Article dialog.
- First observed / last updated: 2026-09-23T23:50Z / 2026-09-25T00:30Z
- Executor/session/claim time: Claude Code (Opus 5.5), desktop session on SMN dev box smn-dev-180, 2026-09-23T23:50Z
- Authorization: the owner (Afshin) asked for the dashboard, its install on SMN dev, and the commit on 2026-09-24. SMN production deploy was not authorized and not done. The TradeWave repo change was not shipped (the owner chose to wait).

## Goal, Scope and Acceptance

The owner asked for an SMN publishing dashboard. It must:

1. List articles with written date, published date, pattern start, pattern end and length. The list can be filtered by each of these.
2. Pin an article to a home-page position until a date or for N days. After that it drops back to its own slot, or it is treated as just published.
3. Add, edit and delete raw-HTML articles. It must be agent-friendly: a JSON API, `/llms.txt`, `/openapi.json`, and an X-Actor audit log. There is no login yet.
4. Preview the hero image (icon, hover, click) and recreate it. It must reuse the existing blog_queue hero mode ("don't reinvent the wheel").
5. Publish and unpublish articles, and move an article to a fixed place in the home-page list.
6. Schedule a publish or an unpublish, with shortcuts (for example tomorrow 7 AM) and the scheduler's user id. An unpublished article with no schedule stays unpublished. New articles still publish at once by default.
7. Fix the defects this work found in the portfolio Publish Article dialog.

Out of scope: login, SMN production deploy, and TradeWave home-page pinning.

## Evidence and Investigation

- `publish_status` in posts.json is written but never read by any page. "Live" means "listed in posts.json". Unpublish therefore removes the entry: it moves the HTML to `/var/lib/smn-dashboard/unpublished/`, and removes Redis, search-index, sitemap, RSS and llms.txt entries. Publish restores all of these.
- A full site refresh (home, sitemaps, RSS, llms.txt) takes about 58s. blog_queue's gunicorn times out after 30s. Refreshes are now queued in the background and coalesced; the every-minute timer finishes any that are left pending.
- **Rec Hero defect.** blog_queue `article_prompt` hero mode called `hero_image_workflow` without `article_id`. So it wrote `hero_<SYM>.jpg`, but 476 of 674 standard articles show `hero_<SYM>_<id>.jpg`. The button reported success and the visible image did not change. It is fixed: the route reuses the id, and it accepts `?article_id=` / `?article_id=none`. A fake-image run over all 674 articles hit the right file each time.
- **Portfolio Delete defect.** One pattern can have several articles (123 patterns, 329 articles). The dialog shows the pattern's Redis entry, but `delete_article_web` deleted the first posts.json match, which is the oldest. It also deleted the pattern's Redis key, and it would delete the pattern's shared chart images (today a no-op: `article_images_root` is unset).
- **Portfolio publish icon defect.** It was rendered from local state only. It started red ("unpublished") for every article and saved nothing.
- Wire home template slots: #1 lead, #2-6 headlines, #7-8 large cards, #9-11 small cards, #12+ list. The HTML order differs from the list order. The dashboard order view uses rebuild_news_home's own pipeline, so it matches the list order exactly.

## Acceptance and Regression Checks

- `python -m unittest tests.test_pub_dashboard tests.test_delete_article_web tests.test_portfolio_publish_state` (from `blog/`, SMN venv): 52 tests, OK.
- Live on SMN dev, with throwaway articles only:
  - create, unpublish (URL file gone), publish (back), move, release, delete: nothing left in posts.json, Redis, search_index, sitemap, RSS or llms.txt.
  - A scheduled publish ran 7s after its due time.
  - The portfolio route through blog_queue answered in 0.1-1.5s, and the audit recorded `tw2-user-999`.
- Not run: a browser-rendered check of the dashboard UI (JS parse only); a real paid Rec Hero regeneration; TradeWave React build and appserver tests.

## Implementation and Handoff

- SMN repo `afshinmoshrefi/SMN`, branch `claude/publishing-dashboard-20260924`, commit `e269a9d79a8cd9464bf162b4b4630239333c944d` (pushed; based on origin/main `c7e5615`). Not merged to main.
- New: `blog/pub_dashboard.py`, `article_index.py`, `pin_store.py`, `schedule_store.py`, `pin_sweeper.py`, `templates/pub_dashboard.html`, `install_pub_dashboard.sh` (has `--rollback`), `systemd/pub_dashboard*.{service,timer}` (force-added; `blog/*` is gitignored), and 3 test files.
- Changed:
  - `rebuild_news_home.py`: apply pins; never fatal.
  - `blog_queue.py`: hero id fix; `article_publish_state_bq` GET/POST; delete passes an optional slug.
  - `publish_article.py`: `delete_article_web` target fix, sibling-safe cleanup, listing refresh.
- Runtime on SMN dev: service `pub_dashboard` (gunicorn on 127.0.0.1:7172 and 192.168.1.180:7172, LAN only), and timer `pub_dashboard_sweep.timer` (every minute). State is in `/var/lib/smn-dashboard`.
- TradeWave side (not committed or pushed): worktree `/root/tw2-worktrees/portfolio-publish-state-20260924` on smn-dev-180, branch `claude/portfolio-publish-state-20260924`, based on `927f3c0`.
  - It adds appserver `/article_publish_state/...` (GET/POST proxy to blog_queue).
  - It makes the React icon show and toggle the real state. The icon stays hidden until the state is known.
  - Hold it until SMN prod has the dashboard: a prod blog_queue without it returns 503, so the icon stays hidden.
- Risks:
  - No authentication: the dashboard is LAN-only. Login is the owner's next step.
  - Moves are pins with no end date, so held articles stay in their slots until released.
- Rollback: `bash install_pub_dashboard.sh --rollback` restores the backed-up blog_queue/publish_article/rebuild_news_home and removes the units. Dashboard state is kept.
- Next action: owner review, then merge to SMN main and deploy to prod through `smn_deploy.sh` (add the new files and units), then ship the TradeWave branch, then add login.

## Environment Verification

Dev (SMN smn-dev-180): verified 2026-09-24T11:25Z at `e269a9d`, executor Claude. The owner ran the install script. The live files match the commit, and blog_queue, pub_dashboard and the timer are active. Health: 680 articles. Staging: not applicable. Production: not deployed.

## History

- 2026-09-23T23:50Z Claude: dashboard requested; built and live-tested on dev in stages (list/pins, hero, publish/unpublish/move, schedule).
- 2026-09-24T11:10Z Claude: found and fixed the Rec Hero file mismatch, the portfolio Delete target, and the 58s synchronous refresh.
- 2026-09-24T11:40Z Claude: committed and pushed `e269a9d`; TradeWave icon change held on a local branch by the owner's choice.

## Codex integration finding - September24
The owner authorized the daily automation repair and today's six improved articles. SMN main057e87f adds a separate primary .180 Dev publisher; it preserves this dashboard's installed source/template, catalog metadata, pins, schedules and archive. No dashboard code has been replaced. The publisher records runtime helper hashes and serializes posts.lock; changes during preparation trigger re-preparation rather than overwriting peers.

Read-only live preflight found /var/www/smn/posts.json mode0600 root:root. Public /posts.json returned the homepage after nginx's403 redirect, and native browser search could not load results. The new publisher writes public catalog files0644 and preserves native search, so today's publication will restore readability. Please review the dashboard's atomic catalog writer so subsequent dashboard edits do not restore0600. This is a reproduced permission/access issue, not a model disagreement; no fix is claimed for future dashboard writes. The current homepage also had robots index, follow; the Dev publisher sets noindex,nofollow on home/search under the existing Dev-only requirement. Tests passed; today's six article generation/live activation still in progress. Production remains untouched.
- 2026-09-24T12:05Z Claude: owner request - dashboard list opens with pinned articles first (display order), then the rest of the home page in display order. Commit `43de39942e3deedcc1e032738b502622d9e0ede7` on the same branch; 55 tests OK; installed and verified on dev (2 real pins shown first, order matches /api/order).
- 2026-09-25T00:30Z Claude: owner decision: login through TradeWave admins (super_admin); named API keys for agents; public HTTPS address behind login. Built:
  - SMN `8e1a219` (dashboard_auth.py: Ed25519 one-time tickets, env-bound, 8 h session, CSRF header, API keys, blog_queue service key; 68 tests OK).
  - TW branch `claude/smn-dashboard-sso-20260925` `2d3b25e` (web `/smn-dashboard/login`, super_admin only; test written, not run here).
  - TW branch `claude/portfolio-publish-state-20260924` `36eb447` (publish icon; HOLD until SMN prod).

  SMN dev runs `8e1a219` with login OFF, LAN only; `/dashboard/` is closed. Next: generate the dev key pair on tw2-dev (private key stays there), activate the SSO branch on TW dev through the fast dev loop, put the public key on SMN dev, set SMN_DASHBOARD_AUTH=required and SMN_DASHBOARD_PUBLIC=1, then have the owner test the browser login.
