# TW-BUG-0035: Manual watchlist validation accepts a different ticker

- Status: open
- Priority: P1
- Confidence: reproduced with read-only production API calls and current provider search results
- Owner: Codex chat 01a13f7d-e3a3-7460-aa4e-4a9dae97833f, October 16, 2026
- Authorization: investigate latest CSV follow-up only; no application fixes or deployment.
- Related: TW-BUG-0033; prior exact production release evidence is in records commit 75451fe16b3ebfea10fc6665bec13a0aa048c989.

## Evidence and cause
Production WEB HEAD c8ea5b0ec4e15d2e3eb33ff337f87ac87caf07ce. Used synthetic
Strategist login and GET validation routes only; no customer watchlist reads/writes.
Input AAME,AAN,AAOI,BP,BATS,BFA detects WILSHIRE5000 and accepts first four,
rejecting BATS/BFA. BP remains fixed. BATS alone detects London and is accepted.

Live NameFromTicker/4/BFA returns Bright Horizons Family Solutions Inc. Provider
search BFA returns Code=BFAM, Exchange=US as its first US match, then BFAP/BFACX.
Live NameFromTicker/4/BATS returns Colliers International Group Inc Bats. Provider
search BATS returns exact BATS/LSE (British American Tobacco PLC), followed by
CIGI/US (Colliers International Group Inc Bats). NameFromTicker/12/BATS correctly
returns British American Tobacco PLC. All diagnostic requests returned HTTP200.

appserver/appserver/get_name_from_ticker.py:get_security_name_from_ticker filters
search results by Exchange only and returns the first Name without matching Code.
NameFromTicker caches that name without expiry. WatchlistSettings.js:handleAddSymbol
treats any nonempty name as valid and submits the original typed ticker, so BFA
is stored as BFA while its confirmation displays BFAM's name. It does not substitute
the canonical provider ticker. Existing wrong name-cache entries may outlive a fix.

The BATS duplicate message comes from add_user_watchlist_item finding the literal
BATS string already stored. It does not prove BATS is a valid US symbol or that the
latest CSV imported it. Its insertion time/history and original full CSV are unknown.
A watchlist has one resource/market; majority detection does not make London symbols
valid in a US watchlist. Customer requested comma-separated manual bulk entry as a
separate enhancement; implementation not authorized.

## Next action / acceptance
When repair authorized, use exact ticker+exchange identity for manual validation,
review invalid persistent name caches, and align CSV/manual results without silently
remapping symbols or exchanges. Prove BFA cannot validate as BFAM; BATS/LSE remains
valid and BATS/US cannot validate as CIGI; BP/US still works; duplicate feedback is
distinct from validity. No customer-list cleanup without separately reviewed scope.
No browser reproduction or original customer CSV upload was performed in this audit.
No code changes, restarts, deployments, campaigns, or email replies.
