# October 6 reader edition recovered before target

Production publication completed at **10:48:51 UTC / 06:48:51 Eastern**, 11 minutes 9 seconds before the 07:00 target. An independent public-content check passed at 10:49:56 UTC. The six expected articles are CPRT, APH, XLK, IBM, MSFT and COST.

Afshin approved the bounded recovery through Dorothy at 10:37 UTC: **"yes run it"**. The execution stayed within six additional subscription job starts and 46 cumulative reader jobs. Exactly one gpt-6-sol medium independent review and five gpt-6-luna low visual jobs ran. No new Astra, research, writer, hero-generation or paid-fallback jobs ran. No application/service/continuity-operator deployment occurred; production stays on `2d1de1a9c9f200fa29a2db7f9660f3527727b660`.

## Evidence and retained state

- `completed-receipts.json`: real job receipts, model/effort/usage, six-attempt ledger, all-six finalization, unchanged original failed edition and mail journal, explicit recovered controller status.
- `public-verification.json`: frozen selection, unique current-date catalog entries, all six homepage links, exact public article bodies after the one known Cloudflare beacon normalization, and all **123 edition origin files** matching the real publication receipt.
- Installed publication verifier: **12 desktop/mobile article layouts and 214 public files** passed. The independent check supplements this proof; HTTP status alone was not accepted.
- `linux-qualification.json`: **16 offline failure-path tests passed on Linux**, also passed locally on Windows. Includes retry interception, seventh-start refusal, crash/restart refusal, cached receipts, peer exclusion, source drift, hard-review failure and the installed publisher's rollback path. No fault was injected into live production.
- Publication receipt SHA256: `b3f921aa83b5b1421c26dfa3f6778480d2ca6ee55df3c43c2027a07ff4516e63`.
- Recovery root: `/var/lib/tradewave/smn-daily/subscription-primary/2026-10-06/chatgpt-recovery-six-20261006`.
- Original failed edition: `/var/lib/tradewave/smn-daily/subscription-primary/2026-10-06/chatgpt`, unchanged byte-for-byte.
- Recovery ledger: `/var/lib/tradewave/smn-daily/subscription-primary/2026-10-06/bounded-recovery-20261006`.
- Publication transaction: `/var/lib/tradewave/release-state/smn-production-2026-10-06-2d1de1a9c9`.
- Day resolution: `/var/lib/tradewave/smn-daily/subscription-primary/2026-10-06/recovery-resolution.json`.

The original controller finished at 10:38:04 UTC. Its authentic failure receipt is retained as `bounded-recovery-20261006/original-controller-last-run.json`. `last-run.json` now explicitly says `status=recovered`, `reader_publication_status=live_verified` and points to the recovery root. Claude comparison remains held and was not included in the six-job repair.

## Newsletter boundary and monitoring

**No newsletter was sent or released.** The existing mail journal is unchanged, no October 6 weekday-newsletter marker existed at 10:49:57 UTC, and the canonical `chatgpt/production-publication-receipt.json` remains absent. The installed newsletter scheduler requires that canonical receipt, so it is intentionally not released by this content-only recovery. Copying the recovery receipt into that canonical location could release the newsletter and requires separate authorization.

The original `smn-production-freshness-check.py` expects the canonical receipt. For this content-only recovery, use **`read-only-freshness-check.py`**, which follows the dated `recovery-resolution.json`, requires a same-day sibling path and verifies its receipt hash before checking the public edition. Do not misclassify the preserved canonical HOLD as missing public content or overwrite it to satisfy the old checker.

## Job-count explanation

A normal article uses six subscription jobs: primary discovery, research, writing, review, hero-text check and screenshot review. One landing review is shared across the edition: six articles normally need **37 jobs**.

| Article | Completed before recovery | Final completed |
| --- | ---: | ---: |
| CPRT | 8 | 8 |
| APH | 8 | 8 |
| XLK | 6 | 9 |
| IBM | 6 | 6 |
| MSFT | 6 | 6 |
| COST | 6 | 8 |
| Shared landing | 0 | 1 |
| **Total** | **40** | **46** |

The installed counter counts prepared directories plus failed-attempt directories, not exactly provider HTTP calls. COST's prepared but unstarted hero check was directory 41. Transient attempts, initial hero-image generation, browser operations and tools are outside that counter. Claude comparison has a separate 40-job root. The recovery guard separately capped six new subscription dispatches, including any unsuccessful start, and refused automatic reattempts.

Actual six-job receipt totals: **132,687 input tokens (6,912 cached) and 2,543 output tokens**. These figures exclude coordinating-task overhead and earlier morning/comparison jobs; do not convert them into an unsupported dollar figure or account-wide usage estimate. See `job-budget.json`.

## Remaining prevention work and model direction

Today's content recovery is complete. Durable prevention is still pending: the installed source-quote validation recovery missed a reviewer concatenating authentic excerpts with ellipses; the default 40-job allowance leaves only three jobs above the 37-job baseline; continuity and operational alert timers remain undeployed under the pending corrected-operator approval. No default budget or policy was changed. The separate missing site-header issue TW-BUG-0028 also remains outside this recovery.

Existing coordination references remain release owner `01a0fcf4-37f1-7d33-bced-ac46999fd9fa`, schedule owner `01a0fcf2-f893-74f0-b850-4105ab151511`, Dorothy `01a0f25f-c964-7675-91ca-caa44db7c0c4`, and draft PR https://github.com/afshinmoshrefi/tradewave-tw2/pull/14. This verifier/executor is `01a10c07-0aa8-767f-84e3-04f9184b50da`.

Afshin explicitly requests GPT-6.1-Sol for most coordinating tasks, including demanding work, and Astra only for a demonstrated selective need. **Dorothy should set this task's next turn to GPT-6.1-Sol.** This agent has no task-model switch tool and has not claimed to change it. The installed production worker does not yet accept 6.1-Sol; changing that profile is a separate qualified change, not an unannounced substitution in the approved six jobs. The parent audit worker owns the broader model inventory; do not run extra benchmarks for this handoff.
