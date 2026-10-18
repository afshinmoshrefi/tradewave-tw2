# TW-BUG-0036: Historical dividend adjustment consistency across daily updates

- Status: open
- Confidence: reproduced on Dev IBM; MSFT/AAPL checked ranges match current provider
- Priority: P2, historical returns may mix adjustment vintages
- Observed: 2026-10-18 UTC, Codex chat 01a15066-8f6d-7cd0-85bb-60db37f39af4
- Authorization: inspection and recording during TW-TASK-0025. No existing-engine/data repair authorized by this record.

## Evidence
EODHD official EOD documentation says adjusted_close includes splits and dividends:
https://eodhd.com/financial-apis/api-for-historical-data-and-volumes .
Current main d6a4fcc: get_symbol_csv.py:66-70 and data_updater/EOD_downloader3.py:172-180
adjust OHLC and store adjusted_close as close. Existing ChartData4 consumes that close.
Dev flask cron invokes data_updater/update_client2.py from active backend pointer.
update_client2.py:728-734 concatenates new returned rows onto unchanged older rows;
its source-missing recovery also adjusts only the newly retrieved range. No prior-row
adjustment refresh is present in this client path. A separate full-history refresh may
mitigate some symbols; event-level numerical impact is not yet audited.

## Expected / Actual
Expected: a dividend-inclusive return uses one consistent provider adjustment basis
for all historical dates. Actual: append path does not itself prove or maintain that
consistency after subsequent corporate actions. This is not proof that all stored
returns omit dividends. No dividend cash ledger or explicit reinvestment engine was
found in the inspected buy/hold path.

## Scope, Verification and Next Step
No data writes or production changes. TW-TASK-0025 preserves engine values and labels
stored adjusted-price basis without claiming verified DRIP total return. Next authorized
investigation: compare retained adjusted closes around an actual ex-dividend event to a
same-vintage provider export, identify full-refresh cadence and update-server semantics,
then discuss exact engine/data repair with Afshin before applying it. Do not add cash
dividends on top of provider-adjusted prices (double-count risk). No fix claim.

## Read-only investigation, 2026-10-18
Executor Codex chat01a15066-8f6d-7cd0-85bb-60db37f39af4, branch
codex/dividend-audit-20261018, worktree /home/tradewave-worktrees/dividend-audit-20261018.
Authorization: investigate and recommend only. No repair, deployment, new paid service,
engine mathematics change or production writes. Source origin/main3eaf4f4ae0ceb7cce39fb9123b211b5734c81dee;
active backend /home/tradewave-worktrees/buy-hold-across-time-20261018; frontend source
bde909db7f6996e9ba043fcbb4c47524246bd2a8 preserved. Status remains open, not fixed.

### Reproduction and limits
Four bounded provider GETs using the existing configured account: daily EOD for MSFT,
AAPL and IBM, 2019-01-01 through2026-10-16; IBM dividends2026-01-01 through2026-10-16.
No application loader was invoked because it can download/write stale files. CSVs were
read directly; diagnostic engine calls used in-memory frames, not repaired on-disk data.
[Price evidence](evidence/TW-BUG-0036-price-audit.json) retains file hashes, selected
rows and mismatch counts; [engine evidence](evidence/TW-BUG-0036-engine-audit.json)
retains dividend events and outputs of the existing completed_holds/long_return_pct.
Repeat by joining stored US/<symbol>.csv date/close against provider date/adjusted_close;
use absolute price tolerance0.00015 for four-decimal provider rounding. Do not compare
stored close with provider raw close, and do not implement a second return formula.

MSFT and AAPL each match all1,959 compared rows. AAPL's2020-08-28/31 split boundary is
correctly represented in the adjusted series. This is evidence of correct present
samples, not a guarantee for every symbol or older dates. The audit does not establish
which earlier refresh made these files consistent.

IBM differs on1,910 of1,959 rows. Last mismatch is2026-08-07: stored237.28,
provider adjusted235.59, raw237.28. The provider confirms a$1.69 dividend with ex-date
2026-08-10 and payment date2026-09-10. On8/10 both series close236.31. Existing engine
long_return_pct therefore returns-0.41% from stored inputs versus+0.31% from the
same-vintage provider inputs. The8/7 stored adjustment factor is1; later rows match.
This reproduces a missing historical dividend adjustment across the event boundary.

Existing completed_holds outputs (same engine, same dates/horizon):
| IBM purchase / exit | Stored | Current provider inputs |
|---|---:|---:|
|2025-10-16 /2026-10-16,1year|-14.31%, $856.90|-13.70%, $863.00|
|2020-10-16 /2026-10-16,6years|143.75%, $2,437.50|145.72%, $2,457.20|
|2025-08-07 /2026-08-07,1year|-2.72%, $972.80|-2.72%, $972.80|
The last case demonstrates that a common missing multiplier can cancel when both
endpoints precede the event. Not every historical return changes. The six-year
difference may include additional earlier provider revisions; do not attribute its
entire difference solely to the August2026 dividend. No market-wide error rate or
production impact was measured; three symbols are a diagnostic sample, not a census.

