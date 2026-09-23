# TW-TASK-0007: Controlled SMN Astra/Sol/Luna article comparison

- Status: verified (private experiment; not deployed)
- Confidence: authorized experiment
- Executor/session: Codex smn-model-benchmark-20260922
- Claimed UTC: 2026-09-23T02:04:08Z (September22 New York)
- Authorization: create the same September22 six articles with GPT-6 Sol and GPT-6 Luna; independent comparison agents evaluate against existing Astra articles; estimate API cost and compare owner-reported production $0.30-$0.40/article.
- Scope: isolated experiment, 12 new writer jobs plus 12 same-model editorial reviews, matching xhigh baseline, saved official ChatGPT CLI authentication only; no paid API fallback. Two blind comparison agents after outputs exist. Preserve failures as evidence, no silent rewrites. Additional repair trials only when required and separately labeled.
- Exclusions: no daily model/profile changes, site deployment, production writes, replacement financial calculations or takeover of Claude's bug/efficiency work. Coordinate findings through TW-TASK-0006.
- SMN source: 277ba7ddb45d2148186d52d4d5f3761b8ca9c3e3, branch codex/smn-model-benchmark-20260922. Baseline article source c2beec6778c89592a8e12d3ac4266d8aea9e0ac0 has identical writing logic.
- Worktrees: Windows orchestrator/smn-model-benchmark-20260922; shared records /home/tradewave-worktrees/smn-model-benchmark-20260922.
- Inputs: immutable September22 MRK/XLK/AZO/SPY/QQQ/GC jobs/results in smn-review-20260921/production-style/2026-09-22; retain original prompts, schemas, engine studies, news sources and visual assets.
- Acceptance: 12 model variants with provenance and measured usage; existing mechanical/editorial/layout checks; blinded per-subject comparison with quotes/reasons and failure distinctions; published official token prices used for API-equivalent estimate, not subscription dollar billing; explicit limits and no extrapolated quality guarantee from six subjects.
- Next: Claude reviews this evidence through SMN-EFFICIENCY-02 before a joint model/workflow decision. No live model switch authorized by this benchmark outcome.

## Completion - September22 New York / September23 UTC

Exactly12 new writers and12 separate same-model reviewers completed via saved ChatGPT CLI, all xhigh, no API fallback or draft repairs. All writer prompt/schema bytes match baseline;264 unchanged evidence/asset comparisons pass. Existing Astra prose was verified equal to its raw model output. All24 new desktop/mobile layouts pass;48 top/full captures were actually inspected.18 article links and report desktop/mobile layout verified. Adapter tests13/13 pass; compile and diff checks pass.

Measured API equivalents per article (writing+review only): Astra0.955993, Sol0.210324, Luna0.014269 USD. These were subscription jobs, not paid API generation; no additional research/hero calls. Deterministic source/structural gates: Astra6/6, Sol4/6, Luna3/6; complete same-model pipeline approvals:6/6,2/6,2/6 respectively. Different reviewer models mean those approval rates are operational outcomes, not an unbiased quality ranking.

Two blind comparison agents each reviewed all18 outputs. Editorial Astra-high reviewer preferred Astra first/tied in5/6 subjects; factual Sol-high reviewer preferred Luna on3 and Sol on3, often favoring detail. Root reconciled actual defects instead of using a vote: Luna SPY mislabels future illustration dates as actual prices even though its own reviewer passed it; Sol AZO has a store-announcement chronology wording error; Sol MRK has a chart/sample-placement ambiguity. Source caps also fail for Sol AZO/QQQ and Luna XLK/QQQ/GC. No engine data or chart values changed. Astra also has a too-broad MRK headline, so baseline approvals do not prove perfection.

Recommendation: Luna is promising as a cheap drafting stage, not a proven unattended replacement. Test bounded repair plus an independent editor before switching. Fresh all-Luna known-component subtotal is about$0.074-$0.106 including one Flux hero and0-4 paid Tavily credits; preliminary$0.12-$0.18 planning allowance includes assumed room for unmeasured smaller-model calls/corrections, not a measured bill. A hypothetical Luna-writer/Sol-editor text estimate is$0.0899, not a tested hybrid. Original production$0.30-$0.40 remains owner-reported, not invoice-verified. No predicted weekly-quota percentage is claimed.

Source pushed only to SMN branch codex/smn-model-benchmark-20260922, final9b3937362093bdb9afe3108f4692b951fa064c2f; initial execution2138964. Source is private-experiment code, not integrated into main or deployed. Daily profile, Dev site and production unchanged. Older daily CLI0.153.1 did not list new models; the experiment used available official desktop CLI0.155.0-alpha.16 without copying credentials. One SPY prefetch ownership race reused its one completed writer receipt; no duplicate generation. Future benchmark runner waits for the existing writer receipt. The original scheduling error and resolution are retained.

Local comparison: C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-review-20260922/model-benchmark/index.html. Shared [findings](evidence/TW-TASK-0007-findings-20260922.md) and [completion proof](evidence/TW-TASK-0007-20260922.json). Private self-contained18-article audit: /var/lib/tradewave/smn-editorial/audits/20260922/model-comparison/comparison-audit.tar.gz on tradewave-vm, outside nginx, root/sudo access. Contains sources, writer/review jobs, outputs, cost records, blind reviews, visual proof and report; excludes account snapshots and credentials.

Audit SHA256: 886e1587a62c23724eee8fb6435245ff6db4e75cf3fc865df3bbd388ea2d98a6; bytes: 63552151.
