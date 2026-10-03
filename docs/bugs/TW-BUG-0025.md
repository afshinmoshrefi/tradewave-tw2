# TW-BUG-0025: SMN article editor loses migrated private images and charts

- Status: verified on dev
- Confidence: reproduced and fixed in the original genuine user Chrome editor; coordinator performed live verification, implementation agent ran focused tests, documentation agent checked retained receipts.
- Priority: P2 - all five Microsoft article images/charts were broken in the edit window.
- Last updated: 2026-10-03T11:01:07.041855+00:00; original claim is retained in Git history `74446f32732f426a747d18cb12740bc952948dfb`.
- Executor/session/claim time: Codex coordinator `/root` and Sol 6.1 implementation agent `/root/membership_builder`; session `01a0ff6b-e439-79a3-9aa3-9d70763f9e85`; claimed 2026-10-03T10:39:44.243605+00:00. `/root/preview_builder` owns this shared record only.
- Authorization: narrow editor preview asset resolution fix and Dev verification. No MSFT draft writes, reader entitlement relaxation, anonymous private assets, financial/math/provider changes or production writes.

## Reproduction and Confirmed Cause

At SMN main/live `2b00e6cbc8ae1ce363fb601cf91a9b0ea1ef6d5b`, user's Chrome tab `333161940` edited MSFT draft `517ef29290284f369147fca49e99f50d`, version 4, for `/editions/2026-10-02/MSFT/article.html`. All five image elements had `naturalWidth=0`: relative references resolved to old `/editions/2026-10-02/MSFT/assets/...` paths intentionally denied after private migration. The editor rendering path lacked private revision-bound asset resolution. Reopening anonymous raw routes would weaken the intended access policy.

## Fix and Regression Verification

SMN pushed/main fix `6f9812d6ad74d9c6d65329c0c3ed91cd95c22bba` changes only `blog/article_editor_routes.py` and `blog/tests/test_editor_private_assets.py`. The owner-only render response embeds verified retained private raster bytes as data URIs. Resolution binds exact canonical/revision/asset SHA/cache-v, including legacy draft-v0 provenance; unresolved/stale/path traversal inputs fail closed. External/data/font references pass through without network fetching or arbitrary filesystem reading. Existing owner authorization, CSP sandbox and no-store remain unchanged; saved draft HTML is not rewritten.

- 32 focused tests passed on Windows and 32 on actual Linux: `test_editor_private_assets`, `test_article_editor`, `test_membership_publication`. Linux used temporary isolated `SMN_DASHBOARD_STATE` and real locks for existing suites; Windows patched only unavailable `posts_lock` platform behavior.
- Original browser editor was closed/reopened with empty input only. All five images decode with positive dimensions; browser SHA256 values match exact private inventory. Original failure is fixed.
- Before/after custody is identical for entire draft state, all five HTML revisions, catalog, private manifest/full HTML and all 14 assets. Draft remains version 4/idle with state SHA256 `90fcb0f69d7d65606a794c3b835073f50d0f503d499148f0c625a1f4146f4317`; zero editor jobs ran.
- Anonymous live local origin (real vhost, no cookies): owner editor preview 401 and old private chart 404. Entitlements/private access remain intact.

## Evidence

Retained local directory: `C:/Users/afshin/Documents/ChatGPT/Seasonal Market News/artifacts/smn-editor-assets-20261003/` contains `editor-before.png`, `editor-after.png`, `browser-images.json`, `before.json`, `after.json`, `activation.json`, `anonymous-origin.json`. Browser image hashes/dimensions, custody comparison and anonymous HTTP checks are inspectable without credentials. Remote receipt directory: `/var/lib/tradewave/release-state/smn-editor-assets-20261003` on .180; authenticated host access is required.

Safe recreation: open this same draft through authenticated dashboard without saving/generating; inspect all image dimensions and hash decoded raster bytes against retained private manifest, compare read-only custody snapshots, then request owner preview and old private chart without cookies. Do not dump private article content or authentication secrets.

## Deployment and Handoff

Dev dashboard `active_verified` at 2026-10-03T10:58:29.985179+00:00, running `/opt/smn-worktrees/smn-editor-assets-20261003/blog`, exact fix/main SHA above. Only `pub_dashboard` restarted. Reader/queue/processor PIDs and `/opt/smn-daily/current` remain at prior `2b00e6c` source; this is a deliberate dashboard-only fix, not an all-service source-parity claim. Coordinator's .180 activation lock is released; prior dashboard unit retained for rollback. No editor publish, model jobs or production deployment.

Implementation branch/worktree: `codex/smn-editor-assets-20261003`, `C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-editor-assets-20261003`, clean/pushed. Shared docs: `codex/smn-editor-assets-bug-20261003`, `C:/Users/afshin/Documents/smn-editor-assets-bug-record-20261003`. Final docs update changes this record, bug index and one ecosystem implementation fact only; identify its accepted commit with `git log -1 -- docs/bugs/TW-BUG-0025.md`.

Next: no code work remains for this reproduction. Preserve draft state and private access; future regressions reopen this same ID with exact source/browser evidence. Related feature [TW-TASK-0018](../tasks/TW-TASK-0018.md) retains its separate provider/media scope.

## Environment Verification and Limits

Dev: original user browser and anonymous local-origin checks verified at exact fix SHA; focused Windows/Linux suites passed. Staging/production: not deployed or checked. Live browser coverage is this original MSFT draft, not every archived article or mobile device; broader resolver cases are focused automated tests.

## History

- Initial claim accepted/refetched on shared main `74446f32732f426a747d18cb12740bc952948dfb`; narrow implementation ownership published before code edits.
- 2026-10-03T10:54:15.949057+00:00: coordinator activated dashboard-only exact fix candidate after focused tests.
- 2026-10-03T10:58:29.985179+00:00: original editor images, byte-identical custody and anonymous denial verified; status changed to verified on Dev. Documentation-only handoff requires no further app activation.
