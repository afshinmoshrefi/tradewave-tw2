# TW-BUG-0034: SMN missing daily hero images

- Status: verified on production; P1; reproduced and repaired 2026-10-15.
- Owner: Codex, session 01a14002-8375-7632-a953-941939d35b99; claim 2026-10-15 UTC.
- Authorization: Afshin explicitly requested diagnosis and repair of missing SMN hero images. Scope includes production repair of this defect only; no mail, facts, studies or model configuration changes.
- Scope: subscription input hero selection, approved archive, decorative recovery for nine live October 14/15 articles, and focused verification. Worktree C:/Users/afshin/Documents/smn-hero-record-20261015; code branch codex/smn-hero-repair-20261015.
- Confirmed cause: live release 94023f7 calls prepare_heroes(nonessential_fallback=True), which only searches a short inspected archive; unlisted symbols get a placeholder and hero_status unavailable. The nine affected symbols are GC, SPY, QQQ, AMZN, NVDA, MSFT, ASML, OZK, SPX.
- Next: inspect existing same-symbol artwork, preserve immutable source receipts, restore through decorative derivative publication, make future input handling reliable. Back up changes; preserve locks and unrelated state. Tests and deployment pending.

## Verified recovery - 2026-10-15

Afshin confirmed: "yes fresh is the way its been for ever". Fresh generation is the intended behavior; the archive-only change was a regression, not an owner preference.

Production source is now `2b0075c85e45d8cd547c95b8868f8560532cf86b`, pushed as `codex/smn-hero-repair-20261015` in SMN, based on the actual production `94023f7` (production and Dev/main have divergent histories; do not replace either with the other). Two code changes: `subscription_inputs.py` always attempts normal fresh generation before optional failure handling; `decorative_hero_reuse.py` also accepts freshly generated, hash-bound and visually inspected decorative derivatives. Existing original article JSON/HTML, approvals and TradeWave charts remain unchanged. Three test files exercise success, fallback, tamper detection and unchanged factual content.

51 focused tests passed on Windows Python 3.12 and production Linux Python 3.12. All nine fresh images were generated with the established production workflow and passed its text check plus visual inspection. No archive image was used for this repair. A separate built-in OZK draft was unused. Original result hashes verified unchanged after publication.

Production published through the existing continuity transaction and browser verification path: October 14 (GC/SPY/QQQ/AMZN/NVDA/MSFT), 12 desktop/mobile article layouts and 221 public files; October 15 (ASML/OZK/SPX), 6 layouts and 158 public files. Both receipts live_verified. Public posts.json confirms 9/9 available; desktop/mobile homepage screenshots inspected. No email or article-writing jobs invoked by the repair scripts.

Evidence: production `/var/lib/tradewave/release-state/smn-hero-repair-20261015/COMPLETE.json`, `code-activation.json`, backup activation config and service units. Publication records `smn-production-2026-10-14-d3f519624249c72a` and `smn-production-2026-10-15-c04456a13bbf63a7`. Local evidence and executable recovery scripts: `C:/Users/afshin/Documents/ChatGPT/Seasonal Market News/artifacts/`. Code worktree clean at the pushed SHA. Production current symlink, activation config and scheduled service paths point to that SHA; timers restored to their prior states.

Recovery details: initial activation encountered an empty file lock created by this repair's code-switch script where the installer expects a directory. Removed only that attributable empty file after its advisory lock was released. A concurrently prepared October 15 transaction became stale after October 14 catalog replacement; preserved/cancelled before activation, then published a fresh second attempt. No live content rollback or lock theft occurred.

Rollback code: restore activation config and the two unit backups from the record, restore current symlink to `94023f7d75cc5a96d4d2f81b1073eaa9d3fcf0df`, daemon-reload under the production directory activation lock with scheduled writers idle. This would restore the defective fresh-generation behavior; use only for an actual new regression. Public image transactions have their own retained backups. Future production source refreshes must carry `2b0075c`; Dev was not changed. Genuine provider failures still follow existing bounded fallback policy; this repair removes unconditional generation skipping.

Status: verified on production. Claim released. No remaining work for the reported missing-image incident.

