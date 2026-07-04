import React, { useEffect, useState } from 'react';
import { themeColors } from './Common';
import { fetchUsageSummary, logEvent, TIER_INFO } from './onboarding';

// =====================================================================
// TrialConversionCard - the end-of-trial trust-signal card ("Your 7 Days,
// Measured"). It LEADS with the down-rec (the cheapest tier that covers the
// user's real, logged usage) and names what NOT to buy, because the product
// shows its work - including when the honest answer is "you don't need more."
//
// On mount it calls fetchUsageSummary() and renders:
//   - the recommended_tier as the ONE highlighted primary button,
//   - the other tiers secondary, each with a plain "why you don't need this",
//   - monthly as the visible default, with a quiet "save with yearly" note,
//   - an HONESTY GATE on the word "measured": if summary.measured is false
//     (or the summary is null) the copy hedges truthfully and never claims a
//     number it cannot produce.
//
// If recommended_tier === 'explorer': the gracious "free Explorer is enough"
// keep-it line, no card-required upsell.
//
// If nonConverter (trial already lapsed to Explorer): the gracious drop line
// instead of any rec - "Everything you saved is still here."
//
// Props:
//   UITheme       'dark' | 'light'
//   rdd           { isMobile, isTablet }  - responsive flags
//   onClose       () => void              - dismiss the card
//   onPick        (tier:string) => void   - user chose a tier to upgrade to
//   nonConverter  boolean                 - trial lapsed; show the Explorer grace line
//
// Voice: AP Title Case headlines, no terminal period, no em-dashes (" - ").
// =====================================================================

const TIER_ORDER = ['explorer', 'navigator', 'analyst', 'strategist'];
const TIER_LABEL = {
  explorer: 'Explorer',
  navigator: 'Navigator',
  analyst: 'Analyst',
  strategist: 'Strategist',
};

const ACCENT = 'rgb(167, 139, 250)';            // calm violet
const ACCENT_SOFT = 'rgba(167, 139, 250, 0.14)';
const ACCENT_BORDER = 'rgba(167, 139, 250, 0.55)';

// Human-join a list with serial-style "and": [] -> '', [a] -> 'a',
// [a,b] -> 'a and b', [a,b,c] -> 'a, b and c'. No Oxford comma (house voice).
function joinAnd(items) {
  const list = (items || []).filter(Boolean);
  if (list.length === 0) return '';
  if (list.length === 1) return list[0];
  if (list.length === 2) return `${list[0]} and ${list[1]}`;
  return `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`;
}

// Plain "why you don't need this yet" line for a tier the user is NOT being
// recommended (only shown for tiers ABOVE the recommendation).
function whyNotNeeded(tier) {
  switch (tier) {
    case 'navigator':
      return 'Adds Dow, NASDAQ and S&P 500 - your week did not need more than the Dow 30.';
    case 'analyst':
      return 'Adds Russell, Wilshire, ETFs and indices - you never opened those.';
    case 'strategist':
      return 'Adds futures, forex, bonds and crypto - nothing in your week touched them.';
    default:
      return '';
  }
}

