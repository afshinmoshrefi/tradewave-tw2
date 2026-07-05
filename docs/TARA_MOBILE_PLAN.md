# Tara on Mobile - Implementation Plan (DEFERRED)

Status: SCOPED 2026-07-05, deferred by owner for future development.
Fact-finding was code-verified (file:line cites below were checked read-only
against main at the time of scoping - re-verify line numbers before building).
Companion memory note: `enh_tara_mobile.md` in the agent memory store.

## Decision Summary (locked at scoping)

1. **Ship Tara on mobile.** Chat is the mobile-native interface to a dense
   product; the 7-day LessonBox (which runs on mobile) already teaches "ask
   Tara" on Day 2; the mobile ask-flow banner currently says "Tara chat is
   available on desktop" (App.js:2762) - retire it when this ships.
2. **NO separate knowledgebase.** One `chatbot_knowledge.txt` with per-section
   platform tags, split at startup into `_KNOWLEDGE_DESKTOP` /
   `_KNOWLEDGE_MOBILE`, selected per request by a new `platform` payload
   field. ~55-60% of the file is platform-neutral product truth; duplicating
   it into a second KB is a guaranteed drift bug (a recurring TW failure
   mode). The KB already uses inline "(Desktop Only)" tags in three places -
   tagging is its native idiom.

## Fact Base (what the investigation established)

### Knowledge file (appserver/appserver/chatbot_knowledge.txt, 1125 lines)
- Platform-neutral (~55-60%): What-is-TradeWave, cognitive-load rules, key
  concepts/metric definitions, Understanding Years, disclaimer rule, 100-Year
  Pattern, News Room, securities groups, subscription tiers, data source,
  AI-scores concept, account/profile.
