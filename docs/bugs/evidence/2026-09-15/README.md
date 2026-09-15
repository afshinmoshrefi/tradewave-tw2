# September 15 Audit Evidence

Baseline: dev frontend fce41885ec8fbdc70fabc1fb56bde38c98339396, main.0ee1de72.js. The bug records contain manual reproduction steps and exact inputs. JSON receipts retain engine/chart state and browser observations; screenshots show the user-visible result. Files copied from the original audit, not regenerated during registration. The manifest hashes bind the stored evidence. Build logs from the two earlier fixes have trailing whitespace removed; their diagnostic content is unchanged. JSON receipts and screenshots are copied intact.

## Reproduce Safely

Use an authorized signed-in dev account, open the Wave Viewer, choose market 2 (US), AAPL and the stated years/start/duration. Interact with the visible controls. Mobile checks used Chromium iPhone emulation and browser touch events; physical Safari was not tested. Calendar inputs in the records are absolute historical dates: preserve them in a controlled replay or adapt deliberately and record changed conditions.

For automation, use the repository's documented capture authentication without recording tokens. The original audit scripts remain on dev under /var/tmp/trend-chart-audit-20260915 (audit-desktop.cjs, audit-extra.cjs, audit-input.cjs, audit-mobile-confirm.cjs); these supplementary host files are not required for the manual reproductions. The existing portable component regression is tools/ui_capture/check_trend_chart_labels.js with fixtures in the repository. It needs the repository UI capture dependencies. On dev run as flask with NODE_PATH=/home/flask/tools/ui_capture/node_modules, pointing node at the regression in the chosen worktree. This is a component check, not a full mobile-layout test.

For TW-BUG-0006, delay only the relevant trend response 2.5 seconds in a disposable browser before entering invalid text during a years change. For TW-BUG-0007, fulfill only the trend request with HTTP 500 in that browser; leave the primary chart requests real. Remove interception and change years to check recovery. Do not alter shared server behavior to simulate these failures.

## Interpretation Limits

Some early harness steps selected hidden duplicate IDs, and some later edits were blocked by the leap-day dialog. Those setup failures are excluded. Use visible controls in .seasonal-barchart-container, check a nonzero bounding box, and close dialogs before a fresh case. Desktop input cases 12, 13, 15 and 16 were superseded by fresh input receipts. Extra input steps following the leap-day modal are not independent findings. The initial unscoped preliminary audit is not included as evidence.

Right-edge checks expecting 366 or 40 timed out because the actual result was 351 or 39; those are genuine reproduced assertion failures. Audit recorder exit zero does not mean all cases passed. Successful normal interactions do not invalidate the failing cases. Fresh landscape startup also logged the speed error, so do not claim it universally passed.

The primary cause of the February 29 main-chart failure remains untraced. The rotation stack was checked against the minified runtime bundle; source maps were unavailable. No financial engine values were reimplemented. No staging/production check or runtime change occurred in the audit or registration task.
