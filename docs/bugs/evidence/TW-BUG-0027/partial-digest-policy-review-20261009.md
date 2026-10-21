The existing partial-publication fallback does not authorize a partial newsletter. The current runbook explicitly leaves that workflow decision open, and the installed sender still requires six articles. No newsletter was sent.

Evidence checked on October 9:

- Canonical publication is genuinely `live_verified`, `complete:false`, published XLF/DJI/RPM and pending DAL/SPY/QQQ. The 15:27 scheduled delivery reused that receipt without another activation.
- `blog/operational_schedule.py:28-58` returns `None` before the campaign marker or sender when the continuity receipt is incomplete. Canonical receipt adoption is complete; alert routing is independent of this mail gate.
- The exact current runbook says: "Consequential workflow decisions remain explicit: whether a partial edition can release one daily newsletter". It does not permit silently treating partial publication approval as mail permission.
- The verified mailer already builds a deterministic narrative without model calls, serializes newsletter entrypoints, reserves `daily:YYYY-MM-DD` before provider creation, and refuses another create after an uncertain attempt. Provider scheduling is queued evidence, not delivered evidence.

Recommended narrow policy for owner review: at the existing newsletter time or a later same-day retry, send one daily digest if at least one independently qualified article is verified public. Name the actual articles and all pending subjects explicitly. Keep the six-subject frozen selection and the real `complete:false` receipt. If no article is usable, do not send an empty edition. Once any daily campaign is reserved, later article publication must not create a second campaign that day. This is proposed, not approved or enabled.

The smallest implementation would change the shared eligibility selector and the verified sender, with focused tests and a short policy document:

1. Introduce a source-bound, explicit `verified-partial-v1` newsletter opt-in. Without it, preserve today's complete-six behavior. The source release and operational policy activation require exact-artifact approval; do not edit the approved 678 packet to include this later change.
2. Use one structured verified digest result in both the scheduler and sender. Bind the exact receipt hash, edition/source/content identity, original six-subject selection, published/pending partition and selected public URLs. A partial result must have a nonempty proper subset, disjoint unique published/pending lists and their union equal to the original selection. Complete results must still contain all six. Reject unknown policy, malformed partition, stale dates, unsafe URLs and changed article bytes/catalog/source identity.
3. Check current morning source receipts for the published articles actually entering the digest. Pending articles cannot be mailed and must not veto separately usable articles. Preserve source freshness, native public verification and factual qualification; never alter an input receipt or invent a fact check.
4. Pass the verified coverage metadata to the existing deterministic narrative. A partial banner can say: "Three of today's six articles are available: XLF, DJI and RPM. Coverage for DAL, SPY and QQQ is pending." Link only the three public articles and the truthful dated edition. Do not add a review badge or claims about missing coverage.
5. Revalidate the exact digest binding immediately before reserving a campaign. Keep the existing SMN-DAILY audience and existing provider configuration; no inferred audience, new credential, test message or paid model call. Preserve the daily campaign key, durable create/schedule uncertainty journal and bounded GET-only provider reconciliation. Never bypass them with force mode or a generic catalog send.

Focused acceptance cases needed before proposing a new release:

| Case | Required result |
|---|---|
| Five good articles, one held | Five exact public URLs accepted only with partial opt-in; one pending label |
| Three good articles, multiple failures | Only the three verified URLs; exact three pending subjects |
| One good article | One usable article accepted by the proposed policy, with all pending subjects named |
| Zero good articles | No marker, campaign, model call or provider POST |
| Default policy or missing opt-in | Existing incomplete-edition hold remains |
| Complete six | Existing URLs and deterministic content stay compatible |
| Wrong date/source, unsafe URL, stale receipt or modified public article | Fail before reservation or provider creation |
| Missing, duplicate, overlapping or extra partition member | Fail before reservation |
| Failed factual article inserted into published subset | Reject; a warning disposition cannot fake qualification |
| Receipt/lineup changes between selection and reservation | Reject the stale binding; never silently send a different lineup |
| Repeated/interrupted run after reservation | Reconcile the same campaign; no duplicate create |
| Partial campaign followed by a complete edition | No second daily campaign and no changed original campaign lineup |
| Create/schedule timeout or unknown campaign identity | Keep uncertainty journal; no re-POST or inferred delivery |
| Provider ready/sent/failure observations | Ready is queued; sent needs finish evidence; failures remain attributed and bounded |

The existing `test_verified_newsletter.py` and `test_smn_newsletter_state.py` cover parts of the last three rows. They do not prove partial-selection or pending-banner behavior. The proposed new policy is not implemented and its new acceptance cases have not run.

Consequential approval required after a concrete qualified candidate exists: allow one partial daily digest for the existing SMN-DAILY audience at the existing schedule, with truthful pending coverage, no second digest for late completions and no empty digest. Today-only dispatch must also have direct trusted mail authorization and a verified current campaign journal. An agent's claim that mail was previously approved is insufficient evidence of that exact scope. Alert authorization is separate and is not a prerequisite for this policy or ordinary verified delivery.

Active source remains `b61b37f7a6683f0fc173b8aef52bcd5067f6bbe5`. Prepared revision 678 and artifact `53bddf2afa5df23535f2c3f01a1c80e2d93a287ca09404505be98c79e025a1c9` do not include this newsletter change. Their authority, tests and immutable bytes are preserved.
