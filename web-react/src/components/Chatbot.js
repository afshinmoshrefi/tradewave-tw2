import React, { useState, useEffect, useRef, useContext } from 'react';
import { UserContext } from './UserContext';
import { appserverURL, trend_chart_left_gap_days, incrementDate, themeColors, getSelectedIDFromSecuritiesList2 } from './Common';
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
import {
  containsInternalToolMarkup,
  taraTrendFailureHasPrimaryData,
  taraViewKey,
} from './taraActionContract';

//--------------------------------------------------------------------------------------------------------
// The bot reply is model-generated HTML rendered via dangerouslySetInnerHTML; with Tara now
// tool-driven and fed user-influenceable context, a crafted prompt could try to emit active
// markup. Strip the XSS vectors (script/style/iframe blocks, inline on* handlers, javascript:/
// data: URLs) while keeping the legit formatting vocabulary (b/br/i/a[data-action]/span).
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
  s = s.replace(/(href|src)\s*=\s*"\s*(?:javascript|data|vbscript):[^"]*"/gi, '$1="#"');
  s = s.replace(/(href|src)\s*=\s*'\s*(?:javascript|data|vbscript):[^']*'/gi, "$1='#'");
  return s;
};

const botHtmlToPlainText = (html) => {
  const safe = sanitizeBotHtml(html).replace(/<br\s*\/?>/gi, '\n');
  if (typeof document !== 'undefined') {
    const node = document.createElement('div');
    node.innerHTML = safe;
    return String(node.textContent || '').trim();
  }
  return safe.replace(/<[^>]*>/g, '').trim();
};

