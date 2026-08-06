import React, { useEffect, useContext, useRef, useMemo } from 'react'
import { UserContext } from './UserContext'
import { themeColors, tierHasAI } from './Common'
import { BsChevronExpand, BsChevronDown, BsChevronUp } from "react-icons/bs"
import Tippy from '@tippyjs/react'
import './styles/TableBox.css'
import jwt_decode from 'jwt-decode'
import OpportunityAICell from './OpportunityAICell'
import {
  AI_COLUMNS,
  AI_METRICS,
  hasAvailableOpportunityAIScores,
  normalizeOpportunityAIScore,
  opportunityAIFlatFields,
  opportunityAIHeaderColor,
  opportunityTableMinimumWidth,
  selectOpportunityVisibleColumns,
} from './opportunityAIScores'
import {
  analyzeOpportunityFilter,
  filterOpportunityRows,
  isOpportunityFilterPending,
  sortOpportunityRows,
} from './opportunityFilters'
import { hasUsableBatchTrendScore } from './trendScoreState'

// GTM playbook CARD W1.4 - fire once per browser session, the first time an
// AI-eligible user actually sees real AI-score data in the table. Module-level
// (not per-mount) so remounting TableBox (tab switches, filters) never re-fires
// within the same session; the server-side handler is ALSO idempotent
// (users.first_ai_score_viewed_at first-touch-only), so this is a courtesy
// dedupe, not the source of truth.
let _aiScoreViewedFiredThisSession = false

const AI_COLS = AI_COLUMNS
const DEFAULT_COLUMN_ORDER = ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'avg_profit', 'avg_profit2', 'sharpe_ratio2', 'TL', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe']
const PENDING_CELL = <span title="Loading" aria-label="Loading">…</span>

