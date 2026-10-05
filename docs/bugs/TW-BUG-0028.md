# TW-BUG-0028: New SMN Articles Omit the Established Site Header

- Status: open; separate repair candidate and owner acknowledgement pending.
- Confidence: reproduced in production, October 5 at 20:50 UTC.
- Priority: P2, all six current articles show the wrong site header/navigation while article content remains available.
- Reporter: Afshin, live-call clarification relayed by Dorothy: "The new articles, headers are wrong. They are missing".
- Investigator: Codex verifier `01a10c07-0aa8-767f-84e3-04f9184b50da`, read-only scope plus shared documentation.
- Requested existing repair owner: `01a0fcf4-37f1-7d33-bced-ac46999fd9fa`; acknowledgement and exact implementation claim pending. No competing implementation or production window claimed.
- Authorization: investigate intended header, inspect six October 5 layouts and future generation, preserve body/charts/sources, and reconcile with the existing owner. Do not silently add a header patch to approved prevention release 32bd869. A separate reviewed production candidate/approval is needed.

## Reproduction and Evidence

Open `https://seasonalmarketnews.com/editions/2026-10-05/SYMBOL/article.html` for XLF, SI, SPY, QQQ, AMZN and NVDA. Headless Chromium inspected all six at 1440x1050 desktop and 390x844 mobile. All twelve views have a visible article H1 and the compact `header.masthead` with "Markets in context" on desktop. They omit the established `.smn-header` with its linked brand and Home/TradeWave navigation. This is absent markup, not a clipped or hidden article title.

Comparison: [older Amazon article](https://seasonalmarketnews.com/articles/US/2026/08/03/amazon-amzn-has-rallied-in-5-of-6-midterm-august-windows-averaging-5-04-gains.html) shows the established header; code reference at installed 2d1 is `blog/article_post_process.py:518`, `_site_header_html()`, with matching CSS. A ticker strip and other older page elements also differ, but they are not automatically included in this header request. Do not restore unrelated sharing, signup, or related-article components merely because they are absent.

All twelve views retain the six body roles, three native charts, loaded images and 3-5 sources. No page JavaScript errors, first-party HTTP errors or horizontal document overflow occurred. Actual article-body/source integrity separately passes the six-article/123-file production freshness check in [TW-BUG-0027](TW-BUG-0027.md). This is verification of the reported defect and preservation baseline, not a claim the template is fixed.

Portable evidence: [twelve-view summary](evidence/TW-BUG-0028/six-headers-summary.json), [full DOM and screenshot hashes](evidence/TW-BUG-0028/inspection.json), [read-only capture script](evidence/TW-BUG-0028/inspect-six-headers.cjs). Screenshot/HTML files are accessible to the existing owner at `C:/Users/afshin/Documents/Codex/2026-10-05/task/smn-template-inspection-20261005/six-header-capture/`; originals are on SMN Dev at `/var/tmp/smn-readonly-headers-20261005-snQ8x5`. Four representative current screenshots and the older desktop header received pixel inspection; all twelve had DOM/layout checks and retained screenshots. This used an isolated headless browser, not Afshin's visible browser. No forms, authenticated requests or production writes occurred.

## Cause and Future Generation

`blog/visual_editorial.py:243` emits the compact standalone masthead. The established `_site_header_html()` is not integrated into this current article-rendering path. The renderer/header helpers are unchanged between installed production `2d1de1a9c9f200fa29a2db7f9660f3527727b660` and approved prevention `32bd869c0ffdd6039145bcaee4223dd67fb533ff`. Installing 32bd869 will therefore not repair current or future article headers. No new generation was run to prove a fact visible in unchanged source and actual public HTML.

The strict publication package binds staged HTML to reviewed presentation evidence. A repair must produce an honest new presentation transaction and rollback evidence; do not edit public HTML in place or replace old review hashes and call the original receipt unchanged. Reuse approved article JSON, source evidence, native chart bytes, business graphics, hero assets and study links without additional model jobs.

## Acceptance and Handoff

Existing owner should acknowledge, confirm the established header contract, then claim a narrow isolated source/presentation repair. Keep it separate from the approved prevention cutover. Restore the linked brand and Home/TradeWave navigation with scoped CSS, preserving article titles and the modern article body. Review whether public publication transformation or a shared pure header helper is the appropriate boundary; avoid importing legacy generation/provider side effects.

Before requesting a separate production decision, supply an exact pushed candidate (draft PR if any), saved-evidence replay and new presentation receipts. Verify all six October 5 pages on desktop/mobile, header link destinations, accessible visible navigation, no duplicate headers on repeated packaging, no overflow/clipping, unchanged body/source/study/chart data, and no duplicate catalog entries or newsletter action. Demonstrate the future publication path uses the same header contract, including relevant continuity/fallback paths. Provide a targeted rollback preserving the original edition and every mail receipt; do not overwrite another release's source pointer.

Dev: no repair deployed by this task. Production: defect reproduced on 2d1, still unfixed. Staging: not applicable to this read-only investigation. No repair commit, publication transaction, generation, provider call or send exists from this verifier. Source owner coordination is blocked here only by unavailable direct task tools; Dorothy must relay/resume the existing owner. The approved prevention deployment remains independently authorized under TW-BUG-0027.
