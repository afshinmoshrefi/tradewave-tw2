
// first 2 characters of tooltip content define the position.  
// l, is left tooltip while b, is bottom tooltip

import React, { useState, useEffect, useContext, useRef, useCallback, useMemo } from 'react'
import ReactDOM from 'react-dom'
import TableBox from './TableBox'
import SelectBox from './SelectBox'
import TextBoxS from './TextBoxS'
// import TextBoxInc from './TextBoxInc'
import './styles/OppTable.css'
import { monthsOptionsList, monthsOptionsListS, appserverURL, getTodayDate } from './Common'
import { redirectBackFromSeasonals } from './Common'
import { UserContext } from './UserContext'
import { FaAngleLeft, FaAngleRight } from "react-icons/fa";
import { BsArrowsExpand, BsArrowsCollapse, BsQuestionCircle, BsPencilSquare } from "react-icons/bs";
import { getSelectedIDFromSecuritiesList2 } from './Common'
import Tippy from '@tippyjs/react'
import { userAccessToSelectedSecurity } from './Common'
import { opp_dashboard_dialog_content } from './Common'
import { settings_dialog_content } from './Common'
import { trend_chart_left_gap_days, maxYearsCap } from './Common'
import jwt_decode from 'jwt-decode'
import { SlSettings } from "react-icons/sl";
import { incrementDate } from './Common'
import { markCaptureReady, clearCaptureReady } from './captureReady'
import { BsFillCircleFill } from "react-icons/bs"
import { BsChatDotsFill, BsChatDots } from "react-icons/bs";
import CheckBox from './CheckBox'
import { themeColors, setCookie, tierHasAI } from './Common'
import { twFetch } from './twFetch'
import {
  analyzeOpportunityFilter,
  EMPTY_DAY_RANGE,
  getOpportunityDayRange,
  normalizeOpportunityFilterText,
  toOpportunityEngineDayRange,
} from './opportunityFilters'
import {
  authoritativeOpportunityTableDate,
  selectDisplayedOpportunityRows,
  selectOpportunityMLScoreSource,
} from './opportunityMLSource'
import { resolveOpportunityRecurrence } from './opportunityRecurrence'
import { normalizeRealtimeQuote } from './realtimePrices'
import {
  advanceOpportunityAIPollBudget,
  isPhonePortrait,
  normalizeOpportunityAIScore,
  opportunityAIRetryDelayMs,
  opportunityAIScoreProgressSignature,
  resolveOpportunityShortDates,
} from './opportunityAIScores'
import {
  buildOpportunityViewerAIRequest,
  createOpportunityAISelectionAnchor,
  currentNewYorkMarketDate,
  selectOpportunityAIPanelSelection,
  shouldInvalidateOpportunityAIAnchor,
  terminalizeOpportunityViewerScores,
} from './opportunityViewerAIScore'
import {
  DEFAULT_OPPORTUNITY_SORT,
  buildOpportunitySortOptions,
  opportunitySortValue,
  parseOpportunitySortValue,
} from './opportunitySorting'

const TARA_LAUNCHER_TOOLTIP_COPY = Object.freeze({
  closed: {
    title: 'Meet Tara, Your TradeWave AI Guide',
    description: "She finds market behavior that repeated around similar dates in past years, loads it on the chart, and explains what you're seeing.",
    prompts: ["Show me today's top pattern."],
    action: 'Open Tara',
  },
  open: {
    title: 'Tara Is Your TradeWave AI Guide',
    description: "She can find a historical pattern, explain this screen and its numbers, or analyze what's loaded in plain English.",
    prompts: ['What am I looking at?', 'Analyze this pattern.'],
    action: 'Hide Chat',
  },
});

const mlPendingKey = opportunity => {
  const engineDays = parseInt(opportunity && opportunity.daysOut, 10)
  const symbol = opportunity && opportunity.symbol
  const direction = opportunity && opportunity.direction

  return `${symbol}|${opportunity && opportunity.date}|${engineDays}|${direction}`
}

const emptyViewerMLState = () => ({
  requestKey: '',
  scores: {},
  pendingKeys: new Set(),
  loading: false,
  unavailableReason: '',
})

