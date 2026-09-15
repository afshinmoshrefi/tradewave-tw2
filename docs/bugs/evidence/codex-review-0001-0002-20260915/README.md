# Independent Review of TW-BUG-0001 and TW-BUG-0002

Codex reviewed Claude Code's fixes and documentation on September 15, 2026 at source
758c3d3e1389eec4096e973c2f655168e0a4f2c3. Dev served source
99bce08d5c6cbbac88dd8832466e00a85cdca700, bundle main.35bdd7c9.js.

## Results

All 28 original live checks passed independently: 14 rotation/retry, 13 desktop
resize, and one fresh-landscape check. Four additional visible touch/rotation checks
passed: initial 366 days, leftward touch movement to 322, rightward movement to 352,
then rotation with 352 days preserved. No browser or console errors were reported
in these successful runs. The layout/desktop screenshots were visually inspected.
Afshin also reported both fixes worked in his own testing; no particular device,
browser or environment is attributed to his statement.

Reviewed the full application diff and the recorded 117-test output, baseline
failures and fixed receipts. Unit tests/build were not rerun; this review reran live
behavior. All 21 files in the activation artifact hash list matched the active
artifact, and the served main JS bytes matched its recorded hash. Current reviewed
frontend source matches the runtime source. Existing backend parity limits remain.

## Documentation Repair

Both bug records linked to the same missing build.log. It existed only under
/var/tmp/claude-tw-bug-0001-0002-20260915 and had been excluded by Git's log ignore
rule. It is now explicitly committed at the linked path. Trailing whitespace was
removed; original and stored hashes are in summary.json. No other broken or untracked
links were found among the 36 local link references in the two records.

The records already included ownership, authorization, reproduction, rationale,
source commits, regression coverage, deployment/rollback evidence and limitations.
The review adds independent verification and owner confirmation. Status stays
verified on dev. No application change or deployment occurred.

## Repeat the Checks

Run as flask on dev from a current repository task worktree. The harness needs the
existing /home/flask/tools/ui_capture/node_modules/puppeteer and authorized local
capture endpoint at port 5500; it exercises live assets and engine responses.
Use a new output directory per run. Do not print capture HTML, cookies or tokens.
The following are actual shell commands, not a pipe-separated mode placeholder:

```sh
node docs/bugs/evidence/claude-tw-bug-0001-0002-20260915/verify-bugs.cjs --mode rotate --out /var/tmp/review-rotation-next
node docs/bugs/evidence/claude-tw-bug-0001-0002-20260915/verify-bugs.cjs --mode resize --out /var/tmp/review-resize-next
node docs/bugs/evidence/claude-tw-bug-0001-0002-20260915/verify-bugs.cjs --mode landscape --out /var/tmp/review-landscape-next
node docs/bugs/evidence/codex-review-0001-0002-20260915/verify-touch.cjs --mode touch --out /var/tmp/review-touch-next
python3 docs/bugs/evidence/codex-review-0001-0002-20260915/assert-receipt.py /var/tmp/review-rotation-next/receipt.json /var/tmp/review-resize-next/receipt.json /var/tmp/review-landscape-next/receipt.json /var/tmp/review-touch-next/receipt.json
```

The browser recorder exits zero even when a recorded assertion fails. Inspect the
receipts or run assert-receipt.py; exit zero alone is insufficient.

## Touch Setup and Limits

The first exploratory second gesture did not reach the resize handle. Changing
duration can navigate away from Trend Chart, and after returning, tapping a point
already considered inside the annotation may not trigger its enter handler again.
The included setup probes retain those failures and the event trace: only the
canvas tap reached the page, not the second handle touchstart. They do not establish
a duration-calculation failure. The successful check returns to Trend Chart and taps
outside then inside the highlight to reveal the handle before the next gesture.
This review does not claim that repeated taps at the same point always reveal the
handle, or that every mobile gesture is covered. A separate usability investigation
may be useful if users report difficulty revealing handles.

Mobile coverage is Chromium phone emulation, not physical Safari. Retry is a forced
error-boundary remount, not a newly induced real production error. The five other
open bugs remain outside this review; their status is unchanged. The review is not
an exhaustive chart audit or staging/production verification.
