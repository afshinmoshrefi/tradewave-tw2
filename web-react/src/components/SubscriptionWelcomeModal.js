import React, { useEffect } from 'react';
import { themeColors, lsGet, lsSet } from './Common';

// =====================================================================
// SubscriptionWelcomeModal - the subscription-aware welcome dialog for the
// TradeWave wave-viewer. It is THE first screen after a subscription event
// (new signup / upgrade / downgrade), rendered OVER everything (z-index
// 10000, above the LessonBox), and on close it hands off to the 7-day
// LessonBox arc via the 'tw-lessonbox-open' window event.
//
// Visual language mirrors LessonBox.js (the dark "Instrument" surface) and
// reuses OnboardingWelcome.js's scrim/card modal pattern.
//
// DEFENSIVE BY DESIGN: this file must NEVER throw or white-screen the app.
// Every window-global read is guarded, every copy lookup falls back to a
// neutral default, and the top-level render is wrapped so any unexpected
// error returns a safe no-op (null) instead of crashing React.
//
// EXPORTS:
//   default SubscriptionWelcomeModal({ UITheme, rdd, tier, subscriptionEvent, onClose })
//   named   decideSubscriptionWelcome()  -> { show, tier, event }
//   named   markSubscriptionWelcomed()
// =====================================================================

// ---------------------------------------------------------------------
// COPY MATRIX (verbatim from docs/SUBSCRIPTION_WELCOME_SPEC.json
// copy_by_tier). Keyed by tier, then by event-block. The 'explorer-trial'
// entry's blocks are 'new' (new_signup), 'upgrade', and 'downgrade'.
// Headlines are AP Title Case with no terminal period; no em-dashes.
// ---------------------------------------------------------------------
const COPY = {
  'explorer-trial': {
    unlocks: 'Now open: all 15 markets, ML scoring, every saved pattern - free for 7 days.',
    new: {
      headline: "You're In - Seven Days, Full Access",
      body: 'Welcome aboard, and thanks for trusting us with a week. For the next seven days you have everything: all 15 markets, the ML scores, the long-hold tools, the lot. No card on file, nothing to cancel. Poke at it hard. Find one window worth watching - that is the whole goal. Anything you save stays yours after day seven, even on the free plan, so build like it counts.',
    },
    upgrade: {
      headline: "You're In - Seven Days, Full Access",
      body: 'Welcome aboard. The next seven days are the full Strategist plan, on the house - every market, every tool, no card on file. Use them to find a real opportunity, not just to click around. Whatever you save is yours to keep when the week ends.',
    },
    downgrade: {
      headline: 'Welcome Back to Explorer',
      body: "You're on the free Explorer plan now, and you keep more than you'd think: the Dow 30, your saved patterns, your portfolio, and ten tracked opportunities. Nothing you built disappears. When you want the rest of the markets back, the door is open and it takes about a minute.",
    },
  },
  navigator: {
    unlocks: 'Now open: the NASDAQ 100 and the S&P 500 alongside the Dow, any start date unlocked.',
    new: {
      headline: 'Welcome to Navigator',
      body: 'Glad to have you on Navigator. You just went from the Dow to the three indexes that move the US market - Dow, NASDAQ and S&P 500 - with any start date unlocked, not just today. Start with the Opportunity Table on a fresh market and read down from the top. The strongest seasonal window is the one sitting first. Want the AI-calibrated score on top of the history? That starts at Analyst.',
    },
    upgrade: {
      headline: 'Welcome to Navigator',
      body: "Nice - you're on Navigator now. The NASDAQ 100 and the S&P 500 just opened up next to the Dow, and you can browse any start date, not just today. More names, same simple read: strongest opportunity on top. Analyst is the next step up if you want the AI-calibrated score riding along.",
    },
    downgrade: {
      headline: "You're on Navigator Now",
      body: "You've moved to Navigator, and here's what stays with you: the Dow, NASDAQ and S&P 500, any start date unlocked, three portfolios, and everything you've already saved. The markets above this tier are paused, not gone - one click brings them back whenever you want them.",
    },
  },
  analyst: {
    unlocks: 'Now open: eight markets including the Russell and Wilshire, the auto PE-cycle filter, SMN research.',
    new: {
      headline: 'Welcome to Analyst',
      body: "Welcome to Analyst - this is where the toolkit really opens up. You've got eight markets now, including the Russell, the Wilshire, ETFs and the indices, plus the automatic election-cycle filter and the SMN research that explains what the data is doing. There's a weekly Q&A too, if you like asking your questions out loud. Start by running a scan on a market you've never looked at.",
    },
    upgrade: {
      headline: 'Welcome to Analyst',
      body: "Good move - Analyst suits you. You've jumped to eight markets - Russell, Wilshire, ETFs, indices and the rest of US stocks - and unlocked the auto PE-cycle filter, the SMN research articles, and a seat at the weekly Q&A. The same date can tell a different story in a different part of the election cycle; now you can see that automatically.",
    },
    downgrade: {
      headline: "You're on Analyst Now",
      body: "You've settled onto Analyst, and it keeps the parts most people use every day: eight markets including the Russell and Wilshire, ETFs and indices, ML scoring, the auto PE-cycle filter, SMN research, and the weekly Q&A. The futures, forex, bonds and crypto markets are paused, and your saved work is all still here. Step back up any time you need the full set.",
    },
  },
  strategist: {
    unlocks: 'Now open: all 15 markets including futures, forex, bonds and crypto, plus the live weekly Zoom.',
    new: {
      headline: 'Welcome to Strategist',
      body: "Welcome to Strategist - you have the whole engine now. Every one of the 15 markets is open, from US stocks all the way out to futures, forex, bonds and crypto, with room to save 500 patterns a market and track 500 opportunities. There's a live weekly Zoom session too. Best first move: run a scan somewhere you've never been and see what almost a century of history says about it.",
    },
    upgrade: {
      headline: 'Welcome to Strategist',
      body: 'There it is - the full plan. Futures, forex, bonds and crypto just joined everything you already had, so all 15 markets are open with nothing held back. The limits get out of your way too: 500 patterns a market, 100 portfolios, the live weekly Zoom. Go somewhere new and let the history surprise you.',
    },
    downgrade: {
      headline: 'Welcome to Strategist',
      body: "You're on Strategist now, with every market open - futures, forex, bonds, crypto and all the rest - and the room to match: 500 patterns a market, 100 portfolios, 500 tracked opportunities, and the live weekly Zoom. Everything you'd saved is right where you left it. This is the full toolkit, no corners cut.",
    },
  },
};

