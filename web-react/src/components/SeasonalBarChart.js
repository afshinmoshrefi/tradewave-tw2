import React, { useMemo, useState, useEffect, useContext, useRef, useCallback } from 'react'
import ReactDOM from 'react-dom'
import './styles/SeasonalBarChart.css'
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import TextBoxInc from './TextBoxInc'
import CheckBox from './CheckBox'
import BarChart from './BarChart'
import Tippy from '@tippyjs/react'
import { monthsAndQtrs, maxDaysOut, minDaysOut } from './Common'
import { redirectBackFromSeasonals } from './Common'
import { appserverURL } from './Common'
import { getTodayDate } from './Common'
import { twFetch } from './twFetch'
import { UserContext } from './UserContext'
import { BsFillCaretUpFill, BsFillCaretDownFill, BsQuestionCircle, BsPlus, BsBell, BsBellFill } from "react-icons/bs";
import { BiLineChart } from "react-icons/bi";
import { userAccessToSelectedSecurity, applyResolvedMatch, upsellDialogForMatch, isMarketEntitled } from './Common'
import { getCookie } from './Common'
import { buildPatternEventDict, insertCalendarEvents, requestCalendarAccessToken, shiftWeekendToNextMonday, loadGsiScript, friendlyDate } from './googleCalendarEvents'
import { getSelectedIDFromSecuritiesList2 } from './Common'
import { setCookie } from './Common'
import { UIcolors, themeColors } from './Common'
import { opp_dashboard_dialog_content } from './Common'
import { brand, trend_chart_left_gap_days, minYears, sameResourceFamily } from './Common'
import { maxYearsCap } from './Common'
import { checkTokenExpired } from './Common'
import { markCaptureReady, clearCaptureReady } from './captureReady'
import { VIEWER_CYCLE_CHANGE_EVENT, isViewerCycle, transitionViewerCycleState } from './viewerCycleState'

// import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
// import { faFileExcel, faHome } from "@fortawesome/free-solid-svg-icons";
// import { FaArrowCircleLeft, FaArrowCircleRight, ImArrowLeft, ImArrowRight } from "react-icons/fa";
// import {fa-solid fa-circle-left} from "@fortawesome/free-solid-svg-icons";

import { FaAngleRight } from "react-icons/fa";

