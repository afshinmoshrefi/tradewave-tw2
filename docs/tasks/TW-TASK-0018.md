# TW-TASK-0018: Subscription article chat editor on SMN Dev

- Status: verified on Dev (typed editing); microphone audio not exercised
- Executor/session: Codex smn-chat-editor-20261002
- Claim: 2026-10-02; owner explicitly requested this capability on Dev.
- Scope: SMN article editor, private drafts/revisions, ChatGPT and Claude subscription adapters, preview, undo, dictation and explicit publish update. No production writes, daily generation settings, newsletter changes or paid API fallback.
- Source: SMN codex/smn-chat-editor-20261002 from 5a7d02b; local worktree C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-chat-editor-20261002.
- Shared record branch: codex/smn-chat-editor-record-20261002. Respect TW-TASK-0016 shared-main release freeze; preserve this claim on its branch until freeze disposition permits integration. No overlapping auth or daily generator ownership is claimed.

## Acceptance

Provider buttons above chat; current draft and conversation follow provider switches; typed or browser-supported dictated instructions; rendered preview; undo/version history; only Publish update changes live article. Subscription authentication checked by official CLIs, no paid API fallback. Draft ownership, concurrent-change conflicts and immutable revision checks protect publishing. Preserve TradeWave mathematics and chart scripts. Existing administrator authentication remains authoritative.

## Verification and handoff

SMN main and active dashboard application source: `1663cecd62e0accf9dc9ff52f7c4a2f16e7f2e4f`. Dedicated Dev checkout `/opt/smn-worktrees/smn-chat-editor-final-20261002`, effective `pub_dashboard` WorkingDirectory is its `blog` directory via `/etc/systemd/system/pub_dashboard.service.d/50-article-editor.conf`. Only dashboard restarted; daily generator pointer and production unchanged. The Dev activation lock is released. App source branch is clean and pushed.

Focused Linux checks: 13 editor tests and 44 existing dashboard tests pass. Covers real Flask/Jinja rendering, preview isolation, owner-only access, version conflicts, draft isolation, provider history, failure preservation, publish retry/rollback/interruption recovery, protected figures/scripts/links and metadata injection. UI JS syntax and diff checks pass. Actual Chrome Dev browser opens MSFT October2 article, shows both provider buttons above chat and renders article/charts, switches provider on the same draft, applies revisions and restores the prior version with Undo. Existing daily article bytes were confirmed unchanged; live article publication was not performed during the smoke. Publication is verified with isolated fixture articles through the Flask routes, not a real reader-article publish.

Three completed subscription test jobs: Codex `gpt-6-sol` medium (initial full-output 152.189s; compact replacements 28.741s) and Claude `claude-sonnet-5-5` medium (8.535s). Actual receipts confirm `billing_source=subscription`, `api_fallback=false`. These are individual observations, not latency guarantees. One earlier Claude job failed during a concurrent OAuth refresh; its original draft was preserved and an explicit later retry succeeded. There are no automatic paid fallbacks or automatic failed-job retries.

The editor uses minimal exact HTML replacements, not whole-article regeneration. SQL sessions are owned by the configured administrator; only `SMN_EDITOR_OWNER_USER_ID` may consume this private account's subscriptions. Existing official CLIs and saved authentication remain unmodified. Workers have no publishing tools. Protected chart/script/style blocks are preserved, resource links and numeral counts must remain unchanged. These are structural guards, not a semantic proof of financial claims. New research, changed figures, scripts and styling are outside this editing path. Browser SpeechRecognition provides optional dictation; no paid transcription API. Actual microphone/audio capture remains untested.

On Dev proxy .176 only, `/smn-dashboard/` now has a dedicated security-header include allowing `microphone=(self)`; other routes retain microphone denial and all other security headers. Exact nginx vhost backup and receipt: `/var/lib/tradewave/release-state/smn-editor-microphone-20261002/`. Dashboard source rollback: remove only the recorded `50-article-editor.conf`, daemon-reload and restart `pub_dashboard` to restore the pre-task WorkingDirectory. Preserve drafts under `/var/lib/smn-dashboard/article-editor`; do not delete data during rollback.

Durable Dev evidence: `/var/lib/tradewave/release-state/smn-chat-editor-20261002/receipt.json` and `verification.json`; immutable job receipts below `/var/lib/smn-dashboard/article-editor/jobs/`. Local browser screenshot: `C:/Users/afshin/Documents/ChatGPT/Seasonal Market News/artifacts/smn-chat-editor-dev.png`. First activation was rolled back after a Jinja CSS/comment delimiter error; render regression added and corrected candidate reactivated and verified. No production writes or newsletter sends.

Shared record/architecture updates remain on `codex/smn-chat-editor-record-20261002` because TW-TASK-0016's shared-main freeze has no recorded release. Integrate this exact documentation branch after that freeze is explicitly released. This does not block SMN's independently authorized Dev feature or source-main integration.