const OppTable = (props) => {
  const tc = themeColors(props.UITheme)
  const setOpportunityAIState = props.SetOpportunityAIState
  const selectedSecurityForAI = props.selectedSecurity
  const viewerCycleForAI = String(props.PEselected || 'cons').trim().toLowerCase()
  const viewerModeForAI = viewerCycleForAI.startsWith('pe') ? 'pe' : 'consecutive'
  const viewerIsBuyAndHold = props.monthsAndQtrs === 'Buy & Hold'
  const taraLauncherCopy = props.showChatbot
    ? TARA_LAUNCHER_TOOLTIP_COPY.open
    : TARA_LAUNCHER_TOOLTIP_COPY.closed;

  const selectbox = document.getElementById('securityTypeList');


  const { wpUserLevels, browserH, browserW, rdd, token, globalTextSize, debug, loggedinUser } = useContext(UserContext)

  const phonePortrait = isPhonePortrait(rdd, browserH, browserW)

  // Resolved once and passed down, so the year label below and TableBox's date
  // cells can never disagree about whether the year is being shown.
  const effectiveShortDates = resolveOpportunityShortDates({
    shortDates: props.shortDates,
    phonePortrait,
  })

  const [seasonalYearsOptionsList, SetSeasonalYearsOptionsList] = useState([])
  const [partialSeasonalYearsOptionsList, SetPartialSeasonalYearsOptionsList] = useState([])

  // current value of options 3 lists

  const [oppTablePartialYearsSuffix, SetOppTablePartialYearsSuffix] = useState('')
  const [rowSelectedId, SetRowSelectedId] = useState(-1)

  const [availableFilters, SetAvailableFilters] = useState([])

  const [oppListExpanded, SetOppListExpanded] = useState(0) //implementing expand contract button next to opp filter

  const [initialMessage, SetInitialMessage] = useState('Loading ...')

  const [oppLoadFailed, SetOppLoadFailed] = useState(false)  // OppList4 failed after twFetch retries - show manual Retry
  const [oppRetryNonce, SetOppRetryNonce] = useState(0)      // bumped by the Retry button to re-run the fetch effect

  const [numLongs, SetNumLongs] = useState(0);     // used to show longs vs shorts breakdown on the opp table
  const [numShorts, SetNumShorts] = useState(0);   // used to show longs vs shorts breakdown on the opp table

  const [stockScores, SetStockScores] = useState({})           // { symbol: { lscore, sscore, lscore1, sscore1 } }

  const [mlScores, SetMLScores] = useState({})                 // date-qualified exact scores plus additive long-pattern checkpoint bundles
  const [mlScoresLoading, SetMLScoresLoading] = useState(false) // true until the current opportunity set has a complete AI-score snapshot
  const [mlEnabled, SetMLEnabled] = useState(false)            // true when backend says this user+market has ML access
  const [mlMarketEligible, SetMLMarketEligible] = useState(false) // true only for supported U.S. stock/ETF resources
  const [mlEligibilityResolved, SetMLEligibilityResolved] = useState(false)
  const [mlPending, SetMLPending] = useState(new Set())        // keys still waiting for scores
  const [mlUnavailableReason, SetMLUnavailableReason] = useState('')
  const mlFetchIdRef = useRef(0)                               // prevents stale ML fetches from writing state
  const [viewerMLState, SetViewerMLState] = useState(emptyViewerMLState)
  const [viewerMLRetryNonce, SetViewerMLRetryNonce] = useState(0)
  const viewerMLFetchIdRef = useRef(0)                         // independent generation for one changed Wave Viewer identity
  const viewerMLRetryRef = useRef({ requestKey: '', attempt: 0 })
  const mlBaselineOppsRef = useRef({ contextKey: '', rows: [] })
  const mlPublishedPanelSignatureRef = useRef('')
  const selectedAIRowIdentityRef = useRef(null)
  const [opportunitySortColumn, SetOpportunitySortColumn] = useState(DEFAULT_OPPORTUNITY_SORT.column)
  const [opportunitySortDirection, SetOpportunitySortDirection] = useState(DEFAULT_OPPORTUNITY_SORT.direction)

  // A market switch must hide the prior market's AI panel immediately. The
  // OppList response will authoritatively enable it again for supported U.S.
  // stock and ETF resources.
  useEffect(() => {
    mlFetchIdRef.current += 1
    viewerMLFetchIdRef.current += 1
    SetMLScores({})
    SetMLScoresLoading(false)
    SetMLEnabled(false)
    SetMLMarketEligible(false)
    SetMLEligibilityResolved(false)
    SetMLPending(new Set())
    SetMLUnavailableReason('')
    SetViewerMLState(emptyViewerMLState())
    selectedAIRowIdentityRef.current = null
    if (typeof setOpportunityAIState === 'function') {
      const clearedState = {
        market: selectedSecurityForAI,
        resolved: false,
        eligible: false,
        enabled: false,
        selected: null,
        loading: false,
        unavailableReason: '',
        bundle: null,
      }
      mlPublishedPanelSignatureRef.current = JSON.stringify(clearedState)
      setOpportunityAIState(clearedState)
    }
  }, [selectedSecurityForAI, setOpportunityAIState])

  // The anchor only belongs to its selected market and symbol. Date, duration,
  // history, and cycle changes are scored directly from the current viewer.
  useEffect(() => {
    const anchor = selectedAIRowIdentityRef.current
    if (!shouldInvalidateOpportunityAIAnchor({
      anchor,
      market: props.selectedSecurity,
      symbol: props.symbol,
      date: props.startDate,
      calendarDays: props.daysOut,
      isBuyAndHold: viewerIsBuyAndHold,
    })) return

    selectedAIRowIdentityRef.current = null
    viewerMLFetchIdRef.current += 1
    SetViewerMLState(emptyViewerMLState())
  }, [props.selectedSecurity, props.symbol, props.startDate, props.daysOut, viewerIsBuyAndHold])

  const [dayRange, SetDayRange] = useState(EMPTY_DAY_RANGE)
  const [curText, SetCurText] = useState('')
  // (declared up here, not next to the search textbox below: it is a dep of the OppList4
  //  fetch effect, and a deps array that references a const declared later in the file
  //  is a temporal-dead-zone ReferenceError at render - it blanked the whole panel)

  const userPickedPYearsRef = useRef('')  // the partial-years value the USER explicitly picked, while it is still selected
  const lastOppUrlRef = useRef('')  // last OppList4 URL actually fetched — fetch when the resolved query changes, not when opportunities happens to be empty
  const metaReqRef = useRef(0)      // ordering guard: only the LATEST YearsMetaData2 response may write state (stale/empty responses clobbered the metadata)
  const metaLoadingRef = useRef(false) // synchronous guard: do not validate against metadata from the previous request
  const oppReqRef = useRef(0)       // ordering guard: only the LATEST OppList4 response may write opportunities/activeOpportunities state
  const oppInFlightRef = useRef(false) // true while an OppList4 request is out - lets the dedupe tell "already fetched" from "cleared, nothing coming"
  const oppSettledKeyRef = useRef('')   // the OppList4 query whose response has already landed
  const oppSettledRowsRef = useRef(0)   // how many rows that response produced - 0 means the query itself is empty

  // True when moving to nextDayRange actually changes the OppList4 query. The
  // displayed range is not that query: it is converted at the engine boundary,
  // and several displayed ranges map to one engine range. Only a real query
  // change may clear the rows, because only a real query change refetches them.
  const oppQueryDayRangeChanged = (nextDayRange) =>
    toOpportunityEngineDayRange(nextDayRange) !== toOpportunityEngineDayRange(dayRange)
  const [metaLoading, SetMetaLoading] = useState(false)

  const [PELabel, SetPELabel] = useState(() => {
    const remainder = new Date().getFullYear() % 4;
    switch (remainder) {
      case 0:
        return 'PE';
      case 1:
        return 'PE+1';
      case 2:
        return 'PE+2';
      case 3:
        return 'PE+3';
      default:
        return '';
    }
  });

  const showSecuritiesSelectToolbar = useState(() => {
    if (rdd.isMobile && !rdd.isTablet && browserH < browserW) return true;
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) {
      return true;
    }
    else return false;

  })

  const peMetaAvailable = Array.isArray(props.yearsMetaDataPE) && props.yearsMetaDataPE.length > 0;

  function getMonth(monthName) {
    const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

    const monthIndex = months.findIndex(month => month.toLowerCase() === monthName.toLowerCase());

    if (monthIndex !== -1) return monthIndex + 1;
    else return -1;

  }
  //-------------------------------------------------------------------------------------------------------
  useEffect(() => { // runs when month is changed - sets meta data for opp selectboxes

    var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)

    let base_y = getTodayDate().substring(0, 4);
    let month = getMonth(props.oppTableMonth);
    let day = props.dayOfTheMonth
    let asURL = appserverURL();
    var url = `${asURL}/YearsMetaData2/${id}/${base_y}/${month}/${day}?token=${token}`

    // id === -1 -> securityTypeList hasn't loaded / selectedSecurity not resolved yet.
    // Do NOT fire the fetch: the '/-1/' URL returns the EMPTY sentinel, and when that
    // response lands after the real market's it clobbers yearsMetaData AND spuriously
    // auto-offs PE mode (live-confirmed race in the access log: /YearsMetaData2/-1 and
    // /YearsMetaData2/0 fired the same second). The securityTypeList dep re-runs this
    // effect once the list loads. Mirrors the id guard the OppList4 effect already has.
    // Ordering guard: two metadata fetches can overlap during a market switch; only
    // the latest one may write state (last-writer-wins otherwise -> stuck dropdowns).
    const metaReqId = ++metaReqRef.current
    if (id === -1 || id === '-1') {
      metaLoadingRef.current = false
      SetMetaLoading(false)
      return
    }

    if (token && token.length > 0) { // 4/8/2025 - occational race condition crashes the app with the line below

      let decoded;
      try { decoded = jwt_decode(token); } catch (e) {
        metaLoadingRef.current = false
        SetMetaLoading(false)
        console.error('jwt_decode failed in OppTable meta effect:', e.message)
        return
      }
      let show_sr2_token = decoded['show_sr2'];
      if (show_sr2_token === 1) {
        props.SetShowSR2(true);
      }

      SetOppLoadFailed(false)
      metaLoadingRef.current = true
      SetMetaLoading(true)

      twFetch(url) //meta
        .then(res => {
          // console.log('meta res=', res.status)
          const contentType = res.headers.get("content-type");
          if (contentType && contentType.indexOf("application/json") !== -1) {
            return res.json();
          }
          else if (res.status === 429) { // too many requests
            props.SetDialogType('rate-limit'); //429
            props.SetInfoBoxVisible(true)
          }
          else {
            console.log('response status = ', res.status)
          }
        })
        .then((oppYearsLists) => {

          // console.log('yyyyyyyyyy oppYearsLists=', oppYearsLists)

          if (metaReqId !== metaReqRef.current) return; // stale response - a newer fetch owns the state

          if (oppYearsLists !== undefined) {

            props.SetYearsMetaData(oppYearsLists['YearsMetaData']);
            props.SetYearsMetaDataPE(oppYearsLists['YearsMetaDataPE']);

            // Pick which metadata drives the dropdowns (minimum change: use existing showPEOpps)
            const peMetaAvailable =
              Array.isArray(oppYearsLists['YearsMetaDataPE']) && oppYearsLists['YearsMetaDataPE'].length > 0;

            // Safety auto-off: only disable PE mode once we have real data confirming no PE meta exists
            // (doing this here instead of a useEffect avoids triggering during the transient clear of yearsMetaDataPE)
            if (!peMetaAvailable && props.showPEOpps) {
              props.SetShowPEOpps(false);
              props.SetPEOppsChecked(false);
            }

            const activeMeta =
              (props.showPEOpps && peMetaAvailable)
                ? oppYearsLists['YearsMetaDataPE']
                : oppYearsLists['YearsMetaData'];

            // -----------------------------
            // Main Years dropdown (from activeMeta)
            // -----------------------------
            var years = activeMeta.map((item) => {
              return parseInt(item[0]);
            });

            years = [...new Set(years)];           // unique years
            years.sort((a, b) => { return a - b }); // sort ascending

            var tmp = [];
            const _yrCap = maxYearsCap();   // per-tier years cap (null = uncapped)
            for (var i = 0; i < years.length; i++) {
              const _locked = _yrCap != null && years[i] > _yrCap;   // above the tier's history cap
              tmp.push({ id: years[i], value: years[i].toString(), label: _locked ? years[i] + ' 🔒' : years[i].toString(), locked: _locked });
            }

            SetSeasonalYearsOptionsList(tmp);
            SetRowSelectedId(-1); // reset selected row

            props.dayOfMonthList(props.oppTableMonth);

          }

          // React 17 may render between the metadata setters above. Keep the
          // ref true until both arrays are installed, then allow exactly one
          // validation pass against the new request's data.
          metaLoadingRef.current = false
          SetMetaLoading(false)
        })
        .catch(err => {
          console.log('catch login error=', err.message)
          // Failed after twFetch's own retries - leaving oppLoadFailed unset here stranded the
          // dropdowns empty with no visible failure state. Surface the same failed/Retry state
          // the OppList4 path uses (guarded so a stale request can't clobber a newer success).
          if (metaReqId === metaReqRef.current) {
            metaLoadingRef.current = false
            SetMetaLoading(false)
            SetInitialMessage('* Data temporarily unavailable')
            SetOppLoadFailed(true)
          }
        })
    }
    else {
      metaLoadingRef.current = false
      SetMetaLoading(false)
    }

    SetOppListExpanded(0); // 1/21/2023

  }, [token, props.dayOfTheMonth, props.selectedSecurity, props.showPEOpps, props.securityTypeList, oppRetryNonce]) // 11/30/2021; securityTypeList so the id=-1 early-return re-fires once the list loads; oppRetryNonce so the Retry button also re-fires this fetch

  //-------------------------------------------------------------------------------------------------------
  // runs when years is changed - set the partial year select from metadata 
  // useEffect(() => { if (props.oppTableYears === -1) { props.SetOppTableYears('12'); } }, [props.oppTableYears])

  //-------------------------------------------------------------------------------------------------------
  // this is the current opportunities list loaded from server
  //-------------------------------------------------------------------------------------------------------

  useEffect(() => {
    // A token, date, market, or PE-mode change can start a metadata request
    // while the previous metadata is still in props. Never use that stale
    // array to declare a fresh user choice invalid and reset it to the first
    // option (the intermittent 8-of-10 -> 10-of-10 snap-back).
    if (metaLoadingRef.current || metaLoading) return;

    // console.log('props.dayOfTheMonth=',props.dayOfTheMonth)
    // console.log('props.oppTablePartialYears=',props.oppTablePartialYears)
    // console.log('props.appliedFilter=',props.appliedFilter)
    // console.log('token=',token)
    // console.log('props.selectedSecurity=',props.selectedSecurity.length)
    // console.log('props.opportunities.length=',props.opportunities.length)
    // console.log('props.oppTableYears=',props.oppTableYears)
    // console.log('oppListExpanded=',oppListExpanded)
    // console.log('\n\n\n')



    // var tmp = [];
    // for (var i = 0; i < props.yearsMetaData.length; i++)
    //   if (props.yearsMetaData[i][0] === props.oppTableYears) tmp.push({ id: props.yearsMetaData[i][1], value: props.yearsMetaData[i][1], label: props.yearsMetaData[i][1] })

    const peMetaAvailable =
      Array.isArray(props.yearsMetaDataPE) && props.yearsMetaDataPE.length > 0;

    const activeMeta =
      (props.showPEOpps && peMetaAvailable) ? props.yearsMetaDataPE : props.yearsMetaData;

    const yearsKey = String(props.oppTableYears);

    // The YEARS value itself can be dead for the ACTIVE metadata - e.g. a PE-slot
    // years (5) stranded in cons mode after a PE auto-off, where no 5-year cons
    // datasets exist. tmp below would stay empty forever, partial-years could never
    // resolve, and the table sat permanently blank (only a manual years toggle
    // unstuck it). When metadata IS loaded and the current years has no rows, snap
    // to the nearest valid years (largest <= current, else the smallest valid; both
    // respecting the tier cap) and let the effect re-run resolve partial normally.
    if (activeMeta.length > 0) {
      const _cap = maxYearsCap();   // per-tier years cap (null = uncapped)
      let validYears = [...new Set(activeMeta.map(r => parseInt(r[0])))].sort((a, b) => a - b);
      if (_cap != null) validYears = validYears.filter(y => y <= _cap);
      const curY = parseInt(props.oppTableYears, 10);
      if (validYears.length > 0 && (isNaN(curY) || !validYears.includes(curY))) {
        const below = validYears.filter(y => y <= curY);
        const snapped = below.length > 0 ? below[below.length - 1] : validYears[0];
        props.SetOppTableYears(snapped.toString());
        props.SetOppTablePartialYears(-1);   // re-resolve partial for the snapped years
        return;                              // effect re-runs with a live years value
      }
    }

    var tmp = [];
    for (var i = 0; i < activeMeta.length; i++) {
      if (String(activeMeta[i][0]) === yearsKey) {
        tmp.push({
          id: activeMeta[i][1],
          value: activeMeta[i][1],
          label: activeMeta[i][1],
        });
      }
    }

    // sort numerically DESC so tmp[0] is the highest (best default)
    tmp.sort((a, b) => Number(b.value) - Number(a.value));

    SetPartialSeasonalYearsOptionsList(tmp);

    // partial-years is invalid when we KNOW the valid options for the current
    // years (tmp populated) and the current value isn't one of them — e.g. a
    // stale 18 left over from a years=15 selection after years drops to 10.
    // Such a pair (10/18) has no Monthly_Opp dataset on the appserver, which
    // returns its -1 sentinel -> empty table. tmp.length===0 means metadata is
    // still loading, so we don't treat the value as invalid yet.
    const partialYearsInvalid =
      tmp.length > 0 &&
      !tmp.some(o => String(o.value) === String(props.oppTablePartialYears));

    if (tmp.length > 0) {
      // Reset to the highest valid option when partial-years is the -1 reset
      // sentinel OR a stale value invalid for the current years. The fetch
      // below is skipped this pass (partialYearsInvalid gate); this state change
      // re-runs the effect with a valid pair that then fetches normally.
      if (props.oppTablePartialYears === -1 || props.oppTablePartialYears === '-1' || partialYearsInvalid) {
        props.SetOppTablePartialYears(tmp[0].value); // highest valid
      }
    }

    if ((rdd.isMobile && !rdd.isTablet && browserH > browserW) | (rdd.isMobile && rdd.isTablet && browserH < browserW)) {
      SetOppTablePartialYearsSuffix(` of ${props.oppTableYears} yrs`)
    }
    else SetOppTablePartialYearsSuffix(` of ${props.oppTableYears} years`)



    // Resolve market id BEFORE the fetch guard. If securityTypeList is empty
    // (still loading from /getResourcesObj on first /app/ mount) the helper
    // returns -1, which the appserver rejects. Skip the fetch entirely until
    // the resources list has loaded and selectedSecurity matches a valid market.
    var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
    if (props.selectedSecurity.length > 0 && id !== -1 && id !== '-1' && props.oppTablePartialYears.length > -1 && props.oppTablePartialYears > '0' && props.oppTableYears !== -1 && props.oppTablePartialYears !== -1 && !partialYearsInvalid) {

      const day_range = toOpportunityEngineDayRange(dayRange)

      let asURL = appserverURL()
      var url = `${asURL}/OppList4/${id}/${props.oppTableMonth}/${props.dayOfTheMonth}/${props.oppTableYears}/${props.oppTablePartialYears}/${day_range}/${oppListExpanded}`

      const mode = props.showPEOpps ? 'pe' : 'consecutive'; // this is the mode where either pe or consecutive (the old behavior) is invoked

      if (props.appliedFilter !== '' & props.appliedFilter !== 'no filter') url += '/' + props.appliedFilter.slice(0, -1) //slice drops the last character
      else url += '/0';

      url += '?token=' + token

      url += `&mode=${mode}` // adding mode as a query string to the end of token so that the opplist4 route doesn't have to change

      // if (debug) console.log('opplist4 url: ', url)

      // Fetch when the resolved query URL changes — NOT gated on
      // opportunities.length===0. The old gate suppressed the fetch for the
      // final settled params whenever a transitional effect pass (during the
      // -1 -> value settle after a market switch) had already populated
      // opportunities, so the table showed a stale/empty interim result and
      // only a manual partial-years toggle (which clears opportunities in
      // App.js) forced the correct fetch. The URL ref also dedupes redundant
      // re-renders that don't change the query.
      //
      // The dedup key folds in the active watchlist filter: a watchlist sits on
      // top of a real securities group, so its OppList4 URL is identical to the
      // bare group's. App.js loads the watchlist symbols asynchronously (null ->
      // populated) AFTER selecting the list, and the symbol filter below only
      // runs inside this fetch's .then. Without the wl signature in the key, the
      // post-symbols refetch dedupes against the bare-group fetch and the filter
      // never re-applies — leaving the whole group's rows showing unfiltered.
      const wlSig = props.activeWatchlistFilter
        ? `|wl=${props.activeWatchlistFilter.name}:${props.activeWatchlistFilter.symbols ? props.activeWatchlistFilter.symbols.size : 'pending'}`
        : ''
      const fetchKey = url + wlSig
      // Safety net for the whole "cleared but never refetched" class. Several
      // controls clear the rows to avoid showing a new setting over old data
      // (App.js selectboxChanged, the PE toggle, the filter handlers), but a
      // control can resolve to the query that is ALREADY loaded - re-picking
      // the selected value, a years pick that maps back to the same pair, a PE
      // round trip. The dedupe then skips the request meant to refill the table
      // and the panel is stuck with a dead-looking control.
      //
      // The test is exact, so it needs no retry budget and cannot loop: this
      // very query has already completed AND it returned rows, yet the table is
      // empty - so something cleared it and nothing is coming. A query that
      // legitimately returns nothing records 0 rows and is never refetched.
      const strandedEmptyTable =
        fetchKey === lastOppUrlRef.current &&
        !oppInFlightRef.current &&
        oppSettledKeyRef.current === fetchKey &&
        oppSettledRowsRef.current > 0 &&
        props.opportunities.length === 0
      if (token.length > 0 && (fetchKey !== lastOppUrlRef.current || strandedEmptyTable)) {
        lastOppUrlRef.current = fetchKey
        oppInFlightRef.current = true
        const oppReqId = ++oppReqRef.current // ordering guard: a slow older response must not clobber a newer one
        SetOppLoadFailed(false)
        SetInitialMessage('Loading ...')   // in-flight marker: gates the auto-step-down until THIS fetch's real result lands (a stale 'no patterns' message otherwise lets it fire mid-fetch)
        clearCaptureReady('oppTable')

        twFetch(url, { onRetry: () => SetInitialMessage('Data temporarily unavailable - retrying ...') })
          .then(res => {
            const contentType = res.headers.get("content-type");

            if (contentType && contentType.indexOf("application/json") !== -1) {
              return res.json();
            }
            else if (res.status === 429) { // too many requests (twFetch already retried with backoff)
              // let trigger = res.headers.get("trigger");
              // props.SetDialogType('info-box'); //429
              props.SetDialogType('rate-limit'); //429
              // props.SetDialogProp({ title: 'Too Many Requests', contentText: ratelimitMessage(trigger, loggedinUser), button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
              props.SetInfoBoxVisible(true)
              SetInitialMessage('* Data temporarily unavailable')
              SetOppLoadFailed(true)
              lastOppUrlRef.current = '' // allow a refetch of the same params
            }
            else {
              // console.log('opptable fetch url = ', url)
              console.log('response status opptable fetch = ', res.status)
              SetInitialMessage('* Data temporarily unavailable')
              SetOppLoadFailed(true)
              lastOppUrlRef.current = ''
            }
          })
          .then((opps) => {
            if (oppReqId !== oppReqRef.current) return; // a newer OppList4 request has since started - drop this stale response
            if (opps !== undefined) {
              if (opps['OppList'].length === 0 || opps['OppList'].includes('-1')) {
                // Name the day range when one is active. The server applies it
                // before ranking, so it - not the market/date/recurrence - is
                // usually why nothing came back, and "no patterns for the
                // current selection" sent people hunting through the dropdowns.
                SetInitialMessage(
                  dayRange !== EMPTY_DAY_RANGE
                    ? `* No patterns between ${dayRange.replace('-', ' and ')} days for the current selection - widen or clear the day filter`
                    : '* No seasonal patterns found for the current selection'
                );
              }
              else SetInitialMessage('Loading ...')

              // Missing-dataset sentinel: when no precomputed opportunity file
              // exists for the selected year combo, the appserver returns
              // {OppList: '-1:<path>'} — a STRING, with no OppActiveList. Bail
              // out to an empty table here; otherwise OppList.map() below throws
              // on the string and the catch mislabels it "Data temporarily
              // unavailable" instead of showing the no-patterns message above.
              if (!Array.isArray(opps['OppList'])) {
                oppSettledKeyRef.current = fetchKey
                oppSettledRowsRef.current = 0
                props.SetOpportunities([]);
                props.SetActiveOpportunities([]);
                return;
              }

              // console.log('opps=', opps)

              const prices = opps['prices'] || {};
              SetMLEnabled(opps['ml_enabled'] || false);
              SetMLMarketEligible(opps['ml_market_eligible'] || false);
              SetMLEligibilityResolved(true);

              var tbl_col_reordered = opps['OppList'].map((row) => {
                // ['date','symbol','days','dir','sharpe_ratio','avg_profit','median_profit','avg_profit2','sharpe_ratio2']

                const newRow = {
                  date: row[0],
                  symbol: row[1],
                  daysOut: parseInt(row[2]) + 1,
                  lOrS: row[3],
                  // median_profit: parseFloat(row[6]),
                  avg_profit: Math.round(parseFloat(row[5]) * 10) / 10,
                  sharpe_ratio: parseFloat(row[4]),
                };

                if (props.showSR2) {
                  newRow.avg_profit2 = Math.round(parseFloat(row[7]) * 10) / 10;
                  newRow.sharpe_ratio2 = parseFloat(row[8]);
                }

                // Inject realtime price data
                const realtimeQuote = normalizeRealtimeQuote(prices[row[1]]);
                if (realtimeQuote) {
                  newRow.price = realtimeQuote.price;
                  newRow.change_p = realtimeQuote.change_p;
                  newRow.realtimeQuote = realtimeQuote;
                } else {
                  newRow.price = null;
                  newRow.change_p = null;
                  newRow.realtimeQuote = null;
                }

                return newRow;
              });

              // load the active rows if exist
              var tbl_col_reordered_active = opps['OppActiveList'].map((row) => {
                // ['date','symbol','days','dir','sharpe_ratio','avg_profit','median_profit','avg_profit2','sharpe_ratio2']

                const newRow = {
                  date: row[0],
                  symbol: row[1],
                  daysOut: parseInt(row[2]) + 1,
                  lOrS: row[3],
                  // median_profit: parseFloat(row[6]),
                  avg_profit: Math.round(parseFloat(row[5]) * 10) / 10,
                  sharpe_ratio: parseFloat(row[4]),
                };

                // if (props.showSR2) {
                //   newRow.avg_profit2 = parseFloat(row[7]);
                //   newRow.sharpe_ratio2 = parseFloat(row[8]);
                // }

                // Inject realtime price data
                const realtimeQuote = normalizeRealtimeQuote(prices[row[1]]);
                if (realtimeQuote) {
                  newRow.price = realtimeQuote.price;
                  newRow.change_p = realtimeQuote.change_p;
                  newRow.realtimeQuote = realtimeQuote;
                } else {
                  newRow.price = null;
                  newRow.change_p = null;
                  newRow.realtimeQuote = null;
                }

                return newRow;
              });




              // check if token was created in the last 10 seconds, if it is , then load the first opp on the current opplist 
              // which is typically by default in S&P 500 - this is only for non loggedin users

              let decoded;
              try { decoded = jwt_decode(token); } catch (e) { console.error('jwt_decode failed in OppTable fetch:', e.message); return; }
              let exp = decoded['exp']
              let secs_now = Math.floor(Date.now() / 1000);
              // 10800 is 3 hours which is expireation time - if changed in appserver, change here
              let secs_since_token = -(secs_now, exp - secs_now - 10800)

              // console.log('decoded',exp,secs_now,secs_since_token)

              // console.log('-----------------------------rowIndexClicked=',props.rowIndexClicked);

              // if this if statement is removed, first time going to the site will load the first financial instrument on the list S&p500
              if (secs_since_token < 30 && loggedinUser === '0') {

                //---------------------------------------------------------------------------------------------
                // when a non loggedin user goes to site, if less than 10 secs, show 
                // load the first item on list - only initially which mean in first 10 secs
                // only load this opp if there is no query string
                if (props.qparams.length === 0) {
                  let daysOut = opps['OppList'][0][2]
                  daysOut = String(+daysOut + 1)  // incrementing a string.  the + sign in front of daysOut is called the unary plus operator
                  props.SetStartDate(opps['OppList'][0][0]);
                  props.SetSymbol(opps['OppList'][0][1]);
                  props.SetDaysOut(daysOut);
                  props.SetSeasonalYears(props.oppTableYears);


                  let trend_chart_start_date = incrementDate(opps['OppList'][0][0], -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
                  props.SetTrendChartStartDate(trend_chart_start_date)


                  props.SetRowIndexClicked(0);
                }
              }






              // console.log('tbl_col_reordered=',tbl_col_reordered)

              // console.log("opps['AvailableFilters']=", opps['AvailableFilters'])

              // filter by watchlist symbols if a watchlist is active in the securities dropdown
              if (props.activeWatchlistFilter && props.activeWatchlistFilter.symbols) {
                tbl_col_reordered = tbl_col_reordered.filter(row => props.activeWatchlistFilter.symbols.has(row.symbol));
                tbl_col_reordered_active = tbl_col_reordered_active.filter(row => props.activeWatchlistFilter.symbols.has(row.symbol));
              }

              // Record what this query actually yielded - the escape above reads
              // it to tell "the query is empty" from "something cleared rows we
              // had".
              oppSettledKeyRef.current = fetchKey
              oppSettledRowsRef.current = tbl_col_reordered.length
              props.SetOpportunities(tbl_col_reordered)
              props.SetActiveOpportunities(tbl_col_reordered_active)
              if (tbl_col_reordered.length > 0) markCaptureReady('oppTable', { rows: tbl_col_reordered.length, month: props.oppTableMonth, day: props.dayOfTheMonth, years: props.oppTableYears })

              var tmp = []


              if (opps['AvailableFilters'] !== undefined) {

                for (var i = 0; i < opps['AvailableFilters'].length; i++) {
                  if (opps['AvailableFilters'][i] === '0%') tmp.push({ id: 0, value: 'no filter', label: 'no filter' })
                  else
                    tmp.push({ id: i + 1, value: opps['AvailableFilters'][i], label: `filter: ${opps['AvailableFilters'][i]} reached each year` })
                }

                SetAvailableFilters(tmp)

              }

            }

          })
          .catch(err => {
            console.log('OppList4 fetch error:', err.message)
            SetInitialMessage('* Data temporarily unavailable')
            SetOppLoadFailed(true)
            lastOppUrlRef.current = ''
          })
          .finally(() => {
            if (oppReqId === oppReqRef.current) oppInFlightRef.current = false
          })
      }
    }
    // }, [props.dayOfTheMonth, props.oppTablePartialYears, props.appliedFilter, token, props.selectedSecurity, props.opportunities.length, props.oppTableYears, yearsMetaData, oppListExpanded]) //removed dependency of oppTableMontha and oppTableYears because oppTablePartialYears will be the last to change
  }, [
    props.showActiveOpps,
    props.dayOfTheMonth,
    props.oppTablePartialYears,
    props.appliedFilter,
    token,
    props.selectedSecurity,
    props.opportunities.length,
    props.activeOpportunities.length,
    props.oppTableYears,
    oppListExpanded,
    props.showPEOpps,
    props.yearsMetaDataPE,
    props.yearsMetaData,
    props.activeWatchlistFilter,
    oppRetryNonce,
    dayRange,
    metaLoading
  ])
  // 10/27/2021 added dayofthemonth after replacing opplist2 with opplist3
  // 8/22/2021 added length of opportunities array which is better than other dependencies - could probably remove some of the others
  //-------------------------------------------------------------------------------------------------------
  // Auto-step-down: when fetch returns empty, automatically try a lower partial years value
  //-------------------------------------------------------------------------------------------------------
  useEffect(() => {
    // only act after a fetch has completed (opportunities array is populated or message says no data)
    if (props.opportunities.length === 0 && (initialMessage === 'Loading ...' || initialMessage.startsWith('Data temporarily unavailable'))) return; // still loading/retrying

    if (oppLoadFailed) return; // load failed, not "no results" - don't step down partial years

    // An EXPLICIT pick is never auto-overridden. Hold the refusal for as long as
    // that value is still selected, rather than consuming it on the first pass:
    // this effect re-runs on every rebuild of the options list, so a one-shot
    // flag was always spent before the fetch it was meant to protect came back,
    // and the user's choice silently flipped down a step.
    if (String(props.oppTablePartialYears) === userPickedPYearsRef.current) return;

    // A partially typed or invalid filter is not an empty settled result and
    // must never change recurrence while the user is editing it.
    if (analyzeOpportunityFilter(curText).status !== 'valid') return;

    // Step down only when the SERVER returned no patterns. Rows in hand with
    // nothing visible means the user's own client-side filter hid them, and
    // their recurrence setting is not what needs changing.
    if (props.opportunities.length > 0) return;

    // oppTableLength is the visible count after TableBox client-side filtering
    if (props.oppTableLength > 0) return; // user sees results, no step-down needed

    const currentPY = Number(props.oppTablePartialYears);
    if (isNaN(currentPY) || currentPY <= 0) return;

    // Step down to the next LOWER *valid* partial-years option, not a blind
    // currentPY-1: a decremented value with no dataset gets yanked back up by the
    // invalid-value reset while the URL dedupe blocks a refetch — an infinite
    // 4<->5 ping-pong with the table stuck empty. Options are sorted DESC, so the
    // first entry below currentPY is the closest valid step. No lower option
    // (or options not loaded yet) -> stop with the guidance message.
    const lowerValid = partialSeasonalYearsOptionsList
      .map(o => Number(o.value))
      .filter(v => !isNaN(v) && v < currentPY);
    if (lowerValid.length === 0) {
      SetInitialMessage(`No patterns matched ${props.oppTablePartialYears} of ${props.oppTableYears} years - adjust the historical years and your filter to see patterns again`);
      return;
    }

    const nextPY = lowerValid[0]; // DESC order -> closest valid below current
    props.SetOpportunities([]);
    props.SetOppTablePartialYears(String(nextPY));
  }, [props.oppTableLength, props.oppTablePartialYears, partialSeasonalYearsOptionsList, curText, props.opportunities.length])

  //-------------------------------------------------------------------------------------------------------
  // Fetch stockscores in batch AFTER opportunities load (async - does not block table render)
  //-------------------------------------------------------------------------------------------------------
  useEffect(() => {
    if (props.opportunities.length === 0) {
      SetStockScores({})
      return
    }

    const symbols = [...new Set(props.opportunities.map(row => row.symbol))]
    if (symbols.length === 0) return

    const id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
    const asURL = appserverURL()
    const url = `${asURL}/StockScoreBatch/${id}?token=${token}`

    const controller = new AbortController()

    twFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols }),
      signal: controller.signal
    })
      .then(res => {
        if (res.ok) return res.json()
        throw new Error('StockScoreBatch failed')
      })
      .then(data => {
        ReactDOM.unstable_batchedUpdates(() => {
          if (data && data.stockscores) {
            SetStockScores(data.stockscores)
          }
        })
      })
      .catch(err => {
        ReactDOM.unstable_batchedUpdates(() => {
          if (err.name !== 'AbortError') {
            console.log('StockScoreBatch error:', err)
            SetStockScores({})
          }
        })
      })

    return () => controller.abort()
  }, [props.opportunities])

  //-------------------------------------------------------------------------------------------------------
  // Fetch ML scores in two phases AFTER opportunities load (async trickle-in)
  // Phase 1: POST all visible rows to MLScoreBatch - get cached scores + pending list
  // Phase 2: Poll MLScorePending every 3s to score a chunk of pending items at a time
  //-------------------------------------------------------------------------------------------------------
  const mlContextKey = [
    props.selectedSecurity,
    props.oppTableMonth,
    props.dayOfTheMonth,
    props.oppTableYears,
    props.oppTablePartialYears,
    props.showPEOpps ? 'pe' : 'cons',
    oppListExpanded,
    props.showActiveOpps ? 'active' : 'standard',
  ].join('|')

  const displayedOpportunities = selectDisplayedOpportunityRows({
    showActiveOpps: props.showActiveOpps,
    opportunities: props.opportunities,
    activeOpportunities: props.activeOpportunities,
  })

  // A server day range can re-rank which pattern represents each ticker. Keep
  // the baseline for stable standalone AI-filter semantics and union in every
  // currently visible identity so reranked rows are always scoreable.
  const mlSourceSelection = selectOpportunityMLScoreSource({
    snapshot: mlBaselineOppsRef.current,
    contextKey: mlContextKey,
    dayRange,
    opportunities: displayedOpportunities,
  })
  mlBaselineOppsRef.current = mlSourceSelection.snapshot
  const mlScoreSource = mlSourceSelection.scoreSource

  const selectedAIAnchor = selectedAIRowIdentityRef.current
  const aiMarketDate = currentNewYorkMarketDate()
  const panelAISelection = useMemo(() => selectOpportunityAIPanelSelection({
    scoreSource: mlScoreSource,
    anchor: selectedAIAnchor,
    market: props.selectedSecurity,
    symbol: props.symbol,
    date: props.startDate,
    calendarDays: props.daysOut,
    years: props.seasonalYears,
    mode: viewerModeForAI,
    cycle: viewerCycleForAI,
    direction: props.barChartLongOrShort,
    isBuyAndHold: viewerIsBuyAndHold,
  }), [mlScoreSource, selectedAIAnchor, props.selectedSecurity, props.symbol, props.startDate, props.daysOut, props.seasonalYears, props.barChartLongOrShort, viewerModeForAI, viewerCycleForAI, viewerIsBuyAndHold])
  const mlResourceId = getSelectedIDFromSecuritiesList2(
    props.securityTypeList,
    props.selectedSecurity,
  )
  const viewerAIRequest = useMemo(() => buildOpportunityViewerAIRequest({
    selection: panelAISelection,
    resourceId: mlResourceId,
    marketDate: aiMarketDate,
  }), [panelAISelection, mlResourceId, aiMarketDate])
  const viewerAIRequestKey = viewerAIRequest ? viewerAIRequest.requestKey : ''
  const viewerAIRequestRef = useRef(null)
  viewerAIRequestRef.current = viewerAIRequest

  // A changed Wave Viewer identity is not an Opportunity Table row. Score that
  // one pattern on an isolated channel so the table cache, sorting, and pending
  // queue remain stable. The desired request key is also the publication guard:
  // an old request can never overwrite a newer selection.
  useEffect(() => {
    const fetchId = ++viewerMLFetchIdRef.current
    // The object is rebuilt when OppList refreshes, but its stable key contains
    // every scoring input. Read the latest body from a ref so an equivalent
    // source-array refresh does not abort and duplicate this isolated request.
    const requestSpec = viewerAIRequestRef.current
    if (
      !requestSpec ||
      !mlEnabled ||
      !mlMarketEligible ||
      !mlEligibilityResolved
    ) {
      SetViewerMLState(previous => previous.requestKey ? emptyViewerMLState() : previous)
      return undefined
    }

    const requestKey = requestSpec.requestKey
    const asURL = appserverURL()
    const controller = new AbortController()
    let cancelled = false
    let pollTimer = null

    const isCurrent = () => (
      !cancelled &&
      fetchId === viewerMLFetchIdRef.current &&
      !controller.signal.aborted
    )
    const updateCurrent = updater => {
      if (!isCurrent()) return
      SetViewerMLState(previous => {
        if (previous.requestKey !== requestKey) return previous
        return typeof updater === 'function' ? updater(previous) : updater
      })
    }

    SetViewerMLState({
      requestKey,
      scores: {},
      pendingKeys: new Set(),
      loading: true,
      unavailableReason: '',
    })

    twFetch(`${asURL}/MLScoreBatch/${requestSpec.resourceId}?token=${token}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestSpec.body),
      signal: controller.signal,
    })
      .then(res => { if (res.ok) return res.json(); throw new Error('Wave Viewer MLScoreBatch failed') })
      .then(data => {
        if (!isCurrent()) return
        let pendingList = Array.isArray(data && data.pending) ? data.pending : []
        const initialScores = data && data.scores && typeof data.scores === 'object'
          ? data.scores
          : {}
        const hasInitialResult = Object.keys(initialScores).length > 0
        SetViewerMLState({
          requestKey,
          scores: initialScores,
          pendingKeys: new Set(pendingList.map(mlPendingKey)),
          loading: pendingList.length > 0,
          unavailableReason: pendingList.length === 0 && !hasInitialResult
            ? 'service_unavailable'
            : '',
        })

        if (pendingList.length === 0) return

        let errorCount = 0
        let pollAttempts = 0
        let noProgressRounds = 0
        let accumulatedScores = initialScores
        let progressSignature = opportunityAIScoreProgressSignature(initialScores)
        const MAX_RETRIES = 3

        const pollPending = () => {
          if (!isCurrent()) return
          if (document.visibilityState === 'hidden') {
            pollTimer = setTimeout(pollPending, 10000)
            return
          }

          twFetch(`${asURL}/MLScorePending/${requestSpec.resourceId}?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              pending: pendingList,
              table_context: requestSpec.body.table_context,
            }),
            signal: controller.signal,
          })
            .then(res => { if (res.ok) return res.json(); throw new Error('Wave Viewer MLScorePending failed') })
            .then(result => {
              if (!isCurrent()) return
              errorCount = 0
              const receivedScores = result && result.scores && typeof result.scores === 'object'
                ? result.scores
                : {}
              const previousPendingCount = pendingList.length
              const nextPendingList = Array.isArray(result && result.still_pending)
                ? result.still_pending
                : []
              const nextAccumulatedScores = { ...accumulatedScores, ...receivedScores }
              const nextProgressSignature = opportunityAIScoreProgressSignature(nextAccumulatedScores)
              const receivedProgressCount = nextProgressSignature === progressSignature
                ? 0
                : Object.keys(receivedScores).length
              accumulatedScores = nextAccumulatedScores
              progressSignature = nextProgressSignature
              const budget = advanceOpportunityAIPollBudget({
                attempts: pollAttempts,
                noProgressRounds,
                previousPendingCount,
                nextPendingCount: nextPendingList.length,
                receivedScoreCount: receivedProgressCount,
                maxAttempts: 6,
                maxNoProgressRounds: 2,
              })
              pollAttempts = budget.attempts
              noProgressRounds = budget.noProgressRounds
              const terminalWithResult = nextPendingList.length === 0 &&
                Object.keys(receivedScores).length > 0
              const exhaustedWithoutResult = budget.exhausted && !terminalWithResult
              pendingList = exhaustedWithoutResult ? [] : nextPendingList

              updateCurrent(previous => {
                const terminalWithoutResult = pendingList.length === 0 &&
                  Object.keys(receivedScores).length === 0
                const terminal = exhaustedWithoutResult || terminalWithoutResult
                const mergedScores = { ...previous.scores, ...receivedScores }
                return {
                  ...previous,
                  scores: terminal
                    ? terminalizeOpportunityViewerScores(mergedScores)
                    : mergedScores,
                  pendingKeys: new Set(pendingList.map(mlPendingKey)),
                  loading: pendingList.length > 0,
                  unavailableReason: terminal && Object.keys(mergedScores).length === 0
                    ? 'service_unavailable'
                    : '',
                }
              })

              if (pendingList.length > 0) {
                pollTimer = setTimeout(pollPending, 3000)
              }
            })
            .catch(err => {
              if (!isCurrent() || err.name === 'AbortError') return
              errorCount += 1
              console.log(`Wave Viewer MLScorePending error (${errorCount}/${MAX_RETRIES}):`, err)
              if (errorCount < MAX_RETRIES) {
                pollTimer = setTimeout(pollPending, 5000)
              } else {
                updateCurrent(previous => ({
                  ...previous,
                  scores: terminalizeOpportunityViewerScores(previous.scores),
                  pendingKeys: new Set(),
                  loading: false,
                  unavailableReason: Object.keys(previous.scores).length === 0
                    ? 'service_unavailable'
                    : '',
                }))
              }
            })
        }

        pollTimer = setTimeout(pollPending, 1000)
      })
      .catch(err => {
        if (!isCurrent() || err.name === 'AbortError') return
        console.log('Wave Viewer MLScoreBatch error:', err)
        SetViewerMLState({
          requestKey,
          scores: {},
          pendingKeys: new Set(),
          loading: false,
          unavailableReason: 'service_unavailable',
        })
      })

    return () => {
      cancelled = true
      controller.abort()
      if (pollTimer) clearTimeout(pollTimer)
    }
  }, [viewerAIRequestKey, viewerMLRetryNonce, mlEnabled, mlMarketEligible, mlEligibilityResolved, token])

  // A temporary scorer outage must not leave the selected pattern permanently
  // unavailable until the user happens to refresh. Retry the isolated selected-
  // pattern request with a capped backoff; a new pattern starts a fresh schedule.
  useEffect(() => {
    const tracker = viewerMLRetryRef.current
    if (tracker.requestKey !== viewerAIRequestKey) {
      tracker.requestKey = viewerAIRequestKey
      tracker.attempt = 0
    }
    const retryableFailure = Boolean(
      viewerAIRequestKey &&
      viewerMLState.requestKey === viewerAIRequestKey &&
      viewerMLState.loading === false &&
      viewerMLState.unavailableReason === 'service_unavailable'
    )
    if (!retryableFailure) return undefined

    const delay = opportunityAIRetryDelayMs(tracker.attempt)
    tracker.attempt += 1
    const retryTimer = setTimeout(() => {
      SetViewerMLRetryNonce(value => value + 1)
    }, delay)
    return () => clearTimeout(retryTimer)
  }, [viewerAIRequestKey, viewerMLState.requestKey, viewerMLState.loading, viewerMLState.unavailableReason])

  // Publish only the selected pattern's normalized view model. Exact table
  // identities use the complete table snapshot; a changed viewer setup uses only
  // the independent viewer request above. One publisher prevents a table poll
  // from clearing or replacing the current viewer result.
  useEffect(() => {
    if (typeof setOpportunityAIState !== 'function') return
    const selectedRow = panelAISelection ? panelAISelection.row : null
    const usesViewerRequest = Boolean(
      selectedRow && viewerAIRequestKey
    )
    const scoreRow = usesViewerRequest && viewerAIRequest && viewerAIRequest.row
      ? viewerAIRequest.row
      : selectedRow
    const viewerStateMatches = Boolean(
      usesViewerRequest &&
      viewerAIRequestKey &&
      viewerMLState.requestKey === viewerAIRequestKey
    )
    const selectedScores = usesViewerRequest
      ? (viewerStateMatches ? viewerMLState.scores : {})
      : mlScores
    const selectedPending = usesViewerRequest
      ? (viewerStateMatches ? viewerMLState.pendingKeys : new Set())
      : mlPending
    const selectedLoading = usesViewerRequest
      ? Boolean(viewerAIRequestKey && (!viewerStateMatches || viewerMLState.loading))
      : mlScoresLoading
    const selectedUnavailableReason = usesViewerRequest
      ? (viewerAIRequestKey
          ? (viewerStateMatches ? viewerMLState.unavailableReason : '')
          : 'service_unavailable')
      : mlUnavailableReason
    const bundle = scoreRow
      ? normalizeOpportunityAIScore({
          row: scoreRow,
          scores: selectedScores,
          pendingKeys: selectedPending,
          loading: selectedLoading,
          unavailableReason: selectedUnavailableReason,
        })
      : null
    const nextState = {
      market: props.selectedSecurity,
      resolved: mlEligibilityResolved,
      eligible: Boolean(mlMarketEligible),
      enabled: Boolean(mlEnabled),
      selectionOrigin: usesViewerRequest ? 'wave_viewer' : (panelAISelection ? panelAISelection.origin : ''),
      selected: selectedRow ? {
        symbol: selectedRow.symbol,
        date: selectedRow.date,
        daysOut: selectedRow.daysOut,
        direction: selectedRow.lOrS,
        averageProfit: selectedRow.avg_profit,
        sharpeRatio: selectedRow.sharpe_ratio,
        years: panelAISelection.context && panelAISelection.context.years,
        yearCount: panelAISelection.context && panelAISelection.context.yearCount,
        mode: panelAISelection.context && panelAISelection.context.mode,
        cycle: panelAISelection.context && panelAISelection.context.cycle,
        isBuyAndHold: Boolean(
          panelAISelection.context && panelAISelection.context.isBuyAndHold
        ),
        activeWindowAdjusted: Boolean(viewerAIRequest && viewerAIRequest.activeWindow),
        effectiveDate: viewerAIRequest && viewerAIRequest.activeWindow
          ? viewerAIRequest.activeWindow.effectiveDate
          : selectedRow.date,
        effectiveDaysOut: viewerAIRequest && viewerAIRequest.activeWindow
          ? viewerAIRequest.activeWindow.effectiveCalendarDays
          : selectedRow.daysOut,
        effectiveEndDate: viewerAIRequest && viewerAIRequest.activeWindow
          ? viewerAIRequest.activeWindow.endDate
          : '',
      } : null,
      loading: Boolean(bundle && bundle.display && bundle.display.status === 'loading'),
      unavailableReason: selectedUnavailableReason,
      bundle,
    }
    const signature = JSON.stringify(nextState)
    if (signature !== mlPublishedPanelSignatureRef.current) {
      mlPublishedPanelSignatureRef.current = signature
      setOpportunityAIState(nextState)
    }
  }, [panelAISelection, viewerAIRequest, viewerAIRequestKey, viewerMLState, mlScores, mlPending, mlScoresLoading, mlUnavailableReason, mlEnabled, mlMarketEligible, mlEligibilityResolved, props.selectedSecurity, setOpportunityAIState])

  useEffect(() => {
    // OppList supplies the authoritative ISO entry date for every row. The
    // New York-aware backend applies the five-day/current-entry gate per row;
    // browser-local midnight must never suppress or relabel an entire table.
    const tableDate = authoritativeOpportunityTableDate(mlScoreSource)

    if (mlScoreSource.length === 0 || !mlEnabled) {
      SetMLScores({})
      SetMLScoresLoading(false)
      SetMLPending(new Set())
      SetMLUnavailableReason(!mlEnabled ? 'unsupported_market' : '')
      return
    }

    // Increment fetch ID - any in-flight fetch with an older ID will be ignored
    const fetchId = ++mlFetchIdRef.current

    const id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
    const asURL = appserverURL()
    let cancelled = false
    let pollTimer = null

    // Build opportunity tuples sorted by sharpe_ratio descending (highest SR scored first)
    const years = String(props.oppTableYears)
    const mode = props.showPEOpps ? 'pe' : 'consecutive'
    const partial = {
      min_winning_years: String(props.oppTablePartialYears),
      mode,
    }
    const tableContext = {
      years,
      partial,
      mode,
      date: tableDate,
      day_range: dayRange,
      is_default: dayRange === EMPTY_DAY_RANGE && !oppListExpanded && !props.showActiveOpps,
    }
    const opps = [...mlScoreSource]
      .sort((a, b) => (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0))
      .map(row => ({
        symbol: row.symbol,
        date: row.date,
        daysOut: parseInt(row.daysOut) - 1,  // undo the +1 display adjustment
        direction: String(row.lOrS).startsWith('L') ? 'l' : 's',
        years,
        partial,
        mode,
        selection_origin: 'opportunity_table',
      }))

    ReactDOM.unstable_batchedUpdates(() => {
      SetMLScores({})
      SetMLScoresLoading(true)
      SetMLPending(new Set())
      SetMLUnavailableReason('')
    })

    // Phase 1: batch request - get cached scores + pending list
    twFetch(`${asURL}/MLScoreBatch/${id}?token=${token}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        opportunities: opps,
        table_context: tableContext,
      }),
    })
      .then(res => { if (res.ok) return res.json(); throw new Error('MLScoreBatch failed') })
      .then(data => {
        if (cancelled || fetchId !== mlFetchIdRef.current) return

        // Phase 2: poll for pending items
        let pendingList = data.pending || []
        ReactDOM.unstable_batchedUpdates(() => {
          if (data.scores && Object.keys(data.scores).length > 0) {
            SetMLScores(prev => ({ ...prev, ...data.scores }))
          }
          // Track pending keys so TableBox can show lightweight loading markers.
          SetMLPending(new Set(pendingList.map(mlPendingKey)))
          if (pendingList.length === 0) SetMLScoresLoading(false)
        })

        if (pendingList.length === 0) return

        let errorCount = 0
        let pollAttempts = 0
        let noProgressRounds = 0
        const MAX_RETRIES = 3

        const pollPending = () => {
          if (cancelled || fetchId !== mlFetchIdRef.current) return
          if (document.visibilityState === 'hidden') {
            pollTimer = setTimeout(pollPending, 10000)
            return
          }

          twFetch(`${asURL}/MLScorePending/${id}?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pending: pendingList, table_context: tableContext }),
          })
            .then(res => { if (res.ok) return res.json(); throw new Error('MLScorePending failed') })
            .then(result => {
              if (cancelled || fetchId !== mlFetchIdRef.current) return
              errorCount = 0  // reset on success

              const previousPendingCount = pendingList.length
              const nextPendingList = result.still_pending || []
              const budget = advanceOpportunityAIPollBudget({
                attempts: pollAttempts,
                noProgressRounds,
                previousPendingCount,
                nextPendingCount: nextPendingList.length,
                receivedScoreCount: result.scores ? Object.keys(result.scores).length : 0,
              })
              pollAttempts = budget.attempts
              noProgressRounds = budget.noProgressRounds
              pendingList = budget.exhausted ? [] : nextPendingList
              ReactDOM.unstable_batchedUpdates(() => {
                if (result.scores && Object.keys(result.scores).length > 0) {
                  SetMLScores(prev => ({ ...prev, ...result.scores }))
                }
                SetMLPending(new Set(pendingList.map(mlPendingKey)))
                if (pendingList.length === 0) {
                  SetMLScoresLoading(false)
                  if (budget.exhausted) SetMLUnavailableReason('service_unavailable')
                }
              })
              if (pendingList.length > 0) {
                pollTimer = setTimeout(pollPending, 3000)
              }
            })
            .catch(err => {
              if (cancelled || fetchId !== mlFetchIdRef.current) return
              errorCount++
              console.log(`MLScorePending error (${errorCount}/${MAX_RETRIES}):`, err)
              if (errorCount < MAX_RETRIES) {
                pollTimer = setTimeout(pollPending, 5000)  // retry after 5s
              } else {
                ReactDOM.unstable_batchedUpdates(() => {
                  SetMLScoresLoading(false)
                  SetMLPending(new Set())
                  SetMLUnavailableReason('service_unavailable')
                })
              }
            })
        }

        pollTimer = setTimeout(pollPending, 1000)  // first poll after 1s
      })
      .catch(err => {
        if (!cancelled) {
          console.log('MLScoreBatch error:', err)
          ReactDOM.unstable_batchedUpdates(() => {
            SetMLScores({})
            SetMLScoresLoading(false)
            SetMLPending(new Set())
            SetMLUnavailableReason('service_unavailable')
          })
        }
      })

    return () => {
      cancelled = true
      if (pollTimer) clearTimeout(pollTimer)
    }
  }, [mlScoreSource, props.selectedSecurity, mlEnabled, props.oppTableMonth, props.dayOfTheMonth, props.oppTableYears, props.oppTablePartialYears, props.showPEOpps, props.showActiveOpps, dayRange, oppListExpanded])

  //-------------------------------------------------------------------------------------------------------
  // Keyboard row selection is intentionally disabled. Keep the callback stable
  // so unrelated chart state does not invalidate the memoized opportunity table.
  const handlerKeyDown = useCallback(() => {}, [])

  // An empty source list means the table is between markets/queries; invalidate
  // Tara's processed-row snapshot so an ordinal command cannot target stale rows.
  useEffect(() => {
    if (props.opportunities.length === 0 && typeof props.SetVisibleOpportunities === 'function') {
      props.SetVisibleOpportunities(null)
    }
  }, [props.opportunities.length, props.SetVisibleOpportunities])

  //-------------------------------------------------------------------------------------------------------
  // when an opportunity row is clicked in TableBox, this runs
  //-------------------------------------------------------------------------------------------------------
  const rowClickStateRef = useRef({ props, PELabel })
  rowClickStateRef.current = { props, PELabel }
  const handlerRowClicked = useCallback((rowIndex, row) => () => { // this is to handleRowClicked in TableBox
    const current = rowClickStateRef.current
    const currentProps = current.props
    // This callback is also invoked by a native lesson event. React 17 does
    // not batch that path automatically, so keep the new anchor and all Wave
    // Viewer identity setters in one render transaction.
    ReactDOM.unstable_batchedUpdates(() => {
      let selectedCycle = 'cons'
      if (currentProps.showPEOpps === true) {
        selectedCycle = String(current.PELabel || 'PE').toLocaleLowerCase().replace('+', '')
        if (selectedCycle === 'pe') selectedCycle = 'pe0'
      }
      selectedAIRowIdentityRef.current = createOpportunityAISelectionAnchor({
        row,
        market: currentProps.selectedSecurity,
        years: currentProps.oppTableYears,
        partialYears: currentProps.oppTablePartialYears,
        mode: currentProps.showPEOpps ? 'pe' : 'consecutive',
        cycle: selectedCycle,
      })
      const sameOpportunity =
        currentProps.rowIndexClicked === rowIndex &&
        currentProps.symbol === row.symbol &&
        currentProps.startDate === row.date &&
        parseInt(currentProps.daysOut, 10) === parseInt(row.daysOut, 10)
      if (!sameOpportunity) {
        const opp_start_date = row.date;

        // Invalidate every payload that belongs to the previously selected
        // opportunity in this same click transaction. Leaving those objects in
        // state until ChartData4 returns makes the new ticker/date temporarily
        // display the prior row's statistics.
        currentProps.SetSeasonalBarChartData([])
        currentProps.SetTradeDetailData([])
        currentProps.SetConsolidatedSeasonalData([])
        currentProps.SetMaxYearsConsolidatedSeasonalData([])
        currentProps.SetCompareSecurityBarChartData([])
        currentProps.SetCompareSecurityTradeDetailData([])
        currentProps.SetSecurityBHstats([])
        currentProps.SetLineChartYear(0)
        if (currentProps.symbol !== row.symbol) currentProps.SetCompany('')

        currentProps.SetStartDate(opp_start_date);
        currentProps.SetLastPrice(['', 0]) // reset last price 6/23/2022
        currentProps.SetSymbol(row.symbol);
        currentProps.SetDaysOut(row.daysOut);

        // PE cycle opplist type is selected
        if (currentProps.showPEOpps === true) {
          currentProps.SetPEselected(selectedCycle)
          currentProps.SetSeasonalYears(currentProps.oppTableYears);
        }
        else {
          currentProps.SetSeasonalYears(currentProps.oppTableYears)
          currentProps.SetPEselected('cons')
        }

        currentProps.SetMonthsAndQtrs('Months & Qtrs')

        const trend_chart_start_date = incrementDate(opp_start_date, -trend_chart_left_gap_days);
        currentProps.SetTrendChartStartDate(trend_chart_start_date)
        currentProps.SetRowIndexClicked(rowIndex);
      }
    })
  }, [])

  // The Day-3 lesson can ask us to load the first opportunity when nothing is on the
  // chart yet, so its live "date range above the chart" example points at something real.
  const loadFirstOppRef = useRef(null);
  loadFirstOppRef.current = () => {
    if (props.opportunities && props.opportunities.length > 0) {
      handlerRowClicked(0, props.opportunities[0])();
    }
  };
  useEffect(() => {
    const h = () => { if (loadFirstOppRef.current) loadFirstOppRef.current(); };
    window.addEventListener('tw-lessonbox-load-first', h);
    return () => window.removeEventListener('tw-lessonbox-load-first', h);
  }, []);
  //-------------------------------------------------------------------------------------------------------

  //-------------------------------------------------------------------------------------------------------

  const handleExpandContract = (event) => {

    if (props.showActiveOpps === false) { // no % filtering for active opps

      if (props.loggedinUser !== '0') {


        let retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity)


        if ((wpUserLevels.length === 1 && wpUserLevels[0] === '1') || retArray[0] === 'F') {
          props.SetDialogType('free-register')
          props.SetInfoBoxVisible(true);
          return;
        } //free registered - cannot expand

        else {
          props.SetOpportunities([]) //clear opportunties table becaues there will be a new fetch

          if (oppListExpanded === 0) SetOppListExpanded(1)
          else SetOppListExpanded(0)

        }

      }

      else {
        props.SetDialogType('free-register')
        props.SetInfoBoxVisible(true);
      }
    }

  }

  //-------------------------------------------------------------------------------------------------------
  // this is for the search textbox
  // Filter history - persisted in localStorage
  const FILTER_HISTORY_KEY = 'tw_filter_history'
  const MAX_FILTER_HISTORY = 8
  const filterBlurTimer = useRef(null)
  const filterWrapperRef = useRef(null)
  const [showFilterHistory, SetShowFilterHistory] = useState(false)
  const [filterDropdownRect, SetFilterDropdownRect] = useState(null)
  const [filterHistory, SetFilterHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem(FILTER_HISTORY_KEY)) || [] } catch { return [] }
  })

  const saveFilterToHistory = (text) => {
    const t = (text || '').trim()
    if (t.length < 2) return
    SetFilterHistory(prev => {
      const next = [t, ...prev.filter(h => h !== t)].slice(0, MAX_FILTER_HISTORY)
      try { localStorage.setItem(FILTER_HISTORY_KEY, JSON.stringify(next)) } catch {}
      return next
    })
  }

  const removeFilterFromHistory = (text, e) => {
    e.stopPropagation()
    SetFilterHistory(prev => {
      const next = prev.filter(h => h !== text)
      try { localStorage.setItem(FILTER_HISTORY_KEY, JSON.stringify(next)) } catch {}
      return next
    })
  }

  const handleFilterFocus = () => {
    if (filterBlurTimer.current) clearTimeout(filterBlurTimer.current)
    if (filterWrapperRef.current) {
      SetFilterDropdownRect(filterWrapperRef.current.getBoundingClientRect())
    }
    SetShowFilterHistory(curText.trim() === '')
  }

  const handleFilterBlur = () => {
    // Save on blur too so users don't need to press Enter
    saveFilterToHistory(curText)
    filterBlurTimer.current = setTimeout(() => SetShowFilterHistory(false), 200)
  }

  const handleFilterKeyDown = (e) => {
    if (e.key === 'Enter') {
      saveFilterToHistory(curText)
      SetShowFilterHistory(false)
    } else if (e.key === 'Escape') {
      SetShowFilterHistory(false)
    }
  }

  const handleClearFilter = (e) => {
    e.preventDefault()
    if (oppQueryDayRangeChanged(EMPTY_DAY_RANGE)) {
      props.SetOpportunities([])
      SetInitialMessage('Loading ...')
    }
    SetCurText('')
    SetShowFilterHistory(false)
    SetDayRange(EMPTY_DAY_RANGE)
  }

  const handleSelectHistoryItem = (item) => {
    if (filterBlurTimer.current) clearTimeout(filterBlurTimer.current)
    const nextDayRange = getOpportunityDayRange(item)
    if (oppQueryDayRangeChanged(nextDayRange)) {
      props.SetOpportunities([])
      SetInitialMessage('Loading ...')
    }
    SetCurText(item)
    SetShowFilterHistory(false)
    SetDayRange(nextDayRange)
  }

  // Portal dropdown - renders at document.body to escape any overflow:hidden parent
  const filterHistoryDropdown = showFilterHistory && filterHistory.length > 0 && filterDropdownRect
    ? ReactDOM.createPortal(
        <div style={{
          position: 'fixed',
          top: filterDropdownRect.bottom + 2,
          left: filterDropdownRect.left,
          zIndex: 99999,
          backgroundColor: tc.inputBg,
          border: '1px solid ' + tc.inputBorder,
          borderRadius: '4px',
          minWidth: Math.max(filterDropdownRect.width, 220),
          boxShadow: '0 3px 8px rgba(0,0,0,0.4)',
        }}>
          {filterHistory.map((item, idx) => (
            <div key={idx}
              onMouseDown={() => handleSelectHistoryItem(item)}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 8px', cursor: 'pointer' }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = tc.inputBorder}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <span style={{ color: tc.text, fontSize: globalTextSize, flexGrow: 1 }}>{item}</span>
              <span
                onMouseDown={(e) => removeFilterFromHistory(item, e)}
                style={{ color: 'gray', paddingLeft: '12px', fontSize: '11px', cursor: 'pointer' }}
              >✕</span>
            </div>
          ))}
        </div>,
        document.body
      )
    : null


  //-------------------------------------------------------------------------------------------------------

  const handleOnChange = (event) => {
    const newText = normalizeOpportunityFilterText(event.target.value)
    const nextDayRange = getOpportunityDayRange(newText)

    // Range transitions intentionally request the server's re-ranked source.
    // Clear the old source in the same input transaction so the textbox can
    // never display a new expression over stale rows while that request runs.
    // Compare the ENGINE range, because that - not the displayed range - is
    // what the OppList4 URL carries. Two displayed ranges can resolve to the
    // same query ("0-30" and "1-30"); clearing on those left the rows gone
    // with no request to replace them.
    if (oppQueryDayRangeChanged(nextDayRange)) {
      props.SetOpportunities([])
      SetInitialMessage('Loading ...')
    }

    SetCurText(newText)
    SetShowFilterHistory(false)
    SetDayRange(nextDayRange)
  };

  //-------------------------------------------------------------------------------------------------------
  // let selectFont='1vw'
  // let textInputFont = '1vw'
  // let spanFont = '1vw'

  //   .opp-table-controls {
  //     /* height: 7%; */
  // }

  // .opp-table-search {
  //     /* height: 7%; */

  // }

  // .opp-table {
  //     /* height:72%; */
  // }

  // .opp-filter{
  //     /* height: 7%; */
  //}


  // dynamic styles



  let spanFontSize = globalTextSize
  // let oppTableControlsHeight = '4%'
  let oppTableControlsHeight = '30px' // after chatbot changed from percent to static px

  // let oppTableSearchHeight = '4%'
  let oppTableSearchHeight = '30px'

  // let oppTableHeight = '88%'
  let oppTableHeight = 'calc(100% - 90px)'

  // let oppFilterHeight = '4%'
  let oppFilterHeight = '30px'


  let leftArrowdisplay = 'none'
  // next 4 items are for child divs in the bottom filter
  let expandDivWidth = '5%'
  let selectDivWidth = '30%'
  let spanDivWidth = '60%'
  let leftSpaceDivWidth = '5%'
  let expandIconSize = 20
  let opp_manager_icon_size = 20
  // console.log('browserW=',browserW)

  if (rdd.isMobile) {
    if (rdd.isTablet) {
      if (browserH > browserW) { //portrait
        oppTableControlsHeight = '9%'
        oppTableSearchHeight = '9%'
        oppTableHeight = '73%'
        oppFilterHeight = '9%'
        spanFontSize = globalTextSize

        expandDivWidth = '5%'
        selectDivWidth = '30%'
        spanDivWidth = '30%'
        leftSpaceDivWidth = '35%'
        expandIconSize = 30
        if (browserW >= 1024) {
          expandIconSize = 40;
          opp_manager_icon_size = 40;
        }
        else {
          expandIconSize = 30;
          opp_manager_icon_size = 25;
        }
      }
      else { //landscape
        oppTableControlsHeight = '4%'
        oppTableSearchHeight = '4%'
        oppTableHeight = '88%'
        oppFilterHeight = '4%'
        spanFontSize = globalTextSize

        expandDivWidth = '10%'
        selectDivWidth = '66%'
        spanDivWidth = '25%'
        leftSpaceDivWidth = '0%'

        if (browserH >= 1024) expandIconSize = 30
        else expandIconSize = 20
      }
    }
    else { // smartphone
      if (browserH > browserW) { //portrait
        oppTableControlsHeight = '9%'
        oppTableSearchHeight = '9%'
        oppTableHeight = '73%'
        oppFilterHeight = '9%'
        spanFontSize = globalTextSize
        //filter widths
        expandDivWidth = '10%'
        selectDivWidth = '36%'
        spanDivWidth = '46%'
        leftSpaceDivWidth = '8%'

      }
      else { //landscape
        oppTableControlsHeight = '12%'
        oppTableSearchHeight = '12%'
        oppTableHeight = '64%'
        oppFilterHeight = '12%'
        // spanFontSize = globalTextSize
        leftArrowdisplay = 'inline'

        //filter widths
        expandDivWidth = '5%'
        selectDivWidth = '30%'
        spanDivWidth = '30%'
        leftSpaceDivWidth = '35%'
        expandIconSize = 25
      }
    }
  }



  const oppTableControlsStyle = {
    height: oppTableControlsHeight,
    backgroundColor: tc.titleBar,
    color: tc.text,
  }
  const oppTableSearchStyle = {
    height: oppTableSearchHeight,
    backgroundColor: tc.statLabelBg,
    color: tc.text,
  }
  const oppTableStyle = {
    height: oppTableHeight,
    backgroundColor: tc.panelBg,
    color: tc.text,
  }
  const oppFilterStyle = {
    height: oppFilterHeight,
    backgroundColor: tc.oppFilterBg,
    color: tc.text,
    position: 'relative',
  }





  const handleForwardClick = () => {
    // props.SetLineChartYear('2020')
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
      props.chartTo(1)
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
      props.chartTo(1)
    }
    // console.log('here I am')
  }
  const handleBackClick = () => {
    if (rdd.isMobile) {
      redirectBackFromSeasonals();
    }
  }





  const handleHelpClicked = () => {
    // props.SetHelpBoxVisible(!props.helpBoxVisible);
    props.SetVideosBoxVisible(true)
  }
  //-------------------------------------------------------------------------------------------------------
  // turn features on or off on opp controls bar
  let SecuritiesDisplay = 'flex', navDivDisplay = 'flex', questionDisplay = 'flex';
  // if ((rdd.isMobile && browserH > browserW) | !rdd.isMobile | (rdd.isTablet && browserH < browserW)) {
  if ((!rdd.isTablet && rdd.isMobile && browserH > browserW) | !rdd.isMobile | (rdd.isTablet && browserH < browserW)) {
    navDivDisplay = 'none'; // remove nav buttions when portrait smartphone tablet
    questionDisplay = 'none'
  }
  if (!rdd.isMobile | (rdd.isTablet && browserH < browserW)) SecuritiesDisplay = 'none'
  if (!rdd.isMobile) {
    questionDisplay = 'none'
  }


  if (rdd.isMobile && rdd.isTablet && browserH > browserW) { //portrait ipad
    questionDisplay = 'none'
  }

  const StyleNavDiv = {
    // backgroundColor: "gold",
    display: navDivDisplay,
    alignItems: "center",
    height: "100%",
    // marginRight:"7px"
  }

  const StyleBackArrow = {
    // backgroundColor: "red",
    // marginRight: "7px",
    marginLeft: "10px",
    display: leftArrowdisplay,

    alignItems: "center"
  }

  const StyleForwardArrow = {
    // backgroundColor: "rgba(0,152,0,0.8",
    display: "none",
    alignItems: "center",
    marginRight: "7px"
  }

  const StyleoppFilterLeftSpace = {
    width: leftSpaceDivWidth,
    backgroundColor: 'transparent'
  }

  const StyleoppFilterExpand = {
    width: expandDivWidth,
    background:'transparent'
  }
  const StyleoppFilterSelect = {
    width: selectDivWidth,
    backgroundColor: 'transparent'
  }
  const StyleoppFilterSpan = {
    width: spanDivWidth,
    backgroundColor: 'transparent'
  }

  const handleSettings = () => {
    if (loggedinUser === '0') {
      props.SetDialogType('info-box');
      props.SetDialogProp({ title: 'Settings', contentText: settings_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      props.SetInfoBoxVisible(true);
    }
    else {
      props.SetShowSettings(true);
    }

  }

  const handleDRreport = () => {

    if (loggedinUser === '0') {
      props.SetDialogType('info-box');
      props.SetDialogProp({ title: 'Portfolio Manager', contentText: opp_dashboard_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      props.SetInfoBoxVisible(true);
    }

    else {
      props.SetReportsDashVisible(true);
    }

  }

  // handles the active opp button toggle

  const handleToggleActiveOpps = () => {
    let retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity)
    if ((wpUserLevels.length === 1 && wpUserLevels[0] === '1') || retArray[0] === 'F') {
      props.SetDialogType('free-register')
      props.SetInfoBoxVisible(true);
      return;
    } //free registered - cannot expand

    props.SetShowActiveOpps(!props.showActiveOpps);
    props.SetAppliedFilter('no filter');
  };


  const PElabelClicked = () => {
    // console.log('wwwwwwwwwwwwwwwwwwwpUserLevel=', wpUserLevels)

    //userlevel == '9' is the test user in dev during debug only
    // Allow all paid members. Block only not-logged-in (loggedinUser === '0') and free registered (only level '1').
    const isNotLoggedIn = loggedinUser === '0';
    const isFreeRegistered = wpUserLevels.length === 1 && wpUserLevels[0] === '1';
    if (isNotLoggedIn || isFreeRegistered) {
      props.SetDialogType('strategist-feature');
      props.SetInfoBoxVisible(true)
      return
    }

    const next = !props.showPEOpps;
    const currentYears = parseInt(props.oppTableYears, 10)
    const currentPartialYears = parseInt(props.oppTablePartialYears, 10)
    if (
      typeof props.SaveOppYearsForGroup === 'function' &&
      currentYears > 0 &&
      currentPartialYears > 0
    ) {
      props.SaveOppYearsForGroup(
        props.selectedSecurity,
        currentYears,
        currentPartialYears,
        props.showPEOpps,
      )
    }

    const saved = typeof props.GetOppYearsForGroup === 'function'
      ? props.GetOppYearsForGroup(props.selectedSecurity, next)
      : [props.oppTableYears, props.oppTablePartialYears]
    const targetMeta = next ? props.yearsMetaDataPE : props.yearsMetaData
    const resolved = resolveOpportunityRecurrence(
      targetMeta,
      saved[0],
      saved[1],
      maxYearsCap(),
    )

    ReactDOM.unstable_batchedUpdates(() => {
      props.SetShowPEOpps(next);
      props.SetPEOppsChecked(next);
      props.SetOpportunities([]);
      props.SetOppTableYears(resolved ? resolved.years : String(saved[0]));
      props.SetOppTablePartialYears(resolved ? resolved.partialYears : String(saved[1]));
    })
    setCookie('showPEOpps', next.toString(), 300);
  }

  const opportunitySortOptions = buildOpportunitySortOptions({
    hasAI: tierHasAI(wpUserLevels),
    mlEnabled,
    marketEligible: mlMarketEligible,
    showSR2: props.showSR2,
  })
  const preferredOpportunitySortValue = opportunitySortValue(
    opportunitySortColumn,
    opportunitySortDirection,
  )
  const preferredSortIsAvailable = opportunitySortOptions.some(
    option => option.value === preferredOpportunitySortValue,
  )
  const effectiveOpportunitySort = preferredSortIsAvailable
    ? { column: opportunitySortColumn, direction: opportunitySortDirection }
    : DEFAULT_OPPORTUNITY_SORT
  const effectiveOpportunitySortValue = opportunitySortValue(
    effectiveOpportunitySort.column,
    effectiveOpportunitySort.direction,
  )

  const handleOpportunitySortChange = event => {
    const next = parseOpportunitySortValue(event.target.value)
    if (!next) return
    SetOpportunitySortColumn(next.column)
    SetOpportunitySortDirection(next.direction)
  }


  // const marginRight = browserH > browserW ? '3vw' : '2vw';
  const marginRight = browserH > browserW ? (peMetaAvailable ? '3vw' : '8.5vw') : '2vw';
  const pe_tooltip = `  Show only opportunities that occur in the ${PELabel} presidential election-cycle year.`;

  //-------------------------------------------------------------------------------------------------------
  return (

    <div className='opp-container' style={{ backgroundColor: tc.panelBg }}>

      <div className='opp-table-controls' style={oppTableControlsStyle}>

        {/* if on mobile put the security selection pull down in oppTable otherwise its on desktoplayout.js */}
        <div style={{ backgroundColor: "transparent", width: "100%", height: "100%", display: "flex", alignItems: "center" }}>
          <div style={{ backgroundColor: "transparent", height: "100%", width: "20%" }}>
            <div style={StyleNavDiv} >

              <div style={StyleBackArrow} >
                <button className="nav-buttons">
                  <FaAngleLeft size={30} style={{ fill: "white" }} onClick={handleBackClick} />
                </button>
              </div>


              <div style={StyleForwardArrow}>
                <button className="nav-buttons">
                  <FaAngleRight size={20} style={{ fill: "white" }} onClick={handleForwardClick} />
                </button>
              </div>


              {/* {(rdd.isMobile & !rdd.isTablet & browserH < browserW) */}
              {showSecuritiesSelectToolbar
                &&
                <div style={{ marginLeft: '4vw', backgroundColor: "transparent", height: "70%", width: "90%", display: SecuritiesDisplay, justifyContent: "flex-start", alignItems: "center" }}>
                  <SelectBox optionList={props.securityTypeList} name="securityTypeList" value={props.selectedSecurityDisplay || props.selectedSecurity} sbChanged={props.selectboxChanged} />
                </div>
              }


            </div>
          </div>

        </div>

        {/* mobile portrait clipboard icon */}
        {(rdd.isMobile && !(rdd.isMobile && rdd.isTablet && browserW > browserH)) &&
          <div style={{ display: 'flex', backgroundColor: 'transparent', marginRight: marginRight, marginLeft: '2vw', alignItems: 'center' }}>
            <BsPencilSquare size={opp_manager_icon_size} style={{ fill: "white" }} onClick={handleDRreport} />
            {/* <SlSettings size={opp_manager_icon_size} style={{ fill: "white", marginLeft: '3vw' }} onClick={handleSettings} /> */}

          </div>
        }

        {/* PE checkbox (only show if PE meta exists) */}
        {peMetaAvailable && (


          <div className='opp-table-controls-items' style={{ backgroundColor: 'transparent' }}>
            <CheckBox
              label={PELabel}
              checked={props.showPEOpps}
              tooltipContent={props.tooltipSW ? pe_tooltip : ''}
              cbChanged={PElabelClicked}
            />
          </div>


        )}

        {/* Short dates year label */}
        {effectiveShortDates && props.opportunities.length > 0 && props.opportunities[0].date && (
          <div className='opp-table-controls-items' style={{ backgroundColor: 'transparent', opacity: 0.7 }}>
            <span style={{ fontSize: '11px', color: 'white' }}>{props.opportunities[0].date.substring(0, 4)}</span>
          </div>
        )}

        {/* month selection  */}
        {/* mobile portrait takes adavtage of short suffixes */}
        {(rdd.isMobile & rdd.isTablet & browserH < browserW) | (rdd.isMobile & !rdd.isTablet & browserH > browserW)
          ? <div className='opp-table-controls-items' ><SelectBox optionList={monthsOptionsListS} value={props.oppTableMonth} suffix="" name="months" sbChanged={props.selectboxChanged} /></div>
          : <div className='opp-table-controls-items' ><SelectBox tooltipContent={props.tooltipSW ? 'b,Change Opportunities Month to see active trades, for backtesting or future analytis' : ''} optionList={monthsOptionsList} value={props.oppTableMonth} suffix="" name="months" sbChanged={props.selectboxChanged} /></div>
        }

        {/* day of the month 4/29/2022  */}

        <div className='opp-table-controls-items'><SelectBox tooltipContent={props.tooltipSW ? 'b,Change opportunities day of the month to see active trades, for backtesting or future analysis' : ''} optionList={props.daysOfMonthList} value={props.dayOfTheMonth} suffix=" " name="day" sbChanged={props.selectboxChanged} /></div>


        {(rdd.isMobile & !rdd.isTablet & browserH > browserW) | (rdd.isMobile & rdd.isTablet & browserH < browserW)
          ? <div className='opp-table-controls-items'><SelectBox optionList={seasonalYearsOptionsList} value={props.oppTableYears} suffix=" yrs" name="years" sbChanged={props.selectboxChanged} /></div>
          : <div className='opp-table-controls-items'><SelectBox tooltipContent={props.tooltipSW ? 'b,You can change the number of analysis years for the TradeWave opportunities. Current Historical Years Setting  ' + props.oppTableYears + ' years' : ''} optionList={seasonalYearsOptionsList} value={props.oppTableYears} suffix=" years" name="years" sbChanged={props.selectboxChanged} /></div>
        }

        {/* number of partial years selection  */}
        <div className='opp-table-controls-items' style={{ marginRight: "12px" }} >
          <SelectBox tooltipContent={'r,' + (props.tooltipSW ? 'TradeWave Probability: Select minimum # of years to filter opportunities in the list. This changes the probability of profitability in the list of opportunities. Currently set to : ' : '') + (parseInt(props.oppTablePartialYears) > 0 && parseInt(props.oppTableYears) > 0 ? Math.round((100 * parseInt(props.oppTablePartialYears) / parseInt(props.oppTableYears))).toString() + '%' : '')} optionList={partialSeasonalYearsOptionsList} value={props.oppTablePartialYears} suffix={oppTablePartialYearsSuffix} name="partialYears" sbChanged={(e) => { userPickedPYearsRef.current = String(e.target.value); props.selectboxChanged(e); }} />
        </div>

        <div style={{ paddingRight: '0%', display: questionDisplay, width: '10%', alignItems: 'center' }}>
          <BsQuestionCircle size={16} style={{ fill: "white" }} onClick={handleHelpClicked} />
        </div>

      </div>

      <div className='opp-table-search' style={oppTableSearchStyle}>

        {
          (rdd.isMobile & !rdd.isTablet & browserH > browserW)
            ? <div style={{ marginLeft: '4vw', backgroundColor: "transparent", height: "70%", width: "90%", display: SecuritiesDisplay, justifyContent: "flex-start", alignItems: "center" }}>
              <SelectBox optionList={props.securityTypeList} name="securityTypeList" value={props.selectedSecurityDisplay || props.selectedSecurity} sbChanged={props.selectboxChanged} />
            </div>
            : <div></div>
        }

        {/* The Sort by dropdown is too wide for a phone and pushed the controls
            row out of shape (owner report 2026-08-17). Hidden on phone portrait
            only - sorting stays fully available there by tapping a column
            header, and the underlying sort state/preference is untouched. */}
        {!phonePortrait && (
          <label className="opp-sort-control">
            <span className="opp-sort-control__label">Sort by</span>
            <select
              aria-label="Sort opportunities by"
              value={effectiveOpportunitySortValue}
              onChange={handleOpportunitySortChange}
              style={{
                backgroundColor: tc.inputBg,
                color: tc.text,
                borderColor: tc.inputBorder,
              }}
            >
              {opportunitySortOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        )}
        {/* ******************************************* */}
        {/* this is for the active opportunities button */}
        {props.activeOpportunities.length > 0 && loggedinUser !== '0' &&

          <Tippy
            placement={'top'}
            disabled={!props.tooltipSW}
            content={
              <div theme="tw" >
                {/* {props.tooltipSW ? 'Premium Feature: By default 1 opportunity is returned per ticker with highest sharpe-ratio. Expand will return every trade for each ticker for the current start date.' : ''} */}
                {props.tooltipSW ? "Click 'Active' to view waves that started within the last 5 days and still fall within the opportunity's date range. Use this to identify which past waves remain viable - such as those with minimal price changes or those moving against the wave's expected direction. This helps refine your analysis and decision-making for active opportunities." : ""}
              </div>
            }
          >

            <div style={{ backgroundColor: tc.titleBar, width: '14%', height: '100%', display: 'flex', marginRight: '0.2%', borderTop: '1px solid ' + tc.border, borderBottom: '1px solid ' + tc.border, justifyContent: 'center', alignItems: 'center', cursor: 'pointer' }} onClick={handleToggleActiveOpps}>
              <span className="noselect" style={{ fontWeight: 'bold', fontSize: globalTextSize, color: props.showActiveOpps ? "blue" : "white" }}>Active&nbsp;&nbsp;</span>
              {/* <BsFillCircleFill size={12} style={{ fill: props.showActiveOpps ? "green" : "white" }} /> */}
            </div>

          </Tippy>
        }

        <div className='opp-table-controls-items noselect opp-filter-control__label' >  <span style={{ fontSize: globalTextSize, color: tc.text }}  >Filter&nbsp;</span>    </div>
        <div ref={filterWrapperRef} className='opp-table-controls-items opp-filter-search-control' style={{ marginRight: "5px" }} >
          {/* <TextBoxS tooltipContent={props.tooltipSW ? 'b,Search and Filter the Opportunities Table by all cells. \n Days can be filtered by a range of days; to filter a range of 30 to 60 days enter the range in the search as: 30-60.  You can also filter the Sharpe Ratio, (SR) by entering > sign and a number.  For example, enter ">2.0" in the filter text box.  Opportunities table is filtered to show only opportunities with Sharpe Ratio > 2.0 ' : ''} handleOnChange={handleOnChange} curText={curText} name='Filter' /> */}
          <TextBoxS
            tooltipContent={
              props.tooltipSW
                ?
                'b,Filter the Opportunities Table using multiple conditions separated by semicolons. ' +
                'For a day range of 30 to 60 days, type "30-60". ' +
                'To filter by Sharpe Ratio, type "SR>2". ' +
                'For Average Profit, type "AP>10" or "AVGP>10". ' +
                'For AI results, use "WIN>70", "PREDR>3", "ML>70", or "PMFE>8". ' +
                'AI filters use the value shown: the 10-day model minimum for a 1-9-day pattern, the complete window from 10 through 90 days, or the 90-day checkpoint for a longer pattern. ' +
                'You can also do a default text search by typing any keyword, like "AAPL". '
                : ''
            }
            handleOnChange={handleOnChange}
            curText={curText}
            name='Filter'
            onFocus={handleFilterFocus}
            onBlur={handleFilterBlur}
            onKeyDown={handleFilterKeyDown}
            onClear={handleClearFilter}
            placeholder='e.g. 10-90; PREDR>3'
            title='Filter by ticker or combine conditions with semicolons: 10-90, SR>2, AVGP>10, WIN>70, PREDR>3, ML>70, PMFE>8. AI filters use the displayed 10-day minimum, full-window, or 90-day checkpoint value.'
            ariaLabel='Filter opportunities'
            ariaDescribedBy='opportunity-filter-help'
          />
          <span id='opportunity-filter-help' style={{
            position: 'absolute',
            width: '1px',
            height: '1px',
            padding: 0,
            margin: '-1px',
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            border: 0,
          }}>
            Enter a ticker, or combine filters with semicolons. Examples: 10-90 for days,
            SR&gt;2, AVGP&gt;10, WIN&gt;70, PREDR&gt;3, ML&gt;70, and PMFE&gt;8.
            AI filters use the displayed 10-day model minimum for 1-9-day patterns, the
            complete-window value from 10 through 90 days, and the displayed 90-day checkpoint
            for longer patterns.
          </span>
          {filterHistoryDropdown}
        </div>

      </div>

      <div className={`opp-table${props.UITheme === 'dark' ? ' opp-table-dark' : ''}`} style={oppTableStyle}>
        {
          props.opportunities.length > 0
            ? (
              <TableBox
                table_data={props.showActiveOpps ? props.activeOpportunities : props.opportunities}
                handlerRowClicked={handlerRowClicked}
                handlerKeyDown={handlerKeyDown}
                rowIndexClicked={props.rowIndexClicked}
                SetRowIndexClicked={props.SetRowIndexClicked}
                filterText={curText}
                tooltipSW={props.tooltipSW}
                SetOppTableLength={props.SetOppTableLength}
                SetVisibleOpportunities={props.SetVisibleOpportunities}
                showSR2={props.showSR2}
                showAciveOpps={props.showActiveOpps}
                upgradeMessage={props.upgradeMessage}
                promotionMessage={props.promotionMessage}
                promotionCouponCode={props.promotionCouponCode}
                promotionBackColor={props.promotionBackColor}
                showUpgradeBanner={props.showUpgradeBanner}
                SetShowUpgradeBanner={props.SetShowUpgradeBanner}
                SetNumLongs={SetNumLongs}
                SetNumShorts={SetNumShorts}
                stockScores={stockScores}
                mlScores={mlScores}
                mlScoresLoading={mlScoresLoading}
                mlPending={mlPending}
                mlEnabled={mlEnabled}
                mlMarketEligible={mlMarketEligible}
                mlUnavailableReason={mlUnavailableReason}
                columnVisibility={props.columnVisibility}
                columnOrder={props.columnOrder}
                shortDates={effectiveShortDates}
                colSorted={effectiveOpportunitySort.column}
                sortedDir={effectiveOpportunitySort.direction}
                SetColSorted={SetOpportunitySortColumn}
                SetSortedDir={SetOpportunitySortDirection}
              />
            )
            : <span>
                {initialMessage}
                {oppLoadFailed &&
                  <button
                    onClick={() => {
                      SetOppLoadFailed(false)
                      SetInitialMessage('Loading ...')
                      SetOppRetryNonce(n => n + 1)
                    }}
                    style={{ marginLeft: '8px', cursor: 'pointer' }}
                  >Retry</button>}
              </span>
        }
      </div>
      {/* create a visual div below to show a nice box below the above div - inside the div say : to see all opportunities create a free account */}


      <div className='opp-filter' style={oppFilterStyle}>

        {rdd.isDesktop && props.showChatbot && typeof props.onChatbotResizeMouseDown === 'function' &&
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize Tara chat from top edge"
            onMouseDown={props.onChatbotResizeMouseDown}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '5px',
              cursor: 'ns-resize',
              zIndex: 3,
              userSelect: 'none',
            }}
          />
        }

        <div className='opp-filter-left-space' style={StyleoppFilterLeftSpace} onClick={handleBackClick}  >
          {
            (rdd.isMobile && browserH > browserW) &&
            <FaAngleLeft size={(rdd.isTablet ? 40 : 30)} style={{ fill: "white" }} onClick={handleBackClick} />
          }
          {
            (rdd.isDesktop && props.chatbotEnabled) &&
            <Tippy
              placement={'top'}
              maxWidth={360}
              content={
                <div style={{ textAlign: 'left', lineHeight: 1.4, padding: '2px 1px' }}>
                  <div style={{ fontWeight: 700, marginBottom: '5px' }}>{taraLauncherCopy.title}</div>
                  <div>{taraLauncherCopy.description}</div>
                  <div style={{ marginTop: '7px' }}>
                    <strong>Start with:</strong>{' '}
                    {taraLauncherCopy.prompts.map((prompt, index) => (
                      <React.Fragment key={prompt}>
                        {index > 0 && ' or '}
                        &ldquo;{prompt}&rdquo;
                      </React.Fragment>
                    ))}
                  </div>
                  <div style={{ marginTop: '7px', color: '#f5c842', fontWeight: 700 }}>{taraLauncherCopy.action}</div>
                </div>
              }
            >
              <span
                role="button"
                tabIndex={0}
                aria-label={props.showChatbot
                  ? 'Hide Tara chat, TradeWave AI guide'
                  : 'Open Tara, TradeWave AI guide'}
                style={{ display: 'inline-flex', alignItems: 'center' }}
                onClick={() => {
                  props.SetShowChatbot(!props.showChatbot);
                  if (!props.showChatbot && props.onChatbotIconClick) props.onChatbotIconClick();
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    props.SetShowChatbot(!props.showChatbot);
                    if (!props.showChatbot && props.onChatbotIconClick) props.onChatbotIconClick();
                  }
                }}
              >
                {props.showChatbot
                  ? <BsChatDotsFill aria-hidden="true" size={24} style={{ color: "#f5c842", cursor: 'pointer' }} />
                  : <BsChatDots aria-hidden="true" size={24} className={props.chatbotIconBlink ? 'chatbot-icon-blink' : ''} style={{ color: "white", cursor: 'pointer' }} />}
              </span>
            </Tippy>
          }
        </div>

        {/* implement the opportunities count and short and long and % below the opp table  */}

        <div className='opp-filter-span' style={StyleoppFilterSpan}>
          {(rdd.isMobile && browserH > browserW) ? (
            // Mobile View: No Tippy
            <span style={{ fontSize: globalTextSize, color: "white" }}>
              {props.oppTableLength} opps&nbsp;
              <span style={{ color: "#ffffff" }}> {numLongs} </span> L &nbsp;
              <span style={{ color: "#ffffff" }}> {numShorts} </span> S
              <span>&nbsp;</span>
              <span
                style={{
                  backgroundColor: numShorts > numLongs ? "red" : "green",
                  color: "white",
                  padding: "0 5px", // Optional for better spacing
                  borderRadius: "4px", // Optional for rounded corners
                }}
              >
                {parseInt(
                  100 *
                  (numShorts > numLongs
                    ? numShorts / (numShorts + numLongs)
                    : numLongs / (numShorts + numLongs)
                  )
                )}
                %
              </span>
            </span>
          ) : (
            // Desktop View: With Tippy
            <span style={{ fontSize: globalTextSize, color: "white" }}>
              <Tippy
                placement={'top'}
                content={
                  <div theme="tw" >
                    Total # of Opportunities
                  </div>
                }
              >
                <span>{props.oppTableLength} opportunities</span>
              </Tippy>
              &nbsp;
              <Tippy
                placement={'top'}
                content={
                  <div theme="tw" >
                    Total # of Long Opportunities
                  </div>
                }
              >
                <span style={{ color: "#ffffff" }}> {numLongs} </span>
              </Tippy>
              Longs &nbsp;
              <Tippy
                placement={'top'}
                content={
                  <div theme="tw" >
                    Total # of Short Opportunities
                  </div>
                }
              >
                <span style={{ color: "#ffffff" }}> {numShorts} </span>
              </Tippy>
              Shorts
              <span>&nbsp;</span>
              <Tippy
                placement={'top'}
                content={
                  <div theme="tw" >
                    If the indicator is green and shows 60%, it means 60% of all opportunities are Long positions.
                    If the indicator is red and shows 70%, it means 70% of all opportunities are Short positions.
                  </div>
                }
              >
                <span
                  style={{
                    backgroundColor: numShorts > numLongs ? "red" : "green",
                    color: "white",
                    padding: "0 5px",
                    borderRadius: "4px",
                  }}
                >
                 
                  {(() => {
                    const percentage = Math.round(
                      100 *
                      (numShorts > numLongs
                        ? numShorts / (numShorts + numLongs)
                        : numLongs / (numShorts + numLongs)
                      )
                    );
                    return isNaN(percentage) ? '' : `${percentage}%`;
                  })()}

                </span>
              </Tippy>
            </span>
          )}
        </div>




        <div className='opp-filter-select' style={StyleoppFilterSelect} >
          <SelectBox tooltipContent={props.tooltipSW ? 'r,filter by minimum % reached each year' : ''} optionList={availableFilters} value={props.appliedFilter} suffix="" name="filter" sbChanged={props.selectboxChanged} />
        </div>

        <Tippy placement={'right'} disabled={!props.tooltipSW} content={
          <div style={{ backgroundColor: 'transparent', color: 'white', paddingLeft: '3px', paddingRight: '3px' }}>
            {props.tooltipSW ? 'Premium Feature: By default 1 opportunity is returned per ticker with highest sharpe-ratio. Expand will return every trade for each ticker for the current start date.' : ''}
          </div>
        }>

          <div className='opp-filter-expand' onClick={handleExpandContract} style={StyleoppFilterExpand}>
            {oppListExpanded === 1
              ? <BsArrowsExpand size={expandIconSize} style={{ fill: "white" }} />
              : <BsArrowsCollapse size={expandIconSize} style={{ fill: "white" }} />
            }
          </div>

        </Tippy>

      </div>


    </div>
  )
}

export default OppTable
