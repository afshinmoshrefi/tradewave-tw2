import React, { useState, useEffect, useRef, useContext, useMemo } from 'react'

import LineChart from './LineChart'
import { datePaddingDays, getTodayDate } from './Common'
import { appserverURL } from './Common'
import { twFetch } from './twFetch'
// import './styles/SeasonalBarChart.css'
import './styles/StockLineChart.css'
import { UserContext } from './UserContext'
import Tippy from '@tippyjs/react'

import { BsFillCaretUpFill, BsFillCaretDownFill, BsQuestionCircle, BsFillCaretLeftFill,BsFillCaretRightFill } from "react-icons/bs";

import { BiExport } from 'react-icons/bi'
import { getCookie, setCookie } from './Common'
import { getSelectedIDFromSecuritiesList2 } from './Common'
import { UIcolors, themeColors } from './Common'
import { BsDownload, BsPencilSquare } from 'react-icons/bs';
import { opp_dashboard_dialog_content } from './Common'
import { markCaptureReady, clearCaptureReady } from './captureReady'
import { BsFillCircleFill } from "react-icons/bs"
import {
    allAvailableYearsProjectionLabel,
    selectedWindowProjectionLabel,
    shouldShowAllYearsProjectionControl,
} from './projectionLabels'
import { isNonCurrentPECycle } from './viewerCycleState'


