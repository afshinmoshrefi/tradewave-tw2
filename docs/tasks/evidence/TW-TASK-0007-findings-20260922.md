# SMN: Astra, Sol and Luna on the same six articles

**Conclusion: Luna is a credible low-cost draft writer, but this test does not justify replacing the current workflow with unattended Luna writing and self-review. Astra remains the strongest finished editorial baseline. Sol is closer stylistically in some stories, but did not solve first-pass reliability.**

## What was actually tested

September 22's MRK, XLK, AZO, SPY, QQQ and gold articles: six existing unedited Astra outputs versus six new Sol and six new Luna outputs. The 12 new writer prompts and schemas matched the baseline bytes exactly. Sources, engine studies, selected years, direction, windows, heroes and charts were retained. All 264 checked evidence/asset files matched their baseline counterparts. No TradeWave calculation was repeated.

Every writer and its separate same-model reviewer used Extra High effort and the saved ChatGPT subscription through the official CLI. Exactly 24 new jobs completed: 12 writers and 12 reviewers, with no rewritten drafts or paid API fallback. Two independent comparison agents reviewed randomized A/B/C packets without model names: Astra High for editorial quality, Sol High for factual/source interpretation. Neither generated the candidate articles. Both covered all six; their original findings and disagreements are preserved.

The historical Astra run used CLI 0.153.1; the new models required the available desktop CLI 0.155.0-alpha.16. Identical user prompts do not establish identical hidden system context across CLI/model versions. This is one run per subject/model, not a statistically conclusive benchmark. The reviewer-model change also means pipeline approval rates are operational outcomes, not an unbiased common-judge quality score.

## Results and measured text cost

| Model | Source/structural gate | Writer + reviewer cleared all gates | API equivalent per article | Six-article total |
|---|---:|---:|---:|---:|
| Astra | 6/6 | 6/6 | $0.9560 | $5.7360 |
| Sol | 4/6 | 2/6 | $0.2103 | $1.2619 |
| Luna | 3/6 | 2/6 | $0.01427 | $0.08561 |