// Map a subscriptionEvent to the copy block key. new_signup uses the 'new'
// block in the matrix above; upgrade/downgrade use their own keys.
const EVENT_BLOCK = { new_signup: 'new', upgrade: 'upgrade', downgrade: 'downgrade' };

// Eyebrow text per event (per component_spec).
const EYEBROW = { new_signup: 'WELCOME', upgrade: "YOU'VE UPGRADED", downgrade: 'PLAN UPDATED' };

// Caps plan label for the tier badge.
const PLAN_LABEL = {
  'explorer-trial': 'EXPLORER TRIAL',
  explorer: 'EXPLORER',
  navigator: 'NAVIGATOR',
  analyst: 'ANALYST',
  strategist: 'STRATEGIST',
};

// Tier rank for upgrade vs downgrade (low -> high).
const TIER_RANK = { explorer: 0, navigator: 1, analyst: 2, strategist: 3 };
const PAID_TIERS = { navigator: true, analyst: true, strategist: true };

// ---------------------------------------------------------------------
// Guarded window-global readers - never throw.
// ---------------------------------------------------------------------
const winGet = (name) => {
  try {
    return (typeof window !== 'undefined') ? window[name] : undefined;
  } catch (e) { return undefined; }
};

// Resolve the copy entry for a (tier, event). The 'explorer' downgrade/cancel
// case maps to the 'explorer-trial' copy block. Falls back to a neutral object
// so a missing tier/event never crashes the render.
const resolveCopy = (tier, event) => {
  const NEUTRAL = { headline: 'Welcome to TradeWave', body: 'You are all set. Jump into the markets whenever you are ready.' };
  try {
    const block = EVENT_BLOCK[event] || 'new';
    // 'explorer' (free, post-cancel/downgrade) selects the explorer-trial copy.
    const tierKey = (tier === 'explorer') ? 'explorer-trial' : tier;
    const tierEntry = COPY[tierKey];
    if (!tierEntry) return NEUTRAL;
    const c = tierEntry[block];
    if (!c || !c.headline) return NEUTRAL;
    return { headline: c.headline, body: c.body || NEUTRAL.body };
  } catch (e) { return NEUTRAL; }
};

