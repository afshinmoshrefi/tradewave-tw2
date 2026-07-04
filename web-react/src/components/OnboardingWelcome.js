import React, { useState, useRef, useEffect } from 'react'
import { themeColors } from './Common'
import { logEvent, TIER_INFO } from './onboarding'

// ---------------------------------------------------------------------------
// OnboardingWelcome
// One centered dark modal fired once on first post-subscribe load (the cookie
// gating + render decision live in App.js / onboarding.js; this component is the
// pure presentation + interaction surface).
//
// Two variants, selected by onTrial / tier:
//   TRIAL  -> "You're In - 7 Days of Full Access" + the score-a-stock CTA.
//   PAID   -> "Welcome to {Tier}" congratulating the plan, NO trial/clock copy,
//             NO card mention. Same inline ticker score CTA, no "Just browse".
//
// It does NOT lead with a demo: the inline ticker input IS the first action, so
// the user's own symbol is the wow, never a canned reel.
//
// Props:
//   UITheme        'dark' | 'light' (we are premium-dark either way)
//   rdd            { isMobile, isTablet } responsive descriptor
//   tier           'explorer' | 'navigator' | 'analyst' | 'strategist'
//   onTrial        bool - true while a reverse trial is active
//   onScoreStock   (symbol:string) => void - route to the Opp Table on that symbol
//   onJustBrowse   () => void - sets tw_welcomed, drops to Stocks-Scored view
//   onSkipTips     () => void - sets tw_onboard_dismissed, stops the whole arc
//   onClose        () => void - dismiss the modal (sets tw_welcomed)
// ---------------------------------------------------------------------------
const OnboardingWelcome = (props) => {
  const { UITheme, rdd, tier, onTrial, onScoreStock, onJustBrowse, onSkipTips, onClose } = props
  const tc = themeColors(UITheme)

  const isMobile = rdd && rdd.isMobile && !rdd.isTablet

  const [symbol, setSymbol] = useState('')
  const inputRef = useRef(null)

  // Telemetry (de-duped across remounts so an unrelated popup opening over us can't
  // double-log), auto-focus the ticker input, and Escape-to-close.
  useEffect(() => {
    if (!window.__twWelcomeShownLogged) {
      window.__twWelcomeShownLogged = true
      logEvent('persona', { stage: 'welcome_shown', tier, on_trial: !!onTrial })
    }
    if (!isMobile && inputRef.current) inputRef.current.focus()
    const onKey = (e) => { if (e.key === 'Escape' && typeof onClose === 'function') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- copy (variant-aware) --------------------------------------------------
  // PAID: congratulate the plan, no trial/clock/card language.
  const info = TIER_INFO && TIER_INFO[tier] ? TIER_INFO[tier] : { markets: 'your markets' }
  const tierLabel = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : 'TradeWave'

  const headline = onTrial
    ? "You're In - 7 Days of Full Access"
    : `Welcome to ${tierLabel}`

  // Bodies kept under 35 words, no em-dashes, AP-voice, confident evidence.
  const body = onTrial
    ? "Type any ticker and I'll score it against ~98 years - good window, bad window, or noise. No card. Your real usage decides which plan (if any) you actually need."
    : `${info.markets}, AI-scored - score your first stock and read the per-year record yourself.`

  // ---- handlers --------------------------------------------------------------
  const submitSymbol = () => {
    const clean = (symbol || '').trim().toUpperCase()
    if (!clean) {
      // Empty submit just focuses the input (primary button doubles as focus).
      if (inputRef.current) inputRef.current.focus()
      return
    }
    logEvent('symbol_scored', { symbol: clean, source: 'welcome', on_trial: !!onTrial })
    if (typeof onScoreStock === 'function') onScoreStock(clean)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      submitSymbol()
    }
  }

  const handleJustBrowse = () => {
    logEvent('persona', { stage: 'welcome_just_browse' })
    if (typeof onJustBrowse === 'function') onJustBrowse()
  }

  const handleSkipTips = () => {
    logEvent('persona', { stage: 'welcome_skip_tips' })
    if (typeof onSkipTips === 'function') onSkipTips()
    else if (typeof onClose === 'function') onClose()
  }

  // ---- sizing (responsive via rdd) ------------------------------------------
  // Full-screen-ish on mobile, centered card on desktop/tablet.
  const cardW = isMobile ? '92vw' : (rdd && rdd.isTablet ? '60vw' : '34rem')
  const cardMaxW = isMobile ? '92vw' : '34rem'
  const cardPad = isMobile ? '22px 20px 24px' : '32px 34px 30px'
  const headlineSize = isMobile ? '1.45rem' : '1.6rem'
  const bodySize = isMobile ? '0.95rem' : '1rem'

  // ---- styles ----------------------------------------------------------------
  const coverStyle = {
    position: 'fixed',
    inset: 0,
    zIndex: 10000,
    backgroundColor: 'rgba(8, 5, 13, 0.72)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: isMobile ? '16px' : '24px',
    animation: 'twOnboardFade 220ms ease-out',
  }

  const cardStyle = {
    position: 'relative',
    width: cardW,
    maxWidth: cardMaxW,
    boxSizing: 'border-box',
    backgroundColor: tc.panelBg || 'rgb(30, 27, 42)',
    color: tc.text || 'rgb(220, 220, 225)',
    border: '1px solid ' + (tc.border || 'rgb(50, 47, 62)'),
    borderRadius: '14px',
    padding: cardPad,
    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.55)',
    display: 'flex',
    flexDirection: 'column',
    animation: 'twOnboardRise 260ms cubic-bezier(0.16, 0.84, 0.44, 1)',
  }

  const skipStyle = {
    position: 'absolute',
    top: '12px',
    right: '14px',
    fontSize: '0.8rem',
    color: tc.textSecondary || 'rgb(150, 148, 160)',
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    padding: '4px 6px',
    letterSpacing: '0.01em',
  }

  const headlineStyle = {
    margin: onTrial ? '6px 0 0' : '6px 0 0',
    paddingRight: '52px', // clear the Skip control
    fontSize: headlineSize,
    fontWeight: 700,
    lineHeight: 1.18,
    color: tc.text || 'rgb(220, 220, 225)',
  }

  const bodyStyle = {
    margin: '12px 0 0',
    fontSize: bodySize,
    lineHeight: 1.5,
    color: tc.textSecondary || 'rgb(190, 188, 200)',
  }

  const inputWrapStyle = {
    display: 'flex',
    gap: '8px',
    marginTop: '20px',
    flexDirection: isMobile ? 'column' : 'row',
  }

  const inputStyle = {
    flex: 1,
    minWidth: 0,
    boxSizing: 'border-box',
    backgroundColor: tc.inputBg || 'rgb(40, 37, 52)',
    color: tc.text || 'rgb(220, 220, 225)',
    border: '1px solid ' + (tc.inputBorder || 'rgb(70, 67, 82)'),
    borderRadius: '9px',
    padding: '12px 14px',
    fontSize: '1rem',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    outline: 'none',
  }

  const primaryBtnStyle = {
    flexShrink: 0,
    background: 'linear-gradient(135deg, rgb(167, 139, 250), rgb(129, 104, 215))',
    color: 'rgb(18, 14, 26)',
    border: 'none',
    borderRadius: '9px',
    padding: isMobile ? '12px 16px' : '12px 20px',
    fontSize: '0.98rem',
    fontWeight: 700,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  }

  const secondaryRowStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '18px',
    marginTop: '18px',
    paddingTop: '16px',
    borderTop: '1px solid ' + (tc.borderLight || 'rgb(40, 37, 52)'),
  }

  const secondaryBtnStyle = {
    background: 'transparent',
    border: 'none',
    color: tc.textSecondary || 'rgb(170, 168, 180)',
    fontSize: '0.9rem',
    cursor: 'pointer',
    padding: 0,
  }

  const hintStyle = {
    marginTop: '10px',
    fontSize: '0.78rem',
    color: tc.textSecondary || 'rgb(140, 138, 150)',
    opacity: 0.75,
  }

  // ---------------------------------------------------------------------------
  return (
    <div style={coverStyle} role="dialog" aria-modal="true" aria-label={headline}
      onClick={(e) => { if (e.target === e.currentTarget && typeof onClose === 'function') onClose() }}>
      <style>{
        '@keyframes twOnboardFade{from{opacity:0}to{opacity:1}}' +
        '@keyframes twOnboardRise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}' +
        '.tw-onboard-skip:hover{color:rgb(210,206,220)}' +
        '.tw-onboard-secondary:hover{color:rgb(210,206,220)}' +
        '.tw-onboard-primary:hover{filter:brightness(1.06)}'
      }</style>

      <div style={cardStyle}>
        {/* Quiet top-right Skip tips (permanent dismiss of the whole arc). */}
        <button
          type="button"
          className="tw-onboard-skip"
          style={skipStyle}
          onClick={handleSkipTips}
          title="Turn off onboarding tips"
        >
          Skip tips
        </button>

        <h2 style={headlineStyle}>{headline}</h2>
        <p style={bodyStyle}>{body}</p>

        <div style={inputWrapStyle}>
          <input
            ref={inputRef}
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ticker - e.g. NVDA"
            aria-label="Stock ticker symbol"
            autoComplete="off"
            spellCheck={false}
            maxLength={12}
            style={inputStyle}
          />
          <button
            type="button"
            className="tw-onboard-primary"
            style={primaryBtnStyle}
            onClick={submitSymbol}
          >
            Score a Stock
          </button>
        </div>

        {onTrial
          ? (
            <div style={secondaryRowStyle}>
              <button
                type="button"
                className="tw-onboard-secondary"
                style={secondaryBtnStyle}
                onClick={handleJustBrowse}
              >
                Just browse
              </button>
            </div>
          )
          : (
            <p style={hintStyle}>
              {info.markets}, AI-scored. Type a symbol above to read its per-year record.
            </p>
          )
        }
      </div>
    </div>
  )
}

export default OnboardingWelcome
