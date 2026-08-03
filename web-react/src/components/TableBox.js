import React, { useEffect, useState, useContext, useRef } from 'react'
import { UserContext } from './UserContext'
import { themeColors, CellSpinner, tierHasAI } from './Common'
import { BsChevronExpand, BsChevronDown, BsChevronUp } from "react-icons/bs"
import Tippy from '@tippyjs/react'
import './styles/TableBox.css'
import jwt_decode from 'jwt-decode'
import {
  analyzeOpportunityFilter,
  filterOpportunityRows,
  isOpportunityFilterPending,
  sortOpportunityRows,
} from './opportunityFilters'

// GTM playbook CARD W1.4 - fire once per browser session, the first time an
// AI-eligible user actually sees real AI-score data in the table. Module-level
// (not per-mount) so remounting TableBox (tab switches, filters) never re-fires
// within the same session; the server-side handler is ALSO idempotent
// (users.first_ai_score_viewed_at first-touch-only), so this is a courtesy
// dedupe, not the source of truth.
let _aiScoreViewedFiredThisSession = false

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
  stockScoresLoading,
  mlScores,
  mlScoresLoading,
  mlPending,
  columnVisibility,
  columnOrder,
  shortDates
}) => {

  const { tableTextSize, tableTitleTextSize, wpUserLevels, loggedinUser, token, rdd, UITheme, SetDialogType, SetDialogProp, SetInfoBoxVisible } = useContext(UserContext)
  const tc = themeColors(UITheme)
  // AI scoring is an Analyst+ feature; non-AI tiers see a single LOCKED "AI Score" teaser column.
  const hasAI = tierHasAI(wpUserLevels)
  const openAILockDialog = () => {
    SetDialogProp({
      title: 'See the AI Score',
      contentText: "The AI Score ranks these opportunities by win-probability - it starts at the Analyst plan. Upgrade to turn it on across all U.S. stocks and ETFs.\n\nPrefer not to see this column? Go to Settings -> Opp Table and uncheck the AI scoring columns.",
      button1Text: 'See Plans', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)'
    })
    SetDialogType('info-box')
    SetInfoBoxVisible(true)
  }

  const [tableDataProcessed, SetTableDataProcessed] = useState(table_data)
  const [colSorted, SetColSorted] = useState('sharpe_ratio')
  const [sortedDir, SetSortedDir] = useState('d') // ascending or descending
  const [tableTitleDict, SetTableTitleDict] = useState({})
  const [tableTitleTooltip, SetTableTitleTooltip] = useState({})
  const prevDataDepsRef = useRef('')

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

  // Not generic, used as a second column for tie-breaks
  const secondColSort = 'date'

  // Build visible columns list based on user-defined order and columnVisibility
  const REQUIRED_COLS = new Set(['symbol', 'daysOut', 'sharpe_ratio']);
  const hasMLData = mlScores && Object.keys(mlScores).length > 0;
  const ALL_COLUMNS = (columnOrder || ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'avg_profit', 'avg_profit2', 'sharpe_ratio2', 'TL', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'])
    .filter(col => {
      if (!showSR2 && (col === 'avg_profit2' || col === 'sharpe_ratio2')) return false;
      if (['ml_score', 'win_prob', 'pred_return', 'pred_mfe'].includes(col)) {
        // AI tier: keep AI columns only when there is data (drop on a non-ML market). Non-AI tier:
        // keep ONLY ml_score as the single locked "AI Score" teaser column (drop the sub-metrics).
        if (hasAI) { if (!hasMLData) return false; }
        else if (col !== 'ml_score') return false;
      }
      return true;
    });

  // GTM playbook CARD W1.4 - Postgres activation signal. The first time this AI-eligible
  // user actually has real AI-score data on screen, tell the server (which stamps
  // users.first_ai_score_viewed_at idempotently, logs an onboarding_events row, and
  // fires the GA4 ai_score_viewed event - all in ONE handler, per the strategy §2
  // persistence rule). Fire-and-forget, same-origin authed fetch; never throws.
  useEffect(() => {
    if (!hasAI || !hasMLData || _aiScoreViewedFiredThisSession) return;
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
  }, [hasAI, hasMLData, loggedinUser, table_data]);

  // On mobile portrait, limit columns to avoid cramped table
  const isMobilePortrait = rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth;
  const MOBILE_COLS = new Set(['symbol', 'daysOut', 'sharpe_ratio', 'lOrS', 'date', 'price', 'sharpe_ratio2']);

  const visibleColumns = ALL_COLUMNS.filter(col => {
    if (isMobilePortrait) return MOBILE_COLS.has(col);
    if (REQUIRED_COLS.has(col)) return true;
    if (columnVisibility && columnVisibility[col] === false) return false;
    return true;
  });

  // If colSorted is not in visibleColumns, reset to sharpe_ratio
  if (colSorted !== '' && !visibleColumns.includes(colSorted)) {
    SetColSorted('sharpe_ratio');
    SetSortedDir('d');
  }

  useEffect(() => {
    // Copy the original table data and inject TL + ML columns
    let tmp = [...table_data].map(row => {
      const score = stockScores && stockScores[row.symbol]
      const lor_s = String(row.lOrS).startsWith('L') ? 'l' : 's'
      const rawDays = parseInt(row.daysOut) - 1
      const mlKey = `${row.symbol}|${rawDays}|${lor_s}`
      const ml = mlScores && mlScores[mlKey]
      const isPending = mlPending && mlPending.has(mlKey)
      return {
        ...row,
        TL: score ? score.lscore : null,
        ml_score: ml ? ml.ml_score : null,
        win_prob: ml ? ml.win_prob : null,
        pred_return: ml ? ml.pred_return : null,
        pred_mfe: ml ? ml.pred_mfe : null,
        ml_pending: isPending,  // true = spinner, false + null = '---'
      }
    })

    const filterAnalysis = analyzeOpportunityFilter(filterText)
    const aiFilterPending = isOpportunityFilterPending(filterText, mlScoresLoading)
    if (filterAnalysis.status !== 'valid' || aiFilterPending) {
      tmp = []
    } else {
      tmp = filterOpportunityRows(tmp, filterText)
    }

    // Sorting receives a copy and therefore cannot mutate source rows or
    // change which rows belong to the active filter.
    tmp = sortOpportunityRows(tmp, colSorted, sortedDir)

    // Update long/short counts
    const shortCount = tmp.filter(item => item.lOrS === 'Short').length
    const longCount = tmp.filter(item => item.lOrS === 'Long').length
    SetNumLongs(longCount)
    SetNumShorts(shortCount)

    // Update processed data & table length
    SetTableDataProcessed(tmp)
    SetOppTableLength(tmp.length)
    if (typeof SetVisibleOpportunities === 'function') SetVisibleOpportunities(tmp)

    // Reset row selection only when data/sort/filter changes - NOT when mlScores or mlPending trickle in
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

    // Rebuild the column titles & tooltips
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
        tmpDict_tt['price'] = 'Current real-time price. Green = up today, Red = down today. Hover for % change. Click to sort.'
      } else if (k === 'ml_score') {
        tmpDict['ml_score'] = 'AIS'
        tmpDict_tt['ml_score'] = 'AI Score (0-100) - the AI models rank how well current conditions support this pattern. Higher is a stronger reading. Patterns longer than 90 days are not scored. Click to sort.'
      } else if (k === 'win_prob') {
        tmpDict['win_prob'] = 'Win%'
        tmpDict_tt['win_prob'] = 'Win Probability - calibrated AI estimate of the chance the pattern ends profitable (return above zero). Patterns longer than 90 days are not scored. Click to sort.'
      } else if (k === 'pred_return') {
        tmpDict['pred_return'] = 'PredR'
        tmpDict_tt['pred_return'] = 'Predicted Return (%) - AI ensemble predicted close-to-close return. Patterns longer than 90 days are not scored. Click to sort.'
      } else if (k === 'pred_mfe') {
        tmpDict['pred_mfe'] = 'PMFE'
        tmpDict_tt['pred_mfe'] = 'Predicted Max Favorable Excursion (%) - AI estimated max upside during the hold period. Patterns longer than 90 days are not scored. Click to sort.'
      } else {
        tmpDict[k] = k
      }
    })

    SetTableTitleDict(tmpDict)
    SetTableTitleTooltip(tmpDict_tt)
  }, [table_data, sortedDir, colSorted, filterText, showAciveOpps, stockScores, mlScores, mlScoresLoading, mlPending, columnVisibility, SetVisibleOpportunities])

  const filterAnalysis = analyzeOpportunityFilter(filterText)
  const aiFilterPending = isOpportunityFilterPending(filterText, mlScoresLoading)
  const filterStatusMessage =
    filterAnalysis.status === 'incomplete'
      ? filterAnalysis.message
      : filterAnalysis.status === 'invalid'
        ? `Invalid filter: ${filterAnalysis.message}`
        : aiFilterPending
          ? 'Loading AI scores before applying this filter...'
          : filterText && filterText.trim() !== '' && tableDataProcessed.length === 0
            ? 'No opportunities match this filter.'
            : ''

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
  const COL_MIN_W = { symbol: 70, date: shortDates ? 55 : 80, daysOut: 60, price: 65, avg_profit: 65, win_prob: 60, pred_return: 65, pred_mfe: 65, ml_score: 55 };
  const DEFAULT_COL_MIN = 55;
  const tableMinWidth = visibleColumns.reduce((sum, c) => sum + (COL_MIN_W[c] || DEFAULT_COL_MIN), 0);

  const AI_COLS = ['ml_score', 'win_prob', 'pred_return', 'pred_mfe'];
  const firstAICol = visibleColumns.find(c => AI_COLS.includes(c));

  //-------------------------------------------------------------------------------------------------------------------
  return (
    <div tabIndex="0" onKeyDown={handlerKeyDown}>
      <table className="table-striped" style={{ ...tableStyle, minWidth: isMobilePortrait ? undefined : tableMinWidth }} >

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
            {visibleColumns.map((title) => (
              <Tippy
                disabled={!tooltipSW}
                key={title}
                placement={'bottom'}
                content={
                  <div theme="tw" >
                    {tooltipSW ? tableTitleTooltip[title] : ''}
                  </div>
                }
              >
                <th
                  key={title}
                  style={{
                    height: rowHeight,
                    whiteSpace: 'nowrap',
                    backgroundColor: title === colSorted ? tc.statLabelBg : tc.tableHeaderBg,
                    color: showAciveOpps
                      ? 'blue'
                      : (['ml_score', 'win_prob', 'pred_return', 'pred_mfe'].includes(title)
                          ? (UITheme === 'dark' ? 'rgb(100, 220, 140)' : 'rgb(22, 163, 74)')
                          : tc.text),
                    ...(title === firstAICol ? { borderLeft: '2px solid #6366f1' } : {}),
                    ...(title === 'symbol' && !isMobilePortrait ? { position: 'sticky', left: 0, zIndex: 2 } : {})
                  }}
                  onClick={(!hasAI && AI_COLS.includes(title)) ? openAILockDialog : handleTitleClicked(title)}
                >
                  {tableTitleDict[title]}{' '}
                  {(!hasAI && AI_COLS.includes(title))
                    ? <span title="AI scoring starts at Analyst" style={{ cursor: 'pointer' }}>🔒</span>
                    : (title === colSorted
                        ? (sortedDir === 'a' ? <BsChevronDown /> : <BsChevronUp />)
                        : <BsChevronExpand />)}
                </th>
              </Tippy>
            ))}
          </tr>
        </thead>

        <tbody>
          {filterStatusMessage && (
            <tr>
              <td
                colSpan={Math.max(visibleColumns.length, 1)}
                role="status"
                aria-live="polite"
                style={{
                  padding: '12px',
                  textAlign: 'center',
                  color: tc.text,
                  backgroundColor: tc.panelBg,
                }}
              >
                {filterStatusMessage}
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
                  ...(key === firstAICol ? { borderLeft: '2px solid #6366f1' } : {}),
                  ...(key === 'symbol' && !isMobilePortrait ? {
                    position: 'sticky',
                    left: 0,
                    zIndex: 1,
                    backgroundColor: rowIndexClicked === index ? tc.stickySelectedBg : tc.panelBg,
                  } : {})
                }}>
                  {(!hasAI && AI_COLS.includes(key))
                    ? <span style={{ color: '#bbb', letterSpacing: '2px' }}>· · ·</span>
                    : key === 'TL' && row[key] === null
                    ? <CellSpinner />
                    : key === 'price'
                      ? (row.price != null
                        ? <Tippy
                            placement="top"
                            content={
                              <div style={{ fontSize: '11px' }}>
                                <span style={{ color: row.change_p > 0 ? '#4caf50' : row.change_p < 0 ? '#f44336' : 'inherit' }}>
                                  {row.change_p > 0 ? '▲' : row.change_p < 0 ? '▼' : '–'}
                                </span>{' '}
                                {row.change_p != null ? `${row.change_p > 0 ? '+' : ''}${row.change_p.toFixed(2)}%` : '0.00%'}
                              </div>
                            }
                          >
                            <span style={{ color: row.change_p > 0 ? '#4caf50' : row.change_p < 0 ? '#f44336' : tc.text }}>
                              {row.price.toFixed(2)}
                            </span>
                          </Tippy>
                        : ' - ')
                      : key === 'ml_score'
                        ? (row.ml_score != null ? row.ml_score.toFixed(1) : row.ml_pending ? <CellSpinner /> : '---')
                        : key === 'win_prob'
                          ? (row.win_prob != null ? (row.win_prob * 100).toFixed(0) + '%' : row.ml_pending ? <CellSpinner /> : '---')
                          : key === 'pred_return'
                            ? (row.pred_return != null ? row.pred_return.toFixed(1) + '%' : row.ml_pending ? <CellSpinner /> : '---')
                            : key === 'pred_mfe'
                              ? (row.pred_mfe != null ? row.pred_mfe.toFixed(1) + '%' : row.ml_pending ? <CellSpinner /> : '---')
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

export default TableBox
