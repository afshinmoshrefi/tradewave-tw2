import React from 'react';
import { themeColors } from './Common';

// DaysRemainingPill - a tiny, calm, monochrome capsule that counts what the
// user still HAS during a reverse trial. It never threatens, never tick-counts.
// "Day {n} of {totalDays}", with a soft amber tint only in the final stretch
// (daysRemaining <= 2). Renders nothing when there is no affirmative trial-end
// (daysRemaining == null), so a payer never sees a clock.
//
// Props:
//   UITheme        'dark' | 'light'
//   daysRemaining  number | null  - days of full access left (null = silent)
//   totalDays      number         - trial length, default 7
//   onClick        () => void     - opens Tara's usage summary
//
// Voice: AP Title Case, no terminal period, no em-dashes (" - " separators).

function DaysRemainingPill({ UITheme, daysRemaining, totalDays = 7, onClick }) {
  // Default-to-silent on ambiguous / absent state.
  if (daysRemaining === null || daysRemaining === undefined) return null;

  const tc = themeColors(UITheme);

  // Clamp into a sane range so the "Day N of M" math never reads wrong.
  const remaining = Math.max(0, Math.min(totalDays, daysRemaining));
  const dayNumber = Math.max(1, Math.min(totalDays, totalDays - remaining + 1));

  // Soft amber only in the final stretch; otherwise calm monochrome.
  const isAmber = remaining <= 2;
  const amber = 'rgb(217, 169, 92)';      // muted, desaturated amber
  const amberBg = 'rgba(217, 169, 92, 0.12)';
  const amberBorder = 'rgba(217, 169, 92, 0.45)';

  const label = `Day ${dayNumber} of ${totalDays}`;
  const title = `${remaining} ${remaining === 1 ? 'Day' : 'Days'} of Full Access Left`;

  const pillStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '3px 10px',
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 600,
    lineHeight: 1.4,
    letterSpacing: '0.02em',
    whiteSpace: 'nowrap',
    userSelect: 'none',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background 160ms ease, border-color 160ms ease, color 160ms ease',
    background: isAmber ? amberBg : (tc.statValueBg || 'rgb(35, 32, 48)'),
    border: `1px solid ${isAmber ? amberBorder : (tc.border || 'rgb(50, 47, 62)')}`,
    color: isAmber ? amber : (tc.textSecondary || 'rgb(180, 180, 190)'),
  };

  const dotStyle = {
    width: 5,
    height: 5,
    borderRadius: '50%',
    flexShrink: 0,
    background: isAmber ? amber : (tc.textSecondary || 'rgb(180, 180, 190)'),
    opacity: isAmber ? 0.9 : 0.55,
  };

  const onKeyDown = (e) => {
    if (!onClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick(e);
    }
  };

  return (
    <span
      style={pillStyle}
      title={title}
      aria-label={`${label}. ${title}`}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <span style={dotStyle} aria-hidden="true" />
      {label}
    </span>
  );
}

export default DaysRemainingPill;