### Cause and paths
- get_symbol_csv.py:28-62 requests daily full EOD with no date bounds; :65-72 scales
  OHLC by adjusted_close/raw close and stores adjusted_close as close plus adj_factor.
  Raw close is not retained as a separate field. :137-168 considers last-date freshness
  sufficient; :178-215 downloads/adjusts/trims missing or stale histories. A current
  last row can thus conceal stale corporate-action adjustments. Full refresh here
  can incidentally repair a file, but is not a corporate-action consistency check.
- buy_hold_across_time.py:22-64 consumes that close and the shared engine return helper;
  appserver.py:9133-9135 wires get_symbol_csv. No dividend ledger or extra cash addition.
- update_client2.py:624-651 requests only after local last_date; :728-734 concatenates
  those rows. Source-missing recovery :495-520 is BRK-B-specific and also tail-only.
- update_server.py:36-58 returns source rows with date>last_date. Even a freshly
  re-adjusted upstream history cannot revise the client's old rows through this contract.
  Deployed upstream host contents/cadence were not inspected; this is repository source.
- Live Dev flask cron runs active-backend data_updater/update_client2.py at5 3-5 * * 2-6
  (installer ops/install_eod_cron.sh:9-20,40). No installed full-history job found.
- EOD_downloader3.py:426-441 skips same-day files; :452-495 bulk path appends;
  :504-525 sequential path replaces full adjusted history. Running this script blindly
  is not a guaranteed, atomic corporate-action repair.

### Meaning of dividend-inclusive
[EODHD EOD contract](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
separates raw OHLC from split/dividend adjusted_close, with split-adjusted volume.
It advises full-series redownload when adjustments change. Use consistent adjusted
close for this view; switching to raw close or split-only OHLC loses dividends.
For other engine consumers, refresh all adjusted OHLC and factor fields together,
not close alone. Do not double-adjust volume.

[EODHD adjustment method](https://eodhd.com/financial-academy/financial-faq/adjusted-close-and-close-whats-the-difference)
uses a backward factor based on the pre-ex-date close less the distribution, with
four-decimal adjusted prices. This supports the precisely labelled provider-adjusted,
dividend-inclusive return. It does not establish an exact brokerage DRIP account:
payment-date reinvestment price, fractional shares, taxes and fees are not modelled.
That alternative requires an explicit owner-approved engine contract and event ledger.
Adding dividend cash to these already adjusted prices would double count.

### Smallest correct repair recommendation, not implemented
1. Preserve the engine formula and calendar-year exit rules. Correct data maintenance.
   For a bounded Dev pilot, download full IBM history into a separate candidate,
   apply the existing adjust/trim contract, retain response provenance/hash, validate
   and atomically replace the complete per-symbol file under a lock shared by every
   writer. Never append a new adjustment basis to old rows. Keep the original file.
2. Make the normal equity updater revision-aware: obtain one validated full adjusted
   snapshot per affected symbol after a corporate action; extend server/client protocol
   to deliver explicit full replacement plus revision, or fetch that snapshot directly
   from EODHD. The upstream snapshot must itself be provider-current. Retain cheap tail
   updates only when adjustment basis is verified unchanged. Include reconciliation for
   late/corrected events; a dividend calendar alone cannot guarantee correction coverage.
   Compare overlapping factor/raw data as a refresh trigger, not as a provider-error claim.
3. Inventory the supported US-stock universe, deduplicate CSVs shared by groups0..4,
   and establish a full-history baseline for files lacking trustworthy vintage provenance.
   A short tail repair cannot fix older dates; audit/replace whole retained histories
   where needed. Do not expand automatically into futures, custom LBR or other markets.
   The two clean samples need no immediate numeric change, but need ongoing protection.
4. Tie downstream cached analyses/readiness to the data revision and regenerate only
   affected derived artifacts. Preserve historical receipts rather than silently rewriting
   past published results. Identify consumers before broad repair because these CSVs are
   shared with ChartData4 and other analyses, not just the new historical view.

Acceptance: reproduce IBM before/after using existing engine outputs above; both sides
of dividend boundaries, holds entirely before/after, and long horizons; no-dividend
control; AAPL split fixture; all adjusted OHLC/factors on one vintage; date coverage,
unique ordered dates, positive finite closes, completed-session cutoff and unchanged
trim/date rules. Test concurrent reader/writer, provider failure/partial response,
late correction, duplicate retry and atomic rollback. Check live Dev tooltips against
engine receipt plus original Buy & Hold; no client financial recalculation.

Cost: four provider reads in this investigation. Published accounting is one call per
EOD or dividend request; no new service or purchase. A baseline is approximately one
EOD request per unique symbol plus event checks/retries, with history bandwidth and
runtime. Actual universe count/account quota/upstream availability remain to be bounded
before approval; they were not audited here.

Rollback/boundaries: versioned backup and manifest per CSV; switch files/revision back
atomically with derived-cache invalidation, preserve prior code and readiness marker.
Pilot is Dev only after explicit repair authorization; staging qualification and
human-operated production data/code rollout remain separate. No runtime/data writes
occurred in this investigation; only shared documentation/evidence updated.
Next: approve a bounded Dev IBM repair plus updater consistency fix, then quantify the
broader baseline before authorizing a market-wide refresh. Documentation commit is
identified by git log -1 -- docs/bugs/TW-BUG-0036.md.