- Desktop-UI-specific (~470 lines) that would MISDIRECT mobile users:
  "TradeWave UI Map (Current Layout)" L30-76 (side-by-side zone model);
  "UI Accuracy Rules" 1-9 L78-91 ("Securities Group ... TOP RIGHT of the top
  bar"); "Wave Viewer Header Banner" L205-223; "Tara Response Template for
  Navigation" + 9 "Common Navigation Playbooks" L375-467; "Troubleshooting"
  L469-551; "Chart Range" L797-806 (already tagged desktop-only); "Settings
  Window" L808-822; projection/weekly/earnings sections L840-917; nudge
  arrows L946-957 + Best Waves L974-985 (already tagged); Portfolio Manager
  popup L315-373.
- CRITICAL: some facts DIFFER by platform rather than merely not applying:
  AI/ML columns (AIS, Win%, PredR, PMFE) are unconditionally suppressed on
  smartphone PORTRAIT regardless of eligibility (OppTable.js:699,711) - the
  KB documents only market/pattern/date conditions. The mobile KB must state
  mobile truths, not just omit desktop sections.
- Confirmed absent on phones (all gated `!rdd.isMobile` in
  StockLineChart.js): chart-range buttons (:777), daily/weekly toggle
  (:809), earnings markers (:834), seasonal projection button (:859),
  full-history projection (:884), draw-price-level (:700,
  tablet-landscape-only).

### Prompt pipeline (appserver/appserver/chatbot.py)
- Knowledge loads ONCE at import (`_load_knowledge()` L170-184 ->
  `_KNOWLEDGE` L186); appserver restart required after edits.
- `build_system_prompt(...)` L597-832 assembles: behavior rules (L601-656) +
  loaded-pattern context (L678-790) + opp-table context (L793-827) + the
  whole `_KNOWLEDGE` blob appended at L829-830.
- `/chat` request parsing at L892-904 (message, history, wave_viewer,
  opportunities, opp_table_*, token). NO platform field exists today.
- Insertion plan: `platform = incoming_data.get("platform", "desktop")` in
  the parse block -> kwarg through the `build_system_prompt` call (L916-917)
  -> select `_KNOWLEDGE_MOBILE` vs `_KNOWLEDGE_DESKTOP` at the append point +
  optionally one extra mobile behavior-rule string in `parts`.
- Split mechanism: extend `_load_knowledge()` to recognize a lightweight
  per-section tag after `##` headings and emit both variants at startup.

### Client (web-react)
- Chatbot.js `handleSend` payload at L205-215 - add `platform` here;
  `rdd.isMobile` (react-device-detect) is already imported in App.js:12 and
  already drives layout choice; a device code already flows to the appserver
  at login (`detectDevice()` App.js:1590-1615 -> appserver.py:564).
- **Phase-2 driving needs NO new plumbing**: `applyViewSpec` (Chatbot.js:
  322-352) calls App-level setters (symbol/startDate/daysOut/seasonalYears/
  PEselected - App.js useState L108-519) which are spread IDENTICALLY into
  DesktopLayout (App.js:2896/2906), MobileLayoutL (:2913), MobileLayoutP
  (:2920) via `{...chartSetProps}`. Verify-by-testing only.
- OPEN RISK (untestable statically): a Tara-driven view change may update a
  chart on an off-screen Swiper slide with no visible feedback. Mitigation:
  mirror OppTable.js:1246-1254's mobile `props.chartTo(1)` slide-nudge after
  actions, and require Tara to narrate every change (mobile cannot glance at
  the chart mid-chat; strengthens the existing NARRATE-EVERY-LOAD contract,
  chatbot.py:139-148).

### Mobile UI approach
- Do NOT embed a docked panel in MobileLayoutP/L. Mount ONE chat component at
  the App.js top level exactly like LessonBox (mounted once at App.js:2732,
  OUTSIDE the layout branch, `rdd` passed as prop; internal
  `isMobile` branch drives fixed-position bottom-sheet CSS -
  LessonBox.js:130, 683, 760-761). Collapsed pill above the chart; expands
  to ~70% height.
- Fix Chatbot.js desktop-calibrated `vw` fonts (0.85vw chat text L414,
  0.8vw input L450/send L464 - ~3px on a 375px phone). Use the existing
  `globalTextSize` device-aware convention (App.js resizeWindow L1524-1576).
- The DesktopLayout resize handle (DesktopLayout.js:1450-1459) is
  onMouseDown-only - mobile sheet should use a fixed height or touch events.
- Screen-real-estate plan: LessonBox launcher already occupies
  fixed bottom:78px/right:14px; two fixed top banners exist (trial "You're
  In" App.js:2745-2748; the retiring ask-banner :2753-2769). Pick a
  non-colliding anchor + z-index for the chat pill.
- Layout matrix: phone-portrait + tablet-portrait -> MobileLayoutP;
  phone-landscape -> MobileLayoutL; tablet-landscape -> DesktopLayout
  (ALREADY has Tara today). (App.js:2891-2923.)

### Gating / quota / cost
- Tara is available to ALL authenticated users - `/chatbot/chatbot_access`
  always allows (chatbot.py:565-579). No per-route Flask-Limiter on /chat;
  metering happens in the v1 gateway per web user ('cb:' principal,
  tara_gateway.py) - platform-agnostic, nothing new needed. Optional belt:
  free-tier daily message cap in the gateway.

## Build Sequence (when un-deferred)

1. **Pipeline flag + minimal mobile ruleset** (S): platform field client ->
   chat() -> build_system_prompt; a short mobile behavior rule ("the user is
   on a phone; never reference the top control bar/left panel; features X
   are unavailable") so Tara is CORRECT on mobile before she is pretty.
2. **Mobile bottom-sheet UI** (M): App-level mount per the LessonBox
   pattern; font + touch fixes; retire the App.js:2762 banner; wire the
   home-page ask-prefill mobile branch (App.js:2373-2396) to open the sheet.
3. **Phase-2 verification** (S): slide-nudge + narration check on a real
   device.
4. **KB platform-tagging + full content audit** (M-L, the risk center):
   tag mechanism in _load_knowledge (S); then rewrite the ~470 desktop lines
   mobile-correct - navigation playbooks, troubleshooting, per-feature
   availability, the AI-columns-portrait truth. CUSTOMER-VOICE COPY: owner
   review pass required (confident-evidence voice, no em-dashes).
5. **Test matrix** (M): 4 layouts, LessonBox/banner collisions, desktop
   regression, KB regression on existing desktop answers.

Riskiest pieces: (1) invisible off-screen view changes (item 3 mitigations);
(2) under-scoping the KB audit as "delete desktop sections" when several
sections need newly written mobile facts.
