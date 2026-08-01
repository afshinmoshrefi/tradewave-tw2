import React, { useState, useEffect, useRef, useContext } from 'react';
import { UserContext } from './UserContext';
import { appserverURL, trend_chart_left_gap_days, incrementDate, themeColors, getSelectedIDFromSecuritiesList2, setCookie } from './Common';
import TrendScorePopup from './TrendScorePopup';
import SharpeRatioPopup from './SharpeRatioPopup';
import SeasonalPatternsPopup from './SeasonalPatternsPopup';
import TrendChartPopup from './TrendChartPopup';
import BarChartPopup from './BarChartPopup';
import ProjectionPopup from './ProjectionPopup';
import PECyclePopup from './PECyclePopup';
import MFEMAEPopup from './MFEMAEPopup';
import TWRPopup from './TWRPopup';
import WatchlistPopup from './WatchlistPopup';
import OppTablePopup from './OppTablePopup';
import GettingStartedPopup from './GettingStartedPopup';
import DaysOutPopup from './DaysOutPopup';
import YearsRangePopup from './YearsRangePopup';
import FilteringPopup from './FilteringPopup';
import AIScoresPopup from './AIScoresPopup';
import './styles/Chatbot.css';
import {
  buildChatbotScreenContext,
  buildOpportunityTableContext,
  deriveDirectionFromBars,
  parseOptionalNumber,
  shouldClearOpportunityTable,
} from './chatbotScreenContext';
import { VIEWER_CYCLE_CHANGE_EVENT, isViewerCycle } from './viewerCycleState';

const CHATBOT_DERIVED_STAT_KEYS = [
  'Trade Dir', 'Num Winners', 'Num Losers', 'Percent Profitable',
  'Avg Profit - All', 'Avg Profit', 'Avg Loss', 'Median Profit',
  'Annualized Return', 'Cumulative Return', 'Std Dev', 'Sharpe Ratio',
  'Sharpe Ratio2', 'Trend Long', 'Trend Short', 'Trend Long1', 'Trend Short1',
  'Trend Score Available', 'next_earnings_est', 'days_to_earnings',
];

//--------------------------------------------------------------------------------------------------------
// The bot reply is model-generated HTML rendered via dangerouslySetInnerHTML; with Tara now
// tool-driven and fed user-influenceable context, a crafted prompt could try to emit active
// markup. Strip the XSS vectors (script/style/iframe blocks, inline on* handlers, javascript:/
// data: URLs) while keeping the legit formatting vocabulary, including the deterministic
// tara-analysis div/class structure used to make long evidence briefs scannable.
// NOTE: this is a strong mitigation for constrained model output; DOMPurify is the gold-standard
// upgrade if the dependency is added later.
const sanitizeBotHtml = (html) => {
  if (typeof html !== 'string') return '';
  let s = html;
  s = s.replace(/<\s*(script|style|iframe|object|embed|svg|math|link|meta)[\s\S]*?<\s*\/\s*\1\s*>/gi, '');
  s = s.replace(/<\s*\/?\s*(script|style|iframe|object|embed|svg|math|link|meta)\b[^>]*>/gi, '');
  s = s.replace(/\son\w+\s*=\s*"[^"]*"/gi, '');
  s = s.replace(/\son\w+\s*=\s*'[^']*'/gi, '');
  s = s.replace(/\son\w+\s*=\s*[^\s>]+/gi, '');
  s = s.replace(/\sstyle\s*=\s*"[^"]*"/gi, '');
  s = s.replace(/\sstyle\s*=\s*'[^']*'/gi, '');
  s = s.replace(/\sstyle\s*=\s*[^\s>]+/gi, '');
  s = s.replace(/(href|src)\s*=\s*"\s*(?:javascript|data|vbscript):[^"]*"/gi, '$1="#"');
  s = s.replace(/(href|src)\s*=\s*'\s*(?:javascript|data|vbscript):[^']*'/gi, "$1='#'");
  s = s.replace(/<(?!\/?(?:b|br|i|a|span|div)\b)[^>]*>/gi, '');
  return s;
};