const taraFailureDetail = (reason) => {
  if (reason === 'rate_limited') return 'the chart service is temporarily rate-limited';
  if (reason === 'not_enough_data') return 'there is not enough history for that setup';
  if (reason === 'empty_or_malformed_chart_data') return 'the server returned no usable chart data';
  if (reason === 'server_normalized_or_unverified_request') {
    return 'the server adjusted the requested date or lookback';
  }
  if (reason === 'view_superseded') return 'the view changed before the request finished';
  if (reason === 'chart_load_timeout') return 'the chart request timed out';
  if (reason === 'network_error') return 'the chart service could not be reached';
  if (String(reason || '').startsWith('trend_')) {
    return 'the lower seasonal graph could not be verified';
  }
  if (String(reason || '').startsWith('http_')) return 'the chart service returned an error';
  return 'the chart request did not complete';
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
  const [pendingViewTransaction, setPendingViewTransaction] = useState(null);
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
  const actionAuditAfterRenderRef = useRef(null);

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

  const postActionResult = (pending, actionState, status, reason, displayedResponse) => {
    const payload = {
      token,
      turn_id: pending.turnId,
      actions: pending.actionProofs,
      status,
      reason: reason || '',
      observed_view: actionState?.observed_view || null,
      data_points: actionState?.data_points || 0,
      displayed_response: displayedResponse || '',
    };
    const send = (attempt) => {
      fetch(`${asURL}/chatbot/action_result`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      }).then(response => {
        if (response.ok) return;
        const err = new Error(`HTTP ${response.status}`);
        err.retryable = response.status === 429 || response.status >= 500;
        throw err;
      }).catch(err => {
        if (attempt < 2 && err?.retryable !== false) {
          setTimeout(() => send(attempt + 1), 750 * (attempt + 1));
          return;
        }
        // The chart result remains authoritative even if audit transport fails.
        console.warn('Tara action audit failed:', err?.message || err);
      });
    };
    send(0);
  };

  // Post only after React has committed the sanitized reply into Tara's
  // message list. Keeping Chatbot mounted while hidden guarantees this effect
  // also runs when the user closes the panel mid-load.
  useEffect(() => {
    const queued = actionAuditAfterRenderRef.current;
    if (!queued) return;
    actionAuditAfterRenderRef.current = null;
    postActionResult(
      queued.pending,
      queued.actionState,
      queued.status,
      queued.reason,
      queued.displayedResponse,
    );
  }, [messages]); // eslint-disable-line react-hooks/exhaustive-deps

  // The model's prose is held back while a view action is pending. Only this
  // client-side terminal state may append a completion statement.
  useEffect(() => {
    if (!pendingViewTransaction || !props.taraActionState) return;
    const state = props.taraActionState;
    const sameActions = (
      Array.isArray(state.action_ids)
      && state.action_ids.join('|') === pendingViewTransaction.actionIds.join('|')
    );
    if (!sameActions || !['succeeded', 'failed'].includes(state.status)) return;

    let finalReply;
    let auditStatus;
    if (state.status === 'succeeded') {
      const requested = state.requested_spec || {};
      const symbol = state.target?.symbol;
      const confirmation = state.requires_chart_data
        ? `${symbol ? `<b>${symbol}</b> ` : ''}pattern and seasonal graph loaded in the Wave Viewer.`
        : (requested.market ? 'Market selection updated.' : 'View settings updated.');
      finalReply = `${pendingViewTransaction.reply || ''}${pendingViewTransaction.reply ? '<br><br>' : ''}${confirmation}`;
      auditStatus = 'succeeded';
    } else {
      const symbol = state.target?.symbol;
      const detail = taraFailureDetail(state.reason);
      finalReply = taraTrendFailureHasPrimaryData(state)
        ? (
          `The pattern data for${symbol ? ` <b>${symbol}</b>` : ' that view'} arrived, `
          + `but ${detail}. I have not marked the full view as loaded; please try again.`
        )
        : (
          `I couldn't load${symbol ? ` <b>${symbol}</b>` : ' that view'} because ${detail}. `
          + 'I have not marked it as loaded; please try again.'
        );
      auditStatus = 'failed';
    }

    const plainReply = botHtmlToPlainText(finalReply);
    actionAuditAfterRenderRef.current = {
      pending: pendingViewTransaction,
      actionState: state,
      status: auditStatus,
      reason: state.reason || '',
      displayedResponse: plainReply,
    };
    displayMessage('bot', finalReply);
    setHistory([
      ...pendingViewTransaction.updatedHistory,
      { role: 'assistant', content: plainReply },
    ]);
    setPendingViewTransaction(null);
    setIsLoading(false);
  }, [pendingViewTransaction, props.taraActionState]); // eslint-disable-line react-hooks/exhaustive-deps

  //--------------------------------------------------------------------------------------------------------
  // Build wave viewer context from props
  const buildWaveViewerContext = () => {
    const marketIdRaw = getSelectedIDFromSecuritiesList2(
      props.securityTypeList || [],
      props.selectedSecurity || ''
    );
    const currentView = {
      market: (
        marketIdRaw !== undefined
        && marketIdRaw !== null
        && String(marketIdRaw) !== '-1'
      ) ? String(marketIdRaw) : '',
      symbol: String(props.symbol || '').toUpperCase(),
      entry_date: props.startDate || '',
      days_out: parseInt(props.daysOut, 10),
      years: parseInt(props.seasonalYears, 10),
      pe_cycle: props.PEselected || 'cons',
      cut_off_year: Number(props.trimYear || 0),
    };
    const viewReady = (
      props.viewerDataState
      && props.viewerDataState.status === 'succeeded'
      && props.viewerDataState.request_key === taraViewKey(currentView)
    );
    const ctx = {
      market: currentView.market,
      symbol: props.symbol || '',
      start_date: props.startDate || '',
      entry_date: props.startDate || '',
      days_out: props.daysOut || '',
      years: props.seasonalYears || '',
      pe_cycle: props.PEselected || 'cons',
      direction: props.barChartLongOrShort || 'long',
      mae_enabled: props.showMAE === true,
      view_ready: viewReady,
      view_request_key: viewReady ? props.viewerDataState.request_key : '',
    };
    // Include last known price for the security
    if (viewReady && props.company) ctx.company = props.company;
    if (
      viewReady
      && Array.isArray(props.lastPrice)
      && props.lastPriceIdentity === `${currentView.market}|${currentView.symbol}`
      && props.lastPrice[0]
      && props.lastPrice[1]
    ) {
      ctx.last_price = props.lastPrice[1];
      ctx.last_price_date = props.lastPrice[0];
    }
    // Include stats if available (tradeDetailData is an object with keys like
    // 'Percent Profitable', 'Avg Profit', 'Sharpe Ratio', etc.)
    if (viewReady && props.tradeDetailData && Object.keys(props.tradeDetailData).length > 0) {
      ctx.stats = props.tradeDetailData;
    }
    // Include year-by-year bar chart data so the bot can discuss specific years
    if (viewReady && Array.isArray(props.seasonalBarChartData) && props.seasonalBarChartData.length > 0) {
      ctx.yearly_results = props.seasonalBarChartData.map(r => {
        const plist = r['pct'].split(',');
        return {
          year: r['year'],
          return_pct: parseFloat(plist[0]),
          mfe_pct: parseFloat(plist[1]) || 0,
          mae_pct: parseFloat(plist[2]) || 0,
        };
      });
    }
    return ctx;
  };

  //--------------------------------------------------------------------------------------------------------
  // Build a trimmed opportunities list to send as context (max 50 rows, key fields only)
  const buildOppTableContext = () => {
    if (!Array.isArray(props.opportunities) || props.opportunities.length === 0) return [];
    return props.opportunities.slice(0, 50).map(o => ({
      date: o.date,
      symbol: o.symbol,
      days_out: o.daysOut,
      direction: o.lOrS,
      avg_profit: o.avg_profit,
      sharpe_ratio: o.sharpe_ratio,
    }));
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
    const oppMarketId = (
      oppMarketIdRaw !== undefined
      && oppMarketIdRaw !== null
      && String(oppMarketIdRaw) !== '-1'
    ) ? String(oppMarketIdRaw) : '';

    const postData = {
      message: text,
      history: updatedHistory.slice(-20), // send last 20 turns max
      wave_viewer: buildWaveViewerContext(),
      opportunities: buildOppTableContext(),
      opp_table_length: props.oppTableLength,
      opp_table_market: oppMarketId,
      opp_table_market_name: oppMarketName,
      opp_table_years: props.oppTableYears,
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
        if (containsInternalToolMarkup(reply)) {
          const safeReply = (
            "I couldn't produce a valid chart action, so I haven't changed the chart. "
            + 'Please try that request again.'
          );
          displayMessage('bot', safeReply);
          setHistory([...updatedHistory, { role: 'assistant', content: safeReply }]);
          setIsLoading(false);
          return;
        }
        // Auto-open popups: check LLM response first, then fall back to keyword matching on the user question
        const hasAction = reply.includes('data-action=');
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
        } else {
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
        const viewActions = Array.isArray(data.actions)
          ? data.actions.filter(action => action && action.type === 'set_view')
          : [];
        if (viewActions.length > 0) {
          if (typeof props.BeginTaraViewAction !== 'function') {
            const safeReply = "I couldn't connect that request to the chart, so nothing was marked as loaded.";
            displayMessage('bot', safeReply);
            setHistory([...updatedHistory, { role: 'assistant', content: safeReply }]);
            setIsLoading(false);
            return;
          }
          const accepted = props.BeginTaraViewAction(viewActions, data.turn_id || '');
          if (!accepted || !accepted.ok) {
            const safeReply = "I couldn't validate that chart request, so I haven't changed the chart.";
            if (accepted?.audit) {
              actionAuditAfterRenderRef.current = {
                pending: {
                  turnId: accepted.audit.turn_id,
                  actionProofs: accepted.audit.action_proofs,
                },
                actionState: null,
                status: 'failed',
                reason: accepted.reason || 'client_validation_failed',
                displayedResponse: botHtmlToPlainText(safeReply),
              };
            }
            displayMessage('bot', safeReply);
            setHistory([...updatedHistory, { role: 'assistant', content: safeReply }]);
            setIsLoading(false);
            return;
          }
          setPendingViewTransaction({
            turnId: data.turn_id || '',
            actionIds: accepted.transaction.action_ids,
            actionProofs: accepted.transaction.action_proofs,
            reply,
            updatedHistory,
          });
          // Keep the loading indicator active. The terminal ChartData4 result
          // effect displays either the model prose + deterministic success, or
          // a deterministic failure with no success language.
          return;
        }

        displayMessage('bot', reply);
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
    props.SetOpportunities([]);
    props.SetStartDate(date);
    let trend_chart_start_date = incrementDate(date, -trend_chart_left_gap_days);
    props.SetTrendChartStartDate(trend_chart_start_date);
    props.SetSymbol(symbol);
    props.SetSeasonalYears(years);
    props.SetConsolidatedSeasonalData([]);
    props.SetDaysOut(days);
    props.SetMonthsAndQtrs('Months & Qtrs');
    let resource_group = resourceObj[parseInt(rid)];
    props.SetReportsDashVisible(false);
    props.SetSelectedSecurity(resource_group);
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
          <div key={index} style={{ marginBottom: '6px' }}>
            <strong style={{ color: msg.role === 'user' ? userLabelColor : botLabelColor }}>
              {msg.role === 'user' ? 'You' : 'Tara'}:
            </strong>
            <div dangerouslySetInnerHTML={{ __html: sanitizeBotHtml(msg.text) }} />
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