const resolveUnlocks = (tier) => {
  try {
    const tierKey = (tier === 'explorer') ? 'explorer-trial' : tier;
    const tierEntry = COPY[tierKey];
    return (tierEntry && tierEntry.unlocks) ? tierEntry.unlocks : '';
  } catch (e) { return ''; }
};

// =====================================================================
// decideSubscriptionWelcome - the trigger. STAGE-1 SAFE: upgrade/downgrade
// stays dormant until window.tw2_user_tier_actual ships (server change).
// Returns { show, tier, event }. Wrapped in try/catch -> { show:false }.
// =====================================================================
export const decideSubscriptionWelcome = () => {
  try {
    const ACTUAL = winGet('tw2_user_tier_actual');           // may be undefined (stage 1)
    const EFFECTIVE = winGet('tw2_user_tier');
    const onTrial = !!winGet('tw2_trial_ends_at');
    const resolved = ACTUAL || EFFECTIVE;                     // degrade to effective pre-deploy

    let params;
    try {
      params = new URLSearchParams((typeof window !== 'undefined' && window.location ? window.location.search : '') || '');
    } catch (e) { params = new URLSearchParams(''); }

    // Strip a one-shot query param so a refresh does not re-fire.
    const stripParam = (key) => {
      try {
        if (typeof window === 'undefined' || !window.history || !window.history.replaceState) return;
        const u = new URL(window.location.href);
        u.searchParams.delete(key);
        window.history.replaceState({}, document.title, u.pathname + (u.search ? u.search : '') + (u.hash || ''));
      } catch (e) { /* no-op */ }
    };

    // (1) explicit trial welcome from the Stripe redirect.
    if (params.get('welcome') === 'trial') {
      stripParam('welcome');
      return { show: true, tier: 'explorer-trial', event: 'new_signup' };
    }

    // (2) explicit paid welcome from the Stripe redirect.
    if (params.get('upgraded') === '1') {
      stripParam('upgraded');
      return { show: true, tier: resolved || 'explorer', event: 'new_signup' };
    }

    const LAST = lsGet('tw_last_welcomed_tier', null);        // {tier, wasTrial} | null

    // ---- first-ever welcome (no LAST record) ----
    if (!LAST) {
      // (3) active reverse trial -> trial welcome.
      if (onTrial) {
        return { show: true, tier: 'explorer-trial', event: 'new_signup' };
      }
      // (4) a paid tier, not on trial, with NO subscribe signal (the ?upgraded param is
      // handled above) is an EXISTING payer on first run - do NOT show a spurious welcome.
      // The caller records the tier silently so a later real upgrade/downgrade is detected.
      if (resolved && PAID_TIERS[resolved] && !onTrial) {
        return { show: false, tier: resolved, event: 'new_signup' };
      }
      // free/expired, no trial -> not a welcome moment.
      return { show: false, tier: resolved || 'explorer', event: 'new_signup' };
    }

    // ---- upgrade / downgrade branch ----
    // STAGE-1 GUARD: requires the raw DB tier global to be DEFINED. Until the
    // server ships window.tw2_user_tier_actual we never emit upgrade/downgrade
    // (effective tier is trial-elevated and would misfire).
    if (typeof ACTUAL === 'undefined' || ACTUAL === null || ACTUAL === '') {
      return { show: false, tier: resolved || 'explorer', event: 'upgrade' };
    }

    // Canceled subscription -> back to free Explorer.
    if (ACTUAL === 'canceled') {
      if (LAST.tier === 'explorer' || LAST.tier === 'canceled') return { show: false, tier: 'explorer', event: 'downgrade' };
      return { show: true, tier: 'explorer', event: 'downgrade' };
    }

    const lastTier = LAST.tier || 'explorer';
    if (ACTUAL === lastTier) {
      return { show: false, tier: ACTUAL, event: 'upgrade' };  // same tier seen twice -> idempotent
    }

    const actualRank = (ACTUAL in TIER_RANK) ? TIER_RANK[ACTUAL] : 0;
    const lastRank = (lastTier in TIER_RANK) ? TIER_RANK[lastTier] : 0;

    if (actualRank > lastRank) {
      return { show: true, tier: ACTUAL, event: 'upgrade' };
    }

    // actualRank < lastRank: a downgrade UNLESS it is a trial->paid conversion
    // (LAST was a trial-elevated strategist and ACTUAL is now a real paid tier).
    const trialToPaid = !!(LAST.wasTrial && lastTier === 'strategist' && PAID_TIERS[ACTUAL]);
    if (trialToPaid) {
      return { show: true, tier: ACTUAL, event: 'upgrade' };
    }
    return { show: true, tier: ACTUAL, event: 'downgrade' };
  } catch (e) {
    return { show: false };
  }
};