function TrialConversionCard({ UITheme, rdd, onClose, onPick, nonConverter }) {
  const tc = themeColors(UITheme);

  const [loading, setLoading] = useState(!nonConverter);
  const [error, setError] = useState(false);
  const [summary, setSummary] = useState(null);

  const isMobile = !!(rdd && rdd.isMobile && !rdd.isTablet);

  // --- Telemetry: the card was shown (de-duped across remounts) ------
  useEffect(() => {
    if (window.__twConvViewLogged) return;
    window.__twConvViewLogged = true;
    logEvent('report_view', { surface: 'trial_conversion', nonConverter: !!nonConverter });
  }, [nonConverter]);

  // Escape closes the card.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && typeof onClose === 'function') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Load the usage summary (skip entirely for the non-converter) --
  useEffect(() => {
    if (nonConverter) return;
    let alive = true;
    setLoading(true);
    setError(false);
    fetchUsageSummary()
      .then((data) => {
        if (!alive) return;
        if (!data) { setError(true); setLoading(false); return; }
        setSummary(data);
        setLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setError(true);
        setLoading(false);
      });
    return () => { alive = false; };
  }, [nonConverter]);

  // ------------------------------------------------------------------
  // Shared chrome (overlay + centered card), so loading/error/content
  // all read as the same InfoPopup-style dark moment.
  // ------------------------------------------------------------------
  const overlayStyle = {
    position: 'fixed',
    inset: 0,
    background: 'rgba(8, 5, 12, 0.66)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10000,
    padding: isMobile ? 12 : 24,
    animation: 'twConvFade 220ms ease',
  };

  const cardStyle = {
    width: '100%',
    maxWidth: isMobile ? 420 : 560,
    maxHeight: '90vh',
    overflowY: 'auto',
    background: tc.panelBg || 'rgb(30, 27, 42)',
    color: tc.text || 'rgb(220, 220, 225)',
    border: `1px solid ${tc.border || 'rgb(50, 47, 62)'}`,
    borderRadius: 14,
    padding: isMobile ? '22px 20px 20px' : '30px 32px 26px',
    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.55)',
    position: 'relative',
    animation: 'twConvRise 260ms cubic-bezier(0.2, 0.7, 0.3, 1)',
  };

  const closeBtnStyle = {
    position: 'absolute',
    top: 12,
    right: 14,
    background: 'transparent',
    border: 'none',
    color: tc.textSecondary || 'rgb(180, 180, 190)',
    fontSize: 20,
    lineHeight: 1,
    cursor: 'pointer',
    padding: 4,
    opacity: 0.7,
  };

  const keyframes = (
    <style>{`
      @keyframes twConvFade { from { opacity: 0; } to { opacity: 1; } }
      @keyframes twConvRise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    `}</style>
  );

  // A render FUNCTION (not a component) so loading/error/content transitions do NOT remount
  // the dialog subtree and re-fire the entry animation each time. Backdrop click closes.
  const shell = (children) => (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-label="Your trial summary"
      onClick={(e) => { if (e.target === e.currentTarget && typeof onClose === 'function') onClose(); }}>
      {keyframes}
      <div style={cardStyle}>
        <button type="button" style={closeBtnStyle} aria-label="Close" onClick={onClose}>
          &times;
        </button>
        {children}
      </div>
    </div>
  );

  // ==================================================================
  // 1) NON-CONVERTER - trial already lapsed to Explorer. Gracious only.
  // ==================================================================
  if (nonConverter) {
    return (
      shell(<>
        <div style={{ fontSize: isMobile ? 19 : 22, fontWeight: 700, lineHeight: 1.25, marginBottom: 14, paddingRight: 24 }}>
          You're On Explorer Now, Free Forever
        </div>
        <p style={{ fontSize: isMobile ? 14 : 15, lineHeight: 1.6, color: tc.textSecondary || 'rgb(180, 180, 190)', margin: '0 0 10px' }}>
          Your full access wrapped up - you're on Explorer now (the Dow 30, free, forever).
          Everything you saved is still here.
        </p>
        <p style={{ fontSize: isMobile ? 14 : 15, lineHeight: 1.6, color: tc.textSecondary || 'rgb(180, 180, 190)', margin: '0 0 22px' }}>
          Upgrade anytime, one click - we'll reopen the exact plan that fit your usage.
        </p>
        <div style={{ display: 'flex', gap: 10, flexDirection: isMobile ? 'column' : 'row' }}>
          <button
            type="button"
            style={primaryBtnStyle(tc, isMobile)}
            onClick={() => { logEvent('report_view', { surface: 'trial_conversion', action: 'reopen_from_lapsed' }); onPick && onPick('navigator'); }}
          >
            Reopen Full Access
          </button>
          <button type="button" style={ghostBtnStyle(tc, isMobile)} onClick={onClose}>
            Keep Exploring
          </button>
        </div>
      </>)
    );
  }

  // ==================================================================
  // 2) LOADING
  // ==================================================================
  if (loading) {
    return (
      shell(<>
        <div style={{ fontSize: isMobile ? 19 : 22, fontWeight: 700, marginBottom: 16, paddingRight: 24 }}>
          Your 7 Days, In Review
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '18px 0', color: tc.textSecondary || 'rgb(180, 180, 190)' }}>
          <span style={spinnerStyle()} aria-hidden="true" />
          <span style={{ fontSize: 14 }}>Reading your week...</span>
        </div>
        <style>{`@keyframes twConvSpin { to { transform: rotate(360deg); } }`}</style>
      </>)
    );
  }

  // ==================================================================
  // 3) ERROR - summary unreachable. Stay honest: no rec, no claimed number.
  // ==================================================================
  if (error || !summary) {
    return (
      shell(<>
        <div style={{ fontSize: isMobile ? 19 : 22, fontWeight: 700, marginBottom: 14, paddingRight: 24 }}>
          Your Full Access Is Wrapping Up
        </div>
        <p style={{ fontSize: isMobile ? 14 : 15, lineHeight: 1.6, color: tc.textSecondary || 'rgb(180, 180, 190)', margin: '0 0 22px' }}>
          We couldn't pull your usage just now, so we won't guess which plan you need.
          Pick whichever fits, or stay on free Explorer (the Dow 30) - everything you
          saved stays here either way.
        </p>
        <div style={{ display: 'flex', gap: 10, flexDirection: isMobile ? 'column' : 'row' }}>
          <button type="button" style={primaryBtnStyle(tc, isMobile)} onClick={() => onPick && onPick('navigator')}>
            See the Plans
          </button>
          <button type="button" style={ghostBtnStyle(tc, isMobile)} onClick={onClose}>
            Stay on Explorer
          </button>
        </div>
      </>)
    );
  }

  // ==================================================================
  // 4) CONTENT - the trust-signal rec, led by the down-rec.
  // ==================================================================
  const measured = summary.measured === true;
  // Null/absent recommended_tier means NOTHING was logged - recommend the free floor
  // (Explorer), never a paid tier. Up-selling off zero signal is the opposite of the
  // card's honesty premise.
  const recTier = TIER_ORDER.includes(summary.recommended_tier) ? summary.recommended_tier : 'explorer';
  const recIdx = TIER_ORDER.indexOf(recTier);

  // Markets phrasing: prefer the human market_names the backend resolved;
  // fall back to the keys; tolerate either being absent.
  const marketNames = (summary.market_names && summary.market_names.length)
    ? summary.market_names
    : (summary.markets_used || []);
  const marketsPhrase = joinAnd(marketNames);

  // persona -> a short "short-term / long-term" flavor for the lead line.
  const persona = (summary.persona || 'neutral').toLowerCase();
  const horizonPhrase =
    persona === 'long' ? 'mostly longer-horizon positioning'
    : persona === 'short' ? 'mostly short-term setups'
    : '';

  // Higher tiers the user is being told NOT to buy.
  const higherTiers = TIER_ORDER.slice(recIdx + 1).filter((t) => t !== 'explorer');

  const recInfo = TIER_INFO[recTier] || {};
  const recPrice = recInfo.price || '';

  // --- The leading line. HONESTY GATE on "measured". ---------------
  let leadLine;
  if (recTier === 'explorer') {
    // Dow-30-only user - the gracious keep-it close, no card.
    leadLine = measured
      ? "Based on your 7 days, you only worked the Dow 30. Honestly, free Explorer is enough for you - keep it, no card."
      : "You spent your week on the Dow 30. Honestly, free Explorer is likely enough for you - keep it, no card.";
  } else {
    // A real up-rec to the cheapest covering tier.
    const usedClause = marketsPhrase
      ? (measured
          ? `you used ${marketsPhrase}${horizonPhrase ? `, ${horizonPhrase}` : ''}`
          : `you spent most of your week on ${marketsPhrase}${horizonPhrase ? `, ${horizonPhrase}` : ''}`)
      : (measured
          ? 'here is what your usage covers'
          : 'here is roughly what your week looked like');

    const intro = measured ? 'Based on your 7 days,' : 'From what we can see this week,';
    leadLine = `${intro} ${usedClause}. ${TIER_LABEL[recTier]} (${recPrice}) covers all of it`;

    if (higherTiers.length) {
      leadLine += ` - you don't need ${joinAnd(higherTiers.map((t) => TIER_LABEL[t]))}, and we'd rather tell you that than sell you more.`;
    } else {
      leadLine += " - it's the right fit, and we'd rather tell you that than sell you more.";
    }
  }

  // Optional depth note: a low-frequency, deep-history user routed up on
  // history depth rather than breadth gets a concrete reason.
  const maxYears = Number(summary.max_years) || 0;
  const depthNote = (recTier !== 'explorer' && maxYears >= 90)
    ? `You pulled ${maxYears}+ years of history - that depth, not extra markets, is what ${TIER_LABEL[recTier]} unlocks.`
    : '';

  return (
    shell(<>
      <div style={{ fontSize: isMobile ? 19 : 22, fontWeight: 700, lineHeight: 1.25, marginBottom: 6, paddingRight: 24 }}>
        {measured ? 'Your 7 Days, Measured' : 'Your 7 Days, In Plain Terms'}
      </div>
      {!measured && (
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: tc.textSecondary || 'rgb(180, 180, 190)', opacity: 0.7, marginBottom: 10 }}>
          Based on what we saw, not an exact count
        </div>
      )}

      <p style={{ fontSize: isMobile ? 14 : 15, lineHeight: 1.62, color: tc.text || 'rgb(220, 220, 225)', margin: '4px 0 14px' }}>
        {leadLine}
      </p>

      {depthNote && (
        <p style={{ fontSize: isMobile ? 13 : 14, lineHeight: 1.55, color: tc.textSecondary || 'rgb(180, 180, 190)', margin: '0 0 16px' }}>
          {depthNote}
        </p>
      )}

      {/* --- Tier choices: recommended primary, others secondary --- */}
      {recTier === 'explorer' ? (
        <div style={{ display: 'flex', gap: 10, flexDirection: isMobile ? 'column' : 'row', marginTop: 4 }}>
          <button type="button" style={primaryBtnStyle(tc, isMobile)} onClick={onClose}>
            Keep Explorer, Free
          </button>
          <button
            type="button"
            style={ghostBtnStyle(tc, isMobile)}
            onClick={() => { logEvent('report_view', { surface: 'trial_conversion', action: 'see_plans_from_explorer' }); onPick && onPick('navigator'); }}
          >
            See the Paid Plans
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
          {/* Recommended - the ONE highlighted button */}
          <button
            type="button"
            onClick={() => { logEvent('report_view', { surface: 'trial_conversion', action: 'pick', tier: recTier, recommended: true }); onPick && onPick(recTier); }}
            style={recBtnStyle(tc, isMobile)}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={recBadgeStyle()}>Recommended</span>
              <span style={{ fontWeight: 700 }}>{`Get ${TIER_LABEL[recTier]}`}</span>
            </span>
            <span style={{ fontWeight: 700, fontSize: isMobile ? 14 : 15 }}>{recPrice}</span>
          </button>

          {/* Quiet "save with yearly" - never annual-first */}
          <div style={{ fontSize: 12, color: tc.textSecondary || 'rgb(180, 180, 190)', opacity: 0.85, margin: '-2px 2px 6px' }}>
            Monthly, cancel anytime.{' '}
            <span
              style={{ color: ACCENT, cursor: 'pointer' }}
              onClick={() => { logEvent('report_view', { surface: 'trial_conversion', action: 'pick_yearly', tier: recTier }); onPick && onPick(`${recTier}:yearly`); }}
            >
              Save with yearly
            </span>
          </div>

          {/* Higher tiers - secondary, each with a plain "why you don't need this" */}
          {higherTiers.map((tier) => (
            <button
              key={tier}
              type="button"
              onClick={() => { logEvent('report_view', { surface: 'trial_conversion', action: 'pick', tier, recommended: false }); onPick && onPick(tier); }}
              style={secondaryTierBtnStyle(tc, isMobile)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontWeight: 600 }}>{TIER_LABEL[tier]}</span>
                <span style={{ fontSize: 13, color: tc.textSecondary || 'rgb(180, 180, 190)' }}>{(TIER_INFO[tier] || {}).price}</span>
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.45, color: tc.textSecondary || 'rgb(180, 180, 190)', opacity: 0.85, marginTop: 4, textAlign: 'left' }}>
                {whyNotNeeded(tier)}
              </div>
            </button>
          ))}
        </div>
      )}

      <div style={{ marginTop: 18, paddingTop: 14, borderTop: `1px solid ${tc.borderLight || 'rgb(40, 37, 52)'}`, fontSize: 12, color: tc.textSecondary || 'rgb(180, 180, 190)', opacity: 0.8 }}>
        Not now? You drop to free Explorer (the Dow 30) - everything you saved stays here, and you can reopen full access in one click.
      </div>
    </>)
  );
}