const TableBox = ({
  table_data,
  handlerRowClicked,
  handlerKeyDown,
  rowIndexClicked,
  SetRowIndexClicked,
  filterText,
  oppListExpanded,
  tooltipSW,
  SetOppTableLength,
  SetVisibleOpportunities,
  showSR2,
  showAciveOpps,
  upgradeMessage,
  promotionMessage,
  promotionCouponCode,
  promotionBackColor,
  showUpgradeBanner,
  SetShowUpgradeBanner,
  SetNumLongs,
  SetNumShorts,
  stockScores,
  mlScores,
  mlScoresLoading,
  mlPending,
  mlEnabled,
  mlMarketEligible,
  mlUnavailableReason,
  columnVisibility,
  columnOrder,
  shortDates,
  colSorted = 'sharpe_ratio',
  sortedDir = 'd',
  SetColSorted = () => {},
  SetSortedDir = () => {},
}) => {

  const { tableTextSize, tableTitleTextSize, wpUserLevels, loggedinUser, token, rdd, UITheme, SetDialogType, SetDialogProp, SetInfoBoxVisible } = useContext(UserContext)
  const tc = useMemo(() => themeColors(UITheme), [UITheme])
  // AI scoring is an Analyst+ feature; non-AI tiers see a single LOCKED "AI Score" teaser column.
  const hasAI = tierHasAI(wpUserLevels)
  const openAILockDialog = () => {
    SetDialogProp({
      title: 'See AI Scores',
      contentText: 'AI Scores use the latest completed stock and market data to estimate win chance, ending return, and the best move during the AI time window. They also include a 0-100 return rank. Available for U.S. stocks and ETFs on the Analyst plan and above.',
      button1Text: 'See Plans', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)'
    })
    SetDialogType('info-box')
    SetInfoBoxVisible(true)
  }

  const prevDataDepsRef = useRef('')
  const lastValidRowsRef = useRef([])
  const lastSourceRowsRef = useRef(table_data)

  if (lastSourceRowsRef.current !== table_data) {
    lastSourceRowsRef.current = table_data
    lastValidRowsRef.current = []
  }

  let rowHeight = '3vh'
  if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) {
    // smartphone portrait
  } else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) {
    // smartphone landscape
    rowHeight = '7vh'
  } else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) {
    // tablet portrait
  } else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) {
    // tablet landscape
  } else if (!rdd.isMobile) {
    // desktop
  }

  // Build visible columns list based on user-defined order and columnVisibility
  const hasMLData = hasAvailableOpportunityAIScores(mlScores)
  const hasOptedInAIColumn = AI_COLS.some(column => columnVisibility && columnVisibility[column] === true)
  // GTM playbook CARD W1.4 - Postgres activation signal. The first time this AI-eligible
  // user actually has real AI-score data on screen, tell the server (which stamps
  // users.first_ai_score_viewed_at idempotently, logs an onboarding_events row, and
  // fires the GA4 ai_score_viewed event - all in ONE handler, per the strategy §2
  // persistence rule). Fire-and-forget, same-origin authed fetch; never throws.
  useEffect(() => {
    if (!hasAI || !hasMLData || !hasOptedInAIColumn || _aiScoreViewedFiredThisSession) return;
    if (loggedinUser === '0') return;
    _aiScoreViewedFiredThisSession = true;
    const firstScoredRow = (table_data || []).find(r => r && r.symbol);
    try {
      fetch('/api/activation/ai-score-viewed', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          detail: {
            symbol: firstScoredRow ? firstScoredRow.symbol : undefined,
            horizon: firstScoredRow ? firstScoredRow.daysOut : undefined,
          },
        }),
        keepalive: true,
      }).catch(() => { /* fire-and-forget */ });
    } catch (e) { /* never throw from telemetry */ }
  }, [hasAI, hasMLData, hasOptedInAIColumn, loggedinUser, table_data]);

  // On mobile portrait, limit columns to avoid cramped table
  const isMobilePortrait = rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth;
  const visibleColumns = useMemo(() => selectOpportunityVisibleColumns({
    columnOrder: columnOrder || DEFAULT_COLUMN_ORDER,
    showSR2,
    hasAI,
    mlEnabled,
    marketEligible: mlMarketEligible,
    isMobilePortrait,
    columnVisibility,
  }), [columnOrder, showSR2, hasAI, mlEnabled, mlMarketEligible, isMobilePortrait, columnVisibility]);

  const aiSortPending = AI_COLS.includes(colSorted) && mlScoresLoading

  const filterAnalysis = useMemo(() => analyzeOpportunityFilter(filterText), [filterText])
  const aiFilterPending = isOpportunityFilterPending(filterText, mlScoresLoading)

  const currentFilterRows = useMemo(() => {
    // Copy the original table data and inject TL plus the displayed AI time length.
    // The full-pattern score remains displayed through 90 days; longer patterns
    // deliberately use only the 90-day reading.
    let tmp = [...table_data].map(row => {
      const score = stockScores && stockScores[row.symbol]
      const aiBundle = normalizeOpportunityAIScore({
        row,
        scores: mlScores,
        pendingKeys: mlPending,
        loading: mlScoresLoading,
        unavailableReason: mlUnavailableReason,
      })
      return {
        ...row,
        TL: hasUsableBatchTrendScore(score) ? score.lscore : null,
        aiBundle,
        ...opportunityAIFlatFields(aiBundle),
      }
    })

    if (filterAnalysis.status !== 'valid' || aiFilterPending) return []

    const filtered = filterOpportunityRows(tmp, filterText)
    // AI values arrive in batches. Keep the current order stable until the whole
    // score snapshot is ready instead of making rows jump after every poll.
    if (aiSortPending) return lastValidRowsRef.current.length > 0
      ? lastValidRowsRef.current
      : sortOpportunityRows(filtered, 'sharpe_ratio', 'd')
    return sortOpportunityRows(filtered, colSorted, sortedDir)
  }, [table_data, sortedDir, colSorted, filterText, stockScores, mlScores, mlPending, mlScoresLoading, mlUnavailableReason, filterAnalysis.status, aiFilterPending, aiSortPending])

  // Incomplete or invalid text is a typing state, not a new empty result.
  // Preserve the last valid membership while the status row explains what is
  // unfinished. A valid AI filter still masks rows while its complete score
  // snapshot is loading, so stale AI membership is never presented as final.
  if (filterAnalysis.status === 'valid' && !aiFilterPending && !aiSortPending) {
    lastValidRowsRef.current = currentFilterRows
  }
  const tableDataProcessed =
    filterAnalysis.status === 'valid'
      ? currentFilterRows
      : lastValidRowsRef.current

  const tableStatusMessage =
    filterAnalysis.status === 'incomplete'
      ? filterAnalysis.message
      : filterAnalysis.status === 'invalid'
        ? `Invalid filter: ${filterAnalysis.message}`
        : aiFilterPending
          ? 'Loading AI scores before applying this filter...'
          : aiSortPending
            ? 'Finishing AI scores before sorting. The table will stay still until they are ready.'
          : tableDataProcessed.length === 0 && String(filterText || '').trim().length > 0
            ? 'No opportunities match this filter.'
            : ''

  useEffect(() => {
    let shortCount = 0
    let longCount = 0
    tableDataProcessed.forEach(item => {
      if (item.lOrS === 'Short') shortCount += 1
      else if (item.lOrS === 'Long') longCount += 1
    })
    SetNumLongs(longCount)
    SetNumShorts(shortCount)
    SetOppTableLength(tableDataProcessed.length)
    if (typeof SetVisibleOpportunities === 'function') {
      SetVisibleOpportunities(tableDataProcessed)
    }
  }, [tableDataProcessed, SetNumLongs, SetNumShorts, SetOppTableLength, SetVisibleOpportunities])

  // Reset row selection only when data/sort/filter changes - NOT when ML scores trickle in.
  useEffect(() => {
    const dataChanged = [sortedDir, colSorted, filterText, showAciveOpps, stockScores, columnVisibility].join('|')
    if (dataChanged !== prevDataDepsRef.current) {
      prevDataDepsRef.current = dataChanged
      let decoded;
      try { decoded = jwt_decode(token); } catch (e) { console.error('jwt_decode failed in TableBox:', e.message); return; }
      const exp = decoded['exp']
      const secs_now = Math.floor(Date.now() / 1000)
      const secs_since_token = -(secs_now, exp - secs_now - 10800)
      if (secs_since_token < 30 && loggedinUser === '0') {
        // do nothing
      } else {
        SetRowIndexClicked(null)
      }
    }
  }, [sortedDir, colSorted, filterText, showAciveOpps, stockScores, columnVisibility, token, loggedinUser, SetRowIndexClicked])

  const { tableTitleDict, tableTitleTooltip } = useMemo(() => {
    let daysout_title = 'Days'
    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) {
      daysout_title = 'Days'
    }

    const tmpDict = {}
    const tmpDict_tt = {}

    visibleColumns.forEach(k => {
      if (k === 'daysOut') {
        tmpDict['daysOut'] = daysout_title
        tmpDict_tt['daysOut'] = 'Number of calendar days the seasonal pattern is held, from entry to exit. Click to sort by Days-Hold'
      } else if (k === 'date') {
        tmpDict['date'] = 'Date'
        tmpDict_tt['date'] = 'Start date of the seasonal pattern'
      } else if (k === 'symbol') {
        tmpDict['symbol'] = 'Ticker'
        tmpDict_tt['symbol'] = 'Ticker symbol for the pattern. Click to sort by Ticker symbol'
      } else if (k === 'lOrS') {
        tmpDict['lOrS'] = 'DIR'
        tmpDict_tt['lOrS'] = 'Direction of the pattern (Long/Short). Click to sort by direction'
      } else if (k === 'sharpe_ratio') {
        tmpDict['sharpe_ratio'] = 'SR'
        tmpDict_tt['sharpe_ratio'] = 'The Sharpe Ratio gauges the quality of the pattern - its average return relative to year-to-year variability. Click to sort by Sharpe Ratio'
      } else if (k === 'median_profit') {
        tmpDict['median_profit'] = 'MP'
        tmpDict_tt['median_profit'] = 'The Median Profit indicates the middle value of strategy profits.'
      } else if (k === 'avg_profit') {
        tmpDict['avg_profit'] = 'AvgP'
        tmpDict_tt['avg_profit'] = 'The Average Profit represents the average of profits generated.'
      } else if (k === 'avg_profit2') {
        tmpDict['avg_profit2'] = 'TWA'
        tmpDict_tt['avg_profit2'] = 'TradeWave Average Profit calculated using MFE.'
      } else if (k === 'sharpe_ratio2') {
        tmpDict['sharpe_ratio2'] = 'TWR'
        tmpDict_tt['sharpe_ratio2'] = 'TradeWave Ratio based on MFE.'
      } else if (k === 'TL') {
        tmpDict['TL'] = 'TL'
        tmpDict_tt['TL'] = 'Trend Long (0-100) - how bullish the current price trend is. Higher means price is above key moving averages with upward momentum. Click to sort.'
      } else if (k === 'price') {
        tmpDict['price'] = 'Price'
        tmpDict_tt['price'] = 'Latest available price. Real-time when available; otherwise the latest completed daily close is clearly labeled. Green = up, Red = down. Hover for details. Click to sort.'
      } else if (k === 'ml_score') {
        tmpDict['ml_score'] = 'AIS'
        tmpDict_tt['ml_score'] = AI_METRICS.ml_score.shortDescription
      } else if (k === 'win_prob') {
        tmpDict['win_prob'] = 'Win%'
        tmpDict_tt['win_prob'] = AI_METRICS.win_prob.shortDescription
      } else if (k === 'pred_return') {
        tmpDict['pred_return'] = 'PredR'
        tmpDict_tt['pred_return'] = AI_METRICS.pred_return.shortDescription
      } else if (k === 'pred_mfe') {
        tmpDict['pred_mfe'] = 'PMFE'
        tmpDict_tt['pred_mfe'] = AI_METRICS.pred_mfe.shortDescription
      } else {
        tmpDict[k] = k
      }
    })

    return { tableTitleDict: tmpDict, tableTitleTooltip: tmpDict_tt }
  }, [visibleColumns, rdd.isMobile, rdd.isTablet])

  //-------------------------------------------------------------------------------------------------------------------
  const handleTitleClicked = title => () => {
    if (colSorted !== title) {
      SetColSorted(title)
      if (title === 'daysOut' || title === 'lOrS' || title === 'symbol') {
        SetSortedDir('a')
      } else {
        SetSortedDir('d')
      }
    } else {
      if (sortedDir === 'a') SetSortedDir('d')
      else SetSortedDir('a')
    }
  }

  //-------------------------------------------------------------------------------------------------------------------
  const tableStyle = {
    fontSize: tableTextSize,
    backgroundColor: tc.panelBg,
    color: tc.text,
  }

  //-------------------------------------------------------------------------------------------------------------------
  const toggleUpgrade = () => {
    SetShowUpgradeBanner(!showUpgradeBanner)
  }

  //-------------------------------------------------------------------------------------------------------------------
  // Min-width per column - when total exceeds container, horizontal scrollbar appears
  const tableMinWidth = opportunityTableMinimumWidth({
    columns: visibleColumns,
    isMobilePortrait,
    shortDates,
  });

  const firstAICol = visibleColumns.find(c => AI_COLS.includes(c));

  //-------------------------------------------------------------------------------------------------------------------
  return (
    <div className="opp-table-box" tabIndex="0" onKeyDown={handlerKeyDown} style={{
      '--opp-ai-text': tc.aiCheckpointText,
      '--opp-ai-bg': tc.aiCheckpointBg,
      '--opp-ai-border': tc.aiCheckpointBorder,
      '--opp-ai-focus': tc.aiCheckpointFocus,
      '--opp-ai-panel': tc.panelBg,
      '--opp-ai-muted': tc.textSecondary,
      '--opp-ai-main-text': tc.text,
    }}>
      <table className="table-striped" style={{ ...tableStyle, minWidth: tableMinWidth }} >

        <colgroup>
          {(() => {
            // Weight per column - symbol and date need more room, rest are equal
            const W = { symbol: 1.3, date: shortDates ? 1.1 : 1.8, daysOut: 1.1, price: 1.1, avg_profit: 1.2, win_prob: 1.1, pred_return: 1.2, pred_mfe: 1.2 };
            const weights = visibleColumns.map(c => W[c] || 1);
            const total = weights.reduce((a, b) => a + b, 0);
            return visibleColumns.map((col, i) => (
              <col key={col} style={{ width: (weights[i] / total * 100).toFixed(1) + '%' }} />
            ));
          })()}
        </colgroup>

        <thead>
          <tr style={{ fontSize: tableTitleTextSize, borderBottom: 'none' }}>
            {visibleColumns.map((title) => {
              const isAIColumn = AI_COLS.includes(title)
              return (
                <Tippy
                  disabled={!tooltipSW || isAIColumn}
                  key={title}
                  placement={'bottom'}
                  maxWidth={350}
                  content={<div theme="tw">{tooltipSW ? tableTitleTooltip[title] : ''}</div>}
                >
                  <th
                    key={title}
                    aria-sort={title === colSorted ? (sortedDir === 'a' ? 'ascending' : 'descending') : 'none'}
                    style={{
                      height: rowHeight,
                      whiteSpace: 'nowrap',
                      backgroundColor: title === colSorted ? tc.statLabelBg : tc.tableHeaderBg,
                      color: showAciveOpps
                        ? 'blue'
                        : (AI_COLS.includes(title)
                            ? opportunityAIHeaderColor(UITheme)
                            : tc.text),
                      ...(title === firstAICol ? { borderLeft: `2px solid ${tc.aiCheckpointBorder || '#6366f1'}` } : {}),
                      ...(title === 'symbol' && !isMobilePortrait ? { position: 'sticky', left: 0, zIndex: 4 } : {})
                    }}
                  >
                    <div className="opp-table-header-actions">
                      <button
                        type="button"
                        className="opp-table-sort-button"
                        onClick={(!hasAI && isAIColumn) ? openAILockDialog : handleTitleClicked(title)}
                        aria-label={(!hasAI && isAIColumn)
                          ? `${tableTitleDict[title]} is locked. Learn about plans with AI Scores.`
                          : `Sort by ${tableTitleDict[title]}${title === colSorted ? `, currently ${sortedDir === 'a' ? 'ascending' : 'descending'}` : ''}`}
                      >
                        <span>{tableTitleDict[title]}</span>
                        {(!hasAI && isAIColumn)
                          ? <span title="AI Scores start at Analyst" aria-hidden="true">🔒</span>
                          : (title === colSorted
                              ? (sortedDir === 'a' ? <BsChevronDown aria-hidden="true" /> : <BsChevronUp aria-hidden="true" />)
                              : <BsChevronExpand aria-hidden="true" />)}
                      </button>
                    </div>
                  </th>
                </Tippy>
              )
            })}
          </tr>
        </thead>

        <tbody>
          {tableStatusMessage && (
            <tr>
              <td
                colSpan={Math.max(visibleColumns.length, 1)}
                role="status"
                aria-live="polite"
                style={{ padding: '14px', textAlign: 'center', color: tc.text }}
              >
                {tableStatusMessage}
              </td>
            </tr>
          )}
          {tableDataProcessed.map((row, index) => (
            <tr
              key={`row-${index}`}
              id={index}
              onClick={handlerRowClicked(index, row)}
              className={rowIndexClicked === index ? "selected" : "stripes"}
            >
              {visibleColumns.map((key) => (
                <td key={`${key}-${index}`} style={{
                  height: rowHeight,
                  whiteSpace: 'nowrap',
                  ...(key === firstAICol ? { borderLeft: `2px solid ${tc.aiCheckpointBorder || '#6366f1'}` } : {}),
                  ...(key === 'symbol' && !isMobilePortrait ? {
                    position: 'sticky',
                    left: 0,
                    zIndex: 1,
                    backgroundColor: rowIndexClicked === index ? tc.stickySelectedBg : tc.panelBg,
                  } : {})
                }}>
                  {(!hasAI && AI_COLS.includes(key))
                    ? <button
                        type="button"
                        className="opp-ai-locked-cell"
                        aria-label="AI Scores are locked. Learn about plans with AI Scores."
                        onClick={event => { event.stopPropagation(); openAILockDialog() }}
                      >· · ·</button>
                    : key === 'TL' && row[key] === null
                    ? PENDING_CELL
                    : key === 'price'
                      ? (Number.isFinite(row.price)
                        ? <Tippy
                            placement="top"
                            content={
                              <div style={{ fontSize: '11px' }}>
                                {row.realtimeQuote && row.realtimeQuote.source === 'eod_close' && (
                                  <div>Latest completed close, {row.realtimeQuote.date || 'date unavailable'}</div>
                                )}
                                <div>
                                  <span style={{ color: row.change_p > 0 ? '#4caf50' : row.change_p < 0 ? '#f44336' : 'inherit' }}>
                                    {row.change_p > 0 ? '▲' : row.change_p < 0 ? '▼' : '–'}
                                  </span>{' '}
                                  {Number.isFinite(row.change_p) ? `${row.change_p > 0 ? '+' : ''}${row.change_p.toFixed(2)}%` : '0.00%'}
                                  {row.realtimeQuote && row.realtimeQuote.source === 'eod_close' ? ' from previous close' : ''}
                                </div>
                              </div>
                            }
                          >
                            <span style={{ color: row.change_p > 0 ? '#4caf50' : row.change_p < 0 ? '#f44336' : tc.text }}>
                              {row.price.toFixed(2)}
                            </span>
                          </Tippy>
                        : ' - ')
                      : AI_COLS.includes(key)
                        ? <OpportunityAICell
                            bundle={row.aiBundle}
                            metric={key}
                            symbol={row.symbol}
                          />
                        : (key === 'date' && shortDates && row[key] && row[key].length > 5)
                                ? row[key].substring(5)
                                : row[key]
                  }
                  {(key === 'avg_profit' || key === 'avg_profit2' || key === 'median_profit')
                    ? '%'
                    : ''}
                </td>
              ))}


            </tr>
          ))}

          {loggedinUser === '0' && (
            <tr>
              <td colSpan='99'>
                <div style={{ border: '4px dashed green', width: '100%', height: '20%', background: 'Honeydew' }}>
                  <span style={{ color: 'green', font: 'Arial', fontSize: '1em' }}>
                    <b>
                      <a href="/register/?lid=1" target="_blank" rel="noopener noreferrer">
                        Register
                      </a>
                      {' '}for a free account or{' '}
                      <a href="/member-login/" target="_blank" rel="noopener noreferrer">
                        login
                      </a>
                      {' '}to see all opportunities for today
                    </b>
                  </span>
                </div>
              </td>
            </tr>
          )}

          {/* desktop */}
          {showUpgradeBanner && wpUserLevels.length === 1 && wpUserLevels[0] === '1' && !rdd.isMobile && (
            <tr>
              <td colSpan='99' style={{ paddingTop: '20px' }}>
                <div
                  style={{
                    position: 'relative',
                    border: '4px dashed green',
                    width: '100%',
                    background: 'Honeydew',
                    padding: '15px',
                    textAlign: 'center',
                    boxSizing: 'border-box'
                  }}
                >
                  <div
                    onClick={toggleUpgrade}
                    style={{
                      position: 'absolute',
                      top: '0',
                      right: '0',
                      width: '30px',
                      height: '30px',
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center',
                      cursor: 'pointer',
                      fontWeight: 'bold',
                      fontSize: '20px',
                      lineHeight: '1',
                      margin: '0',
                      padding: '0',
                      borderRadius: '50%',
                      color: 'green',
                      backgroundColor: 'transparent'
                    }}
                  >
                    ✖
                  </div>

                  <div
                    style={{
                      color: 'green',
                      fontFamily: 'Arial, sans-serif',
                      fontSize: '1em',
                      maxWidth: '750px',
                      margin: '7px auto',
                      lineHeight: '1.5em'
                    }}
                  >
                    <b>{upgradeMessage}</b>
                  </div>
                  <div
                    style={{
                      marginTop: '10px',
                      display: 'flex',
                      justifyContent: 'center'
                    }}
                  >
                    <a
                      href="/pricing"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        textDecoration: 'none',
                        color: 'white',
                        backgroundColor: 'green',
                        padding: '10px 20px',
                        borderRadius: '5px',
                        fontWeight: 'bold',
                        display: 'inline-block',
                        border: '2px solid white',
                        width: 'fit-content'
                      }}
                    >
                      Click Here to Upgrade Now!
                    </a>
                  </div>
                </div>

                {/* Promotion Banner */}
                {promotionMessage && (
                  <div
                    style={{
                      width: '100%',
                      padding: '15px',
                      background: promotionBackColor,
                      boxSizing: 'border-box',
                      textAlign: 'center',
                      fontFamily: 'Arial, sans-serif',
                      marginTop: '15px',
                      border: '4px dashed black'
                    }}
                  >
                    <div
                      style={{
                        color: 'white',
                        fontSize: '1.2em',
                        fontWeight: 'bold'
                      }}
                    >
                      {promotionMessage}
                    </div>
                    <div
                      style={{
                        backgroundColor: 'black',
                        color: 'yellow',
                        padding: '10px 20px',
                        borderRadius: '5px',
                        display: 'inline-block',
                        fontWeight: 'bold',
                        fontSize: '1.4em',
                        marginTop: '10px'
                      }}
                    >
                      Use Code: {promotionCouponCode}
                    </div>
                  </div>
                )}
              </td>
            </tr>
          )}

          {/* smartphone portrait */}
          {showUpgradeBanner && wpUserLevels.length === 1 && wpUserLevels[0] === '1' && rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth && (
            <tr style={{ padding: '0', margin: '0', width: '100%' }}>
              <td colSpan='99' style={{ padding: '0', margin: '0', width: '100%' }}>
                <div
                  style={{
                    width: '100vw',
                    padding: '0',
                    margin: '0',
                    background: 'lightgreen',
                    boxSizing: 'border-box',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center'
                  }}
                >
                  {/* Left Div: Upgrade Button */}
                  <div
                    style={{
                      width: promotionMessage !== '' ? '90%' : '100%',
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center'
                    }}
                  >
                    <a
                      href={`/cp/mobile-upgrade.html?upgradeMessage=${encodeURIComponent(upgradeMessage)}&promotionMessage=${encodeURIComponent(promotionMessage)}&promotionBackColor=${encodeURIComponent(promotionBackColor)}&promotionCouponCode=${encodeURIComponent(promotionCouponCode)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        textDecoration: 'none',
                        color: 'white',
                        backgroundColor: 'green',
                        padding: '15px 0',
                        borderRadius: '5px',
                        fontWeight: 'bold',
                        textAlign: 'center',
                        width: '100%',
                        fontSize: '1.2em',
                        margin: '0 auto',
                        boxSizing: 'border-box'
                      }}
                    >
                      Upgrade to Premium for Full Access
                    </a>
                  </div>

                  {/* Right Div: Gift Box */}
                  {promotionMessage !== '' && (
                    <div
                      style={{
                        width: '10%',
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center'
                      }}
                    >
                      <a
                        href={`/mobile-upgrade?upgradeMessage=${encodeURIComponent(upgradeMessage)}&promotionMessage=${encodeURIComponent(promotionMessage)}&promotionBackColor=${encodeURIComponent(promotionBackColor)}&promotionCouponCode=${encodeURIComponent(promotionCouponCode)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          textDecoration: 'none',
                          color: 'white',
                          backgroundColor: 'red',
                          padding: '15px 0',
                          borderRadius: '5px',
                          fontWeight: 'bold',
                          textAlign: 'center',
                          width: '100%',
                          fontSize: '1.6em',
                          margin: '0 auto',
                          boxSizing: 'border-box'
                        }}
                      >
                        🎁
                      </a>
                    </div>
                  )}
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default React.memo(TableBox)