These are standard API price equivalents from actual job token receipts, **not API charges or the total cost of production**. Output already includes reasoning tokens, which are charged only once. All recorded cache counts were zero. Prices per million input/output tokens: Astra $10/$50; Sol $2/$10; Luna $0.10/$0.50. [Official prices](https://developers.openai.com/api/docs/pricing).

All 12 new articles passed automated desktop/mobile layout checks; a separate visual agent actually inspected all 48 top/full captures. Heroes, responsive TradeWave charts, additional context charts and links remain. Preview hold banners and finalized-page breadcrumbs reflect review status, not a model-generated redesign. Candidate pages remain private test artifacts; no site or daily model setting was changed.

## What the blind readers preferred

| Subject | Editorial preference | Factual/interpretation preference | Useful difference |
|---|---|---|---|
| MRK | Sol, then Luna | Luna | Sol gives a useful next-business-check question, but its 2024-25 example sits beside a midterm chart that excludes that year. Luna uses a plotted 1974 example. Astra's headline broadens the pending combination-use decision. |
| XLK | Astra | Luna | Astra is clearer and more balanced about gains remaining typical despite losses. Luna supplies more context and comparison detail, but exceeds two source budgets. |
| AZO | Astra | Sol | Astra leads with that day's results and explains profit durability. Luna is careful but opens more generically. Sol has a date-order wording problem and exceeds its Q4 source budget. |
| SPY | Astra and Sol tied | Sol | Both connect the Fed decision and the window cleanly. Luna incorrectly attaches future illustration dates to actual prices. |
| QQQ | Astra | Sol | Astra makes the December index review a distinct story. Luna exposes editorial scaffolding and omits the September source from one paragraph making the September claim. |
| Gold | Astra and Sol tied | Luna | Astra/Sol read more naturally. Luna offers detailed cohort/context explanation, but its illustration wording is ambiguous and its WGC source budget is exceeded. |

The editorial reviewer put Astra first or tied first in five of six subjects, Sol in three including ties, and Luna in none. The factual reviewer preferred Luna on three and Sol on three, largely rewarding explanatory detail. That does **not** establish that Astra's figures were less accurate. Both reviewers found most candidates close and generally grounded. Ranking differences are evidence about preferences, not a vote that can override a confirmed defect.

## Defects that change the deployment decision

- **Luna SPY:** “actual SPY prices from September 22 through December 14” describes future illustration dates as actual observations; the input explicitly says actual prices stop September 21. Both blind readers flagged it. Luna's single-article reviewer had passed it. The engine data and chart are unchanged; the prose mislabels their meaning.
- **Luna source budgets:** XLK reached 253 and 274 words against two 200-word caps; QQQ reached 209 and 226; gold reached 233. These deterministic counts include the protected chart text and other page surfaces. A reviewer calling an article readable cannot waive them.
- **Sol source budgets:** AutoZone reached 232 words; QQQ reached 208, each against 200. Sol also says AutoZone had 8,031 stores on August 29 “after announcing its 8,000th opening,” although the supplied announcement is dated September 10. That chronology needs correction.
- **Sol MRK:** the 2024-25 example is accurately labeled as consecutive history, so its numbers are not invented. Its placement next to the selected-midterm chart can nevertheless mislead readers about which observations are plotted. The reviewers disagreed on severity; I would clarify or move it before publishing.
- **Astra is not flawless:** the MRK headline “KEYTRUDA awaits Europe” is broader than the pending decision on the particular combination use. Its original 6/6 approval is not proof that every editorial choice is ideal.

No article was silently repaired to improve its score. Sol's other review holds include debatable placement/qualification preferences; do not interpret every hold as a false financial statement. Luna's longest writer, AutoZone, took 603 seconds and used 32,059 reasoning tokens. Cheap did not mean fast at Extra High.

## Estimated full article cost versus the old $0.30-$0.40

The original production manifests identify GPT-5.1 writing, GPT-5-mini research, GPT-5-nano domain lookup, two Tavily responses and a Flux hero. They do not contain enough token/billing evidence to verify the owner's $0.30-$0.40 all-in range.

For a **fresh** Luna workflow using these services:

| Component | Per-article estimate |
|---|---:|
| Luna writing + separate Luna review, measured six-subject average | $0.0143 |
| One Flux 1.1 Pro Ultra hero | $0.0600 |
| Two advanced Tavily searches | $0 to $0.0320 |
| Known-components subtotal | **$0.0743 to $0.1063** |
| Other research/domain/hero-prompt model calls, repairs and orchestration | Not measured in this replay |

[Replicate's exact image model](https://replicate.com/black-forest-labs/flux-1.1-pro-ultra) lists $0.06/output. [Tavily pricing](https://docs.tavily.com/documentation/api-credits) makes two advanced searches four credits, or $0.032 at pay-as-you-go rates; included credits can make the incremental cash cost zero. Their allocation and invoices were not inspected.

**A preliminary planning allowance is roughly $0.12-$0.18 per fresh Luna article**, including a few cents beyond the known subtotal for smaller model calls and corrections. That allowance is an assumption, not a measured all-in bill, and does not include a newly added paid Astra editing pass. Against the reported $0.30-$0.40 baseline, this suggests worthwhile potential savings, not yet verified production savings. The benchmark itself reused research/images and ran on the subscription: no new Tavily, Flux or paid OpenAI generation charge was incurred by those jobs.

An alternative worth testing is Luna drafting plus an independent Sol editor. Using this test's Luna writer tokens and Sol review tokens gives a **hypothetical 8.99-cent text cost**, or about **15-18 cents including the known hero/search components**, before smaller model calls and repairs. This is not a tested hybrid outcome; it must still demonstrate that it catches and repairs the actual defects. It would cost more than the all-Luna allowance above. Do not promise a reduction from 7% weekly quota to a particular percentage: subscription accounting, other account activity, the orchestrator and these one-off comparison agents are not represented by the text-price table.

## Recommendation

Keep the live workflow unchanged for now. Treat Luna as the leading cost-reduction candidate for drafting, retaining deterministic source/data checks and an independent editing/repair stage. Sol is a plausible editor; this run does not prove that combination preserves quality. The next small experiment should repair and re-review the specific failed Luna examples, measure the added cost, and compare the corrected versions blind against Astra. Avoid switching merely because the prose sounds good or because its own reviewer approves it.

Results and the exact experimental branch are shared under TW-TASK-0007 for Claude's review through TW-TASK-0006. Claude's acknowledgement and any joint deployment decision remain pending. No consensus or production upgrade is implied by this report.