//--------------------------------------------------------------------------------------------------------
function Chatbot(props) {
  const { token, resourceObj } = useContext(UserContext);
  const tc = themeColors(props.UITheme);
  const asURL = appserverURL();
  const baseURL = `${asURL}/chatbot/chat`;

  const [messages, setMessages] = useState([]);     // { role, text } for display
  const [history, setHistory] = useState([]);        // { role, content } for API context
  const [userInput, setUserInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showTrendPopup, setShowTrendPopup] = useState(false);
  const [showSharpePopup, setShowSharpePopup] = useState(false);
  const [showSeasonalPopup, setShowSeasonalPopup] = useState(false);
  const [showTrendChartPopup, setShowTrendChartPopup] = useState(false);
  const [showBarChartPopup, setShowBarChartPopup] = useState(false);
  const [showProjectionPopup, setShowProjectionPopup] = useState(false);
  const [showPECyclePopup, setShowPECyclePopup] = useState(false);
  const [showMFEMAEPopup, setShowMFEMAEPopup] = useState(false);
  const [showTWRPopup, setShowTWRPopup] = useState(false);
  const [showWatchlistPopup, setShowWatchlistPopup] = useState(false);
  const [showOppTablePopup, setShowOppTablePopup] = useState(false);
  const [showGettingStartedPopup, setShowGettingStartedPopup] = useState(false);
  const [showDaysOutPopup, setShowDaysOutPopup] = useState(false);
  const [showYearsRangePopup, setShowYearsRangePopup] = useState(false);
  const [showFilteringPopup, setShowFilteringPopup] = useState(false);
  const [showAIScoresPopup, setShowAIScoresPopup] = useState(false);
  const chatboxRef = useRef(null);

  // Intro greeting on first open.
  useEffect(() => {
    setMessages([{ role: 'bot', text: "Hi, I'm <b>Tara</b>. Ask me for today's best setups, any stock's seasonal pattern, or a concept like <b>what is a Sharpe ratio</b> - I'll pull it up on the chart and explain it." }]);
  }, []);

  // Consume a pending tip (daily onboarding card / legacy tip) WHENEVER one is set - keyed on
  // the prop, not a one-shot []-deps mount effect, so a tip set while the chat is already open
  // is appended and cleared. (A mount-only effect stranded it -> the launcher icon blinks forever.)
  useEffect(() => {
    if (props.chatbotPendingTip) {
      setMessages(prev => [...prev, { role: 'bot', text: props.chatbotPendingTip }]);
      if (props.SetChatbotPendingTip) props.SetChatbotPendingTip(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.chatbotPendingTip]);

  // Home-page "ask Tara" prefill: when App passes props.chatbotPrefill (from the ?ask=
  // deep link), echo it into the input and auto-send it ONCE so the user bubble appears
  // under the greeting. Gated on token so the POST in handleSend has its auth; fired once
  // via prefillFiredRef, then cleared in App so it can't re-fire.
  const prefillFiredRef = useRef(false);
  useEffect(() => {
    if (prefillFiredRef.current) return;
    const q = props.chatbotPrefill;
    if (q && typeof q === 'string' && q.trim() && token && token.length > 0) {
      prefillFiredRef.current = true;
      setUserInput(q);              // visible echo in the input
      handleSend(q, { fromHome: true });
      if (props.SetChatbotPrefill) props.SetChatbotPrefill(null); // clear so it can't re-fire
    }
  }, [props.chatbotPrefill, token]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll chatbox to bottom when new messages arrive
  useEffect(() => {
    if (chatboxRef.current) {
      chatboxRef.current.scrollTop = chatboxRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  //--------------------------------------------------------------------------------------------------------
  const displayMessage = (role, text) => {
    setMessages((prev) => [...prev, { role, text }]);
  };

  //--------------------------------------------------------------------------------------------------------
  // Build wave viewer context from props
  const buildWaveViewerContext = () => {
    const isArbitraryWindow = props.rowIndexClicked === -1;
    const direction = isArbitraryWindow
      ? deriveDirectionFromBars(props.seasonalBarChartData, props.barChartLongOrShort)
      : (props.barChartLongOrShort || 'long');
    const marketIdRaw = getSelectedIDFromSecuritiesList2(
      props.securityTypeList || [],
      props.selectedSecurity || '',
    );
    const ctx = {
      symbol: props.symbol || '',
      company: props.company || '',
      start_date: props.startDate || '',
      days_out: props.daysOut || '',
      years: props.seasonalYears || '',
      pe_cycle: props.PEselected || 'cons',
      direction,
      selection_origin: isArbitraryWindow ? 'user_defined' : 'scanner',
      mfe_enabled: props.showMFE === true,
      mae_enabled: props.showMAE === true,
    };
    if (marketIdRaw !== -1 && marketIdRaw !== '-1' && marketIdRaw != null) {
      ctx.market = String(marketIdRaw);
    }
    // Send only derived percentages/scores and the compact next-earnings estimate. Raw
    // prices, moving averages, volume, and nested filing history do not belong in Tara's
    // context; the server repeats this allowlist as a trust-boundary check.
    if (props.tradeDetailData && Object.keys(props.tradeDetailData).length > 0) {
      const selectedStats = {};
      CHATBOT_DERIVED_STAT_KEYS.forEach(key => {
        const value = props.tradeDetailData[key];
        if (value !== undefined && value !== null && value !== '') selectedStats[key] = value;
      });
      if (Object.keys(selectedStats).length > 0) ctx.stats = selectedStats;
    }
    // Include year-by-year bar chart data so the bot can discuss specific years
    if (Array.isArray(props.seasonalBarChartData) && props.seasonalBarChartData.length > 0) {
      ctx.yearly_results = props.seasonalBarChartData.map(r => {
        const plist = String(r['pct'] || '').split(',');
        return {
          year: r['year'],
          // ChartData4 bars are underlying price moves. They are deliberately NOT
          // direction-adjusted trade P&L: a negative/red year wins for a short setup.
          underlying_return_pct: parseOptionalNumber(plist[0]),
          // Preserve a real zero but keep missing/invalid path data as null. Turning
          // missing excursions into 0% would falsely claim that a trade had no heat.
          upside_excursion_pct: parseOptionalNumber(plist[1]),
          downside_excursion_pct: parseOptionalNumber(plist[2]),
        };
      });
    }
    return ctx;
  };

  //--------------------------------------------------------------------------------------------------------
  // Build a trimmed snapshot of the rows the user actually sees (max 50, key fields only).
  // TableBox publishes its filtered/sorted order; before that first snapshot, fall back to
  // the raw normal/active list so a command sent immediately after load still has context.
  const buildOppTableContext = () => {
    const fallbackRows = props.showActiveOpps ? props.activeOpportunities : props.opportunities;
    return buildOpportunityTableContext(props.visibleOpportunities, fallbackRows);
  };

  //--------------------------------------------------------------------------------------------------------
  const handleSend = (textArg, opts = {}) => {
    // textArg lets a caller (e.g. the home-page prefill) pass the message explicitly;
    // normal typing calls handleSend() with no args and uses the userInput state.
    const text = (typeof textArg === 'string' ? textArg : userInput);
    if (!text.trim() || isLoading) return;

    setUserInput('');

    // Clear command
    if (text.trim().toLowerCase() === 'clear') {
      setMessages([]);
      setHistory([]);
      return;
    }

    displayMessage('user', text);

    // Cold-start gate REMOVED 2026-06-21: it predated Tara's tool loop and was
    // intercepting market-wide / scan / pick questions ("what's the best tech
    // setup today?") with a client-side "Click an opportunity in the table"
    // block before they ever reached the server. The server now answers those
    // cold (find_best_opportunities + a blank-message guard), so every non-empty
    // message goes straight through - the server decides whether to load, list,
    // or answer, and it never tells the user to click a row. (opts.fromHome kept
    // for the home-page prefill path.)

    // Add user message to history
    const updatedHistory = [...history, { role: 'user', content: text }];

    // Which market/group the opportunity table is CURRENTLY showing. Tara needs this to know
    // whether the table already matches the group the user is asking about ("which tech
    // stocks ..."): if it does, she answers FROM the passed rows (an exact match to what's on
    // screen); if not, she fires update_view(market) to switch the table to that group. Without
    // it she ran an independent, divergent scan whose names didn't match the visible table.
    const oppMarketName = props.selectedSecurity || '';
    const oppMarketIdRaw = getSelectedIDFromSecuritiesList2(props.securityTypeList || [], oppMarketName);
    const oppMarketId = (oppMarketIdRaw !== -1 && oppMarketIdRaw !== '-1') ? String(oppMarketIdRaw) : '';
    const oppTablePECycle = props.showPEOpps ? `pe${new Date().getFullYear() % 4}` : 'cons';

    const postData = {
      message: text,
      history: updatedHistory.slice(-20), // send last 20 turns max
      wave_viewer: buildWaveViewerContext(),
      screen_context: buildChatbotScreenContext(props),
      opportunities: buildOppTableContext(),
      opp_table_length: props.oppTableLength,
      opp_table_market: oppMarketId,
      opp_table_market_name: oppMarketName,
      opp_table_years: props.oppTableYears,
      opp_table_pe_cycle: oppTablePECycle,
      token: token,
    };

    setIsLoading(true);

    fetch(baseURL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(postData),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const reply = data.reply || '';
        displayMessage('bot', reply);
        // Auto-open popups: check LLM response first, then fall back to keyword matching on the user question
        const hasAction = reply.includes('data-action=');
        const hasMFEMAEViewAction = Array.isArray(data.actions) && data.actions.some(action => (
          action && action.type === 'set_view' && action.spec &&
          (typeof action.spec.show_mfe === 'boolean' || typeof action.spec.show_mae === 'boolean')
        ));
        if (hasAction) {
          if (reply.includes('data-action="open-sharpe-popup"')) setShowSharpePopup(true);
          if (reply.includes('data-action="open-trend-popup"')) setShowTrendPopup(true);
          if (reply.includes('data-action="open-seasonal-popup"')) setShowSeasonalPopup(true);
          if (reply.includes('data-action="open-trendchart-popup"')) setShowTrendChartPopup(true);
          if (reply.includes('data-action="open-barchart-popup"')) setShowBarChartPopup(true);
          if (reply.includes('data-action="open-projection-popup"')) setShowProjectionPopup(true);
          if (reply.includes('data-action="open-pecycle-popup"')) setShowPECyclePopup(true);
          if (reply.includes('data-action="open-mfemae-popup"')) setShowMFEMAEPopup(true);
          if (reply.includes('data-action="open-twr-popup"')) setShowTWRPopup(true);
          if (reply.includes('data-action="open-watchlist-popup"')) setShowWatchlistPopup(true);
          if (reply.includes('data-action="open-opptable-popup"')) setShowOppTablePopup(true);
          if (reply.includes('data-action="open-gettingstarted-popup"')) setShowGettingStartedPopup(true);
          if (reply.includes('data-action="open-daysout-popup"')) setShowDaysOutPopup(true);
          if (reply.includes('data-action="open-years-popup"')) setShowYearsRangePopup(true);
          if (reply.includes('data-action="open-filtering-popup"')) setShowFilteringPopup(true);
          if (reply.includes('data-action="open-aiscores-popup"')) setShowAIScoresPopup(true);
        } else if (!hasMFEMAEViewAction) {
          // Fallback: match user question keywords to auto-open the most relevant popup
          const q = text.toLowerCase();
          const popupKeywordMap = [
            { keywords: ['getting started', 'new here', "i'm new", 'i am new', 'teach me', 'how do i use', 'walk me through', 'where do i start', 'tour'], setter: setShowGettingStartedPopup },
            { keywords: ['sharpe ratio', 'sharpe', 'what is sr', 'risk adjusted'], setter: setShowSharpePopup },
            { keywords: ['trend score', 'trend long', 'trend short', 'what is tl', 'what is ts'], setter: setShowTrendPopup },
            { keywords: ['seasonality', 'seasonal pattern', 'what is seasonal', 'how seasonal'], setter: setShowSeasonalPopup },
            { keywords: ['trend chart', 'price chart with seasonal'], setter: setShowTrendChartPopup },
            { keywords: ['bar chart', 'year by year', 'green bars', 'red bars', 'gain loss chart'], setter: setShowBarChartPopup },
            { keywords: ['projection', 'dashed golden', 'projected price', 'where will price'], setter: setShowProjectionPopup },
            { keywords: ['pe cycle', 'presidential election', 'election cycle', 'midterm', 'pe+1', 'pe+2', 'pe+3'], setter: setShowPECyclePopup },
            { keywords: ['mfe', 'mae', 'maximum favorable', 'maximum adverse', 'excursion', 'drawdown'], setter: setShowMFEMAEPopup },
            { keywords: ['twr', 'tradewave ratio'], setter: setShowTWRPopup },
            { keywords: ['watchlist', 'watch list', 'track stocks'], setter: setShowWatchlistPopup },
            { keywords: ['opportunity table', 'opp table', 'how to read the table', 'what is the table'], setter: setShowOppTablePopup },
            { keywords: ['days out', 'holding period', 'how long to hold'], setter: setShowDaysOutPopup },
            { keywords: ['years setting', 'data depth', 'lookback', 'how many years', 'how far back'], setter: setShowYearsRangePopup },
            { keywords: ['filter syntax', 'how to filter', 'advanced filter', 'filter the table'], setter: setShowFilteringPopup },
            { keywords: ['ai score', 'ai column', 'ais column', 'win prob', 'predicted return', 'pred return', 'pmfe', 'predicted mfe', 'ai calibrat', 'ml score', 'machine learning'], setter: setShowAIScoresPopup },
          ];
          for (const entry of popupKeywordMap) {
            if (entry.keywords.some(kw => q.includes(kw))) {
              entry.setter(true);
              break; // only open one popup
            }
          }
        }
        // Phase 2: apply any wave-viewer actions Tara requested (load a symbol/setup, change knobs)
        if (Array.isArray(data.actions)) {
          for (const action of data.actions) {
            if (action && action.type === 'set_view' && action.spec) {
              applyViewSpec(action.spec);
            } else if (action && action.type === 'load_opportunity' && action.spec) {
              // This is the deterministic equivalent of clicking the visible row. Keep the
              // table's string lookback and row highlight aligned with the loaded chart.
              applyViewSpec(action.spec);
              props.SetSeasonalYears(String(props.oppTableYears));
              if (Number.isInteger(action.rank) && action.rank >= 1) {
                props.SetRowIndexClicked(action.rank - 1);
              }
            }
          }
        }
        // Keep history in plain text (strip HTML tags for history context)
        const plainReply = reply.replace(/<[^>]*>/g, '');
        setHistory([...updatedHistory, { role: 'assistant', content: plainReply }]);
        setIsLoading(false);
      })
      .catch((err) => {
        displayMessage('bot', `Error: ${err.message}`);
        setHistory(updatedHistory);
        setIsLoading(false);
      });
  };

  //--------------------------------------------------------------------------------------------------------
  const handleKeyDown = (event) => {
    if (event.key === 'Enter') handleSend();
  };

  //--------------------------------------------------------------------------------------------------------
  // Loads opportunity to the wave-viewer operated from the chatbot
  const loadOppWV = (rid, date, tcsd, symbol, days, years) => {
    const resource_group = resourceObj[parseInt(rid)];
    if (shouldClearOpportunityTable(props.selectedSecurity, resource_group)) {
      props.SetOpportunities([]);
    }
    props.SetStartDate(date);
    let trend_chart_start_date = incrementDate(date, -trend_chart_left_gap_days);
    props.SetTrendChartStartDate(trend_chart_start_date);
    props.SetSymbol(symbol);
    props.SetSeasonalYears(years);
    props.SetConsolidatedSeasonalData([]);
    props.SetDaysOut(days);
    props.SetMonthsAndQtrs('Months & Qtrs');
    props.SetReportsDashVisible(false);
    props.SetSelectedSecurity(resource_group);
  };

  //--------------------------------------------------------------------------------------------------------
  // Phase 2: apply a validated ViewSpec from Tara (update_view) to DRIVE the wave-viewer. The
  // server already allowlists + range-checks the spec; we re-check each field here (defense in
  // depth) before touching state. Loading a symbol mirrors loadOppWV (clear stale state first).
  const applyViewSpec = (spec) => {
    if (!spec || typeof spec !== 'object') return;
    if (spec.market != null && resourceObj && resourceObj[parseInt(spec.market)]) {
      const targetMarket = resourceObj[parseInt(spec.market)];
      if (shouldClearOpportunityTable(props.selectedSecurity, targetMarket)) {
        props.SetOpportunities([]);
      }
      props.SetSelectedSecurity(targetMarket);
    }
    // Only a CHANGE of symbol is a fresh load (clear stale chart/report state); when the model
    // re-asserts the already-loaded symbol alongside a knob change, leave the chart in place.
    if (typeof spec.symbol === 'string' && /^[A-Za-z0-9.-]{1,15}$/.test(spec.symbol)) {
      const sym = spec.symbol.toUpperCase();
      if (sym !== (props.symbol || '').toUpperCase()) {
        props.SetConsolidatedSeasonalData([]);
        props.SetReportsDashVisible(false);
        props.SetMonthsAndQtrs('Months & Qtrs');
        props.SetSymbol(sym);
      }
    }
    if (typeof spec.entry_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(spec.entry_date)) {
      props.SetStartDate(spec.entry_date);
      props.SetTrendChartStartDate(incrementDate(spec.entry_date, -trend_chart_left_gap_days));
    }
    if (Number.isInteger(spec.days_out) && spec.days_out >= 1 && spec.days_out <= 366) {
      props.SetDaysOut(spec.days_out);
    }
    if (Number.isInteger(spec.years) && spec.years >= 1 && spec.years <= 99) {
      let years = spec.years;
      const targetCycle = typeof spec.pe_cycle === 'string' ? spec.pe_cycle : props.PEselected;
      const maxAvailable = Number.parseInt(String(props.maxAvailableYears), 10);
      // The model/API schema permits 1..99, but 99 is not a "max history" sentinel.
      // In consecutive mode, never let an out-of-range action put a controlled select
      // into a value it cannot display (the browser otherwise shows its first option).
      if (targetCycle === 'cons' && Number.isInteger(maxAvailable) && maxAvailable > 0) {
        years = Math.min(years, maxAvailable);
      }
      props.SetSeasonalYears(String(years));
    }
    if (typeof spec.pe_cycle === 'string' && ['cons', 'pe0', 'pe1', 'pe2', 'pe3'].includes(spec.pe_cycle)) {
      if (props.SetPEselected) props.SetPEselected(spec.pe_cycle);
    }
    if (typeof spec.show_mfe === 'boolean' && typeof props.setShowMFE === 'function') {
      props.setShowMFE(spec.show_mfe);
      setCookie('MFE', spec.show_mfe.toString(), 300);
    }
    if (typeof spec.show_mae === 'boolean' && typeof props.setShowMAE === 'function') {
      props.setShowMAE(spec.show_mae);
      setCookie('MAE', spec.show_mae.toString(), 300);
    }
  };

  //--------------------------------------------------------------------------------------------------------
  const handleRowClick = (event) => {
    // Handle action links (e.g. open-sharpe-popup, open-trend-popup)
    const actionLink = event.target.closest('[data-action]');
    if (actionLink) {
      event.preventDefault();
      const action = actionLink.dataset.action;
      if (action === 'open-sharpe-popup') setShowSharpePopup(true);
      else if (action === 'open-trend-popup') setShowTrendPopup(true);
      else if (action === 'open-seasonal-popup') setShowSeasonalPopup(true);
      else if (action === 'open-trendchart-popup') setShowTrendChartPopup(true);
      else if (action === 'open-barchart-popup') setShowBarChartPopup(true);
      else if (action === 'open-projection-popup') setShowProjectionPopup(true);
      else if (action === 'open-pecycle-popup') setShowPECyclePopup(true);
      else if (action === 'open-mfemae-popup') setShowMFEMAEPopup(true);
      else if (action === 'open-twr-popup') setShowTWRPopup(true);
      else if (action === 'open-watchlist-popup') setShowWatchlistPopup(true);
      else if (action === 'open-opptable-popup') setShowOppTablePopup(true);
      else if (action === 'open-gettingstarted-popup') setShowGettingStartedPopup(true);
      else if (action === 'open-daysout-popup') setShowDaysOutPopup(true);
      else if (action === 'open-years-popup') setShowYearsRangePopup(true);
      else if (action === 'open-filtering-popup') setShowFilteringPopup(true);
      else if (action === 'open-aiscores-popup') setShowAIScoresPopup(true);
      else if (action === 'switch-viewer-cycle') {
        const nextCycle = actionLink.dataset.cycle;
        if (isViewerCycle(nextCycle)) {
          window.dispatchEvent(new CustomEvent(VIEWER_CYCLE_CHANGE_EVENT, {
            detail: { cycle: nextCycle },
          }));
        }
      }
      return;
    }

    const row = event.target.closest('tr');
    if (row && row.dataset.rid) {
      const { rid, date, tcsd, symbol, days, years } = row.dataset;
      loadOppWV(rid, date, tcsd, symbol, days, years);
    }
  };

  //--------------------------------------------------------------------------------------------------------
  const userLabelColor  = props.UITheme === 'dark' ? '#6aadff' : '#1a6bb5';
  const botLabelColor   = props.UITheme === 'dark' ? '#6fcc8a' : '#2a7a3b';
  const mutedColor      = tc.textSecondary;

  return (
    <div
      id="tradewave-chatbot-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        boxSizing: 'border-box',
        backgroundColor: tc.panelBg,
      }}
    >
      {/* Chatbox Display */}
      <div
        ref={chatboxRef}
        id="chatbox"
        style={{
          flex: 1,
          border: '1px solid ' + tc.inputBorder,
          overflowY: 'auto',
          padding: '10px',
          boxSizing: 'border-box',
          fontSize: '0.85vw',
          color: tc.text,
          backgroundColor: tc.statValueBg,
          colorScheme: props.UITheme === 'dark' ? 'dark' : 'light',
        }}
        onClick={handleRowClick}
      >
        {messages.map((msg, index) => (
          <div
            key={index}
            className={msg.role === 'bot' ? 'tara-chat-message tara-chat-message-bot' : 'tara-chat-message tara-chat-message-user'}
            style={{
              marginBottom: '6px',
              '--tara-analysis-accent': botLabelColor,
              '--tara-analysis-bg': tc.panelBg,
              '--tara-analysis-border': tc.inputBorder,
              '--tara-analysis-muted': mutedColor,
            }}
          >
            <strong style={{ color: msg.role === 'user' ? userLabelColor : botLabelColor }}>
              {msg.role === 'user' ? 'You' : 'Tara'}:
            </strong>
            <div className="tara-message-body" dangerouslySetInnerHTML={{ __html: sanitizeBotHtml(msg.text) }} />
          </div>
        ))}
        {isLoading && (
          <div style={{ color: mutedColor, fontStyle: 'italic' }}>Tara is thinking...</div>
        )}
      </div>

      {/* Input Field and Button */}
      <div
        style={{
          display: 'flex',
          padding: '6px',
          boxSizing: 'border-box',
          gap: '6px',
          backgroundColor: tc.panelBg,
        }}
      >
        <input
          type="text"
          placeholder="Ask about the current pattern or opportunities..."
          style={{
            flex: 1,
            padding: '5px',
            fontSize: '0.8vw',
            backgroundColor: tc.selectBg,
            color: tc.selectText,
            border: '1px solid ' + tc.inputBorder,
          }}
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
        />
        <button
          style={{
            width: '60px',
            padding: '5px',
            fontSize: '0.8vw',
            backgroundColor: tc.closeBtnBg,
            color: tc.text,
            border: '1px solid ' + tc.inputBorder,
            cursor: isLoading ? 'default' : 'pointer',
          }}
          onClick={handleSend}
          disabled={isLoading}
        >
          Send
        </button>
      </div>

      {showTrendPopup && <TrendScorePopup onClose={() => setShowTrendPopup(false)} iconRect={null} />}
      {showSharpePopup && <SharpeRatioPopup onClose={() => setShowSharpePopup(false)} iconRect={null} />}
      {showSeasonalPopup && <SeasonalPatternsPopup onClose={() => setShowSeasonalPopup(false)} iconRect={null} />}
      {showTrendChartPopup && <TrendChartPopup onClose={() => setShowTrendChartPopup(false)} iconRect={null} />}
      {showBarChartPopup && <BarChartPopup onClose={() => setShowBarChartPopup(false)} iconRect={null} />}
      {showProjectionPopup && <ProjectionPopup onClose={() => setShowProjectionPopup(false)} iconRect={null} />}
      {showPECyclePopup && <PECyclePopup onClose={() => setShowPECyclePopup(false)} iconRect={null} />}
      {showMFEMAEPopup && <MFEMAEPopup onClose={() => setShowMFEMAEPopup(false)} iconRect={null} />}
      {showTWRPopup && <TWRPopup onClose={() => setShowTWRPopup(false)} iconRect={null} />}
      {showWatchlistPopup && <WatchlistPopup onClose={() => setShowWatchlistPopup(false)} iconRect={null} />}
      {showOppTablePopup && <OppTablePopup onClose={() => setShowOppTablePopup(false)} iconRect={null} />}
      {showGettingStartedPopup && <GettingStartedPopup onClose={() => setShowGettingStartedPopup(false)} iconRect={null} />}
      {showDaysOutPopup && <DaysOutPopup onClose={() => setShowDaysOutPopup(false)} iconRect={null} />}
      {showYearsRangePopup && <YearsRangePopup onClose={() => setShowYearsRangePopup(false)} iconRect={null} />}
      {showFilteringPopup && <FilteringPopup onClose={() => setShowFilteringPopup(false)} iconRect={null} />}
      {showAIScoresPopup && <AIScoresPopup onClose={() => setShowAIScoresPopup(false)} iconRect={null} />}
    </div>
  );
}

export default Chatbot;