const StockLineChart = (props) => {

    // find if year is leap
    const isLeap = year => new Date(year, 1, 29).getDate() === 29;

    const { browserH, browserW, rdd, token, infoTextSize, loggedinUser } = useContext(UserContext)
    const tc = themeColors(props.UITheme)
    const selectedProjectionLabel = selectedWindowProjectionLabel(props.seasonalYears)
    const maxProjectionLabel = allAvailableYearsProjectionLabel(props.maxAvailableYears)
    const nonCurrentPECycle = isNonCurrentPECycle(
        props.PEselected,
        Number(getTodayDate().slice(0, 4)),
    )


    const [lineChartMsg, SetLineChartMsg] = useState('Price Chart') // message shown when no linechart data

    const [lineChartData, SetLineChartData] = useState([])
    const [smaSeedData, SetSmaSeedData] = useState([])
    // const [linePointStyle, SetLinePointStyle] = useState([])

    const [lineChartDate0, SetLineChartDate0] = useState('') // lineChartDate0 and 1 is used for the text display of linechart
    const [lineChartDate1, SetLineChartDate1] = useState('')
    const [statDisplay, SetStatDisplay] = useState(() => {

        var disp = getCookie('statdisplay')
        if (disp == null) {

            disp = 'none'; //initial condition before there is a cookie
            setCookie('statdisplay', disp, 300);
        }

        if (props.symbol === 'none') disp = 'none';

        return disp;
    })

    const [showCurrentLineChart, SetShowCurrentLineChart] = useState(true)  // set to true when showing current inactive linechart
    const [headerTooltip, SetHeaderTooltip] = useState('Date Range for the displayed Trade')
    const fetchTimerRef = useRef(null)  // debounce timer to prevent multiple fetches when props change together
    const lineChartReqRef = useRef(0)  // generation counter - guards against a slow older ChartHistorical2 response clobbering a newer one

    // price level drawing state - stored in localStorage (not cookies)
    // so they don't bloat request headers and trigger nginx 400s
    const priceLevelStorageKey = `pl_${props.selectedSecurity}_${props.startDate}_${props.daysOut}_${props.symbol}_${props.seasonalYears}_${props.lineChartYear}`
    const readPriceLevels = (key) => {
        try {
            // one-time migration: if legacy cookie exists, move to localStorage and delete cookie
            const legacy = getCookie(key)
            if (legacy) {
                try { localStorage.setItem(key, legacy) } catch {}
                setCookie(key, '', -1)
                return JSON.parse(legacy)
            }
            const saved = localStorage.getItem(key)
            return saved ? JSON.parse(saved) : []
        } catch { return [] }
    }
    const [priceLevels, SetPriceLevels] = useState(() => readPriceLevels(priceLevelStorageKey))
    const [selectedLevelId, SetSelectedLevelId] = useState(null)
    const [drawingMode, SetDrawingMode] = useState(false)

    // save price levels to localStorage whenever they change
    const prevStorageKeyRef = useRef(priceLevelStorageKey)
    useEffect(() => {
        // On the render where the key just changed, priceLevels here is still the OLD
        // symbol's data (the load effect below hasn't fired yet) - skip the write so we
        // don't persist stale data under the NEW key (or removeItem-delete its saved levels).
        if (priceLevelStorageKey !== prevStorageKeyRef.current) return
        try {
            if (priceLevels.length > 0) localStorage.setItem(priceLevelStorageKey, JSON.stringify(priceLevels))
            else localStorage.removeItem(priceLevelStorageKey)
        } catch {}
    }, [priceLevels, priceLevelStorageKey])

    // load price levels when the storage key changes (different opp/symbol/etc)
    useEffect(() => {
        if (priceLevelStorageKey !== prevStorageKeyRef.current) {
            prevStorageKeyRef.current = priceLevelStorageKey
            SetSelectedLevelId(null); SetDrawingMode(false)
            SetPriceLevels(readPriceLevels(priceLevelStorageKey))
        }
    }, [priceLevelStorageKey])

    // Listen for "Clear All Price Lines" from Settings - drop in-memory state
    // so the persistence effect doesn't re-write the cleared levels back.
    useEffect(() => {
        const handler = () => { SetSelectedLevelId(null); SetDrawingMode(false); SetPriceLevels([]) }
        window.addEventListener('pl_clear_all', handler)
        return () => window.removeEventListener('pl_clear_all', handler)
    }, [])

    // Aggregate daily OHLCV rows into weekly rows
    // Each row: [date, open, high, low, close, volume]
    // Weekly: open of first day, high of max, low of min, close of last day, volume summed
    const aggregateToWeekly = (dailyRows) => {
        if (!dailyRows || dailyRows.length === 0) return [];
        const weeks = [];
        let currentWeek = null;

        for (const row of dailyRows) {
            const date = new Date(row[0]);
            // Get ISO week Monday
            const day = date.getDay();
            const diff = date.getDate() - day + (day === 0 ? -6 : 1);
            const monday = new Date(date);
            monday.setDate(diff);
            const weekKey = monday.toISOString().substring(0, 10);

            if (!currentWeek || currentWeek.key !== weekKey) {
                if (currentWeek) weeks.push(currentWeek);
                currentWeek = {
                    key: weekKey,
                    date: row[0],
                    open: row[1],
                    high: row[2],
                    low: row[3],
                    close: row[4],
                    volume: row[5] || 0,
                };
            } else {
                currentWeek.date = row[0]; // last trading day of the week
                currentWeek.high = Math.max(currentWeek.high, row[2]);
                currentWeek.low = Math.min(currentWeek.low, row[3]);
                currentWeek.close = row[4];
                currentWeek.volume += (row[5] || 0);
            }
        }
        if (currentWeek) weeks.push(currentWeek);

        return weeks.map(w => [w.date, w.open, w.high, w.low, w.close, w.volume]);
    };

    const selectedRealtimeQuote = useMemo(() => findRealtimeQuoteForSymbol(
        props.symbol,
        props.opportunities,
        props.activeOpportunities,
    ), [props.symbol, props.opportunities, props.activeOpportunities]);

    const dailyLineChartData = useMemo(() => {
        if (!showCurrentLineChart) return lineChartData;
        return appendRealtimePriceBar(lineChartData, selectedRealtimeQuote, getTodayDate());
    }, [lineChartData, selectedRealtimeQuote, showCurrentLineChart]);

    // When timeframe is weekly, aggregate the daily display rows, including today's live bar.
    const isWeekly = props.priceChartTimeframe === 'weekly';
    const effectiveLineChartData = useMemo(() => {
        if (!isWeekly || !showCurrentLineChart) return dailyLineChartData;
        return aggregateToWeekly(dailyLineChartData);
    }, [isWeekly, showCurrentLineChart, dailyLineChartData]);

    const effectiveSmaSeedData = useMemo(() => {
        if (!isWeekly || !showCurrentLineChart) return smaSeedData;
        return aggregateToWeekly(smaSeedData);
    }, [isWeekly, showCurrentLineChart, smaSeedData]);

    // otherwise false.  used to change the linechart heading text

    var questionSize = 16;
    if (rdd.isTablet && browserH > browserW) {
        if (browserH > 1024) questionSize = 30;
        else questionSize = 22;
    }


    // find the index number from the value of the selected security.  want to just pass the index number to flask
    // const getSelectedIDFromSecuritiesList = () => {
    //     for (var i = 0; i < props.securityTypeList.length; i++) {
    //         if (props.securityTypeList[i]['value'] === props.selectedSecurity) break
    //     }

    //     return (i)
    // }

    // turn off stat display when seasonal viewer is blank with no stock displayed
    useEffect(() => {
        if (props.symbol === 'none') SetStatDisplay('none')
    }, [props.symbol])

    // clear stale chart data when the market (security group) changes
    useEffect(() => {
        SetLineChartData([])
        SetSmaSeedData([])
        SetLineChartMsg('Price Chart')
    }, [props.selectedSecurity])


    useEffect(() => { //fetch linechart data

        // When lineChartYear is 0, SeasonalBarChart has started a new fetch but hasn't
        // received the data yet. Cancel any pending timer and skip - keep old chart visible.
        // StockLineChart will fire again when lineChartYear is set to the correct year.
        if (props.lineChartYear === 0) {
            if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current)
            return
        }

        // Debounce: even after lineChartYear is set, other deps (startDate, daysOut) may
        // still be settling. Wait 80ms before firing the fetch.
        if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current)
        fetchTimerRef.current = setTimeout(() => {

        // calculate the date range to download daily stock data from the server

        var d = props.startDate
        var daysOut = parseInt(props.daysOut)

        // daysOut need to be decremented by 1 since we did the cosmetic incremting of daysOut so the months daysOut was the same as the number of the months
        daysOut--;

        // if leap day feb 29th is inside the date-range, increment daysOut by 1 because we are ignoring existance of feb 29th

        var ds = d.split('-')
        var dd = ds[1] + '/' + ds[2] + '/' + props.lineChartYear //same date in mm/dd/yyyy format - wrote before I knew how to do it easier


        //for padded dates
        var date0 = new Date(dd);
        var date1 = new Date(dd);
        //original dates  
        var dateo0 = new Date(dd);
        var dateo1 = new Date(dd);




        dateo0.setDate(dateo0.getDate());
        dateo1.setDate(dateo1.getDate() + daysOut);

        // check if dateo0 to dateo1 range contains a feb29th.  if it does, advance the dateo1 by 1 day 12/6/2021

        var isExitYearLeap = isLeap(dateo1.getFullYear())
        let feb29 = new Date(dateo1.getFullYear(), 1, 29);
        if (isExitYearLeap && dateo1 > feb29 && dateo0 < feb29) {
            dateo1.setDate(dateo1.getDate() + 1);
        }


        var do0 = dateo0.getFullYear() + '-' + (dateo0.getMonth() + 1 < 10 ? '0' : '') + (dateo0.getMonth() + 1) + '-' + (dateo0.getDate() < 10 ? '0' : '') + dateo0.getDate() //original dates in yyyy-mm-dd formats
        var do1 = dateo1.getFullYear() + '-' + (dateo1.getMonth() + 1 < 10 ? '0' : '') + (dateo1.getMonth() + 1) + '-' + (dateo1.getDate() < 10 ? '0' : '') + dateo1.getDate()


        // When weekly timeframe, double the padding to show twice as much history
        const timeframePadMultiplier = props.priceChartTimeframe === 'weekly' ? 2 : 1;
        date0.setDate(date0.getDate() - datePaddingDays * timeframePadMultiplier);
        date1.setDate(date1.getDate() + daysOut + datePaddingDays);


        let mm0 = String(date0.getMonth() + 1).padStart(2, '0');
        let mm1 = String(date1.getMonth() + 1).padStart(2, '0');
        let dd0 = String(date0.getDate() + 1).padStart(2, '0');
        let dd1 = String(date1.getDate() + 1).padStart(2, '0');

        var d0 = date0.getFullYear() + '-' + mm0 + '-' + dd0 //padded dates in yyyy-mm-dd formats
        var d1 = date1.getFullYear() + '-' + mm1 + '-' + dd1

        let td = getTodayDate();
        const currentChartRequest = d1 > td;
        if (currentChartRequest) {

            d1 = td;

            // Use chartRange to set how far back the current price chart goes
            const rangeDaysMap = { '3m': 90, '6m': 180, '1y': 365, '2y': 730 };
            const rangeDays = rangeDaysMap[props.chartRange] || 180;
            const rangeDate = new Date(td);
            rangeDate.setDate(rangeDate.getDate() - rangeDays);
            date0 = rangeDate;

            mm0 = String(date0.getMonth() + 1).padStart(2, '0');
            mm1 = String(date1.getMonth() + 1).padStart(2, '0');
            dd0 = String(date0.getDate()).padStart(2, '0');
            d0 = date0.getFullYear() + '-' + mm0 + '-' + dd0
        }

        // do0/do1 are computed above - defer setting them until data arrives
        // so LineChart doesn't re-render with new dates but old price data

        // Extend fetch start back enough calendar days to seed the largest enabled MA
        const maConfig = props.maConfig || [];
        const enabledPeriods = maConfig.filter(ma => ma.enabled).map(ma => ma.period);
        const bbConfig = props.bbConfig || {};
        const bbPeriod = bbConfig.enabled ? (bbConfig.period || 20) : 0;
        const maxPeriod = Math.max(bbPeriod, enabledPeriods.length > 0 ? Math.max(...enabledPeriods) : 0);
        // For weekly timeframe, MAs need 5x more daily rows to fill the same number of periods
        const seedMultiplier = props.priceChartTimeframe === 'weekly' ? 7 : 1;
        const smaSeedDays = Math.max(70, Math.ceil(maxPeriod * 1.5 * seedMultiplier));
        const d0_sma_date = new Date(date0);
        d0_sma_date.setDate(d0_sma_date.getDate() - smaSeedDays);
        const d0_sma = d0_sma_date.getFullYear() + '-' +
            String(d0_sma_date.getMonth() + 1).padStart(2, '0') + '-' +
            String(d0_sma_date.getDate()).padStart(2, '0');

        // var id = getSelectedIDFromSecuritiesList()
        var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
        let asURL = appserverURL()
        var url = `${asURL}/ChartHistorical2/${id}/${props.symbol}/${d0_sma}/${d1}?token=${token}`

        // console.log('charthistorical 2 url=',url)
        // if (token && token.length > 0) {
        // # if (token  is added due to occational crash caused race condition
        if (token && token.length > 0 && props.lineChartYear !== 0) {
            lineChartReqRef.current += 1
            const reqId = lineChartReqRef.current
            clearCaptureReady('price')
            twFetch(url)
                .then(res => {
                    const contentType = res.headers.get("content-type");

                    if (contentType && contentType.indexOf("application/json") !== -1) {
                        return res.json();
                    }
                    else if (res.status === 429) { // too many requests
                        let trigger = res.headers.get("trigger");
                        // console.log('trigger=', trigger)
                        // props.SetDialogType('info-box'); //429
                        props.SetDialogType('rate-limit'); //429
                        // props.SetDialogProp({ title: 'Too Many Requests', contentText: ratelimitMessage(trigger, loggedinUser), button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
                        props.SetInfoBoxVisible(true)

                    }
                    else {
                        console.log('response status = ', res.status)
                    }
                })
                .then((t) => {
                    if (reqId !== lineChartReqRef.current) return // a newer request has since started - drop this stale response
                    if (t !== undefined) {
                        // Split data: sma seed rows (before display start d0) and display rows
                        const allData = t['ChartHistorical2'];
                        if (!Array.isArray(allData)) return
                        const smaPreRows = allData.filter(r => r[0] < d0);
                        const displayRows = allData.filter(r => r[0] >= d0);

                        // Set trade dates together with new data so LineChart updates atomically
                        props.SetTradeDate0(do0)
                        props.SetTradeDate1(do1)
                        SetSmaSeedData(smaPreRows);
                        SetLineChartData(displayRows)

                        // console.log('fetch line chart')
                        // console.log('charthistorical2=', t)
                        // console.log('length=', t['ChartHistorical2'].length)
                        // console.log("t['ChartHistorical2']=", t['ChartHistorical2'])

                        if (allData.length > 0) {

                            var stock_price = parseFloat(allData[allData.length - 1][4])
                            var price_date = allData[allData.length - 1][0]


                            if (price_date > props.lastPrice[0]) {
                                // props.SetLastPrice([price_date,stock_price])
                            }

                        }
                        else {
                            // props.SetLastPrice(['',-1])
                        }



                        if (displayRows.length > 0) {

                            // tmp = JSON.parse(JSON.stringify(t['ChartHistorical2'])); //making a clone / copy
                            // console.log(,t['ChartHistorical2'][t['ChartHistorical2'].length-1][0])

                            SetLineChartDate0(displayRows[0][0])
                            SetLineChartDate1(displayRows[displayRows.length - 1][0])
                            markCaptureReady('price', { symbol: props.symbol, points: displayRows.length })


                            let lastDate = displayRows[displayRows.length - 1][0]; // last date in displayed linechart 5/26/2022


                            var tmpDates = displayRows.map((r) => { //create array of only the dates in the dataset
                                return r[0]
                            })


                            // console.log('tmpDates = ',tmpDates)
                            // console.log('lastDate=',tmpDates[tmpDates.length-1])

                            var includesTradeDate1 = do1 < tmpDates[tmpDates.length - 1]

                            var isActive = false;
                            if (!includesTradeDate1) isActive = true;
                            if (props.startDate > lastDate) isActive = false; //5/26/2022 - override Active if startDate is > last date in linechart

                            // if (props.seasonalBarChartData[props.seasonalBarChartData.length-1]['pct']=='0,0,0')isActive = false;

                            props.SetTradeActive(isActive) //true if the latest trade is active
                        }
                        else { // no current data for this ticker
                            SetLineChartData([])
                            SetSmaSeedData([])
                            SetLineChartMsg('Not Traded')
                            // props.SetLastPrice(['',-1])
                        }
                    }
                })
                .catch(err => { console.error('ChartHistorical2 fetch failed', err) })
        }
        // lineChartYear === 0 case is handled above (early return), so no else needed here


        if (props.seasonalBarChartData.length > 0) {

            // let tmp2 = props.seasonalBarChartData[props.seasonalYears];
            let tmp2 = props.seasonalBarChartData[props.seasonalBarChartData.length - 1];

            // check if linechart shown is the current inactive linechart
            if (nonCurrentPECycle || (tmp2['pct'] === '0,0,0' && tmp2['year'] === props.lineChartYear)) {
                SetShowCurrentLineChart(true)
                SetHeaderTooltip(nonCurrentPECycle
                    ? 'This PE phase is not the current year, so TradeWave shows the up-to-date price chart without a seasonal projection.'
                    : 'This is the up-to-date daily price chart until the last available date.  There is no active trade for this chart yet.')
            }
            else {
                SetShowCurrentLineChart(false)
                SetHeaderTooltip('Date Range for the displayed Trade')
            }
        }

        }, 80) // end debounce setTimeout
        return () => { if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current) }

    }, [props.lineChartYear, props.startDate, props.symbol, props.daysOut, props.seasonalYears, props.PEselected, token, props.maConfig, props.bbConfig, props.priceChartTimeframe, props.chartRange])


    // dynamic styles

    var linechartDescFontSize = '0.85vw';


    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { linechartDescFontSize = '2.9vw'; }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { linechartDescFontSize = '1.7vw'; }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { linechartDescFontSize = '1.9vw'; }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { linechartDescFontSize = '1.9vw'; }




    const linechartDescStyle = {
        fontSize: linechartDescFontSize,
        backgroundColor: "transparent",
        color: tc.textOnControl,
        textAlign: "center",
    }
    let linechartControlsHeight = '8%'
    let linechartHeight = '92%'

    if (rdd.isMobile) {
        if (rdd.isTablet) {
            if (browserH > browserW) {
                linechartControlsHeight = '12%'
                linechartHeight = '88%'
            }
        }
        else {
            linechartControlsHeight = '12%'
            linechartHeight = '88%'
        }

    }


    const linechartControlsStyle = {
        backgroundColor: tc.controlBar,
        height: linechartControlsHeight,
        display: "flex",
        justifyContent: props.seasonalBarChartData.length > 0 ? 'center' : 'left'

    }

    const linechartStyle = {
        height: linechartHeight,
        backgroundColor: UIcolors(props.loggedinUser, props.UITheme)['background_price_chart'],
        borderLeft: '1px solid ' + tc.border
    }

    const StyleBackArrow = {
        display: 'none'
    }

    var questionDisplay = "flex";
    var caretSize = '4vw';
    var dispSecurity = 'inline';
    var svFont = '7vw';
    var boldYearSize = '1.1vw';
    var pencil_icon_size = 20;
    var download_icon_size = 20;

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        caretSize = '5vw';
        dispSecurity = 'none';
        svFont = '10vw';
        boldYearSize = '5vw'
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
        caretSize = '4vw';
        // questionDisplay = "none";
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        caretSize = '4vw';
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape
        caretSize = '2.0vw';
        questionDisplay = "none";
    }
    else if (!rdd.isMobile) {                                       // desktop
        caretSize = '1.2vw';
        questionDisplay = "none";
    }

    const boldYear = {
        // fontWeight: 'bold', //bold doesn't seem to work on react.  maybe after upgrade to new ver it will work
        // as a work around I increasd the size of the font.
        fontSize: boldYearSize,
        backgroundColor: 'transparent'
    }

    const handleBackClick = () => {
        if (rdd.isMobile && browserH > browserW) {
            props.chartTo(0)
        }
        else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
            props.chartTo(1)
        }
    }


    //---------------------------------------------------------------------------------------------

    useEffect(() => {
        // console.log('lineChartData=', props.lineChartYear, lineChartData[lineChartData.length - 1])
    }, [props.lineChartYear])

    //---------------------------------------------------------------------------------------------

    useEffect(() => {
        SetStatDisplay(statDisplay); // stores state of floating window on linechart (trade stat)
    }, [statDisplay])

    //---------------------------------------------------------------------------------------------

    const saveStatDisplay = (display) => {
        setCookie('statdisplay', display, 300)
    }


    const handleStatTurnOn = (event) => {

        if (statDisplay === 'none') {
            SetStatDisplay('inline');
            saveStatDisplay('inline')
            // setCookie('statdisplay', 'inline', 300)
            // console.log('statDisplay=inline')

        }
        else {
            SetStatDisplay('none');
            saveStatDisplay('none')
            // setCookie('statdisplay', 'none', 300);
            // console.log('statDisplay=none')
        }
    }

    const handleHelpClicked = () => {
        // props.SetHelpBoxVisible(!props.helpBoxVisible);
        props.SetVideosBoxVisible(true)
    }

    const handleSwitchToCurrentChart = () => {
        if (props.seasonalBarChartData.length > 0) {
            const lastBar = props.seasonalBarChartData[props.seasonalBarChartData.length - 1];
            props.SetLineChartYear(lastBar['year']);
        }
    }

    // Projection eligibility: the current price chart, OR the current-year TRADE view while
    // the trade is still ACTIVE. An active trade's chart ends at the latest close, so a
    // forward projection anchors there exactly like the current chart - without this, the
    // projections vanished for the whole life of a pattern the moment its first post-entry
    // close landed (the current-year bar loses its '0,0,0' placeholder, so current mode
    // becomes unreachable). Historical years and completed trades stay projection-free:
    // their last point is in the past, there is nothing to project forward from.
    const lastSeasonalBar = props.seasonalBarChartData && props.seasonalBarChartData.length > 0
        ? props.seasonalBarChartData[props.seasonalBarChartData.length - 1] : null;
    const projectionCapable = !nonCurrentPECycle && (
        showCurrentLineChart ||
        (props.tradeActive === true && lastSeasonalBar !== null && lastSeasonalBar['year'] === props.lineChartYear)
    );
    const showAllYearsProjectionControl = shouldShowAllYearsProjectionControl({
        projectionCapable,
        isMobile: rdd.isMobile,
        selectedYears: props.seasonalYears,
        maxAvailableYears: props.maxAvailableYears,
    });

    // Report the rendered Price Chart state to Tara's sibling component. Settings
    // alone are insufficient: projection toggles can be on while the lines are
    // hidden on a past/completed view, so expose the same eligibility conditions
    // the chart uses instead of making the chatbot infer them.
    useEffect(() => {
        if (typeof props.SetPriceChartContext !== 'function') return
        props.SetPriceChartContext({
            symbol: props.symbol,
            start_date: props.startDate,
            days_out: String(props.daysOut),
            years: String(props.seasonalYears),
            pe_cycle: props.PEselected || 'cons',
            mode: showCurrentLineChart
                ? 'current'
                : (projectionCapable && props.tradeActive ? 'active_trade' : 'historical'),
            year: props.lineChartYear,
            projection_capable: projectionCapable,
            selected_projection_visible: Boolean(
                projectionCapable && props.showProjection &&
                Array.isArray(props.consolidatedSeasonalData) && props.consolidatedSeasonalData.length > 0
            ),
            full_history_projection_visible: Boolean(
                projectionCapable && props.showMaxProjection &&
                Array.isArray(props.maxYearsConsolidatedSeasonalData) && props.maxYearsConsolidatedSeasonalData.length > 0
            ),
            projection_period_days: props.projectionPeriod,
            selected_years: props.seasonalYears,
            full_history_years: props.maxAvailableYears,
            timeframe: props.priceChartTimeframe,
        })
    }, [
        showCurrentLineChart,
        projectionCapable,
        props.lineChartYear,
        props.symbol,
        props.startDate,
        props.daysOut,
        props.seasonalYears,
        props.PEselected,
        props.tradeActive,
        props.showProjection,
        props.showMaxProjection,
        props.consolidatedSeasonalData,
        props.maxYearsConsolidatedSeasonalData,
        props.projectionPeriod,
        props.seasonalYears,
        props.maxAvailableYears,
        props.priceChartTimeframe,
        props.SetPriceChartContext,
    ])

    //-------------------------------------------------------------------------------------------------
    const handleExport = () => {
        props.SetShowWatermark(true);
        props.SetExportImage(true)
    }
    //------------------------------------------------------------------------------------------
    const handleDrawModeToggle = () => {
        SetDrawingMode(prev => !prev)
        SetSelectedLevelId(null)
    }
    const handleDeleteLevel = () => {
        if (selectedLevelId) {
            SetPriceLevels(prev => prev.filter(l => l.id !== selectedLevelId))
            SetSelectedLevelId(null)
        }
    }
    const handleLevelColorChange = (color) => {
        if (selectedLevelId) {
            SetPriceLevels(prev => prev.map(l => l.id === selectedLevelId ? { ...l, color } : l))
        }
    }
    const handleLevelDashToggle = () => {
        if (selectedLevelId) {
            SetPriceLevels(prev => prev.map(l => l.id === selectedLevelId ? { ...l, dash: l.dash === 'solid' ? 'dashed' : 'solid' } : l))
        }
    }
    //------------------------------------------------------------------------------------------
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

    //------------------------------------------------------------------------------------------
    const handle3Circles = (num) => {

    }
    //-------------------------------------------------------------------------------------------------
    return (
        <div className="linechart-parent" style={{ backgroundColor: tc.controlBar }}>

            <div className="linechart-controls" style={linechartControlsStyle}  >

                <div style={{ backgroundColor: 'transparent', width: '20%', display: 'flex', alignItems: 'center' }}>

                    {selectedLevelId ? (
                        /* ── Price level editing controls ── */
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '10px' }}>
                            {/* Delete button */}
                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={<div theme="tw">Delete Price Level</div>}>
                                <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }} onClick={handleDeleteLevel}>
                                    <svg width="18" height="18" viewBox="0 0 18 18"><line x1="4" y1="4" x2="14" y2="14" stroke="white" strokeWidth="2"/><line x1="14" y1="4" x2="4" y2="14" stroke="white" strokeWidth="2"/></svg>
                                </div>
                            </Tippy>
                            {/* Dash toggle */}
                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={<div theme="tw">Toggle Solid/Dashed</div>}>
                                <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }} onClick={handleLevelDashToggle}>
                                    <svg width="24" height="18" viewBox="0 0 24 18">
                                        {(() => {
                                            const sel = priceLevels.find(l => l.id === selectedLevelId)
                                            return sel && sel.dash === 'dashed'
                                                ? <line x1="2" y1="9" x2="22" y2="9" stroke="white" strokeWidth="2" strokeDasharray="4 3"/>
                                                : <line x1="2" y1="9" x2="22" y2="9" stroke="white" strokeWidth="2"/>
                                        })()}
                                    </svg>
                                </div>
                            </Tippy>
                            {/* Color swatches */}
                            {['#c850c8','#e8a838','#38b8e8','#48c848','#e84848','#888888'].map(c => {
                                const sel = priceLevels.find(l => l.id === selectedLevelId)
                                const isActive = sel && sel.color === c
                                return (
                                    <div key={c} onClick={() => handleLevelColorChange(c)}
                                        style={{
                                            width: 14, height: 14, borderRadius: '50%', backgroundColor: c, cursor: 'pointer',
                                            border: isActive ? '2px solid white' : '2px solid transparent',
                                            boxSizing: 'border-box',
                                        }}
                                    />
                                )
                            })}
                        </div>
                    ) : (
                        /* ── Normal title bar icons ── */
                        <>
                            {(!rdd.isMobile || (rdd.isMobile && rdd.isTablet && browserW > browserH)) &&
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw">{props.tooltipSW ? 'Portfolio Manager' : ''}</div>
                                }>
                                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'left' }}>
                                        <BsPencilSquare size={pencil_icon_size} style={{ fill: "white", marginLeft: '10px' }} onClick={handleDRreport} />
                                    </div>
                                </Tippy>
                            }

                            {((!rdd.isMobile && props.symbol !== ' ') || (rdd.isMobile && rdd.isTablet && browserH < browserW && props.symbol !== ' '))
                                ?
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw">{props.tooltipSW ? 'Export Strategy Barchart and Price Chart as Jpeg' : ''}</div>
                                }>
                                    <div role="button" aria-label="Download Wave Viewer screenshot" tabIndex={0} onClick={handleExport} style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'left', paddingLeft: '10px', cursor: 'pointer' }}>
                                        <BsDownload size={download_icon_size} style={{ fill: "white" }} aria-hidden="true" />
                                    </div>
                                </Tippy>
                                :
                                <div style={{ height: '100%', width: '10%', display: 'flex', alignItems: 'center', justifyContent: 'left', paddingLeft: '10px' }}></div>
                            }

                            {/* Draw price level icon */}
                            {((!rdd.isMobile && props.symbol !== ' ') || (rdd.isMobile && rdd.isTablet && browserH < browserW && props.symbol !== ' ')) &&
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw">{drawingMode ? 'Cancel Drawing Mode' : 'Draw Price Level'}</div>
                                }>
                                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'left', paddingLeft: '10px', cursor: 'pointer' }} onClick={handleDrawModeToggle}>
                                        <svg width="20" height="20" viewBox="0 0 20 20">
                                            <line x1="2" y1="10" x2="18" y2="10" stroke={drawingMode ? '#38b8e8' : 'white'} strokeWidth="2"/>
                                            <circle cx="2" cy="10" r="2" fill={drawingMode ? '#38b8e8' : 'white'}/>
                                            <circle cx="18" cy="10" r="2" fill={drawingMode ? '#38b8e8' : 'white'}/>
                                        </svg>
                                    </div>
                                </Tippy>
                            }

                            {props.symbol !== ' ' &&
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw">{props.tooltipSW ? 'toggle switch to show or hide the trade detail window ' : ''}</div>
                                }>
                                    {showCurrentLineChart
                                        ? <div className='linechart-desc-left'></div>
                                        : <div className='linechart-desc-left' onClick={handleStatTurnOn}>
                                            {statDisplay === 'none'
                                                ? <BsFillCaretDownFill size={caretSize} style={{ fill: "white" }} />
                                                : <BsFillCaretUpFill size={caretSize} style={{ fill: "white" }} />
                                            }
                                        </div>
                                    }
                                </Tippy>
                            }
                        </>
                    )}
                </div>


                <div style={{ backgroundColor: 'transparent', width: "90%", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>

                    {/* description on the top control bar */}
                    {props.symbol !== ' ' ?
                        <div className='linechart-desc' style={linechartDescStyle} >

                            <Tippy disabled = {!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {props.tooltipSW ? 'Name of the security' : ''}
                                </div>
                            }>
                                <span style={{ color: UIcolors(loggedinUser)['security_name'], display: dispSecurity }}>&nbsp;
                                    <strong>{props.company}</strong>
                                </span>
                            </Tippy>
                            <span style={{ color: "white" }}>
                                &nbsp;
                            </span>

                            {/* tradedate0 to tradedate1 displayed on control bar of stocklinechart */}

                            <Tippy disabled = {!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {props.tooltipSW ? headerTooltip : ''}
                                </div>
                            }>
                                {showCurrentLineChart
                                    ? <span style={{ whiteSpace: 'nowrap' }}>Current Price Chart</span>
                                    : <span style={{ whiteSpace: 'nowrap' }}>
                                        <span style={boldYear} >Price Chart {props.tradeDate0.substring(0, 4)}</span>
                                        <span>{props.tradeDate0.substring(4)}  </span>
                                        <span>   to   </span>
                                        <span style={boldYear}  >{props.tradeDate1.substring(0, 4)}</span>
                                        <span>{props.tradeDate1.substring(4)}</span>

                                    </span>
                                }
                            </Tippy>

                            <span style={{ color: 'red', fontSize: linechartDescFontSize, paddingLeft: '10px' }}>
                                {props.tradeActive ? "ACTIVE" : ""}
                            </span>

                            {showCurrentLineChart && !rdd.isMobile &&
                                [
                                    { key: '3m', label: '3M', tip: '3 Months' },
                                    { key: '6m', label: '6M', tip: '6 Months' },
                                    { key: '1y', label: '1Y', tip: '1 Year' },
                                    { key: '2y', label: '2Y', tip: '2 Years' },
                                ].map(({ key, label, tip }) => (
                                    <Tippy key={key} placement={'top'} content={
                                        <div theme="tw">{tip}</div>
                                    }>
                                        <span
                                            onClick={() => props.SetChartRange(key)}
                                            style={{
                                                marginLeft: key === '3m' ? '10px' : '2px',
                                                padding: '1px 5px',
                                                fontSize: linechartDescFontSize,
                                                color: props.chartRange === key ? '#1a1a1a' : 'rgba(255,255,255,0.6)',
                                                backgroundColor: props.chartRange === key ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.08)',
                                                border: props.chartRange === key ? '1px solid rgba(255,255,255,0.85)' : '1px solid rgba(255,255,255,0.20)',
                                                borderRadius: '3px',
                                                cursor: 'pointer',
                                                whiteSpace: 'nowrap',
                                                fontWeight: props.chartRange === key ? '600' : '400',
                                                transition: 'all 0.15s',
                                            }}
                                        >
                                            {label}
                                        </span>
                                    </Tippy>
                                ))
                            }

                            {showCurrentLineChart && !rdd.isMobile &&
                                <Tippy placement={'top'} content={
                                    <div theme="tw">Switch between Daily and Weekly chart</div>
                                }>
                                    <span
                                        onClick={() => props.SetPriceChartTimeframe(props.priceChartTimeframe === 'daily' ? 'weekly' : 'daily')}
                                        style={{
                                            marginLeft: '10px',
                                            padding: '1px 8px',
                                            fontSize: linechartDescFontSize,
                                            color: props.priceChartTimeframe === 'weekly' ? '#1a1a1a' : 'rgba(255,255,255,0.7)',
                                            backgroundColor: props.priceChartTimeframe === 'weekly' ? '#38b8e8' : 'rgba(255,255,255,0.10)',
                                            border: props.priceChartTimeframe === 'weekly' ? '1px solid #38b8e8' : '1px solid rgba(255,255,255,0.25)',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            whiteSpace: 'nowrap',
                                            fontWeight: props.priceChartTimeframe === 'weekly' ? '600' : '400',
                                            transition: 'all 0.15s',
                                        }}
                                    >
                                        {props.priceChartTimeframe === 'weekly' ? 'W' : 'D'}
                                    </span>
                                </Tippy>
                            }

                            {!rdd.isMobile && props.tradeDetailData && props.tradeDetailData.earnings_filings && props.tradeDetailData.earnings_filings.length > 0 &&
                                <Tippy placement={'top'} content={
                                    <div theme="tw">Toggle Earnings Date Markers</div>
                                }>
                                    <span
                                        onClick={() => props.SetShowEarnings(!props.showEarnings)}
                                        style={{
                                            marginLeft: '10px',
                                            padding: '1px 8px',
                                            fontSize: linechartDescFontSize,
                                            color: props.showEarnings ? '#1a1a1a' : 'rgba(255,255,255,0.7)',
                                            backgroundColor: props.showEarnings ? '#c850c8' : 'rgba(255,255,255,0.10)',
                                            border: props.showEarnings ? '1px solid #c850c8' : '1px solid rgba(255,255,255,0.25)',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            whiteSpace: 'nowrap',
                                            fontWeight: props.showEarnings ? '600' : '400',
                                            transition: 'all 0.15s',
                                        }}
                                    >
                                        E
                                    </span>
                                </Tippy>
                            }

                            {projectionCapable && !rdd.isMobile && props.consolidatedSeasonalData && props.consolidatedSeasonalData.length > 0 &&
                                <Tippy disabled={!props.tooltipSW} placement={'top'} content={
                                    <div theme="tw">{selectedProjectionLabel}</div>
                                }>
                                    <span
                                        onClick={() => props.SetShowProjection(!props.showProjection)}
                                        style={{
                                            marginLeft: '10px',
                                            padding: '1px 8px',
                                            fontSize: linechartDescFontSize,
                                            color: props.showProjection ? '#1a1a1a' : 'rgba(255,255,255,0.7)',
                                            backgroundColor: props.showProjection ? '#e8a838' : 'rgba(255,255,255,0.10)',
                                            border: props.showProjection ? '1px solid #e8a838' : '1px solid rgba(255,255,255,0.25)',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            whiteSpace: 'nowrap',
                                            fontWeight: props.showProjection ? '600' : '400',
                                            transition: 'all 0.15s',
                                        }}
                                    >
                                        Proj
                                    </span>
                                </Tippy>
                            }

                            {showAllYearsProjectionControl &&
                                <Tippy disabled={!props.tooltipSW} placement={'top'} content={
                                    <div theme="tw">{maxProjectionLabel}</div>
                                }>
                                    <span
                                        onClick={() => props.SetShowMaxProjection(!props.showMaxProjection)}
                                        style={{
                                            marginLeft: '6px',
                                            padding: '1px 8px',
                                            fontSize: linechartDescFontSize,
                                            color: props.showMaxProjection ? '#ffffff' : 'rgba(255,255,255,0.7)',
                                            backgroundColor: props.showMaxProjection ? '#7c5cff' : 'rgba(255,255,255,0.10)',
                                            border: props.showMaxProjection ? '1px solid #7c5cff' : '1px solid rgba(255,255,255,0.25)',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            whiteSpace: 'nowrap',
                                            fontWeight: props.showMaxProjection ? '600' : '400',
                                            transition: 'all 0.15s',
                                        }}
                                    >
                                        Proj {props.maxAvailableYears}-Y
                                    </span>
                                </Tippy>
                            }

                            {!showCurrentLineChart && !rdd.isMobile &&
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw">
                                        {props.tooltipSW ? 'Switch to Current Price Chart' : ''}
                                    </div>
                                }>
                                    <span
                                        onClick={handleSwitchToCurrentChart}
                                        style={{
                                            marginLeft: '10px',
                                            padding: '1px 8px',
                                            fontSize: linechartDescFontSize,
                                            color: 'white',
                                            backgroundColor: 'rgba(255,255,255,0.15)',
                                            border: '1px solid rgba(255,255,255,0.3)',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            whiteSpace: 'nowrap',
                                        }}
                                    >
                                        Current
                                    </span>
                                </Tippy>
                            }
                        </div>
                        :
                        <div className='linechart-desc' style={linechartDescStyle} ></div>
                    }

                </div>




                {/* right spacing div to match the left divs to center the text in the middle */}
                {
                    (!rdd.isMobile || (rdd.isMobile && rdd.isTablet && browserH < browserW))
                        ?
                        <div style={{ width: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>


                            <Tippy placement={'top'} content={
                                <div theme="tw" >
                                    {'Trend Chart'}

                                </div>
                            }>


                                <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}> <BsFillCircleFill size={12} style={{ fill: "white" }} onClick={() => props.chartTo(0)} /></div>
                            </Tippy>




                            <Tippy placement={'top'} content={
                                <div theme="tw" >
                                    {'Wave Stats'}
                                </div>
                            }>


                                <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}> <BsFillCircleFill size={12} style={{ fill: "white" }} onClick={() => props.chartTo(1)} /></div>
                            </Tippy>


                            {props.showAIScoreNavigation &&
                                <Tippy placement={'top'} content={
                                    <div theme="tw" >
                                        {'AI Scores'}
                                    </div>
                                }>
                                    <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}>
                                        <BsFillCircleFill size={12} style={{ fill: "white" }} onClick={() => props.chartTo('ai_scores')} />
                                    </div>
                                </Tippy>
                            }

                            <Tippy placement={'top'} content={
                                <div theme="tw" >
                                    {'Price Chart'}
                                </div>
                            }>

                                <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}> <BsFillCircleFill size={12} style={{ fill: "red" }} /></div>
                            </Tippy>


                        </div>
                        : rdd.isMobile && rdd.isTable && browserH < browserW ?
                            <div style={{ width: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'right', paddingRight: '2vw' }}>
                                <BsQuestionCircle size={questionSize} style={{ fill: "white" }} onClick={handleHelpClicked} />
                            </div>
                            : <div style={{ width: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'right', paddingRight: '2vw' }}>
                            </div>
                }




            </div>

            <div className="linechart" style={{ ...linechartStyle, position: 'relative' }}>
                {lineChartData.length > 0
                    ? <LineChart showCurrentLineChart={showCurrentLineChart} projectionCapable={projectionCapable} statDisplay={statDisplay} SetStatDisplay={SetStatDisplay} lineChartData={effectiveLineChartData} smaSeedData={effectiveSmaSeedData} barChartLongOrShort={props.barChartLongOrShort} tradeDate0={props.tradeDate0} tradeDate1={props.tradeDate1} activeTrade={props.tradeActive} saveStatDisplay={saveStatDisplay} statBoxCoordinates={props.statBoxCoordinates} SetStatBoxCoordinates={props.SetStatBoxCoordinates} UITheme={props.UITheme} showWatermark={props.showWatermark} priceChartType={props.priceChartType} showVolume={props.showVolume} maConfig={props.maConfig} bbConfig={props.bbConfig} priceLevels={priceLevels} SetPriceLevels={SetPriceLevels} selectedLevelId={selectedLevelId} SetSelectedLevelId={SetSelectedLevelId} drawingMode={drawingMode} SetDrawingMode={SetDrawingMode} showProjection={props.showProjection} projectionPeriod={props.projectionPeriod} consolidatedSeasonalData={props.consolidatedSeasonalData} showMaxProjection={props.showMaxProjection} maxYearsConsolidatedSeasonalData={props.maxYearsConsolidatedSeasonalData} maxAvailableYears={props.maxAvailableYears} seasonalYears={props.seasonalYears} priceChartTimeframe={props.priceChartTimeframe} showEarnings={props.showEarnings} tradeDetailData={props.tradeDetailData} tooltipSW={props.tooltipSW} />
                    : <div className='barchart-background'><span style={{ fontSize: svFont, color: tc.watermark }} >{lineChartMsg}</span></div>
                }
                {props.lineChartYear === 0 && lineChartData.length > 0 &&
                    <div style={{
                        position: 'absolute', inset: 0,
                        backgroundColor: 'rgba(0,0,0,0.25)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        pointerEvents: 'none',
                    }}>
                        <span style={{ color: 'white', fontSize: '1vw', opacity: 0.8 }}>Loading...</span>
                    </div>
                }
            </div>

            {/* statBoxCoordinates={props.statBoxCoordinates} SetStatBoxCoordinates={props.SetStatBoxCoordinates} */}
        </div>
    )
}

export default StockLineChart
