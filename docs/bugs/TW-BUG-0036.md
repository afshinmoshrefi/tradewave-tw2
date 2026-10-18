# TW-BUG-0036: Historical dividend adjustment consistency across daily updates

- Status: open
- Confidence: suspected numerical impact; append-only update mechanism reproduced in source
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
