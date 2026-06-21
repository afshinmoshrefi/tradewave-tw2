import React, { useState, useEffect, useRef, useContext } from 'react';
import { UserContext } from './UserContext';
import { appserverURL, trend_chart_left_gap_days, incrementDate, themeColors } from './Common';
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

  // Intro message on first open, include pending tip if one exists
  useEffect(() => {
    const intro = [{ role: 'bot', text: "Hi, I'm <b>Tara</b>. Ask me for today's best setups, any stock's seasonal pattern, or a concept like <b>what is a Sharpe ratio</b> - I'll pull it up on the chart and explain it." }];
    if (props.chatbotPendingTip) {
      intro.push({ role: 'bot', text: props.chatbotPendingTip });
      if (props.SetChatbotPendingTip) props.SetChatbotPendingTip(null);
    }
    setMessages(intro);
  }, []);

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
    const ctx = {
      symbol: props.symbol || '',
      company: props.company || '',
      start_date: props.startDate || '',
      days_out: props.daysOut || '',
      years: props.seasonalYears || '',
      pe_cycle: props.PEselected || 'cons',
      direction: props.barChartLongOrShort || 'long',
      mae_enabled: props.showMAE === true,
    };
    // Include last known price for the security
    if (Array.isArray(props.lastPrice) && props.lastPrice[0] && props.lastPrice[1]) {
      ctx.last_price = props.lastPrice[1];
      ctx.last_price_date = props.lastPrice[0];
    }
    // Include stats if available (tradeDetailData is an object with keys like
    // 'Percent Profitable', 'Avg Profit', 'Sharpe Ratio', etc.)
    if (props.tradeDetailData && Object.keys(props.tradeDetailData).length > 0) {
      ctx.stats = props.tradeDetailData;
    }
    // Include year-by-year bar chart data so the bot can discuss specific years
    if (Array.isArray(props.seasonalBarChartData) && props.seasonalBarChartData.length > 0) {
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

    const postData = {
      message: text,
      history: updatedHistory.slice(-20), // send last 20 turns max
      wave_viewer: buildWaveViewerContext(),
      opportunities: buildOppTableContext(),
      opp_table_length: props.oppTableLength,
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
        // Phase 2: apply any wave-viewer actions Tara requested (load a symbol/setup, change knobs)
        if (Array.isArray(data.actions)) {
          for (const action of data.actions) {
            if (action && action.type === 'set_view' && action.spec) applyViewSpec(action.spec);
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
  // Phase 2: apply a validated ViewSpec from Tara (update_view) to DRIVE the wave-viewer. The
  // server already allowlists + range-checks the spec; we re-check each field here (defense in
  // depth) before touching state. Loading a symbol mirrors loadOppWV (clear stale state first).
  const applyViewSpec = (spec) => {
    if (!spec || typeof spec !== 'object') return;
    if (spec.market != null && resourceObj && resourceObj[parseInt(spec.market)]) {
      props.SetSelectedSecurity(resourceObj[parseInt(spec.market)]);
    }
    // Only a CHANGE of symbol is a fresh load (clear stale chart/report state); when the model
    // re-asserts the already-loaded symbol alongside a knob change, leave the chart in place.
    if (typeof spec.symbol === 'string' && /^[A-Za-z0-9.\-]{1,15}$/.test(spec.symbol)) {
      const sym = spec.symbol.toUpperCase();
      if (sym !== (props.symbol || '').toUpperCase()) {
        props.SetOpportunities([]);
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
      props.SetSeasonalYears(String(spec.years));
    }
    if (typeof spec.pe_cycle === 'string' && ['cons', 'pe0', 'pe1', 'pe2', 'pe3'].includes(spec.pe_cycle)) {
      if (props.SetPEselected) props.SetPEselected(spec.pe_cycle);
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