// =====================================================================
// markSubscriptionWelcomed - record the last-welcomed tier (user-scoped via
// lsSet). Stores {tier, wasTrial} so a trial-strategist does not later read
// as a downgrade when the user converts to a real paid tier. Guarded.
// =====================================================================
export const markSubscriptionWelcomed = () => {
  try {
    const tier = winGet('tw2_user_tier_actual') || winGet('tw2_user_tier') || 'explorer';
    const wasTrial = !!winGet('tw2_trial_ends_at');
    lsSet('tw_last_welcomed_tier', { tier, wasTrial });
  } catch (e) { /* no-op */ }
};

// =====================================================================
// SubscriptionWelcomeModal - the presentation surface.
// =====================================================================
const SubscriptionWelcomeModal = (props) => {
  // ---- defensive prop extraction (never throw on a bad/missing prop) ----
  const UITheme = props ? props.UITheme : undefined;
  const rdd = props ? props.rdd : undefined;
  const tier = props ? props.tier : undefined;
  const subscriptionEvent = props ? props.subscriptionEvent : undefined;
  const onClose = (props && typeof props.onClose === 'function') ? props.onClose : (() => {});

  // Escape closes (parity with OnboardingWelcome). Registered before any
  // early return so the hook order stays stable across renders.
  useEffect(() => {
    const onKey = (e) => { try { if (e && e.key === 'Escape') onClose(); } catch (err) { /* no-op */ } };
    try { document.addEventListener('keydown', onKey); } catch (e) { /* no-op */ }
    return () => { try { document.removeEventListener('keydown', onKey); } catch (e) { /* no-op */ } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // EVERYTHING below is wrapped so any unexpected error returns null (no-op)
  // rather than white-screening the app.
  try {
    const event = (subscriptionEvent && EVENT_BLOCK[subscriptionEvent]) ? subscriptionEvent : 'new_signup';
    const isDowngrade = event === 'downgrade';

    const isMobile = !!(rdd && rdd.isMobile && !rdd.isTablet);
    const tc = themeColors(UITheme) || {};

    const copy = resolveCopy(tier, event);
    const headline = copy.headline || 'Welcome to TradeWave';
    const body = copy.body || '';
    const eyebrow = EYEBROW[event] || 'WELCOME';
    const planLabel = PLAN_LABEL[tier] || 'TRADEWAVE';
    // "what you unlocked" line: only for new_signup/upgrade, never downgrade.
    const unlocks = isDowngrade ? '' : resolveUnlocks(tier);

    // ---- palette (LessonBox C tokens; premium dark, theme-independent) ----
    const C = {
      panel: '#15111E',
      panelGrad: 'linear-gradient(180deg,#1E1830 0%,#15111E 60%,#130F1B 100%)',
      plateGrad: 'linear-gradient(180deg,#1F1A2C,#1A1626)',
      well: '#120E1A',
      text: '#F2EFF8',
      textDim: '#B8B2C8',
      textLabel: '#8A8399',
      textFaint: '#635D74',
      accentText: '#C9B8FF',
      violet: 'rgb(167,139,250)',
      violetBright: '#C4B2FF',
      violetDeep: '#7C5CE0',
      cyan: '#6EE7F0',
      ink: '#14101F',
      edge: 'rgba(167,139,250,0.22)',
      hair: 'rgba(255,255,255,0.06)',
      divider: 'rgba(167,139,250,0.12)',
      border: tc.border || 'rgb(50, 47, 62)',
    };
    const MONO = '"SF Mono", ui-monospace, "JetBrains Mono", "Roboto Mono", Menlo, Consolas, monospace';
    const SANS = '"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif';

    const keyframes =
      '@keyframes twSwFade{from{opacity:0}to{opacity:1}}' +
      '@keyframes twSwRise{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}' +
      '@keyframes twSwLed{0%,100%{opacity:.45}50%{opacity:1}}' +
      '.tw-sw-primary:hover{filter:brightness(1.07);transform:translateY(-1px)}' +
      '.tw-sw-secondary:hover{color:' + C.text + ';border-color:' + C.edge + '}' +
      '.tw-sw-x:hover{background:rgba(167,139,250,0.32)}' +
      '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}';

    // ---- handlers ----
    // PRIMARY for new_signup/upgrade hands off to the LessonBox arc.
    const onPrimary = () => {
      try {
        onClose();
        if (!isDowngrade && typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
          window.dispatchEvent(new CustomEvent('tw-lessonbox-open'));
        }
      } catch (e) { /* no-op */ }
    };
    const onSecondary = () => { try { onClose(); } catch (e) { /* no-op */ } };

    const primaryLabel = isDowngrade
      ? 'Got It'
      : (event === 'new_signup' && tier === 'explorer-trial' ? 'Start the 7-Day Lessons' : 'Show Me Around');

    // ---- styles ----
    const coverStyle = {
      position: 'fixed',
      inset: 0,
      zIndex: 10000,
      backgroundColor: 'rgba(10,10,14,0.72)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: isMobile ? '16px' : '24px',
      animation: 'twSwFade 220ms ease-out',
      fontFamily: SANS,
    };

    const cardStyle = {
      position: 'relative',
      width: 'clamp(280px, 92vw, 460px)',
      maxWidth: '92vw',
      boxSizing: 'border-box',
      overflow: 'hidden',
      background: C.panelGrad,
      color: C.text,
      border: '1px solid ' + C.edge,
      borderRadius: '18px',
      padding: isMobile ? '24px 20px 22px' : '30px 32px 26px',
      boxShadow: '0 0 0 1px rgba(167,139,250,0.10),0 28px 80px -12px rgba(124,92,224,0.45),0 14px 40px rgba(0,0,0,0.70),inset 0 1px 0 rgba(255,255,255,0.07)',
      filter: 'drop-shadow(0 0 24px rgba(167,139,250,0.25))',
      animation: 'twSwRise 300ms cubic-bezier(0.16,0.84,0.44,1)',
      display: 'flex',
      flexDirection: 'column',
    };

    const closeBtnStyle = {
      position: 'absolute',
      top: '14px',
      right: '14px',
      width: '28px',
      height: '28px',
      borderRadius: '8px',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(167,139,250,0.14)',
      border: '1px solid ' + C.edge,
      color: C.text,
      fontSize: '18px',
      lineHeight: 1,
      cursor: 'pointer',
      padding: 0,
    };

    return (
      <div
        style={coverStyle}
        role="dialog"
        aria-modal="true"
        aria-label={headline}
        onClick={(e) => { if (e.target === e.currentTarget) onSecondary(); }}
      >
        <style>{keyframes}</style>

        <div style={cardStyle}>
          {/* mesh overlay: violet/cyan corner blooms (above background, below content) */}
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', borderRadius: '18px', mixBlendMode: 'screen', opacity: 0.9, background: 'radial-gradient(120% 80% at 15% 0%, rgba(167,139,250,0.14), transparent 55%), radial-gradient(100% 70% at 100% 0%, rgba(110,231,240,0.06), transparent 50%)' }} />

          {/* top-right close glyph */}
          <button
            type="button"
            className="tw-sw-x"
            style={closeBtnStyle}
            onClick={onSecondary}
            title="Close"
            aria-label="Close"
          >&times;</button>

          <div style={{ position: 'relative' }}>
            {/* eyebrow + plan badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', paddingRight: '36px', flexWrap: 'wrap' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '4px 10px',
                borderRadius: '999px', background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.30)',
              }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: C.violetBright, boxShadow: '0 0 8px ' + C.violetBright, animation: 'twSwLed 2.4s ease-in-out infinite' }} />
                <span style={{ fontFamily: MONO, fontSize: '10px', fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: C.accentText }}>
                  {eyebrow}
                </span>
              </span>
              <span style={{ fontFamily: MONO, fontSize: '10px', fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: C.textLabel }}>
                {planLabel}
              </span>
            </div>

            {/* headline */}
            <h2 style={{ margin: '0 0 12px', fontSize: isMobile ? '22px' : '24px', fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.2, color: C.text }}>
              {headline}
            </h2>

            {/* body */}
            {body ? (
              <p style={{ margin: 0, fontSize: '15px', lineHeight: 1.5, color: C.textDim }}>
                {body}
              </p>
            ) : null}

            {/* optional one-line "what you unlocked" (omitted on downgrade) */}
            {unlocks ? (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: '9px', marginTop: '16px',
                padding: '11px 13px', borderRadius: '10px', background: C.well,
                border: '1px solid ' + C.edge, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
              }}>
                <span style={{ flexShrink: 0, width: '2px', alignSelf: 'stretch', borderRadius: '1px', background: 'linear-gradient(180deg,' + C.violetBright + ',' + C.violet + ')' }} />
                <span style={{ fontSize: '13px', lineHeight: 1.45, color: C.accentText }}>{unlocks}</span>
              </div>
            ) : null}

            {/* CTAs */}
            <div style={{
              display: 'flex',
              flexDirection: isMobile ? 'column' : 'row-reverse',
              alignItems: isMobile ? 'stretch' : 'center',
              gap: '10px',
              marginTop: '22px',
            }}>
              <button
                type="button"
                className="tw-sw-primary"
                onClick={onPrimary}
                style={{
                  background: 'linear-gradient(135deg,' + C.violet + ',' + C.violetDeep + ')',
                  color: C.ink,
                  border: 'none',
                  borderRadius: '9px',
                  padding: '11px 20px',
                  fontSize: '14px',
                  fontWeight: 700,
                  boxShadow: '0 2px 12px rgba(124,92,224,0.40)',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                {primaryLabel}
              </button>

              {/* SECONDARY - omitted on downgrade */}
              {!isDowngrade ? (
                <button
                  type="button"
                  className="tw-sw-secondary"
                  onClick={onSecondary}
                  style={{
                    background: 'transparent',
                    border: '1px solid ' + C.hair,
                    color: C.textDim,
                    borderRadius: '9px',
                    padding: '11px 18px',
                    fontSize: '14px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Explore on My Own
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  } catch (e) {
    // Defensive: never white-screen the app on a render error.
    return null;
  }
};

export default SubscriptionWelcomeModal;
