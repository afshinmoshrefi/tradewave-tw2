# TW-BUG-0011: Some Tara Help Questions Miss the Analysis-Menu Reply

- Status: open
- Confidence: reproduced on dev and staging
- Priority: P2; help intent is redirected, but no unsupported chart action or invented result is returned
- First observed / last updated: 2026-09-16T02:00Z / 2026-09-16T02:12Z
- Executor/session: unassigned for implementation; recorded by Codex staging-release-20260915-auth
- Authorization: deployment investigation and documentation only

## User Impact and Reproduction

On release `05ae209ecaba231e5816f835dc133f7c0cdf00e8`, send authenticated
`/chatbot/chat` requests with empty history, wave_viewer and opportunities:

1. `where do i find exclude current range`: actual reply refuses to explain a
   missing validated Exclusion Report rather than giving the menu-help reply.
2. `What can I do in the Analysis menu?`: actual reply is generic research guidance
   rather than the four-action Analysis menu overview.

Both return HTTP 200 and no actions. `Open Compare Symbols.` correctly points to
the Analysis menu and says it cannot open the dialog. Explicitly asking to explain
a missing Exclusion Report correctly refuses to invent unmatched-window results.

## Evidence and Investigation

The isolated `build_analysis_menu_reply` unit tests pass, but those helper results
are not the same as these live dispatcher results. Likely interception by earlier
report/investor-intent routing; exact precedence repair is not diagnosed fully.
[Dev contract receipt](evidence/staging-release-20260915/dev-api-contract.json) and
[staging receipt](evidence/staging-release-20260915/staging-api-contract.json) retain
both failed exploratory expectations as `markers_present: false`, with reply hashes.
They were not mandatory release gates; they are not relabelled as successful help
tests. No application code or reply guard was changed to make them pass.

## Acceptance and Regression Checks

Add full-route tests, not just helper tests, for these exact help questions with
empty and populated valid viewer context. Explain where controls are without claiming
an unsupported UI action. Preserve the guard requiring a validated report for actual
report explanation and do not redirect real symbol comparisons to menu help.

## Implementation and Handoff

No repair. Dev and staging carry the same behavior; promotion was requested to
match dev, not to implement these additional help improvements. Report-only branch
`codex/staging-report-20260915`; application SHA remains `05ae209e`.

## Environment Verification

Dev and staging: matching responses in September 16 authenticated live probes.
Browser conversation with populated report context: not tested. Production: untouched.

## History

- 2026-09-16: Added exploratory probes while qualifying current dev; recorded route/helper
  discrepancy and retained failures explicitly. Implementation requires a separate task.
