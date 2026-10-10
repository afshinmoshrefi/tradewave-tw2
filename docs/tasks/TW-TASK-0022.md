# TW-TASK-0022: SMN per-article open access (no reader login)

- Status: in-progress
- Executor/session/claim time: Claude Code (Opus 5.5), session `d880358d-1dfd-42a2-ac0e-d539d1fa6517`; claimed 2026-10-09 UTC
- Authorization: Afshin, 2026-10-09: remove the reader login requirement for the manual opinion article "Two clocks, one date: bullish until July 2027, then cautious" (slug `two-clocks-one-date-bullish-until-july-2027-then-cautious`) so it is fully public when pushed to production. Dev development and Dev activation only. Production is read-only and is not touched by this task.
- SMN branch/worktree: `claude/smn-open-access-20261009`, `/opt/smn-worktrees/smn-open-access-20261009` on .180, from SMN main `2bb0221`.
- Record branch/worktree: `claude/smn-open-access-record-20261009`, `/home/tradewave-worktrees/smn-open-access-record-20261009` on .176.

## Goal, Scope and Acceptance

Add an explicit per-article access setting to the SMN membership system. `access: "open"` on a catalog post makes its immutable revision open: the reader serves the complete article and its assets to anonymous visitors. Default (`members` or absent) keeps today's gated behavior, and existing revision identities stay unchanged.

Files: `blog/article_content_store.py` (manifest flag), `blog/membership_publication.py` (carry the post field into the revision), `blog/reader_app.py` (serve open revisions and their assets without entitlement), `blog/pub_dashboard.py` (writable, validated `access` field), focused tests.

Acceptance: an anonymous request returns the full Two clocks article and all 7 of its assets on Dev; a gated article still returns only its preview and 403 for protected assets; existing focused reader, content-store, publication and dashboard tests pass.

Exclusions: no change to `can_read`, the central authority, offers/billing, other articles' previews, TradeWave engine math or production. TW-TASK-0018 owns the membership system; this is a narrow linked addition. Review request to the TW-TASK-0018 owner (Codex): please review the open-access flag design. Status `awaiting-peer`; not a hold.

## History

- 2026-10-09: Claimed before SMN source edits. Next: implement and test in the SMN worktree, integrate to SMN main, activate on Dev under `dev-activation.lock`, set the article to open and verify anonymously.