// ---------------------------------------------------------------------
// Button / element style helpers (kept out of render for readability).
// ---------------------------------------------------------------------
function primaryBtnStyle(tc, isMobile) {
  return {
    flex: 1,
    padding: isMobile ? '13px 16px' : '12px 20px',
    borderRadius: 10,
    border: 'none',
    cursor: 'pointer',
    fontSize: isMobile ? 15 : 14,
    fontWeight: 700,
    color: 'rgb(15, 10, 21)',
    background: `linear-gradient(135deg, ${ACCENT}, rgb(139, 110, 240))`,
  };
}

function ghostBtnStyle(tc, isMobile) {
  return {
    flex: 1,
    padding: isMobile ? '13px 16px' : '12px 20px',
    borderRadius: 10,
    border: `1px solid ${tc.border || 'rgb(50, 47, 62)'}`,
    cursor: 'pointer',
    fontSize: isMobile ? 15 : 14,
    fontWeight: 600,
    color: tc.textSecondary || 'rgb(180, 180, 190)',
    background: 'transparent',
  };
}

function recBtnStyle(tc, isMobile) {
  return {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    padding: isMobile ? '14px 16px' : '14px 18px',
    borderRadius: 11,
    border: `1px solid ${ACCENT_BORDER}`,
    background: ACCENT_SOFT,
    color: tc.text || 'rgb(220, 220, 225)',
    cursor: 'pointer',
    fontSize: isMobile ? 15 : 15,
    textAlign: 'left',
  };
}

function recBadgeStyle() {
  return {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    color: 'rgb(15, 10, 21)',
    background: ACCENT,
    padding: '2px 7px',
    borderRadius: 999,
    whiteSpace: 'nowrap',
  };
}

function secondaryTierBtnStyle(tc, isMobile) {
  return {
    width: '100%',
    display: 'block',
    padding: isMobile ? '12px 14px' : '11px 16px',
    borderRadius: 10,
    border: `1px solid ${tc.border || 'rgb(50, 47, 62)'}`,
    background: tc.statValueBg || 'rgb(35, 32, 48)',
    color: tc.text || 'rgb(220, 220, 225)',
    cursor: 'pointer',
    fontSize: isMobile ? 14 : 14,
  };
}

function spinnerStyle() {
  return {
    width: 18,
    height: 18,
    borderRadius: '50%',
    border: `2px solid ${ACCENT_SOFT}`,
    borderTopColor: ACCENT,
    display: 'inline-block',
    animation: 'twConvSpin 0.8s linear infinite',
  };
}

export default TrialConversionCard;