const SeasonalBarChart = (props) => {

  const { wpUserLevels, browserH, browserW, rdd, token, globalTextSize, infoTextSize, loggedinUser, debug } = useContext(UserContext)
  const tc = themeColors(props.UITheme)

  // Stable market/resource id for all fetches in this component
  const marketId = useMemo(
    () => getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity),
    [props.securityTypeList, props.selectedSecurity]
  )

  // Request guards: only the latest response is allowed to update state
  const reqMetaRef = useRef(0)
  const reqChartRef = useRef(0)
  const [primaryChartLoading, setPrimaryChartLoading] = useState(false)
  const reqCompareRef = useRef(0)
  const reqBHRef = useRef(0)
  const reqTrendRef = useRef(0)
  const reqMaxTrendRef = useRef(0)
  const reqOppBySymbolRef = useRef(0)
  const cycleViewStatesRef = useRef({})
  // Ordering guard shared by the manual ticker-entry/resolution paths (handleBlur, handleEnter,
  // handleWatchlistItemClick, resolveSymbolAcrossMarkets) - these fire bare twFetch calls with
  // no AbortController, so two in-flight resolutions could otherwise land out of order and let
  // the OLDER entry's SetSymbol/applyResolvedMatch win.
  const reqSymbolEntryRef = useRef(0)
  // Guards the data-miss -> cross-market resolve path against a market-flip loop when the
  // SAME ticker is short on data in more than one market (see the Not Enough Data branch).
  const resolveMissRef = useRef('')
  // Bumped when a typed symbol is REJECTED (not found anywhere): forces the symbol TextBox
  // to re-sync back to props.symbol, which never changed - see defaultNotFound.
  const [symbolBoxSyncNonce, SetSymbolBoxSyncNonce] = useState(0)

  // when true, the next startDate change will NOT trigger a trend chart refetch (used by date nudge)
  const skipNextTrendRefetch = useRef(false)

  const [watchlistDropdownOpen, setWatchlistDropdownOpen] = useState(false)

  var showDate2 = false;



  // these are display for from and to dates if 2021-09-02 to 2021-09-24, they should be:
  // sep 2 to sep 24
  const [dateStartDisp, SetDateStartDisp] = useState(() => {
    return (props.startDate.substring(5, 10))
  })

  const [dateEndDisp, SetDateEndDisp] = useState(() => {
    if (props.daysOut !== '') {
      return incrementDate(props.startDate, props.daysOut - 1).substring(5, 10);
    }
    return '';
  });

  const [dateEnd, SetDateEnd] = useState(() => {
    if (props.daysOut !== '') {
      return incrementDate(props.startDate, props.daysOut - 1);
    }
    return '';
  });



  const [daysOutList, setDaysOutList] = useState([])

  const [seasonalYearsList, setSeasonalYearsList] = useState(() => {
    // initially set the years to 30 years manually.  make it work by getting metaData from appserver later
    var tmp = [];
    for (var i = 5; i <= 30; i++)
      tmp.push({ id: i, value: i.toString(), label: i.toString() })
    return (tmp)
  })

  // tmp.push({ id: 'pe1', value: 'pe1', label: 'Pres Election+1' })

  const [oppBySymbolOptions, setOppBySymbolOptions] = useState([])
  const [selectedOppBySymbol, setSelectedOppBySymbol] = useState('')
  // Measured width of the Best Waves flex wrapper (the row's slack). The wrapper is
  // flex:1 1 0 / minWidth:0, so its size is set by the row's OTHER content, never by
  // which select variant we render inside it - measuring it is feedback-loop-free.
  const bwWrapRef = useRef(null)
  const [bwSlackPx, setBwSlackPx] = useState(0)
  useEffect(() => {
    const el = bwWrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setBwSlackPx(e.contentRect.width)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [oppBySymbolOptions.length > 0])

  const [PEselectionList, SetPEselectionList] = useState(
    [
      { id: 'cons', value: 'cons', label: 'consecutive' },
      { id: 'pe0', value: 'pe0', label: 'PE Years' },
      { id: 'pe1', value: 'pe1', label: 'PE+1 Years' },
      { id: 'pe2', value: 'pe2', label: 'PE+2 Years' },
      { id: 'pe3', value: 'pe3', label: 'PE+3 Years' },
    ]
  );


  // const [secondLayerControlsVisible, SetSecondLayerControlsVisible] = useState('none') // for smartphone portrait only
  const [secondLayerControlsOpen, SetSecondLayerControlsOpen] = useState(false) // for smartphone portrait only
  const [secondLayerDisplay, SetSecondLayerDisplay] = useState('none')


  //const [symbolError,SetSymbolError] = useState('false') // used to trigger removing bad ticker symbol from textbox

  // find the index number from the value of the selected security.  want to just pass the index number to flask
  // const getSelectedIDFromSecuritiesList = () => {
  //   for (var i = 0; i < props.securityTypeList.length; i++) {
  //     if (props.securityTypeList[i]['value'] === props.selectedSecurity) break
  //   }

  //   return (i)
  // }



  //-----------------------------------------------------------------------------------------------------------------------
  function daysBetweenDates(date0, date1) { //increment date in format of yyyy-mm-dd and return same format

    const date1Obj = new Date(date1);
    const date0Obj = new Date(date0);

    // Calculate the time difference in milliseconds
    const timeDifference = date1Obj - date0Obj;

    // Convert milliseconds to days (1 day = 24 hours * 60 minutes * 60 seconds * 1000 milliseconds)
    const daysDifference = Math.floor(timeDifference / (24 * 60 * 60 * 1000));

    return Math.abs(daysDifference);

  }
  //-----------------------------------------------------------------------------------------------------------------------
  function incrementyear(dateStr, num) { //increment year in format of yyyy-mm-dd and return same format

    let substrings = dateStr.split('-');
    let year = parseInt(substrings[0]);
    year = year + num;

    return `${year}-${substrings[1]}-${substrings[2]}`
  }
  //-----------------------------------------------------------------------------------------------------------------------
  function incrementDate(dateStr, days) { //increment date in format of yyyy-mm-dd and return same format
    var d = new Date(dateStr + 'T00:00:00')
    d.setDate(d.getDate() + parseInt(days))
    var incDate = d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate()
    return (incDate)
  }
  //-----------------------------------------------------------------------------------------------------------------------
  // Build daysOutList once (it does not depend on symbol)
  useEffect(() => {
    const tmp = []
    for (let i = minDaysOut; i <= maxDaysOut; i++) {
      tmp.push({ id: i, value: i.toString(), label: i.toString() })
    }
    setDaysOutList(tmp)
  }, [])

  // Fetch StockMetaData safely (abort + latest response wins)
  useEffect(() => {
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return

    const reqId = ++reqMetaRef.current
    const controller = new AbortController()

    const asURL = appserverURL()
    const url = `${asURL}/StockMetaData/${marketId}/${props.symbol}?token=${token}`

    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type")
        if (contentType && contentType.indexOf("application/json") !== -1) return res.json()

        if (res.status === 429) {
          props.SetDialogType('rate-limit')
          props.SetInfoBoxVisible(true)
          return undefined
        }
        if (res.status === 500) {
          props.SetDialogType('info-box')
          props.SetDialogProp({ title: 'Symbol not Found', contentText: props.symbol + ' is not found', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          props.SetInfoBoxVisible(true)
          return undefined
        }

        console.log('StockMetaData response status = ', res.status)
        return undefined
      })
      .then(t => {
        // Ignore stale response
        if (reqId !== reqMetaRef.current) return
        if (!t) return

        const lst = t['StockMetaData']
        if (typeof lst === 'string' && lst.includes('Not Traded')) {
          props.SetSymbol('')
          props.SetDialogType('info-box')
          props.SetDialogProp({ title: 'Symbol Not Traded', contentText: lst, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          props.SetInfoBoxVisible(true)
          return
        }

        const y1 = parseInt(lst[0])
        const y2 = parseInt(lst[1])

        let tmp = []
        let minYears = 5
        let maxYears = y2 - y1

        if (props.PEselected !== 'cons') {
          minYears = 3
          const peRemainder = parseInt(props.PEselected[2]) // 0, 1, 2, or 3
          let count = 0
          for (let yr = y1; yr < y2; yr++) {
            if (yr % 4 === peRemainder) count++
          }
          maxYears = count
        }

        const _yrCap = maxYearsCap()   // tier cap (null=uncapped); NOTE: local `maxYears` above is the DATA range, not this

        // Lift the consecutive-cons max (tier-capped) to App state so the price-chart's
        // second seasonal-projection line ("Proj N-Y") knows both its label and its `sy`.
        // Always use y2-y1 (the raw range), not the local `maxYears` which is PE-adjusted.
        const consecutiveMax = y2 - y1
        const effectiveMaxYears = _yrCap != null ? Math.min(consecutiveMax, _yrCap) : consecutiveMax
        props.SetMaxAvailableYears(effectiveMaxYears)

        for (let i = minYears; i <= maxYears; i++) {
          const _locked = _yrCap != null && i > _yrCap
          tmp.push({ id: i, value: i.toString(), label: _locked ? i + ' 🔒' : i.toString(), locked: _locked })
        }
        setSeasonalYearsList(tmp)

        // NOTE: deliberately do NOT snap props.seasonalYears UP or to a smaller
        // in-range value here. This block used to snap it to maxYears/minYears,
        // but under a PE filter maxYears collapses to ~N/4, silently clobbering
        // the user's selection on every market/symbol switch and emptying the
        // chart. The years value is owned by App.js (cookie -> per-market
        // override -> global default; PE default [6,6]). The dropdown may
        // legitimately show fewer options than a smaller selected value.
        //
        // EXCEPTION - overflow only (step-down clamp, same invariant family as
        // the OppTable dead-years snap): a controlled <select value=N> whose N
        // is ABOVE every option does NOT keep showing N - the browser silently
        // displays the FIRST option instead (e.g. cons 95yr -> switch to PE+2:
        // the PE list is 3..24, 95 overflows, so the box shows "3" while state
        // stays "95" and the chart renders the full 24 - selector and chart
        // disagree). So when the selected value exceeds the max SELECTABLE
        // option, snap it DOWN to that max. This only fires on true overflow,
        // never on an in-range value, so it cannot reintroduce the clobber bug.
        // maxSelectable = the largest unlocked option (tier cap wins over range).
        const maxSelectable = _yrCap != null ? Math.min(maxYears, _yrCap) : maxYears
        const curYears = parseInt(props.seasonalYears, 10)
        if (!isNaN(curYears) && curYears > maxSelectable && maxSelectable >= minYears) {
          props.SetSeasonalYears(maxSelectable.toString())
        }
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        console.log('StockMetaData fetch error:', err?.message || err)
      })

    return () => controller.abort()
  }, [marketId, props.symbol, token, props.PEselected])
  //-----------------------------------------------------------------------------------------------------------------------
  // calculate end date 9/10/2023 - I don't know how it was working before
  //-----------------------------------------------------------------------------------------------------------------------
  useEffect(() => {

    if (props.daysOut !== '') {
      SetDateStartDisp(props.startDate.substring(5, 10))
      let ded = incrementDate(props.startDate, props.daysOut - 1);

      SetDateEndDisp(ded.substring(5, 10));
      SetDateEnd(ded);
    }


  }, [props.startDate, props.daysOut])

  //-----------------------------------------------------------------------------------------------------------------------
  useEffect(() => { // fetch barchart data (stable: abort + latest response wins)
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return
    if (!props.startDate) return
    if (!props.daysOut) return
    if (!props.seasonalYears) return

    const reqId = ++reqChartRef.current
    const controller = new AbortController()
    clearCaptureReady('seasonal')

    // The request identity changed, so prior chart/statistics payloads cannot
    // remain visible under the new controls while this request is in flight.
    // Keep the existing Chart.js instance mounted behind an opaque loading
    // cover. Clearing its data here makes Chart.js perform a blank update and
    // then a second update for the response, delaying the usable chart.
    setPrimaryChartLoading(true)
    props.SetTradeDetailData([])


    const asURL = appserverURL()
    const days_out_processed = (parseInt(props.daysOut) - 1)
    // const sy = props.seasonalYears; if (props.PEselected !== 'cons') sy += '-' + props.seasonalYears;
    let sy = props.seasonalYears; if (props.PEselected !== 'cons') sy = `${props.PEselected}-${props.seasonalYears}`
    // console.log('sssssssssyyyyyyyy=', props.PEselected, props.symbol, sy)
    let url = `${asURL}/ChartData4/${marketId}/${props.startDate}/${props.symbol}/${days_out_processed}/${sy}`
    if (props.trimYear !== 0) url += `/${props.trimYear}`
    url += `?token=${token}`


    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type")
        if (contentType && contentType.indexOf("application/json") !== -1) return res.json()

        if (res.status === 429) {
          props.SetDialogType('rate-limit')
          props.SetInfoBoxVisible(true)
          return undefined
        }

        // transient failure already retried by twFetch - surface instead of a blank chart
        console.log('ChartData4 response status = ', res.status)
        props.SetDialogType('info-box')
        props.SetDialogProp({ title: 'Data Temporarily Unavailable', contentText: 'The chart data could not be loaded. Please try again in a moment - reselect the pattern or refresh the browser.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        props.SetInfoBoxVisible(true)
        props.SetSeasonalBarChartData([])
        setPrimaryChartLoading(false)
        return undefined
      })
      .then(t => {
        // Ignore stale response
        if (reqId !== reqChartRef.current) return
        if (!t) return

        const cd = t["ChartData4"]


        if (typeof cd === 'string' && cd.includes('Not Enough Data')) {
          const notEnoughData = () => {
            props.SetDialogType('info-box')
            props.SetDialogProp({ title: 'Not Enough Data', contentText: `${props.symbol} does not have enough data. At least 5 years are required`, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
            props.SetInfoBoxVisible(true)
            props.SetSeasonalBarChartData([])
            setPrimaryChartLoading(false)
            props.SetTradeDetailData([])
            props.SetConsolidatedSeasonalData([])
            props.SetSymbol('')
            props.SetLineChartYear(0)
          }
          // The ticker may belong to a DIFFERENT market (e.g. SPX typed on DJ30 lives in
          // Indices). NameFromTicker can't catch this - it matches any same-exchange security -
          // so ChartData4's data-miss is the real "wrong market" signal. Try to resolve across
          // markets first; only show the dead-end if it isn't served elsewhere. Guard against a
          // flip-loop when the same ticker is thin in >1 market (resolve once per symbol).
          if (resolveMissRef.current === props.symbol) {
            resolveMissRef.current = ''
            notEnoughData()
          } else {
            resolveMissRef.current = props.symbol
            resolveSymbolAcrossMarkets(props.symbol, { excludeMarketId: marketId, notFound: notEnoughData })
          }
          return
        }

        // Determine lastYearOfData + trade dir
        let lastYearOfData = 0
        cd.forEach(r => { lastYearOfData = r['year'] })

        const eDate = incrementDate(props.startDate, props.daysOut - 1).substring(5, 10)
        let download_img_name = `TradeWave Opportunity Export for ${props.symbol} date range  ${props.startDate} to ${eDate}.jpg`
        if (props.monthsAndQtrs !== 'Months & Qtrs') {
          download_img_name = props.symbol + '_' + props.monthsAndQtrs + '.jpg'
        }

        // React 17 does not automatically batch promise callbacks. Commit the
        // bar-chart response first, then let the browser paint before installing
        // downstream stats and price-chart state.
        resolveMissRef.current = ''   // clean load - clear the data-miss cross-market guard
        ReactDOM.unstable_batchedUpdates(() => {
          props.SetSeasonalBarChartData(cd)
          props.SetBarChartLongOrShort(t["stats"]["Trade Dir"])
          setPrimaryChartLoading(false)
          if (cd.length > 0) {
            markCaptureReady('seasonal', {
              symbol: props.symbol,
              years: props.seasonalYears,
              points: cd.length,
            })
          }
        })
        window.requestAnimationFrame(() => {
          window.setTimeout(() => {
            if (reqId !== reqChartRef.current) return
            ReactDOM.unstable_batchedUpdates(() => {
              props.SetTradeDetailData(t["stats"])
              props.SetLineChartYear(lastYearOfData)
              props.SetDownloadImageName(download_img_name)
            })
          }, 1200)
        })
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        // network failure after twFetch retries - surface instead of a blank chart
        console.log('ChartData4 fetch error:', err?.message || err)
        props.SetSeasonalBarChartData([])
        setPrimaryChartLoading(false)
        props.SetDialogType('info-box')
        props.SetDialogProp({ title: 'Data Temporarily Unavailable', contentText: 'The chart data could not be loaded. Please try again in a moment - reselect the pattern or refresh the browser.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        props.SetInfoBoxVisible(true)
      })

    return () => controller.abort()
  }, [marketId, props.startDate, props.symbol, props.daysOut, props.seasonalYears, props.PEselected, props.trimYear, props.monthsAndQtrs, token])
  //--------------------------------------------------------------------------------------------------------------------
  // this fetch is for the comparison security - spx by default
  //--------------------------------------------------------------------------------------------------------------------
  // --------------------------------------------------------------------------------------------------------------------
  // Comparison barchart fetch (stable: abort + latest response wins)
  // --------------------------------------------------------------------------------------------------------------------
  useEffect(() => {
    if (!token || token.length === 0) return;

    const compareMarketId = props.compareSecurity?.[0];
    const compareSymbol = props.compareSecurity?.[1];
    const compareMMDD = props.compareSecurity?.[2];   // ideally "01-01" but we normalize below
    const compareDays = props.compareSecurity?.[3];   // typically 365

    if (compareMarketId === undefined || compareMarketId === null) return;
    if (!compareSymbol || compareSymbol.length === 0) return;
    if (!compareMMDD) return;
    if (!compareDays) return;
    if (!props.seasonalYears) return;

    const reqId = ++reqCompareRef.current;
    const controller = new AbortController();

    const asURL = appserverURL();

    // Normalize compareMMDD so it works whether you pass "01-01" or "-01-01"
    const mmdd = (typeof compareMMDD === 'string' && compareMMDD.startsWith('-'))
      ? compareMMDD.slice(1)
      : compareMMDD;

    const year = getTodayDate().substring(0, 4);
    const startDate = `${year}-${mmdd}`;

    // console.log("compareMarketId  props.PEselected  props.seasonalYears", compareMarketId, props.PEselected, props.seasonalYears)

    const days_out_processed = (parseInt(compareDays, 10) - 1);
    // const sy = props.seasonalYears; if (props.PEselected !== 'cons') sy += '-' + props.seasonalYears;
    let sy = props.seasonalYears; if (props.PEselected !== 'cons') sy = `${props.PEselected}-${props.seasonalYears}`;
    const url =
      `${asURL}/ChartData4/${compareMarketId}/${startDate}/${compareSymbol}/${days_out_processed}/${sy}` +
      `?token=${token}`;

    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type");

        if (contentType && contentType.indexOf("application/json") !== -1) return res.json();

        if (res.status === 429) {
          props.SetDialogType('rate-limit');
          props.SetInfoBoxVisible(true);
          return undefined;
        }

        console.log('Compare ChartData4 response status = ', res.status);
        return undefined;
      })
      .then(t => {
        if (reqId !== reqCompareRef.current) return;
        if (!t) return;

        const chart = t["ChartData4"];
        const stats = t["stats"];

        props.SetCompareSecurityBarChartData(chart || []);
        props.SetCompareSecurityTradeDetailData(stats || {});

        let pos = 0, neg = 0;

        (chart || []).forEach(r => {
          const plist = (r?.pct || '').split(',');
          const first = parseFloat(plist[0]);
          if (!Number.isFinite(first)) return;
          if (first >= 0) pos++;
          else neg++;
        });

        props.SetCompareSecurityLongOrShort((pos >= neg) ? 'long' : 'short');
      })
      .catch(err => {
        if (err?.name === 'AbortError') return;
        console.log('Compare ChartData4 fetch error:', err?.message || err);
      });

    return () => controller.abort();
  }, [
    props.compareSecurity?.[0],
    props.compareSecurity?.[1],
    props.compareSecurity?.[2],
    props.compareSecurity?.[3],
    props.seasonalYears,
    props.PEselected,
    token
  ]);
  //-----------------------------------------------------------------------------------------------------------------------
  //--------------------------------------------------------------------------------------------------------------------
  // Buy & Hold stats for the currently displayed security (used by SeasonalChartStats on desktop)
  // Re-fetch when symbol or seasonalYears changes (and token/marketId changes).
  //--------------------------------------------------------------------------------------------------------------------
  useEffect(() => {
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return

    const reqId = ++reqBHRef.current
    const controller = new AbortController()

    const base_year = getTodayDate().substring(0, 4)
    const date_0 = `${base_year}-01-01`
    const date_1 = incrementyear(date_0, 1)

    // days between Jan 1 and next Jan 1 (365 or 366)
    const days = daysBetweenDates(date_0, date_1)
    const days_out_processed = days - 1

    const asURL = appserverURL()
    // const sy = props.seasonalYears; if (props.PEselected !== 'cons') sy += '-' + props.seasonalYears;
    let sy = props.seasonalYears; if (props.PEselected !== 'cons') sy = `${props.PEselected}-${props.seasonalYears}`
    const url = `${asURL}/ChartData4/${marketId}/${date_0}/${props.symbol}/${days_out_processed}/${sy}?token=${token}`

    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type")
        if (contentType && contentType.indexOf("application/json") !== -1) return res.json()

        if (res.status === 429) {
          props.SetDialogType('rate-limit')
          props.SetInfoBoxVisible(true)
          return undefined
        }

        console.log('BH ChartData4 response status = ', res.status)
        return undefined
      })
      .then(t => {
        if (reqId !== reqBHRef.current) return
        if (!t) return

        // Old behavior: stats lives at t["stats"]
        props.SetSecurityBHstats(t["stats"] || {})
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        console.log('BH ChartData4 fetch error:', err?.message || err)
      })

    return () => controller.abort()
  }, [marketId, props.symbol, props.seasonalYears, props.PEselected, token])


  //-----------------------------------------------------------------------------------------------------------------------
  function isCurrentYearLeap() {
    const currentYear = new Date().getFullYear();
    return (currentYear % 4 === 0 && currentYear % 100 !== 0) || (currentYear % 400 === 0);
  }



  //--------------------------------------------------------------------------------------------------------------------
  // this fetch is for the buy and hold of the currently displayed security
  // it should only envoke if the number of years is changed
  //--------------------------------------------------------------------------------------------------------------------


  useEffect(() => { // fetch trendchart data (stable: abort + latest response wins)
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return

    // date nudge sets this flag so the trend chart doesn't refetch on startDate shift
    if (skipNextTrendRefetch.current) { skipNextTrendRefetch.current = false; return }

    const reqId = ++reqTrendRef.current
    const controller = new AbortController()
    clearCaptureReady('trendChart')

    let asURL = appserverURL()
    let td = getTodayDate()
    let start_date = td.substring(0, 5) + '01-01'
    let opp_start_date = props.startDate

    if (!props.janDecDateRange) {
      start_date = props.trendChartStartDate
    }

    let yrs = props.seasonalYears;
    if (props.PEselected !== 'cons') yrs = `${props.PEselected}-${props.seasonalYears}`;

    const url = `${asURL}/consolidated_seasonal_chart2/${marketId}/${props.symbol}/${yrs}/${start_date}/${opp_start_date}?token=${token}`

    // console.log('ttttttttttttttttttttttttrendchart triggered with props. opp_start_date=',opp_start_date)

    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type")
        if (contentType && contentType.indexOf("application/json") !== -1) return res.json()

        if (res.status === 429) {
          props.SetDialogType('rate-limit')
          props.SetInfoBoxVisible(true)
          return undefined
        }

        console.log('consolidated_seasonal_chart2 response status = ', res.status)
        return undefined
      })
      .then(t => {
        if (reqId !== reqTrendRef.current) return
        if (!t) return

        const chart = t['cons_seas_chart']
        if (!Array.isArray(chart) || chart.length < 5) props.SetConsolidatedSeasonalData([])
        else {
          props.SetConsolidatedSeasonalData(chart)
          markCaptureReady('trendChart', { symbol: props.symbol, points: chart.length })
        }
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        console.log('Trend chart fetch error:', err?.message || err)
      })

    return () => controller.abort()
  }, [props.refreshKey, marketId, props.symbol, props.seasonalYears, props.PEselected, props.janDecDateRange, props.trendChartStartDate, props.startDate, token])

  //--------------------------------------------------------------------------------------------------------------------
  // Second consolidated seasonal fetch: MAX-years history, always PE=cons, for the price-chart's
  // secondary projection line. Skips the request when the toggle is off, when the ticker's
  // max already equals the user-selected sy (both lines would be identical), or before we know N.
  useEffect(() => {
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return
    if (!props.showMaxProjection) return
    if (!props.maxAvailableYears || props.maxAvailableYears <= 0) return
    // If cons and the user is already viewing max, the primary line covers this — no fetch needed,
    // and clear the stale max-cycle so we don't render two identical dashed lines on top of each other.
    if (props.PEselected === 'cons' && parseInt(props.seasonalYears, 10) === props.maxAvailableYears) {
      if (props.maxYearsConsolidatedSeasonalData && props.maxYearsConsolidatedSeasonalData.length > 0) {
        props.SetMaxYearsConsolidatedSeasonalData([])
      }
      return
    }

    const reqId = ++reqMaxTrendRef.current
    const controller = new AbortController()

    const asURL = appserverURL()
    const td = getTodayDate()
    let start_date = td.substring(0, 5) + '01-01'
    const opp_start_date = props.startDate
    if (!props.janDecDateRange) start_date = props.trendChartStartDate

    // Always cons + max years, regardless of the user's current PE / sy pick.
    const yrs = props.maxAvailableYears
    const url = `${asURL}/consolidated_seasonal_chart2/${marketId}/${props.symbol}/${yrs}/${start_date}/${opp_start_date}?token=${token}`

    twFetch(url, { signal: controller.signal })
      .then(res => {
        const contentType = res.headers.get("content-type")
        if (contentType && contentType.indexOf("application/json") !== -1) return res.json()
        if (res.status === 429) return undefined  // primary fetch already surfaces the rate-limit dialog
        return undefined
      })
      .then(t => {
        if (reqId !== reqMaxTrendRef.current) return
        if (!t) return
        const chart = t && t['cons_seas_chart']
        if (!Array.isArray(chart) || chart.length < 5) props.SetMaxYearsConsolidatedSeasonalData([])
        else props.SetMaxYearsConsolidatedSeasonalData(chart)
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        console.log('Max-years trend chart fetch error:', err?.message || err)
      })

    return () => controller.abort()
  }, [props.refreshKey, marketId, props.symbol, props.maxAvailableYears, props.showMaxProjection, props.PEselected, props.seasonalYears, props.janDecDateRange, props.trendChartStartDate, props.startDate, token])

  //--------------------------------------------------------------------------------------------------------------------
  // Clear OppBySymbol options immediately when symbol or market changes
  useEffect(() => {
    setOppBySymbolOptions([])
    setSelectedOppBySymbol('')
  }, [props.symbol, marketId])

  //--------------------------------------------------------------------------------------------------------------------
  // Fetch best waves for the current symbol (desktop + paid users only)
  //--------------------------------------------------------------------------------------------------------------------
  useEffect(() => {
    if (rdd.isMobile) return
    if (!token || token.length === 0) return
    if (!props.symbol || props.symbol.length === 0) return
    if (marketId === undefined || marketId === null) return
    if (!props.seasonalYears) return
    if (loggedinUser === '0') return

    const retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity)
    if (retArray[0] === 'F') return

    const reqId = ++reqOppBySymbolRef.current
    const controller = new AbortController()

    const asURL = appserverURL()
    const mode = props.PEselected !== 'cons' ? 'pe' : 'consecutive'
    const url = `${asURL}/OppBySymbol/${marketId}/${props.symbol}/${props.seasonalYears}/${props.seasonalYears}/-/100?token=${token}&mode=${mode}`
    console.log('OppBySymbol url:', url)

    twFetch(url, { signal: controller.signal })
      .then(res => {
        if (res.ok && res.headers.get('content-type')?.includes('application/json')) return res.json()
        return undefined
      })
      .then(t => {
        if (reqId !== reqOppBySymbolRef.current) return
        if (!t) return
        console.log('OppBySymbol response:', t)
        if (t.status === 'feature_not_available') { setOppBySymbolOptions([]); return }
        if (t.status !== 'ok' || !t.OppBySymbol?.length) { setOppBySymbolOptions([]); return }

        const placeholder = [{ id: 0, value: '', label: 'Best Waves' }] // no decorative dashes - the select sizes to the selected option and this row is width-critical
        const options = t.OppBySymbol.map((row, i) => {
          const date = row[0]
          // OppBySymbol stores the analytics-engine offset. Viewer state and
          // labels use inclusive calendar days, with the entry date as day 1.
          const daysOut = parseInt(row[2], 10) + 1
          const lOrS = row[3]
          const sharpe = row[4]
          const avgProfit = row[5]
          const startMMDD = date.substring(5).replace('-', '/')
          const endMMDD = incrementDate(date, daysOut - 1).substring(5).replace('-', '/')
          const dir = lOrS[0]
          return {
            id: i + 1,
            value: `${date}|${daysOut}|${lOrS}`,
            label: `${startMMDD}-${endMMDD} ${dir} SR:${parseFloat(sharpe).toFixed(2)}`
          }
        })
        setOppBySymbolOptions([...placeholder, ...options])
        setSelectedOppBySymbol('')
      })
      .catch(err => {
        if (err?.name === 'AbortError') return
        console.log('OppBySymbol fetch error:', err?.message || err)
      })

    return () => controller.abort()
  }, [marketId, props.symbol, props.seasonalYears, props.PEselected, token, loggedinUser])

  //--------------------------------------------------------------------------------------------------------------------
  const checkboxChanged = (event) => {
    // console.log(event.target.value, event.target.checked)

    if (event.target.value === 'MFE') {
      props.setShowMFE(event.target.checked)
      setCookie('MFE', event.target.checked.toString(), 300)
    }
    if (event.target.value === 'MAE') {
      props.setShowMAE(event.target.checked)
      setCookie('MAE', event.target.checked.toString(), 300)
    }
  }
  //--------------------------------------------------------------------------------------------------------------------
  const handleSymbolFocus = () => {
    if (props.showWatchlistOnFocus && props.defaultWatchlistItems && props.defaultWatchlistItems.length > 0 && loggedinUser !== '0'
      && sameResourceFamily(marketId, props.defaultWatchlistResourceId)) {
      setWatchlistDropdownOpen(true)
    }
  }
  const handleSymbolBlur = () => {
    setTimeout(() => { setWatchlistDropdownOpen(false) }, 200)
  }
  //-----------------------------------------------------------------------------------------------------------
  // Symbol not in the CURRENT market -> resolve it across ALL markets (appserver /ResolveSymbol):
  //   0 matches   -> the usual "not found" dialog
  //   1 entitled  -> auto-switch the market + render (applyResolvedMatch)
  //   1 locked    -> "Unlock This Market" upsell
  //   >1 matches  -> always show the market picker; never auto-guess (e.g. CL = stock + future)
  //-----------------------------------------------------------------------------------------------------------
  const resolveSymbolAcrossMarkets = (symbolValue, opts = {}) => {
    // A truly-unknown symbol must NOT destroy the current view: props.symbol was never
    // overwritten (only accepted symbols are Set), so every chart still shows the old
    // symbol - keep them intact, show the dialog, and snap the text box back to the old
    // symbol (syncNonce forces the TextBox re-sync since the `text` prop didn't change).
    const defaultNotFound = () => {
      props.SetDialogType('info-box')
      props.SetDialogProp({ title: 'Symbol not Found', contentText: symbolValue + ' not found', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
      props.SetInfoBoxVisible(true)
      SetSymbolBoxSyncNonce(n => n + 1)   // revert the typed text; charts/data untouched
    }
    // Caller can override the dead-end (e.g. a data-miss shows "Not Enough Data", not "not found").
    const notFound = opts.notFound || defaultNotFound
    const asURL = appserverURL()
    const reqId = ++reqSymbolEntryRef.current
    twFetch(`${asURL}/ResolveSymbol/${symbolValue}?token=${token}`)
      .then(res => res.json())
      .then(res => {
        if (reqId !== reqSymbolEntryRef.current) return // a newer symbol-entry action has started - drop this stale resolution
        let matches = (res && res.matches) || []
        // When called from a data-miss on the CURRENT market, drop that market so we only offer
        // a genuinely DIFFERENT one (SPX on DJ30 -> Indices, never "switch to DJ30" again).
        if (opts.excludeMarketId !== undefined && opts.excludeMarketId !== null) {
          matches = matches.filter(m => String(m.resourceID) !== String(opts.excludeMarketId))
        }
        if (matches.length === 0) { notFound(); return }
        if (matches.length === 1) {
          const m = matches[0]
          if (isMarketEntitled(props.securityTypeList2, props.resourceObj, m.resourceID)) {
            applyResolvedMatch(props, m, symbolValue)          // entitled -> auto-switch + render
          } else {
            props.SetDialogProp(upsellDialogForMatch(m, symbolValue))  // locked -> upsell
            props.SetDialogType('info-box')
            props.SetInfoBoxVisible(true)
          }
          return
        }
        // >1 markets contain this ticker -> always let the user choose
        props.SetDialogProp({ title: 'Choose a Market', matches: matches, symbol: symbolValue, button1Text: 'Close', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
        props.SetDialogType('symbol-picker')
        props.SetInfoBoxVisible(true)
      })
      .catch(err => {
        if (reqId !== reqSymbolEntryRef.current) return
        console.log('ResolveSymbol error:', err && err.message); notFound()
      })
  }
  //-----------------------------------------------------------------------------------------------------------
  const handleWatchlistItemClick = (sym) => {
    setWatchlistDropdownOpen(false)
    let asURL = appserverURL()
    let id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
    const reqId = ++reqSymbolEntryRef.current
    twFetch(`${asURL}/NameFromTicker/${id}/${sym}?token=${token}`)
      .then(res => res.json())
      .then(g => {
        if (reqId !== reqSymbolEntryRef.current) return // a newer symbol-entry action has started - drop this stale resolution
        if (g['name'] !== '') {
          props.SetSymbol(sym)
          props.SetConsolidatedSeasonalData([])
          let trend_chart_start_date = incrementDate(props.startDate, -trend_chart_left_gap_days)
          props.SetTrendChartStartDate(trend_chart_start_date)
          props.SetCompany(g['name'])
        } else {
          resolveSymbolAcrossMarkets(sym)   // try the other markets before giving up
        }
      })
      .catch(err => console.log('watchlist NameFromTicker error:', err.message))
  }
  //--------------------------------------------------------------------------------------------------------------------
  // react changed the behavior of onchange -
  const handleBlur = (event) => {
    if (event.target.id === 'date') {

      if (props.startDate !== event.target.value) {

        let old_start_date = props.startDate
        // check if the typed date is valid
        let isValid = true;
        let d = event.target.value;
        let dl = d.split('-');
        if (dl.length !== 3 || dl[0].length !== 4 || dl[1].length !== 2 || dl[2].length != 2) isValid = false;
        else {
          let y = parseInt(dl[0]);
          let m = parseInt(dl[1]);
          let d = parseInt(dl[2]);
          if (y < 1920) isValid = false;
          if (m < 1 || m > 12) isValid = false;
          if (d < 1 || d > 31) isValid = false;
        }
        if (isValid) {
          props.SetStartDate(event.target.value);
          setSelectedOppBySymbol('');
          const trend_chart_start_date = incrementDate(event.target.value, -trend_chart_left_gap_days);
          props.SetTrendChartStartDate(trend_chart_start_date);
          props.SetConsolidatedSeasonalData([]);
        }
        else { // entered date is invalid

          const forcedStart = props.consolidatedSeasonalData[0][0];
          props.SetStartDate(forcedStart); // change invalid date to first day in seasonal chart

          // keep trend chart aligned with forced start date
          let trend_chart_start_date = incrementDate(forcedStart, -trend_chart_left_gap_days);
          props.SetTrendChartStartDate(trend_chart_start_date);
          props.SetConsolidatedSeasonalData([]);

          props.SetDialogType('info-box');
          props.SetDialogProp({ title: 'Invalid Date', contentText: `${d} Date must be in YYYY-MM-DD format.`, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          props.SetInfoBoxVisible(true)
        }

      }

    }


    if (event.target.id === 'symbol') {
      if (props.symbol !== event.target.value) {



        let asURL = appserverURL()
        let id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity);
        let url = `${asURL}/NameFromTicker/${id}/${event.target.value}?token=${token}`

        const reqId = ++reqSymbolEntryRef.current
        twFetch(url)
          .then((res) => {
            return res.json();
          })
          .then((g) => {

            // console.log('g1111111111111111111111111111111',g)

            if (reqId !== reqSymbolEntryRef.current) return // a newer symbol-entry action has started - drop this stale resolution

            if (g['name'] != "") {
              props.SetSymbol(event.target.value);
              props.SetConsolidatedSeasonalData([])

              // console.log('ppppppppppppprops.startDate 615', props.startDate);

              let trend_chart_start_date = incrementDate(props.startDate, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
              props.SetTrendChartStartDate(trend_chart_start_date)
              props.SetCompany(g['name'])
            }
            else {
              if (event.target.value !== '' && props.symbol !== '') {
                resolveSymbolAcrossMarkets(event.target.value)
              }
            }

          })
          .catch(err => {
            console.log('NameFromTicker error in SeasonalBarChart =', err.message)
          })
      }
    }
  }
  //--------------------------------------------------------------------------------------------------------------------
  const handleEnter = (event) => {

    // console.log('symbol before =', props.symbol)


    if (event.key === 'Enter') {

      if (event.target.id === 'date') {
        // props.SetMonthsAndQtrs('Months & Qtrs')
        // props.SetStartDate(event.target.value)

        // let old_start_date = props.startDate
        // check if the typed date is valid
        let isValid = true;
        let d = event.target.value;
        let dl = d.split('-');
        if (dl.length !== 3 || dl[0].length !== 4 || dl[1].length !== 2 || dl[2].length !== 2) isValid = false;
        else {
          let y = parseInt(dl[0]);
          let m = parseInt(dl[1]);
          let d = parseInt(dl[2]);
          if (y < 1920) isValid = false;
          if (m < 1 || m > 12) isValid = false;
          if (d < 1 || d > 31) isValid = false;
        }
        if (isValid) {
          props.SetStartDate(event.target.value);
          setSelectedOppBySymbol('');
          const trend_chart_start_date = incrementDate(event.target.value, -trend_chart_left_gap_days);
          props.SetTrendChartStartDate(trend_chart_start_date);
          props.SetConsolidatedSeasonalData([]);
          // now check years set to pe0, pe1, pe2, pe3 - check if the year is advanced to the following year, then adjust pe also


        }
        else { // entered date is invalid
          const forcedStart = props.consolidatedSeasonalData[0][0];
          props.SetStartDate(forcedStart); // change invalid date to first day of seasonal chart

          // keep trend chart aligned with forced start date
          let trend_chart_start_date = incrementDate(forcedStart, -trend_chart_left_gap_days);
          props.SetTrendChartStartDate(trend_chart_start_date);
          props.SetConsolidatedSeasonalData([]);

          props.SetDialogType('info-box');
          props.SetDialogProp({ title: 'Invalid Date', contentText: `${d} Date must be in YYYY-MM-DD format.`, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          props.SetInfoBoxVisible(true)
        }

      }
      if (event.target.id === 'symbol') {

        let asURL = appserverURL()
        let id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity);
        let url = `${asURL}/NameFromTicker/${id}/${event.target.value}?token=${token}`

        const reqId = ++reqSymbolEntryRef.current
        twFetch(url)
          .then((res) => {
            return res.json();
          })
          .then((g) => {

            // console.log('g22222222222222222222222222222222222',g)

            if (reqId !== reqSymbolEntryRef.current) return // a newer symbol-entry action has started - drop this stale resolution

            if (g['name'] != "") {
              props.SetSymbol(event.target.value);
              props.SetConsolidatedSeasonalData([]);

              // console.log('ppppppppppppprops.startDate 699',props.startDate);

              let trend_chart_start_date = incrementDate(props.startDate, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
              props.SetTrendChartStartDate(trend_chart_start_date)
              props.SetCompany(g['name'])
            }
            else {
              if (event.target.value !== '') {
                resolveSymbolAcrossMarkets(event.target.value)
              }
            }
          })
          .catch(err => {
            console.log('NameFromTicker error in SeasonalBarChart =', err.message)
          })
      }
      props.SetRowIndexClicked(-1)
    }
  }
  //-----------------------------------------------------------------------------------------------------------
  // nudge start date by +-1 day while keeping end date fixed (adjusts daysOut inversely)
  // does NOT trigger trend chart refetch - only the highlight window moves
  //-----------------------------------------------------------------------------------------------------------
  const handleDateNudge = (direction) => {
    const newDaysOut = parseInt(props.daysOut) - direction
    if (newDaysOut < 2 || newDaysOut > maxDaysOut) return
    const newDate = incrementDate(props.startDate, direction)
    if (direction < 0 && props.consolidatedSeasonalData.length > 0 && newDate < props.consolidatedSeasonalData[0][0]) return
    skipNextTrendRefetch.current = true  // nudge should NOT trigger trend chart refetch
    props.SetStartDate(newDate)
    props.SetDaysOut(String(newDaysOut))
    setSelectedOppBySymbol('')
  }
  //-----------------------------------------------------------------------------------------------------------

  // Keep Tara's PE comparison links on exactly the same state transition as
  // the Wave Viewer selector. The ref gives the native event listener current
  // props without recreating it on every render.
  const viewerCyclePropsRef = useRef(props)
  viewerCyclePropsRef.current = props
  const changeViewerCycle = useCallback((nextCycle) => {
    if (!isViewerCycle(nextCycle)) return
    const currentProps = viewerCyclePropsRef.current
    const currentCycle = currentProps.PEselected || 'cons'
    if (nextCycle === currentCycle) return

    const bumpStartDateYearToPE = (startDate, peValue) => {
      const target = { pe0: 0, pe1: 1, pe2: 2, pe3: 3 }[peValue]
      if (target === undefined) return startDate
      const baseYear = parseInt(getTodayDate().substring(0, 4), 10)
      const [, mm, dd] = startDate.split('-')
      const delta = (target - (baseYear % 4) + 4) % 4
      return `${baseYear + delta}-${mm}-${dd}`
    }

    const currentView = {
      startDate: currentProps.startDate,
      trendChartStartDate: currentProps.trendChartStartDate,
      seasonalYears: String(currentProps.seasonalYears),
    }
    const nextStartDate = nextCycle === 'cons'
      ? currentProps.startDate
      : bumpStartDateYearToPE(currentProps.startDate, nextCycle)
    const defaultNextView = {
      startDate: nextStartDate,
      trendChartStartDate: incrementDate(nextStartDate, -trend_chart_left_gap_days),
      seasonalYears: String(currentProps.seasonalYears),
    }
    const transition = transitionViewerCycleState({
      savedStates: cycleViewStatesRef.current,
      currentCycle,
      nextCycle,
      currentView,
      defaultNextView,
    })
    cycleViewStatesRef.current = transition.savedStates

    currentProps.SetPEselected(nextCycle)
    currentProps.SetStartDate(transition.nextView.startDate)
    currentProps.SetTrendChartStartDate(transition.nextView.trendChartStartDate)
    currentProps.SetSeasonalYears(transition.nextView.seasonalYears)
    currentProps.SetLineChartYear(0)
    currentProps.SetSeasonalBarChartData([])
    currentProps.SetTradeDetailData([])
    currentProps.SetConsolidatedSeasonalData([])
    currentProps.SetMaxYearsConsolidatedSeasonalData([])
    currentProps.SetCompareSecurityBarChartData([])
    currentProps.SetCompareSecurityTradeDetailData([])
    currentProps.SetSecurityBHstats([])
    setSelectedOppBySymbol('')
  }, [])

  useEffect(() => {
    const handleCycleLink = event => changeViewerCycle(event?.detail?.cycle)
    window.addEventListener(VIEWER_CYCLE_CHANGE_EVENT, handleCycleLink)
    return () => window.removeEventListener(VIEWER_CYCLE_CHANGE_EVENT, handleCycleLink)
  }, [changeViewerCycle])

  //-----------------------------------------------------------------------------------------------------------

  const selectboxChanged = (event) => {

    console.log('select changed', event.target.id)

    // console.log(event.target.id, event.target.value)
    if (event.target.id === 'daysout') {
      props.SetDaysOut(event.target.value)
      props.SetMonthsAndQtrs('Months & Qtrs')
      setSelectedOppBySymbol('')
    }

    // 

    if (event.target.id === 'years') {
      const newYears = event.target.value.toLowerCase();

      // Years cap: deeper history is an Analyst/Strategist feature. PE values ('pe2') parseInt
      // to NaN and are skipped (not depth-capped). This is the chart-side twin of App.js's
      // opp-table years guard so neither surface can silently exceed the cap.
      const _yrCap = maxYearsCap();
      const _ny = parseInt(newYears, 10);
      if (_yrCap != null && !isNaN(_ny) && _ny > _yrCap) {
        props.SetDialogProp({ title: 'See More History', contentText: `Your plan shows ${_yrCap} years of history. Upgrade to Analyst or Strategist for the full record - decades of seasonal evidence behind every pattern.`, button1Text: 'See Plans', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true);
        return;
      }

      if (newYears !== props.seasonalYears) {
        props.SetSeasonalYears(newYears);
        props.SetLineChartYear(0);
        props.SetConsolidatedSeasonalData([]);

        // If selecting PE cycle years, advance startDate to the next matching cycle year
        // if (newYears === 'pe0' || newYears === 'pe1' || newYears === 'pe2' || newYears === 'pe3') {
        //   const bumped = bumpStartDateYearToPE(props.startDate, newYears);

        //   if (bumped !== props.startDate) {
        //     props.SetStartDate(bumped);
        //     const trend_chart_start_date = incrementDate(bumped, -trend_chart_left_gap_days);
        //     props.SetTrendChartStartDate(trend_chart_start_date);
        //     props.SetConsolidatedSeasonalData([]);
        //   }
        // }
      }
    }

    if (event.target.id === 'PEselection') {
      changeViewerCycle(event.target.value)
    }

    if (event.target.id === 'monthsAndQtrs') {

      if (loggedinUser === '0' || (wpUserLevels.length === 1 && wpUserLevels[0] === '1')) {
        props.SetDialogType('free-register') // stop non logged-in users from changing dates
        props.SetInfoBoxVisible(true);
        return; //user 0 cannot change months and qtrs
      }

      let retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity)
      if (retArray[0] === 'F') {
        props.SetDialogType('free-register')
        props.SetInfoBoxVisible(true);
        return;
      }

      props.SetMonthsAndQtrs(event.target.value)

      if (event.target.value !== "Months & Qtrs") {
        for (var i = 0; i < monthsAndQtrs.length; i++) { // find the numeric id for the selected pulldown 
          if (monthsAndQtrs[i]['label'] === event.target.value) {
            break;
          }
        }

        // console.log('event.target.value=', event.target.value, i)

        if (event.target.value === 'Buy & Hold') { // 9/27/2022 - set jan-dec when buy and hold 
          props.SetJanDecDateRange(true);
          props.SetConsolidatedSeasonalData([])
        }


        // get current year
        var d = new Date();
        var y = d.getFullYear();
        // get the date range selected
        var date0 = y + '-' + monthsAndQtrs[i]['range'][0]
        var date1;


        if (event.target.value === 'Today to Year End') {
          date0 = getTodayDate();

          date1 = date0.substring(0, 4) + '-12-31'; // last day of the current year
          let date = new Date(date1);
          let dayOfWeek = date.getDay();
          if (dayOfWeek === 6) date1 = date0.substring(0, 4) + '-12-30'; // when last day of the year falls on saturday - use previous friday as last day of the year
          if (dayOfWeek === 0) date1 = date0.substring(0, 4) + '-12-29'; // when last day of the year falls on sunday   - use previous friday as last day of the year

          console.log('date0,date1', date0, date1)
        }



        if (event.target.value === 'Year to Date') {
          date1 = getTodayDate();
        }


        // reverse the date range
        else if (event.target.value === 'Reverse Date Range') { // reverse the range; for ex. if range is october, reverse would be all year except october
          let current_date0 = props.startDate;
          let current_date1 = incrementDate(current_date0, props.daysOut - 1)


          // console.log('rrrrrrrrrrrrrrrrrre3', date0, date1)



          // let base_year = current_date0.substring(0, 4);
          let base_year = getTodayDate().substring(0, 4); //10/14/2023


          let reverse_date0 = incrementDate(current_date1, 1)

          // console.log('---------------------reverse started d0,days', current_date0, current_date1, props.daysOut)

          //decrement year

          while (reverse_date0.substring(0, 4) > base_year) { // date0 must be in the current year
            reverse_date0 = incrementyear(reverse_date0, -1);
          }

          let reverse_date1 = incrementDate(current_date0, -1) //decrement by 1 day

          // check if buy & hold is being reversed.  it cannot
          var is_buy_and_hold_being_reversed = false;


          if (current_date0.substring(current_date0.length - 5) === current_date1.substring(current_date1.length - 5))
            is_buy_and_hold_being_reversed = true;

          if (reverse_date1 < reverse_date0) reverse_date1 = incrementyear(reverse_date1, 1) //increament by 1 year

          // console.log('reverse_date0 and reverse date1 = ', reverse_date0, reverse_date1)

          date0 = reverse_date0;
          date1 = reverse_date1;
          props.SetMonthsAndQtrs('Months & Qtrs')

        }
        else {
          date1 = y + '-' + monthsAndQtrs[i]['range'][1] // if winter increment year

        }

        if ((Date.parse(date1) > Date.parse(date0)) === false) { // date1 year need to be incremented by 1
          y++; // increment because winter date1 is one year later
          date1 = y + '-' + monthsAndQtrs[i]['range'][1]
        }

        var daysOut = Math.floor((Date.parse(date1) - Date.parse(date0)) / 86400000) + 1;  // cosmetic increment by 1 - 9/4/2022

        // console.log('................................reverse date0, date1,daysOut,', date0, date1, daysOut)



        if (is_buy_and_hold_being_reversed === true) { // bad way of stopping reversing of buy and hold - didn't want to deal with some of the messy conditions - it was working


          let content = `Buy & Hold Date Range cannot be reversed.  To reverse a Date Range, the length has to be less than 1 year.`
          props.SetDialogType('info-box');
          props.SetDialogProp({ title: 'Reverse Date Range Error', contentText: content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          props.SetInfoBoxVisible(true);


        }
        else {


          if (date0 !== props.startDate) { // if this if statement is not there if date0 is the same as props.startDate, the trend chart disappears 10/25/2023

            let new_trend_chart_start_date = incrementDate(date0, -trend_chart_left_gap_days) // this is the new date0 for the trend chart 
            props.SetTrendChartStartDate(new_trend_chart_start_date)
            props.SetStartDate(date0)
            props.SetConsolidatedSeasonalData([])

            props.SetJanDecDateRange(false);  // 5/9/2025 - removing Jan Dec to make sure we can see all of the range

          }

          props.SetDaysOut(daysOut)

        }


      }

    }

    props.SetRowIndexClicked(-1); //remove the selection on opp table

  }
  //-----------------------------------------------------------------------------------------------------------
  const barClickStateRef = useRef({ props, rdd, browserH, browserW })
  barClickStateRef.current = { props, rdd, browserH, browserW }
  const barClicked = useCallback((year) => {
    const current = barClickStateRef.current
    current.props.SetLineChartYear(year)

    if (current.rdd.isMobile) {
      if (current.browserH > current.browserW) {// portrait
        current.props.chartTo(1)
      }
      else { //landscape - only for landscape smartphones
        if (!current.rdd.isTablet) current.props.chartTo(2)
        else current.props.chartTo(2) // added for landscape tablet when it points back to desktop view
      }
    }
    else {
      current.props.chartTo(2)
    }
  }, [])

  //---------------------------------------
  // dynamic styles for mobile
  //---------------------------------------
  let barchartHeight = "92%"
  let barchartControlsHeight = '8%'
  var navArrowSize = 30

  if (rdd.isMobile) {
    if (rdd.isTablet) {
      if (browserH > browserW) {
        barchartHeight = "88%"
        barchartControlsHeight = '12%'
      }
    }
    else {
      barchartHeight = "88%"
      barchartControlsHeight = '12%'
    }
  }

  //-----------------------------------------------------------------------------------------------------------
  const barchartStyle = {
    height: barchartHeight,
    backgroundColor: UIcolors(loggedinUser, props.UITheme)['background_barchart'],
    borderLeft: '1px solid ' + tc.border
  }
  //-----------------------------------------------------------------------------------------------------------
  const barchartControlsStyle = {
    height: barchartControlsHeight,
    display: "flex",
    alignItems: "center",
    backgroundColor: tc.controlBar,
    // fontFamily:'san-serif'
    // justifyContent: "space-between",
    // marginRight: "5px"
  }

  //-----------------------------------------------------------------------------------------------------------
  //---------------------------------------
  var textsize = "12px";
  var displayElement = new Array(16)
  var questionSize = 15;
  var questionDivWidth = '3%';
  // scale placeholder font relative to actual right-panel width so it never wraps
  // right panel = (100 - leftNavWidthPct)% of viewport; 6vw at default 70% ≈ 8.57% of right panel
  var svFont = !rdd.isMobile && props.leftNavWidthPct != null
    ? `${((100 - props.leftNavWidthPct) * 0.0857).toFixed(2)}vw`
    : '6.0vw';
  var svIconSize = '20';
  var LSsquareSize = "14px"; // this is size of the long short square added on 8/31/2022
  var barchartControlDateWidth = '10';  // added to fix tablet portrait issue 8/31/2022
  var barchartControlTickerWidth = '5'; // added to fix tablet portrait issue 8/31/2022
  var SVDIVwidth = '7%';
  var ticker_description = props.company;


  var icon_size_plus = 33;


  for (var i = 0; i <= 16; i++)displayElement[i] = "flex";
  displayElement[12] = "none";
  displayElement[14] = "none";
  // displayElement[15] = "none"; // this is for PEselection box

  if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { // smartphone portrait
    for (var ii = 7; ii <= 11; ii++)displayElement[ii] = "none"; //remove display of text and select/options in this mode
    textsize = "2.8vw";
    // displayElement[1] = "none"; // remove the right left nav arrow from top bar for now
    displayElement[12] = "flex"  //this is smartphone portrait 2nd layer control
    displayElement[13] = "flex"; // this is question mark help on mobile portrait
    displayElement[14] = "flex"; // this is for seasonal chart icon for mobile portrait
    displayElement[2] = "none";
    displayElement[0] = "none"; // removed the left arrow to home
    displayElement[15] = "none"; // removed PEselection selectbox from main mobile bar
    navArrowSize = 30
    questionDivWidth = '9%';
    svFont = '8vw';
  }
  else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { //smartphone landscape
    displayElement[13] = "flex"; //question mark
    displayElement[3] = "none";
    displayElement[1] = "flex"; // remove the right left nav arrow from top bar for now
    displayElement[2] = "none";
    questionDivWidth = '5%';
    displayElement[14] = "flex"; // this is for seasonal chart icon for mobile portrait
  }
  else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { // tablet portrait
    displayElement[3] = "flex";
    SVDIVwidth = '6%';

    barchartControlDateWidth = "8";   // this is for text box 8/31/2022
    barchartControlTickerWidth = "4"; // this is for text box 8/31/2022
    displayElement[14] = "flex"; // seasonal chart icon for mobile portrait both tablet and smartphones
    svIconSize = '28';
    // displayElement[1] = "none"; // remove the right left nav arrow from top bar for now
    displayElement[2] = "none";  // right single arrow
    if (browserH > 1024) {   //ipad pro
      navArrowSize = 50
      questionSize = 30;
      svIconSize = '40';
      LSsquareSize = '20px';
      icon_size_plus = 40;
    }
    else {
      navArrowSize = 40;
      questionSize = 22;
      icon_size_plus = 30;
    }

    questionDivWidth = '5%';
  }
  else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { //tablet landscape
    displayElement[3] = "flex";

    displayElement[1] = displayElement[2] = "none";

    icon_size_plus = 27;

    if (browserW > 1024) {   //ipad pro
      questionSize = 20;
      questionDivWidth = '5%';
    }
    else {
      questionSize = 16;
      questionDivWidth = '5%';
    }
  }
  else if (!rdd.isMobile) {
    displayElement[1] = "flex";                                  // desktop
    displayElement[2] = "none"; // don't need nav arrows in desktops
    displayElement[8] = "none"; // hide the toolbar ticker box on desktop - it now lives inline in the description line (StyleSymbol)

    if (ticker_description != null && ticker_description.length > 40) {
      if (rdd.isMacOs) {
        let trunc_chars = 35;
        if (rdd.isSafari) trunc_chars = 32;
        ticker_description = ticker_description.substring(0, trunc_chars) + '..'; // only show the first 40 characters of description
      }
    }
  }

  //-----------------------------------------------------------------------------------------------------------
  const longShortSquare = {
    width: LSsquareSize,
    height: LSsquareSize,
    backgroundColor: props.barChartLongOrShort === 'long' ? 'green' : 'red',
    marginRight: "5px",

    // display:"flex"
  }
  //-----------------------------------------------------------------------------------------------------------

  const StyleNavDiv = {
    // backgroundColor: "red",
    display: displayElement[0],
    alignItems: "center",
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleBackArrow = {
    // backgroundColor: "red",
    // display:"none"
    // marginRight: "7px",
    // width: "20px",
    height: "100%",
    display: displayElement[1],
    // flexDirection: 'column',
    // justifyContent:'center',
    alignItems: 'center'

  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleForwardArrow = {
    // backgroundColor: "rgba(0,152,0,0.8",
    height: "100%",
    display: displayElement[2],
    // alignItems: "center"
    marginLeft: "39%"
  }
  //-----------------------------------------------------------------------------------------------------------
  // scale description font relative to right-panel width so it shrinks as panel narrows
  const descFontSize = !rdd.isMobile && props.leftNavWidthPct != null
    ? `${((100 - props.leftNavWidthPct) * 0.0107).toFixed(3)}vw`
    : rdd.isMobile && !rdd.isTablet ? '3.2vw' : '1.5vw';
  const StyleDescription = {
    // backgroundColor: "pink",
    fontSize: descFontSize,
    color: tc.textOnControl,
    // When the Best Waves select is rendered, IT takes the row's slack (flex:1, centered)
    // so it sits midway between the Remind me pill and the ticker; the description then only
    // wraps its content. With no select (no symbol/options), grow as before so the
    // ticker+dates stay right-anchored next to the MFE/MAE controls.
    flexGrow: (!rdd.isMobile && oppBySymbolOptions.length > 0) ? "0" : "2",
    justifyContent: "end",
    display: displayElement[3],
    whiteSpace: 'nowrap',
    overflow: 'visible',  // was 'hidden'; visible so the inline ticker box's watchlist dropdown isn't clipped
    textOverflow: 'ellipsis',
    minWidth: 0,
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleLSSquare = {
    // backgroundColor: "rgba(102,52,250,0.8",
    display: "flex",
    alignItems: "center",

    display: displayElement[4],
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleMFE = {
    // backgroundColor: "rgba(152,152,0,0.8",
    display: displayElement[5],
    fontSize: globalTextSize,
    alignItems: "center",
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleMAE = {
    // backgroundColor: "rgba(100,200,0,0.8",
    display: displayElement[6],
    fontSize: globalTextSize,
    alignItems: "center",
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleStartDate = {
    // backgroundColor: "rgba(0,0,0,0.8",
    display: displayElement[7],
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleSymbol = {
    // backgroundColor: "rgba(0,0,252,0.8",
    display: displayElement[8],
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleDaysOut = {
    // backgroundColor: "rgba(252,0,252,0.8",
    display: displayElement[9],
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleSeasonalYears = {
    // backgroundColor: "rgba(125,125,125,0.8",
    display: displayElement[10],
  }
  //-----------------------------------------------------------------------------------------------------------
  const StyleMQtrs = {
    // backgroundColor: "rgba(152,252,152,0.8",
    display: displayElement[11],
  }
  //---------------------------------------
  const StylePEselection = {
    display: displayElement[15],
  }
  //---------------------------------------

  const handleForwardClick = () => {
    // props.SetLineChartYear('2020')
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
      props.chartTo(1)
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
      props.chartTo(2)
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) {
      props.chartTo(1)
    }
    // console.log('here I am')
  }
  //-----------------------------------------------------------------------------------------------------------
  const handleBackClick = () => {
    if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
      props.chartTo(0)
    }
    else if (rdd.isMobile && browserH > browserW) {
      redirectBackFromSeasonals();
    }
  }
  //-----------------------------------------------------------------------------------------------------------
  const handleLayer2Visible = () => {

    if (secondLayerControlsOpen) {
      // displayElement[13] = 'none';
      SetSecondLayerDisplay('none')
      SetSecondLayerControlsOpen(false)
    }
    else {
      // displayElement[13] = 'flex';
      SetSecondLayerDisplay('flex')
      SetSecondLayerControlsOpen(true)
    }
  }

  const handleHelpClicked = () => {
    // props.SetHelpBoxVisible(!props.helpBoxVisible);  remove the old help 9/14/2022

    // new help 9/14/2022
    // props.SetDialogType('quick-help');
    // props.SetInfoBoxVisible(true); 
    props.SetVideosBoxVisible(true)

    console.log('question clicked')

  }

  const handleExport = () => {
    props.SetShowWatermark(true);
    props.SetExportImage(true)
  }

  // this is triggered when trend chart icon is clciked on mobile portrait
  const handleSCclicked = () => {
    if (browserH > browserW) props.chartTo(4);
    else props.chartTo(5);
  }





  //-------------------------------------------------------------------------------------------------------------------------------------
  const handleOppBySymbolChanged = (event) => {
    const val = event.target.value
    if (!val) return
    setSelectedOppBySymbol(val)
    const parts = val.split('|')
    const date = parts[0]
    const daysOut = parseInt(parts[1])
    props.SetStartDate(date)
    props.SetDaysOut(daysOut)
    props.SetMonthsAndQtrs('Months & Qtrs')
    const trend_chart_start_date = incrementDate(date, -trend_chart_left_gap_days)
    props.SetTrendChartStartDate(trend_chart_start_date)
    props.SetConsolidatedSeasonalData([])
    props.SetRowIndexClicked(-1)
  }

  //-------------------------------------------------------------------------------------------------------------------------------------
  // new report added by clicking the plus in reports dashboard dialog
  // THIS FUNCTION IS DUPLICATED IN REPORTS DASHBAROD DUE TO ISSUES WITH PROPS SCOPE - CHANGES ARE REQUIRED IN BOTH PLACES
  //------------------------------------------------------------------------------------------------------------------------------------- 
  //-------------------------------------------------------------------------------
  // ONE-CLICK REMIND-ME BELL (2026-07-04; stateful pill + current-portfolio rework
  // 2026-07-08, renamed from "Notify me"). One click saves the pattern to the
  // CURRENT portfolio (the same destination as the Plus icon; '&' autotrade
  // portfolios fall back to 'main'), then opens the Google consent popup and
  // inserts both start/end events with the user's saved dialog defaults.
  // The pill is STATEFUL: dr_report_exists reports whether this exact pattern
  // (symbol+date+days+years) is saved in ANY portfolio and whether Google events
  // were actually created for it (gc_events, stamped on successful insert).
  // saved+events -> "✓ Reminder set", click manages/re-creates; saved without
  // events (Plus-icon save, abandoned popup) -> click adds events WITHOUT
  // re-saving; unsaved -> save + events. Never re-publish a saved pattern: the
  // server dedup is portfolio-scoped, so a re-publish from another portfolio
  // would duplicate the record AND burn lifetime quota.
  // Popup-blocker note: the publish call before requestAccessToken stays inside
  // the ~5s transient-activation window, so the popup is allowed; the Retry /
  // Re-create dialog buttons provide a fresh gesture if it ever isn't.
  //-------------------------------------------------------------------------------
  const [notifyBusy, SetNotifyBusy] = useState(false)
  // One-time attention pulse until the first click (same pattern as the symbol box).
  const [notifyPulse, SetNotifyPulse] = useState(() => {
    try { return !window.localStorage.getItem('tw_notifybell_seen') } catch (e) { return false }
  })
  // null = unknown (logged out / check pending or failed); else { key, saved:false }
  // or { key, saved:true, gcEvents, portfolio, slug, publishDate }. key = the
  // pattern identity the info belongs to (guards slow-async updates).
  const [reminderInfo, SetReminderInfo] = useState(null)
  const reminderReqRef = useRef(0)
  // Preload the GIS script so the click path doesn't spend its popup window on it.
  useEffect(() => { loadGsiScript().catch(() => { }) }, [])

  // The years string as saved with the pattern (PE mode encodes as e.g. "pe2-10").
  const patternYearsStr = () => props.PEselected != 'cons' ? `${props.PEselected}-${props.seasonalYears}` : `${props.seasonalYears}`
  // The saved-record identity of the loaded pattern (mirrors the appserver's
  // check_for_duplicates fields minus portfolio). key is used to guard async
  // state updates against the pattern changing mid-flight (OAuth popups are slow).
  const patternIdentity = () => ({
    key: `${props.symbol}|${props.startDate}|${props.daysOut}|${patternYearsStr()}`,
    symbol: props.symbol, date: props.startDate, days_hold: props.daysOut, years: patternYearsStr(),
  })

  const fetchReminderInfo = () => {
    const idn = patternIdentity()
    return twFetch(`${appserverURL()}/dr_report_exists/${idn.symbol}/${idn.date}/${idn.days_hold}/${idn.years}?token=${token}`)
      .then((r) => r.json())
      .then((d) => d['dr_report_exists']
        ? { key: idn.key, saved: true, gcEvents: !!d['gc_events'], portfolio: d['portfolio_name'], drId: d['dr_id'], slug: d['slug'] || '', publishDate: d['publishDate'] || null }
        : { key: idn.key, saved: false })
  }

  // Keep the pill state in sync with the loaded pattern. numReportsCreated is a
  // dep on purpose: every save/delete path in the app mutates it (Plus icon,
  // Portfolio Manager delete, populate/autotrade add+remove), so it doubles as a
  // portfolio-changed signal without new plumbing. reqRef guards out-of-order
  // responses when the identity props change quickly.
  useEffect(() => {
    if (!token || token.length === 0 || loggedinUser === '0' || !props.symbol || !props.startDate) {
      SetReminderInfo(null)
      return
    }
    const reqId = ++reminderReqRef.current
    fetchReminderInfo()
      .then((info) => { if (reqId === reminderReqRef.current) SetReminderInfo(info) })
      .catch(() => { if (reqId === reminderReqRef.current) SetReminderInfo(null) })
    // addGCVisible: re-check when the Portfolio Manager's calendar dialog closes -
    // it may have just created (and stamped) events for the loaded pattern.
  }, [props.symbol, props.startDate, props.daysOut, props.seasonalYears, props.PEselected, props.numReportsCreated, props.addGCVisible, token, loggedinUser])

  const showInfoDialog = (dialogProp) => {
    props.SetDialogProp(dialogProp)
    props.SetDialogType('info-box');
    props.SetInfoBoxVisible(true)
  }

  // Token + insert phase; called from the click flow and re-callable from the
  // Retry / Re-create dialog buttons (each dialog click is a fresh gesture).
  // markIdentity: on a fully successful insert, stamp gc_events_created on the
  // saved record (fire-and-forget) and flip the pill to "Reminder set" - but only
  // if the viewer still shows the same pattern (key guard: the OAuth popup is slow
  // and the user may have moved on).
  const startCalendarTokenFlow = (eventDicts, savedNote, markIdentity, accessTokenPromise = null) => {
    // When supplied, this promise was started directly inside the bell's click
    // handler. That preserves the browser's trusted user gesture on mobile while
    // the portfolio lookup/save requests continue in parallel.
    const accessPromise = accessTokenPromise || requestCalendarAccessToken()
    const accessTimeout = new Promise((resolve, reject) => {
      setTimeout(() => reject(new Error('Google sign-in did not open or complete within 30 seconds')), 30000)
    })
    Promise.race([accessPromise, accessTimeout])
      .then((accessToken) => insertCalendarEvents(accessToken, eventDicts))
      .then((results) => {
        const errors = results.filter((r) => r && r.hasOwnProperty('error')).map((r) => r['error']['message'])
        if (errors.length) {
          showInfoDialog({ title: 'Google Calendar Events', contentText: 'Error: ' + errors.join(' / '), button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        } else {
          if (markIdentity) {
            twFetch(`${appserverURL()}/dr_report_mark_gc_events/${markIdentity.symbol}/${markIdentity.date}/${markIdentity.days_hold}/${markIdentity.years}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => { })
            SetReminderInfo((prev) => prev && prev.saved && prev.key === markIdentity.key ? { ...prev, gcEvents: true } : prev)
          }
          showInfoDialog({ title: 'Reminders Added', contentText: `Start and end reminders for ${props.symbol} were added to your Google Calendar${savedNote}. To customize the event time or reminder types, open the Portfolio Manager (clipboard-with-pencil icon) and click the calendar icon on the pattern.`, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        }
      })
      .catch((err) => {
        showInfoDialog({
          title: 'Google Sign-in Needed',
          contentText: `Your pattern is saved, but the Google Calendar events were not created (${err.message}). Click Retry to open the Google sign-in again - and make sure popups are allowed for this site.`,
          button1Text: 'Retry', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)',
          onButton1: () => startCalendarTokenFlow(eventDicts, savedNote, markIdentity),
        })
      })
  }

  // Build both event dicts from what the viewer already knows (tradeDetailData
  // IS the ChartData4 stats dict - no extra fetch needed). slug/publishDate come
  // from the publish response (fresh save) or dr_report_exists (already saved).
  const buildNotifyEventDicts = (id, slug, publishDate) => {
    const date = props.startDate
    const date2 = incrementDate(date, parseInt(props.daysOut, 10) - 1)
    const p = {
      rid: id,
      ticker: props.symbol,
      direction: props.tradeDetailData['Trade Dir'],
      date1: date,
      date2: date2,
      days: props.daysOut,
      years: patternYearsStr(),
      resource_group: props.selectedSecurity,
      slug: slug,
      sharpe_ratio: props.tradeDetailData['Sharpe Ratio'],
      publishDate: publishDate,
      stats: props.tradeDetailData,
      eventTime: getCookie('event_time') || '8:00AM',
      emailReminder: getCookie('email_reminder') !== 'false',
      popupReminder: getCookie('popup_reminder') !== 'false',
      reminderDate1: shiftWeekendToNextMonday(date),
      reminderDate2: shiftWeekendToNextMonday(date2),
    }
    return [buildPatternEventDict('start', p), buildPatternEventDict('end', p)]
  }

  // "Edit reminder settings" -> open the SAME AddGC calendar dialog the
  // Portfolio Manager's calendar icon opens, pre-filled for this pattern.
  // Dims reproduce the manager path exactly (its dialog dims / 1.14, centered -
  // ReportsDashboard.js:130,934-937) so the dialog looks identical from both
  // doors. forceGC routes the layout gates to AddGC even when an '&' autotrade
  // portfolio happens to be the current selection (the gate normally keys off
  // selectedPortfolio, which is unrelated to the pattern's portfolio here).
  const addGCDialogDims = () => {
    let W = 60, H = 57, T = 25, L = 20
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { W = 100; H = 88; T = 12; L = 0 }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { W = 100; H = 100; T = 20; L = 0 }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { W = 90; H = 70; T = 15; L = 5 }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { W = 70; H = 50; T = 25; L = 15 }
    const f = 1.14
    return { 'DialogW': W / f + '%', 'DialogH': H / f + '%', 'DialogT': (T + (H - H / f) / 2) + '%', 'DialogL': (L + (W - W / f) / 2) + '%' }
  }

  const openEditReminderDialog = (info, id) => {
    const date2 = incrementDate(props.startDate, parseInt(props.daysOut, 10) - 1)
    props.SetGoogleCalendarDict({
      ...addGCDialogDims(),
      'forceGC': true,
      'dr_id': info.drId,
      'rid': id,
      'resource_group': props.selectedSecurity,
      'date1': props.startDate,
      'date2': date2,
      'years': patternYearsStr(),
      'ticker': props.symbol,
      'days': props.daysOut,
      'direction': props.tradeDetailData['Trade Dir'],
      'slug': info.slug,
      'sharpe_ratio': props.tradeDetailData['Sharpe Ratio'],
      'publishDate': info.publishDate,
      'order_id_list': [],
    })
    props.SetInfoBoxVisible(false)
    props.SetAddGCVisible(true)
  }

  // Reminder already created for this pattern -> show the reminder's DETAILS
  // as a designed layout, not prose (owner feedback 2026-07-08): header =
  // symbol + direction chip + window, two side-by-side date cards (start/end
  // reminder), then the portfolio meta line and an Edit LINK that opens the
  // AddGC calendar dialog directly. InfoPopup's info-box renders contentText
  // bare inside a centered flex column, so it accepts a JSX element; em font
  // sizes ride the dialog's per-device contentFontSize. Dates/time come from
  // the same sources a Re-create would use, so whatever the user does from
  // this dialog matches what it shows.
  const showRemindersAlreadySetDialog = (info, id) => {
    const eventDicts = buildNotifyEventDicts(id, info.slug, info.publishDate)
    const date2 = incrementDate(props.startDate, parseInt(props.daysOut, 10) - 1)
    const rd1 = shiftWeekendToNextMonday(props.startDate)
    const rd2 = shiftWeekendToNextMonday(date2)
    const eventTime = getCookie('event_time') || '8:00AM'
    const isShort = String(props.tradeDetailData['Trade Dir']).toLowerCase().startsWith('s')
    const dirColor = isShort ? tc.barRed : tc.barGreen

    const reminderCard = (label, actualIso, reminderIso) => (
      <div style={{ flex: '1 1 0', minWidth: '110px', maxWidth: '220px', backgroundColor: tc.statValueBg, border: '1px solid ' + tc.border, borderRadius: '8px', padding: '10px 14px', textAlign: 'center' }}>
        <div style={{ fontSize: '0.6em', letterSpacing: '1.5px', color: tc.textSecondary, marginBottom: '5px' }}>{label}</div>
        <div style={{ fontSize: '1.05em', fontWeight: 600 }}>{friendlyDate(reminderIso)}</div>
        <div style={{ fontSize: '0.8em', color: tc.textSecondary, marginTop: '3px' }}>{eventTime}</div>
        {actualIso !== reminderIso &&
          <div style={{ fontSize: '0.6em', color: tc.textSecondary, fontStyle: 'italic', marginTop: '3px' }}>moved off the weekend</div>}
      </div>
    )

    showInfoDialog({
      title: 'Reminder Set',
      contentText: (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', width: '100%' }}>
          <div>
            <span style={{ fontSize: '1.2em', fontWeight: 700 }}>{props.symbol}</span>
            <span style={{ marginLeft: '9px', padding: '2px 10px', borderRadius: '999px', border: '1px solid ' + dirColor, color: dirColor, fontSize: '0.65em', fontWeight: 600, letterSpacing: '1px', verticalAlign: '3px' }}>{isShort ? 'SHORT' : 'LONG'}</span>
          </div>
          <div style={{ fontSize: '0.8em', color: tc.textSecondary, marginTop: '-8px' }}>{friendlyDate(props.startDate)} – {friendlyDate(date2)} · {props.daysOut} days</div>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center', width: '90%' }}>
            {reminderCard('START REMINDER', props.startDate, rd1)}
            {reminderCard('END REMINDER', date2, rd2)}
          </div>
          <div style={{ fontSize: '0.8em' }}>Saved in your "{info.portfolio}" portfolio</div>
          <div style={{ fontSize: '0.8em' }}>
            <span onClick={() => openEditReminderDialog(info, id)} style={{ color: '#7C5CFF', textDecoration: 'underline', cursor: 'pointer', fontWeight: 600 }}>Edit reminder settings</span>
          </div>
        </div>
      ),
      button1Text: 'Re-create', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)',
      onButton1: () => startCalendarTokenFlow(eventDicts, '', patternIdentity()),
    })
  }

  const handleNotifyClicked = async () => {
    if (loggedinUser === '0') {
      showInfoDialog({ title: 'Portfolio Manager', contentText: opp_dashboard_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      return
    }
    if (notifyBusy) return
    if (notifyPulse) {
      SetNotifyPulse(false)
      try { window.localStorage.setItem('tw_notifybell_seen', '1') } catch (e) { }
    }
    const id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
    if (id < 0) {
      showInfoDialog({ title: 'Reminder Unavailable', contentText: 'The current market could not be identified. Reload the Wave Viewer and try again.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
      return
    }

    // Google Calendar's popup must begin directly from the user's tap. Starting
    // it after fetchReminderInfo / dr_report_publish can lose transient user
    // activation (especially in Chrome on Android), leaving the bell apparently
    // inert. A known set reminder only opens its management dialog, so it does
    // not need a new token request.
    const calendarAccessPromise = reminderInfo?.saved && reminderInfo?.gcEvents
      ? null
      : requestCalendarAccessToken()
    // Attach a rejection handler immediately in case the user closes the popup
    // before the portfolio request finishes; startCalendarTokenFlow still owns
    // the user-facing error dialog below.
    if (calendarAccessPromise) calendarAccessPromise.catch(() => { })

    SetNotifyBusy(true)
    try {
      // Saved in ANY portfolio -> never re-save (a cross-portfolio re-publish would
      // duplicate the record and burn lifetime quota). Re-check inline when the
      // pill state is unknown (check failed or still in flight).
      let info = reminderInfo
      if (info === null) {
        try { info = await fetchReminderInfo(); SetReminderInfo(info) } catch (e) { info = { saved: false } }
      }
      if (info.saved && info.gcEvents) {
        // Reminders exist -> manage/re-create dialog, nothing to save.
        showRemindersAlreadySetDialog(info, id)
        return
      }
      if (info.saved) {
        // Saved (via the Plus icon, or a bell click whose Google popup was
        // abandoned) but no reminders yet -> skip the re-save, go straight to
        // calendar-event creation against the existing record.
        startCalendarTokenFlow(buildNotifyEventDicts(id, info.slug, info.publishDate), ` - the pattern was already saved in your "${info.portfolio}" portfolio`, patternIdentity(), calendarAccessPromise)
        return
      }

      const symbol = props.symbol
      const date = props.startDate
      const days_hold = props.daysOut
      const years = patternYearsStr()
      const direction = props.tradeDetailData['Trade Dir']
      const sharpe_ratio = props.tradeDetailData['Sharpe Ratio']
      const asURL = appserverURL()

      // Save to the CURRENT portfolio - the same destination as the Plus icon, so
      // the toolbar has one mental model. '&'-prefixed autotrade portfolios hold
      // trade instruments, not patterns -> fall back to 'main'.
      let portfolio = props.selectedPortfolio
      if (!portfolio || portfolio[0] === '&') portfolio = 'main'

      const data = await twFetch(`${asURL}/dr_report_publish/${id}/${symbol}/${date}/${days_hold}/${years}/${direction}/${sharpe_ratio}/${portfolio}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then((r) => r.json())

      if (data['publish_dr_report'] !== 'success') {
        if (data['publish_dr_report'] === 'daily_limit_reached') {
          showInfoDialog({ title: 'Daily Limit Reached', contentText: `Your daily limit of ${data['limit']} opportunities per day has been reached. You can add new opportunities after midnight eastern timezone, or upgrade your subscription to increase the limit.`, button1Text: 'Subscriptions', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        } else if (data['publish_dr_report'] === 'total_limit_reached') {
          showInfoDialog({ title: 'Opportunities Limit Reached', contentText: `You have reached the maximum number of tracked opportunities (${data['limit']}) for your current plan. Remove an existing one, or upgrade your subscription to track more.`, button1Text: 'Subscriptions', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        } else {
          showInfoDialog({ title: 'Google Calendar Events', contentText: 'Could not save the pattern (' + String(data['publish_dr_report']) + '). Please try again.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        }
        return
      }

      const slug = String(data['report_url'] || '').split('/r/')[1] ? String(data['report_url']).split('/r/')[1].replace(/\/+$/, '') : ''

      if (data['refreshed']) {
        // Safety net: the exists check said unsaved but the server found the pattern
        // already in this portfolio (race with another tab). Reminders may or may
        // not exist - offer creation without re-saving, like the saved branch above.
        const inf = { key: patternIdentity().key, saved: true, gcEvents: false, portfolio: portfolio, slug: slug, publishDate: null }
        SetReminderInfo(inf)
        startCalendarTokenFlow(buildNotifyEventDicts(id, slug, null), ` - the pattern was already saved in your "${portfolio}" portfolio`, patternIdentity(), calendarAccessPromise)
        return
      }

      props.SetNumReportsCreated(props.numReportsCreated + 1)
      SetReminderInfo({ key: patternIdentity().key, saved: true, gcEvents: false, portfolio: portfolio, slug: slug, publishDate: null })
      startCalendarTokenFlow(buildNotifyEventDicts(id, slug, null), ` and the pattern was saved to your "${portfolio}" portfolio`, patternIdentity(), calendarAccessPromise)
    } catch (err) {
      showInfoDialog({ title: 'Reminder Error', contentText: `The reminder could not be completed (${err.message || 'unknown error'}). Please try again.`, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
    } finally {
      SetNotifyBusy(false)
    }
  }

  const handleAddReport = () => {
    // new opportunity added to the portfolio by clicking the plus in reports dashboard dialog
    // check if this report can be added based on how many reports are allowed for this user and how many have already been created
    // numReportsAllowed is already determined from login - returned by useContext

    // console.log('handleAddReport clicked')


    if (loggedinUser === '0') {
      props.SetDialogType('info-box');
      // props.SetDialogProp({ title: 'Opportunities Dashboard', contentText: 'With Opportunities Dashboard users can save and create Date-Range Web Reports.  This feature is available to Loggedin-Users.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      props.SetDialogProp({ title: 'Portfolio Manager', contentText: opp_dashboard_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      props.SetInfoBoxVisible(true);
    }
    else {
      // console.log('if logoed in user is not 0')
      if (props.numReportsCreated >= props.numReportsAllowed) {
        // this user cannot create any more reports unless they delete some first
        // let content = `you have reached the maximum number of reports allowed (${props.numReportsAllowed}). To create a new Date-Range-Report, you need to delete an existing report. You can manage your existing reports with Opportunities Manager, which can be accessed by clicking below or by the clipboard with a pencil icon.`
        let content = `You have reached the maximum number of tracked opportunities allowed for your current subscription level.  Your subscription allows for ${props.numReportsAllowed} opportunities to be saved. To track additional opportunities in your portfolio, consider upgrading your subscription.`

        // console.log(props.numReportsCreated, props.numReportsAllowed)

        if (props.numReportsCreated >= props.numReportsAllowed) {
          content = `You have exceeded the maximum number of tracked opportunities allowed for your current subscription level.  Your subscription allows for ${props.numReportsAllowed} opportunities to be saved while you have ${props.numReportsCreated} opportunities in your portfolios. Please remove some of the tracked opportunities to match the allowed opportunities for your subscription level. To track additional opportunities in your portfolio, consider upgrading your subscription.`
        }
        props.SetDialogType('info-box');
        props.SetDialogProp({ title: 'Opportunities Limit Reached', contentText: content, button1Text: 'Subscriptions', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        props.SetInfoBoxVisible(true);
      }

      else {
        // console.log('begin calling dr_report_publish')


        let id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)

        if (id >= 0) {

          let symbol = props.symbol
          let date = props.startDate
          let days_hold = props.daysOut;
          let years = props.seasonalYears;
          if (props.PEselected != 'cons') { // if its custom year then format lookos like pe2-10
            years = `${props.PEselected}-${props.seasonalYears}`;
          }
          let direction = props.tradeDetailData['Trade Dir']
          let sharpe_ratio = props.tradeDetailData['Sharpe Ratio']
          let selected_portfolio = props.selectedPortfolio;

          let cumulative_return = props.tradeDetailData['Cumulative Return'] // have not passed added this yet 

          // console.log('............... length of reportslist = ', props.reprotsList.length)

          let asURL = appserverURL()
          let url = `${asURL}/dr_report_publish/${id}/${symbol}/${date}/${days_hold}/${years}/${direction}/${sharpe_ratio}/${selected_portfolio}?token=${token}`

          // console.log('add report url in seasonalbarchart',url)

          twFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
              // console.log('response=',response)
              if (!response.ok) {
                throw new Error(response.status); // throw an error if the response status is not OK
              }
              return response.json();
            })
            .then((data) => {

              // console.log('--------add report returned ---', props.numReportsAllowed, props.numReportsCreated)

              if (data['publish_dr_report'] === 'success' && data['refreshed']) {
                // Idempotent-refresh response (2026-07-04): the pattern was already in
                // this portfolio - the server re-rendered its report instead of
                // duplicating. Don't increment the count.
                props.SetDialogProp({ title: 'delay', contentText: 'Already in your portfolio - report refreshed', button1Text: '', button2Text: '', coverDivColor: 'rgba(0,0,0,0.4)' })
              }
              else if (data['publish_dr_report'] === 'success') {
                props.SetNumReportsCreated(props.numReportsCreated + 1) // increment the number of reports created
                let contentText = `Opportunity Added - ${(props.numReportsAllowed - props.numReportsCreated - 1)} Remaining`;
                props.SetDialogProp({ title: 'delay', contentText: contentText, button1Text: '', button2Text: '', coverDivColor: 'rgba(0,0,0,0.4)' })
              }
              else if (data['publish_dr_report'] === 'duplicate') { // pre-2026-07 server response, kept for safety
                props.SetDialogProp({ title: 'delay', contentText: 'Already in your portfolio (duplicate)', button1Text: '', button2Text: '', coverDivColor: 'rgba(0,0,0,0.4)' })
              }
              else if (data['publish_dr_report'] === 'daily_limit_reached') {
                let limit = data['limit'];
                let daily_limit_content = `Your daily limit of ${limit} opportunities per day has been reached.  
              You can add new opportunities to your portfolio after midnight eastern timezone.
              To increase your daily limit, please consider upgrading your subscription.
              `
                props.SetDialogProp({ title: 'Daily Limit Reached', contentText: daily_limit_content, button1Text: 'Subscriptions', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
              }
              else if (data['publish_dr_report'] === 'total_limit_reached') {
                let limit = data['limit'];
                let total_limit_content = `You have reached the maximum number of tracked opportunities (${limit}) for your current plan. Remove an existing one, or upgrade your subscription to track more.`
                props.SetDialogProp({ title: 'Opportunities Limit Reached', contentText: total_limit_content, button1Text: 'Subscriptions', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
              }
              else { // should not happen
                props.SetDialogProp({ title: 'delay', contentText: 'should not happen', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
              }
              // console.log('before calling info-box')
              props.SetDialogType('info-box');
              props.SetInfoBoxVisible(true)
            })
            .catch((error) => {
              if (error.message === '404') {
                console.log('Resource not found'); // handle a 404 error response
              } else {
                console.log('Error:', error.message); // handle any other error response
              }
            });

          props.SetReportsList([])
        }
        else {
          console.log('market id returned = -1 should not happen: props.securityTypeList, props.selectedSecurity=', props.securityTypeList, props.selectedSecurity)
        }




      }



    }
  }
  //-------------------------------------------------------------------------------------------------------------------------------------





  // Right-panel width in px (the split-aware version of window.innerWidth) - drives the
  // Remind me pill's icon-only collapse.
  const rightPanelPx = window.innerWidth * (props.leftNavWidthPct != null ? (100 - props.leftNavWidthPct) / 100 : 1)
  // "Reminder set" = Google Calendar events actually exist for this pattern (a save
  // via the Plus icon alone does NOT flip it - gc_events is stamped only on insert).
  const reminderSet = !!(reminderInfo?.saved && reminderInfo?.gcEvents)
  // Best Waves keeps its "── Best Waves ──" decoration until the wide box, centered in the
  // measured slack, would have under 3px of air per side - only then drop to the compact
  // undecorated variant (owner-specified threshold). 0.07 = the 7vw wide-variant width.
  const bwWide = bwSlackPx >= window.innerWidth * 0.07 + 6

  //--------------------------------------------------------------------------------
  return (

    <div className="seasonal-barchart-container" style={{ backgroundColor: tc.panelBg }}>

      {/* _______________________________________________container_________________________________________________________ */}

      <div className="barchart-controls" style={barchartControlsStyle} >

        <div className="barchart-controls-div" style={StyleNavDiv} >

          <div style={StyleForwardArrow}>
            <button className="nav-buttons">
              <FaAngleRight size={30} style={{ fill: "white" }} onClick={handleForwardClick} />
            </button>
          </div>

          {/* <BiExport size={20} style={{ fill: "white" }} onClick={handleExport} /> */}

        </div>

        {
          props.seasonalBarChartData.length > 0 &&

          <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
            <div theme="tw" >
              {props.tooltipSW ? 'Click the Plus icon to save the Date-Range-Opportunity to your portfolio.  All saved opportunities also generate a comprehensive Web Report that can be viewed and shared.  Your portfolio can be accessed by Clicking the Opportunities Manager icon, that looks like a clipboard with a pencil' : ''}
            </div>
          }>
            <div style={{ backgroundColor: 'transparent' }}>
              <BsPlus size={icon_size_plus} style={{ fill: "white", backgroundColor: "transparent", verticalAlign: 'bottom' }} onClick={handleAddReport} />
            </div>

          </Tippy>

        }

        {/* One-click Remind me bell (stateful): filled purple "Remind me" pill until
            Google Calendar events actually exist for this pattern (saved via the
            Plus icon alone does NOT flip it - gc_events is stamped only on a
            successful insert); outline "✓ Reminder set" after. Desktop = labeled
            pill (icon-only below 1120px), mobile = compact icon (outline bell =
            unset, filled purple = set). First-visit pulse (localStorage-gated)
            makes it discoverable; suppressed once set. */}
        {props.seasonalBarChartData.length > 0 &&
          <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
            <div theme="tw" >
              {props.tooltipSW ? (reminderSet
                ? `Reminder set - this pattern is saved in your "${reminderInfo.portfolio}" portfolio. Click to view or edit it.`
                : reminderInfo?.saved
                  ? `This pattern is saved in your "${reminderInfo.portfolio}" portfolio - one click adds Google Calendar reminders for its start and end dates.`
                  : 'One click adds Google Calendar reminders for this pattern’s start and end dates, and saves it to your current portfolio. Customize times later via the Portfolio Manager’s calendar icon.') : ''}
            </div>
          }>
            {rdd.isMobile
              ? <button
                  type="button"
                  className={'tw-notify-mobile-btn' + (reminderSet ? ' tw-notify-mobile-btn--set' : '') + (notifyPulse && !reminderSet ? ' tw-notify-pulse' : '')}
                  onClick={handleNotifyClicked}
                  disabled={notifyBusy}
                  aria-label={reminderSet ? 'View or edit reminder' : 'Set reminder'}
                  aria-pressed={reminderSet}
                >
                  {reminderSet
                    ? <BsBellFill aria-hidden="true" size={icon_size_plus - 12} style={{ fill: "#4ade80" }} />
                    : <BsBell aria-hidden="true" size={icon_size_plus - 12} style={{ fill: "white" }} />}
                </button>
              : <button className={'tw-notify-btn' + (reminderSet ? ' tw-notify-btn--set' : '') + (notifyPulse && !reminderSet ? ' tw-notify-pulse' : '')} onClick={handleNotifyClicked} disabled={notifyBusy}>
                  {/* Icon-only when the right panel is narrow (absolute px, not split %:
                      a small window with the default split is just as cramped) - the
                      labeled pill otherwise overflows this fixed row into Best Waves. */}
                  {rightPanelPx < 1120
                    ? <BsBellFill size={13} style={{ verticalAlign: '-2px' }} />
                    : reminderSet
                      ? <><span style={{ color: '#4ade80', marginRight: '4px' }}>✓</span>Reminder set</>
                      : <><BsBellFill size={12} style={{ marginRight: '5px', verticalAlign: '-1px' }} />Remind me</>}
                </button>
            }
          </Tippy>
        }

        {/* Best Waves floats CENTERED in the slack between the Remind me pill and the ticker
            (flex:1 here + flexGrow 0 on the description while this select is rendered).
            The "── Best Waves ──" box-drawing rules (U+2500 - the original decoration this
            row shipped with before c16a969 slimmed it; not prose em-dashes) and the wider
            box stay until the measured slack leaves under 3px per side (bwWide); only then
            drop to the compact undecorated label. */}
        {!rdd.isMobile && oppBySymbolOptions.length > 0 &&
          <div ref={bwWrapRef} style={{ paddingLeft: '2px', paddingRight: '6px', flex: '1 1 0', display: 'flex', justifyContent: 'center' }}>
          <SelectBox
            optionList={bwWide ? [{ ...oppBySymbolOptions[0], label: '── Best Waves ──' }, ...oppBySymbolOptions.slice(1)] : oppBySymbolOptions}
            value={selectedOppBySymbol}
            name="oppBySymbol"
            suffix=""
            widthOverride={bwWide ? '7vw' : undefined}
            sbChanged={handleOppBySymbolChanged}
            tooltipContent={props.tooltipSW ? 'b,Best seasonal waves for this ticker sorted by Sharpe Ratio. Select a wave to load it in the viewer.' : ''}
          />
          </div>
        }

        <div style={StyleDescription} >

          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>

            {/* Inline ticker input - replaces the old static symbol text. The "N-Year" label that
                used to sit before the ticker was dropped per request. Desktop only: on mobile/tablet
                the toolbar symbol box (or the smartphone-portrait second layer) is used instead, so
                gating on !rdd.isMobile avoids rendering a duplicate id="symbol" input off-screen.
                Rendered even when props.symbol === '' so there's always somewhere to type a ticker
                (on desktop the toolbar box is now hidden). */}
            {!rdd.isMobile &&
              <span style={{ position: 'relative', display: 'flex', alignItems: 'center', marginRight: '6px' }} onFocus={handleSymbolFocus} onBlur={handleSymbolBlur}>
                <TextBox securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} tooltipContent={props.tooltipSW ? 'b,Ticker Symbol to analyze.  Ticker must be a part of current securities group' : ''} text={props.symbol} width={barchartControlTickerWidth} tbBlur={handleBlur} tbEnter={handleEnter} name="symbol" syncNonce={symbolBoxSyncNonce} qparams={props.qparams} />
                {watchlistDropdownOpen && props.defaultWatchlistItems && props.defaultWatchlistItems.length > 0 &&
                  <div className='watchlist-dropdown' style={{ position: 'absolute', top: '100%', left: 0, zIndex: 9000, backgroundColor: tc.panelBg, border: '1px solid ' + tc.border, maxHeight: '200px', overflowY: 'auto', minWidth: '100px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
                    {props.defaultWatchlistItems.map((sym, idx) => (
                      <div key={idx} onMouseDown={(e) => { e.preventDefault(); handleWatchlistItemClick(sym) }} style={{ padding: '3px 8px', cursor: 'pointer', fontSize: globalTextSize, color: tc.text, backgroundColor: sym === props.symbol ? tc.statLabelBg : 'transparent' }} onMouseEnter={(e) => e.target.style.backgroundColor = tc.inputBg} onMouseLeave={(e) => e.target.style.backgroundColor = sym === props.symbol ? tc.statLabelBg : 'transparent'}>
                        {sym}
                      </div>
                    ))}
                  </div>
                }
              </span>
            }

            <Tippy placement={'bottom'} disabled={!props.tooltipSW} content={
                <div theme="tw" >
                  {props.tooltipSW ? 'Date Range for the Wave strategy' : ''}
                </div>
              }>
                <span className={rdd.isMobile ? 'tw-wave-date-range tw-wave-date-range--mobile' : 'tw-wave-date-range'} style={{ fontWeight: 'bold', marginTop: '1px', border: '1px solid ' + tc.border, paddingLeft: '4px', paddingRight: '4px', marginRight: '5px', whiteSpace: 'nowrap', visibility: props.symbol !== '' ? 'visible' : 'hidden', width: '16ch', textAlign: 'center', boxSizing: 'border-box', display: 'inline-block' }}>{dateStartDisp} to {dateEndDisp}</span>
              </Tippy>

          </span>
        </div>






        {/* this is for 2nd layer for smartphone portraits - rect that drops when down triangle clicked*/}

        {/* mobile seasonal chart icon jumps to seasonal chart quickly */}
        <div style={{ width: SVDIVwidth, display: displayElement[14], justifyContent: 'center', backgroundColor: 'transparent' }} onClick={handleSCclicked} >
          <BiLineChart size={svIconSize} style={{ fill: "white" }} />
        </div>


        <div style={{ width: '12%', height: '100%', display: displayElement[12], alignItems: 'center', justifyContent: 'center' }} onClick={handleLayer2Visible}>
          {secondLayerControlsOpen === true
            ? <BsFillCaretUpFill size={20} style={{ fill: "white" }} />
            : <BsFillCaretDownFill size={20} style={{ fill: "white" }} />
          }
        </div>
        {/* absolute position for 2nd layer on smartphone portrait */}
        <div className="second-layer-parent" style={{ display: secondLayerDisplay }}>
          <div className='barchart-controls-div2' >
            <TextBox text={props.startDate} width="9" tbBlur={handleBlur} tbEnter={handleEnter} name="date" securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} />
          </div>
          <div className='barchart-controls-div2' style={{ position: 'relative' }} onFocus={handleSymbolFocus} onBlur={handleSymbolBlur}>
            <TextBox text={props.symbol} width="5" tbBlur={handleBlur} tbEnter={handleEnter} name="symbol" syncNonce={symbolBoxSyncNonce} securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} qparams={props.qparams} />
            {watchlistDropdownOpen && props.defaultWatchlistItems && props.defaultWatchlistItems.length > 0 &&
              <div className='watchlist-dropdown' style={{ position: 'absolute', top: '100%', left: 0, zIndex: 9000, backgroundColor: tc.panelBg, border: '1px solid ' + tc.border, maxHeight: '200px', overflowY: 'auto', minWidth: '80px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
                {props.defaultWatchlistItems.map((sym, idx) => (
                  <div key={idx} onMouseDown={(e) => { e.preventDefault(); handleWatchlistItemClick(sym) }} style={{ padding: '3px 8px', cursor: 'pointer', fontSize: globalTextSize, color: tc.text, backgroundColor: sym === props.symbol ? tc.statLabelBg : 'transparent' }}>
                    {sym}
                  </div>
                ))}
              </div>
            }
          </div>

          <div className='barchart-controls-div2' >
            <SelectBox optionList={daysOutList} value={props.daysOut} suffix=" days" name="daysout" sbChanged={selectboxChanged} />
          </div>

          <div className='barchart-controls-div2' >
            <SelectBox optionList={seasonalYearsList} value={props.seasonalYears} suffix=" years" name="years" sbChanged={selectboxChanged} />
          </div>
          
          <div className='barchart-controls-div2' >
            <SelectBox optionList={PEselectionList} value={props.PEselected} suffix="" name="PEselection" sbChanged={selectboxChanged} />
          </div>


        </div>



        <div style={{ display: "flex", alignItems: "center", height: "90%", backgroundColor: 'transparent' }}>

          {props.seasonalBarChartData.length > 0 &&
            <div className='barchart-controls-div' style={StyleLSSquare}>
              <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                <div theme="tw" >
                  {props.tooltipSW ? 'Color of square can be red or green.  WaveViewer determines if the current date range should be analyzed as bullish or bearish.  Bullish trade have at least 50% of years as bullish.  The only special condition is for Buy & Hold - Buy and Hold is always analyzed as bullish even if there are more losing years than winning years.' : ''}
                </div>
              }>
                <div style={longShortSquare}  ></div>

              </Tippy>
            </div>
          }


          <div className='barchart-controls-div' style={StyleMFE}>
            <CheckBox tooltipContent={props.tooltipSW ? 'b,MFE: Maximum Favorable Excursion, adds the maximum level the price reached in favor of the trade as light green on bullish and light red on bearish barcharts' : ''} label="MFE" cbChanged={checkboxChanged} checked={props.showMFE} />
          </div>

          <div className='barchart-controls-div' style={StyleMAE}>
            <CheckBox tooltipContent={props.tooltipSW ? 'b,MAE: Maximum Adverse Excursion, adds the maximum price reached against the trade as light red on bullish and light green on bearish barchars' : ''} label="MAE" cbChanged={checkboxChanged} checked={props.showMAE} />
          </div>

          <div className='barchart-controls-div' style={StyleStartDate}>
            <TextBoxInc securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} tooltipContent={props.tooltipSW ? 'b,Start Date to analyze a Wave. Use arrows to shift start date while keeping end date fixed.' : ''} text={props.startDate} width={barchartControlDateWidth} tbBlur={handleBlur} tbEnter={handleEnter} name="date" onLeftClick={() => handleDateNudge(-1)} onRightClick={() => handleDateNudge(1)} />
          </div>

          <div className='barchart-controls-div' style={{...StyleSymbol, position: 'relative'}} onFocus={handleSymbolFocus} onBlur={handleSymbolBlur}>
            <TextBox securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} tooltipContent={props.tooltipSW ? 'b,Ticker Symbol to analyze.  Ticker must be a part of current securities group' : ''} text={props.symbol} width={barchartControlTickerWidth} tbBlur={handleBlur} tbEnter={handleEnter} name="symbol" syncNonce={symbolBoxSyncNonce} qparams={props.qparams} />
            {watchlistDropdownOpen && props.defaultWatchlistItems && props.defaultWatchlistItems.length > 0 &&
              <div className='watchlist-dropdown' style={{ position: 'absolute', top: '100%', left: 0, zIndex: 9000, backgroundColor: tc.panelBg, border: '1px solid ' + tc.border, maxHeight: '200px', overflowY: 'auto', minWidth: '100px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
                {props.defaultWatchlistItems.map((sym, idx) => (
                  <div key={idx} onMouseDown={(e) => { e.preventDefault(); handleWatchlistItemClick(sym) }} style={{ padding: '3px 8px', cursor: 'pointer', fontSize: globalTextSize, color: tc.text, backgroundColor: sym === props.symbol ? tc.statLabelBg : 'transparent' }} onMouseEnter={(e) => e.target.style.backgroundColor = tc.inputBg} onMouseLeave={(e) => e.target.style.backgroundColor = sym === props.symbol ? tc.statLabelBg : 'transparent'}>
                    {sym}
                  </div>
                ))}
              </div>
            }
          </div>

          <div className='barchart-controls-div' style={StyleDaysOut}>
            <SelectBox tooltipContent={props.tooltipSW ? 'b,Wave Viewer Control: Select number of days for the date range. Changes the end date while keeping the start date fixed' : ''} optionList={daysOutList} value={props.daysOut} suffix=" days" name="daysout" sbChanged={selectboxChanged} />
          </div>

          {/* date2 is only shown on desktop for now  */}
          {showDate2 &&
            <div className='barchart-controls-div' style={StyleStartDate}>
              <TextBox securityTypeList2={props.securityTypeList2} selectedSecurity={props.selectedSecurity} tooltipContent={props.tooltipSW ? 'b,End Date to analyze a Wave' : ''} text={dateEnd} width={barchartControlDateWidth} tbBlur={handleBlur} tbEnter={handleEnter} name="date2" />
            </div>
          }



          <div className='barchart-controls-div' style={StyleSeasonalYears}>
            <SelectBox tooltipContent={props.tooltipSW ? 'b,Select how many matching years to include: if Cycle Filter is Consecutive, “10 years” means the last 10 calendar years; if Cycle Filter is PE/PE+1/PE+2/PE+3, “10 years” means the most recent 10 years in that cycle category (for example, the last 10 PE+2 years).' : ''} optionList={seasonalYearsList} value={props.seasonalYears} suffix=" years" name="years" sbChanged={selectboxChanged} />
          </div>
          <div className='barchart-controls-div' style={StylePEselection} >
            <SelectBox optionList={PEselectionList} value={props.PEselected} suffix="" name="PEselection" sbChanged={selectboxChanged} tooltipContent={props.tooltipSW ? 'b,Choose which years are included: Consecutive uses the last N years in a row, while PE/PE+1/PE+2/PE+3 uses only years matching that Presidential Election cycle phase.)' : ''} />
          </div>
          <div className='barchart-controls-div' style={StyleMQtrs}>
            <SelectBox tooltipContent={props.tooltipSW ? 'b,Premium Feature: TradeWave Shortcut to quickly enter date range for each month of the year, each season and by each quarter.  You can also select shortcuts for the following date ranges: "Year To Date", "Today to Year End" and "Buy & Hold" . \n When Reverse Date Range is selected, the resulting date range is the entire year except the initial date range.' : ''} optionList={monthsAndQtrs} name="monthsAndQtrs" value={props.monthsAndQtrs} sbChanged={selectboxChanged} />
          </div>

        </div>


        <div style={{ width: questionDivWidth, height: '100%', display: displayElement[13], alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent' }}>
          <BsQuestionCircle size={questionSize} style={{ fill: "white" }} onClick={handleHelpClicked} />
        </div>


      </div>



      <div className="barchart" style={{ ...barchartStyle, position: 'relative' }}>
        <BarChart seasonalBarChartData={props.seasonalBarChartData} showMAE={props.showMAE} showMFE={props.showMFE} barClicked={barClicked} barChartLongOrShort={props.barChartLongOrShort} UITheme={props.UITheme} barChartExcursionStyle={props.barChartExcursionStyle} />
        {
          (primaryChartLoading || props.seasonalBarChartData.length === 0) &&
          <div className='barchart-background' style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', top: 0, left: 0, pointerEvents: 'none', backgroundColor: barchartStyle.backgroundColor }}>
            <span style={{ fontSize: svFont, color: tc.watermark, whiteSpace: 'nowrap' }} >{brand['barchart']}</span>
          </div>
        }
      </div>

      {/* _______________________________________________end of container_________________________________________________________ */}

    </div>
  )
}

export default SeasonalBarChart
