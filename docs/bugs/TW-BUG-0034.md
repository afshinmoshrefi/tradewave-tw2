# TW-BUG-0034: SMN missing daily hero images

- Status: in-progress; P1; reproduced on production 2026-10-15.
- Owner: Codex, session 01a14002-8375-7632-a953-941939d35b99; claim 2026-10-15 UTC.
- Authorization: Afshin explicitly requested diagnosis and repair of missing SMN hero images. Scope includes production repair of this defect only; no mail, facts, studies or model configuration changes.
- Scope: subscription input hero selection, approved archive, decorative recovery for nine live October 14/15 articles, and focused verification. Worktree C:/Users/afshin/Documents/smn-hero-record-20261015; code branch codex/smn-hero-repair-20261015.
- Confirmed cause: live release 94023f7 calls prepare_heroes(nonessential_fallback=True), which only searches a short inspected archive; unlisted symbols get a placeholder and hero_status unavailable. The nine affected symbols are GC, SPY, QQQ, AMZN, NVDA, MSFT, ASML, OZK, SPX.
- Next: inspect existing same-symbol artwork, preserve immutable source receipts, restore through decorative derivative publication, make future input handling reliable. Back up changes; preserve locks and unrelated state. Tests and deployment pending.
