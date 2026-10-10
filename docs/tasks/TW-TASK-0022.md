# TW-TASK-0022: SMN articles open by default, with a per-article members lock

- Status: verified on dev
- Executor/session/claim time: Claude Code (Opus 5.5), session `d880358d-1dfd-42a2-ac0e-d539d1fa6517`; claimed 2026-10-09 UTC
- Authorization: Afshin, 2026-10-09. First: remove the reader login requirement for the manual opinion article "Two clocks, one date: bullish until July 2027, then cautious" (slug `two-clocks-one-date-bullish-until-july-2027-then-cautious`). Then widened: "I want all the logins removed, not everything needs login"; chosen option "every article is free to read with no login, keep a switch to make a specific article members-only later". Dev development and Dev activation only. Production is read-only and is not touched by this task.
- SMN branch/worktree: `claude/smn-open-access-20261009`, `/opt/smn-worktrees/smn-open-access-20261009` on .180, from SMN main `2bb0221`.
- Record branch/worktree: `claude/smn-open-access-record-20261009`, `/home/tradewave-worktrees/smn-open-access-record-20261009` on .176.

## Goal, Scope and Acceptance

Owner product decision: complete SMN articles are readable without reader login. A post may be locked with `access: "members"`; that lock is part of the immutable revision. Absent or `open` means open, so all existing revision ids and manifest bytes are unchanged and all 705+ migrated revisions become readable once the reader runs this code.

Files: `blog/article_content_store.py` (`is_open`, members lock in the manifest), `blog/membership_publication.py` (post `access` into revision identity and manifest), `blog/reader_app.py` (open revisions and their assets served without entitlement; locked ones keep the existing preview/403 path), `blog/pub_dashboard.py` (validated, writable `access`), `blog/membership_migrate.py` (policy text), focused tests.

Acceptance: anonymous requests return the full Two clocks article and all 7 assets on Dev, and a sampled generated edition article in full; a members-locked revision keeps the preview and 403 asset behavior (tests); focused reader, content-store, publication, dashboard, membership and migration suites pass.

Unchanged: reader sign-in, accounts, `can_read`, the central authority, offers/billing records, previews, TradeWave engine math and production. Distribution copy that says "Register to read the complete article" (public_derivative/membership panel) is not changed here and is now inaccurate for open articles; follow-up.

Peer note to the TW-TASK-0018 owner (Codex): this reverses that task's default gate on Afshin's instruction. Please review the flag design and any downstream assumptions of gating (status `awaiting-peer`; not a hold).

## Implementation and Handoff

SMN commit `dc0d3d6` (parent `2bb0221`) is on branch `claude/smn-open-access-20261009` and fast-forwarded onto SMN main. Changed: `article_content_store.py`, `membership_publication.py`, `reader_app.py`, `pub_dashboard.py`, `membership_migrate.py` and the reader, content-store, publication and dashboard tests. 191 focused tests passed on .180 with `venv-smn-membership-20261003` (content store, reader app/auth/promise, membership publication/transactions/runtime/dashboard/pipeline, publication dashboard, and the present migration/derivative suites).

Dev activation under `dev-activation.lock`, with origin/main re-fetched first: new drop-ins `smn-reader.service.d/80-open-access.conf` and `pub_dashboard.service.d/80-open-access.conf` set the working directory to `/opt/smn-worktrees/smn-open-access-20261009/blog`, and `/opt/smn-daily/current` points to the same tree. Both services are active and their health checks return 200. Other services (blog_queue, article_processor, promotion) are unchanged; their code writes no `access` key, which reads as open.

Live anonymous smoke (no cookies): Two clocks went from a 3,936-byte preview to the 31,537-byte full article with its AI disclosure and 7/7 assets 200; MSFT edition and the Sept. 27 SPX article are served in full, with MSFT 5/5 assets 200. Main, the live HEAD and the clean tree are in parity; lock released. Receipt: `/var/tmp/smn-open-access-dev-dc0d3d6/proof.json` on .180 (before.txt alongside).

Rollback: remove both `80-open-access.conf` drop-ins, point `/opt/smn-daily/current` back to `/opt/smn-worktrees/smn-chart-identity-2bb0221`, `daemon-reload`, restart `smn-reader` and `pub_dashboard`; revert `dc0d3d6` on main if needed.

Not verified: a members-locked article live on Dev (none exists; covered by tests). Follow-ups: distribution/preview copy that invites registration to read the complete article; production launch of the reader must ship this code. Production unchanged.

## History

- 2026-10-09: Claimed for the single article before SMN source edits.
- 2026-10-09: Scope widened by Afshin to open-by-default with a per-article members lock. 191 focused tests pass on the candidate.
- 2026-10-10 03:24 UTC (server clock): lock acquired, `dc0d3d6` activated on Dev, anonymous smoke passed, main advanced without force, parity proven, lock released. Status: verified on dev.
