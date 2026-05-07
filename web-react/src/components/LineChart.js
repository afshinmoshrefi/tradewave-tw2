import React, { useState, useContext, useMemo, useEffect, useRef } from 'react';

import { Line, Chart } from 'react-chartjs-2';
import uparrowImage from './images/uparrow8.png';
import dnarrowImage from './images/downarrow8.png';
import { UserContext } from './UserContext'
import './styles/lineChart.css'
import 'chartjs-plugin-annotation';
// import annotationPlugin from 'chartjs-plugin-annotation';


import { BsFillCaretRightFill, BsFillCaretLeftFill } from "react-icons/bs";
import { BiX } from "react-icons/bi";
import { UIcolors, themeColors } from './Common'

import annotationPlugin from "chartjs-plugin-annotation";
// import datalabelsPlugin from "chartjs-plugin-datalabels";


Chart.register([annotationPlugin,]);

// defaults.global.tooltips.enabled = true // turns off tooltips when hovering over chart itself
// defaults.global.legend.position = 'bottom' //legend position top is the default
// defaults.global.legend.display = false;    //removing legends all together.  position is not needed, keeping it for reference.

var dnArrow = new Image();
dnArrow.src = dnarrowImage;

var upArrow = new Image();
upArrow.src = uparrowImage;


// showCurrentLineChart should not have any annotation also no trade stat box

const DEFAULT_MA_CONFIG = [
    { enabled: false, period: 20,  type: 'ema', color: '#e8a838', dash: 'solid' },
    { enabled: true,  period: 50,  type: 'sma', color: '#c850c8', dash: 'solid' },
    { enabled: false, period: 100, type: 'sma', color: '#38b8e8', dash: 'solid' },
    { enabled: false, period: 200, type: 'sma', color: '#48c848', dash: 'solid' },
];

const DEFAULT_BB_CONFIG = {
    enabled: false,
    period: 20,
    multiplier: 2,
    color: '#e8a838',
    fill: true,
};

const LineChart = ({ showCurrentLineChart, lineChartData, smaSeedData = [], barChartLongOrShort, tradeDate0, tradeDate1, statDisplay, SetStatDisplay, saveStatDisplay, statBoxCoordinates, SetStatBoxCoordinates, UITheme, showWatermark, priceChartType = 'line', showVolume = true, maConfig = DEFAULT_MA_CONFIG, bbConfig = DEFAULT_BB_CONFIG, priceLevels = [], SetPriceLevels, selectedLevelId = null, SetSelectedLevelId, drawingMode = false, SetDrawingMode, showProjection = false, projectionPeriod = '30', consolidatedSeasonalData = [], priceChartTimeframe = 'daily', showEarnings = true, tradeDetailData = null }) => {

    const { browserH, browserW, rdd, loggedinUser } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const chartRef = useRef(null);

    // default values are just for testing - not used

    const [dataClose, setDataClose] = useState([21.02, 7.92, 1.73, 3.65, 4.13, 1.36, 3.56, 5.02, 1.85, 1.17, 6.29, 24.07])

    const [labels, setLabels] = useState(['2009', '2010', '2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])
    const [pointStyle, setPointStyle] = useState([upArrow, dnArrow, dnArrow, upArrow, '', '', ''])

    const [x0, SetX0] = useState(0)
    const [x1, SetX1] = useState(0)
    const [y0, SetY0] = useState(0)
    const [y1, SetY1] = useState(0)
    const [tradeLineColor, SetTradeLineColor] = useState('green')
    const [tradeBoxColor, SetTradeBoxColor] = useState('rgb(255, 99, 132,0.2)')
    const [profit, SetProfit] = useState('')
    const [profitP, SetProfitP] = useState('')
    const [profitColor, SetProfitColor] = useState('rgb(0,70,0,1)')
    const [activeTrade, SetActiveTrade] = useState(false)
    const [showActive, SetShowActive] = useState('')
    const [ohlcData, setOhlcData] = useState([])
    const [volumeData, setVolumeData] = useState([])

    // Refs so the inline plugin (created once on mount) always reads the latest values
    const ohlcDataRef = useRef([])
    const priceChartTypeRef = useRef(priceChartType)
    const wickColorRef = useRef('#000')

    // Earnings marker refs (plugin reads latest values)
    const earningsRef = useRef({ filings: [], nextEst: null, daysTo: null, show: false })
    const earningsHoverRef = useRef({ positions: [], mouseX: -1, mouseY: -1, wasHovering: false })

    // Price level refs (so plugins/events always read latest values)
    const priceLevelsRef = useRef([])
    const selectedLevelIdRef = useRef(null)
    const drawingModeRef = useRef(false)
    const dragRef = useRef({ type: null, levelId: null, startY: 0, startPrice: 0, startX0: 0, startX1: 0 })



    const lineColorWin = 'green'
    const lineColorLose = 'red'
    const boxColorWin = 'rgb(0, 200, 0,0.1)'
    const boxColorLose = 'rgb(200, 0, 0,0.1)'
    // --------------------------------------------------------
    // useeffect for floating window
    const [boxLocation, SetBoxLocation] = useState('top-left')
    const [fBackColor, SetFBackColor] = useState('rgb(200,200,200,0.75)')

    const tmpObjL = () => {
        var tObjL = ['15%', '10.5%', '65%', '55%'];
        if (rdd.isMobile && !rdd.isTablet && browserH > browserW) tObjL = ['15%', '10.5%', '65%', '55%'] // --smartphone portrait
        else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) tObjL = ['15%', '6.0%', '40%', '45%'] // --smartphone landscape
        else if (rdd.isMobile && rdd.isTablet && browserH > browserW) tObjL = ['15%', '6.0%', '40%', '45%'] // --tablet portrait
        else if (rdd.isMobile && rdd.isTablet && browserH < browserW) tObjL = ['10%', '6.0%', '35%', '40%']// --tablet landscape
        else if (!rdd.isMobile) tObjL = ['8%', '4%', '25%', '30%']// --desktop
        return tObjL
    }

    const tmpObjR = () => {
        var tObjR = ['15%', '30%', '65%', '55%'];
        var tObjL = ['15%', '10.5%', '65%', '55%']
        if (rdd.isMobile && !rdd.isTablet && browserH > browserW) tObjR = ['15%', '30%', '65%', '55%']// --smartphone portrait
        else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) tObjR = ['15%', '58%', '40%', '45%']// --smartphone landscape
        else if (rdd.isMobile && rdd.isTablet && browserH > browserW) tObjR = ['15%', '58%', '40%', '45%'] // --tablet portrait
        else if (rdd.isMobile && rdd.isTablet && browserH < browserW) tObjR = ['10%', '63%', '35%', '40%']// --tablet landscape
        else if (!rdd.isMobile) tObjR = ['8%', '74%', '25%', '30%'] // --desktop
        return tObjR
    }

    const ffontSize = () => {
        var fontSize = '1vw';
        if (rdd.isMobile && !rdd.isTablet && browserH > browserW) fontSize = '4vw'// --smartphone portrait
        else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) fontSize = '2.0vw'// --smartphone landscape
        else if (rdd.isMobile && rdd.isTablet && browserH > browserW) fontSize = '2.9vw' // --tablet portrait
        else if (rdd.isMobile && rdd.isTablet && browserH < browserW) fontSize = '1.7vw'// --tablet landscape
        else if (!rdd.isMobile) fontSize = '1vw' // --desktop
        return fontSize
    }

    //-------------------------------------------------

    const coordsEqual = (a, b) =>
        Array.isArray(a) &&
        Array.isArray(b) &&
        a.length === b.length &&
        a.every((v, i) => v === b[i]);
    //-------------------------------------------------
    useEffect(() => {
        if (statDisplay === 'none') return;

        const desired =
            boxLocation === 'top-left' ? tmpObjL() :
                boxLocation === 'top-right' ? tmpObjR() :
                    null;

        if (!desired) return;

        if (!coordsEqual(statBoxCoordinates, desired)) {
            SetStatBoxCoordinates(desired);
        }
    }, [
        statDisplay,
        boxLocation,
        browserH,
        browserW,
        rdd.isMobile,
        rdd.isTablet,
        statBoxCoordinates,
        SetStatBoxCoordinates
    ]);
    //-------------------------------------------------
    useEffect(() => {


        var tmpDataClose = []
        var tmpDataLabel = []
        var tmpPointStyle = []

        var tmpDates = lineChartData.map((r) => { //create array of only the dates in the dataset
            return r[0]
        })

        var tmp_tradeDate0 = tradeDate0
        var tmp_tradeDate1 = tradeDate1



        var includesTradeDate0 = tmpDates.includes(tmp_tradeDate0)
        var includesTradeDate1 = tmpDates.includes(tmp_tradeDate1)

        if (!includesTradeDate0) { // if date0 not in the list, find the next date
            for (var i = 0; i < tmpDates.length; i++) {
                if (tmpDates[i] > tmp_tradeDate0) { // found it
                    tmp_tradeDate0 = tmpDates[i]
                    break;
                }
            }
        }


        if (!includesTradeDate1) { // if date1 not in the list, find the next date
            for (i = 0; i < tmpDates.length; i++) {

                // console.log('^',i,tmpDates[i] > tmp_tradeDate1)
                if (tmpDates[i] > tmp_tradeDate1) { // found it
                    tmp_tradeDate1 = tmpDates[i]
                    break;
                }
            }
        }
        var x = 0; // counting for rectangle coordinates
        var xx0 = 0, xx1 = 0

        var entryPrice = 0;
        var exitPrice = 0;
        var tmpOhlcArr = []
        var tmpVolume = []
        lineChartData.forEach((r) => {

            tmpDataClose.push(r[4])  // r: [date, open, high, low, close, volume]
            tmpDataLabel.push(r[0])
            tmpOhlcArr.push({ open: parseFloat(r[1]), high: parseFloat(r[2]), low: parseFloat(r[3]), close: parseFloat(r[4]) })
            tmpVolume.push(r[5] !== undefined ? parseFloat(r[5]) : 0)


            switch (barChartLongOrShort) {
                case 'long':
                    if (r[0] === tmp_tradeDate0) {
                        tmpPointStyle.push(upArrow);
                        xx0 = x;
                        entryPrice = r[4]
                        let p = parseFloat(r[4]).toFixed(5).toString()
                        SetY0(p)


                    }
                    else if (r[0] === tmp_tradeDate1) {
                        tmpPointStyle.push(dnArrow);
                        xx1 = x;
                        let p = parseFloat(r[4]).toFixed(5).toString()
                        SetY1(p)
                        exitPrice = p;

                        if (r[4] - entryPrice >= 0) {
                            SetTradeLineColor(lineColorWin)
                            SetTradeBoxColor(boxColorWin)
                        }
                        else {
                            SetTradeLineColor(lineColorLose)
                            SetTradeBoxColor(boxColorLose)
                        }
                    }

                    else {
                        // SetY0(0)
                        tmpPointStyle.push('circle');
                    }
                    break;
                case 'short':
                    if (r[0] === tmp_tradeDate0) {
                        tmpPointStyle.push(dnArrow);
                        xx0 = x;
                        let p = parseFloat(r[4]).toFixed(5).toString()
                        SetY0(p)
                        entryPrice = r[4]
                    }
                    else if (r[0] === tmp_tradeDate1) {
                        tmpPointStyle.push(upArrow);
                        xx1 = x;
                        let p = parseFloat(r[4]).toFixed(5).toString()
                        SetY1(p)
                        exitPrice = r[4];
                        if (entryPrice - r[4] >= 0) {
                            SetTradeLineColor(lineColorLose);
                            SetTradeBoxColor(boxColorLose);
                        }
                        else {
                            SetTradeLineColor(lineColorWin);
                            SetTradeBoxColor(boxColorWin);
                        }
                    }
                    else {
                        // SetY0(0)
                        tmpPointStyle.push('circle');
                    }
                    break;
                default:
                    break;
            }
            x++;
        })

        SetX0(xx0);


        if (xx1 === 0) { // active trade
            SetX1(x - 1);  //active trade.  set xx1 to the last bar on the chart
            SetActiveTrade(true)
            SetShowActive('Active  ')
            if (lineChartData.length > 0) {
                let lastPriceInData = lineChartData[lineChartData.length - 1][4] //last close price in the passed data
                SetY1(lastPriceInData) //if its active set the exit price to last price in the data for calculations
                exitPrice = lastPriceInData
            }
        }
        else {
            SetX1(xx1);
            SetActiveTrade(false)
            SetShowActive('')
        }


        // console.log('xx0,xx1=',xx0,xx1)


        setDataClose(tmpDataClose)
        setLabels(tmpDataLabel)
        setPointStyle(tmpPointStyle)
        setOhlcData(tmpOhlcArr)
        setVolumeData(tmpVolume)

        // calculate profit
        if (barChartLongOrShort === 'long') {
            var p, pp;
            if (entryPrice !== 0) {
                p = (exitPrice - entryPrice).toFixed(2);
                pp = (100 * p / entryPrice).toFixed(2);
                SetProfit(p.toString() + 'pts')
            }
            else {
                p = 0;
                pp = 0;
                SetProfit('0')
                SetY0(0)
            }





            if (pp === 0) {
                SetProfitP('')
            }

            else if (pp > 0) { // set winning colors and other things
                SetProfitP('+' + pp.toString() + '%')
                SetTradeLineColor(lineColorWin);
                SetTradeBoxColor(boxColorWin);
            }
            else { // set losing colors and other things
                SetProfitP(pp.toString() + '%')
                SetTradeLineColor(lineColorLose);
                SetTradeBoxColor(boxColorLose);
            }
            if (p >= 0) SetProfitColor('rgb(10,70,10,1');
            else SetProfitColor('rgb(215,0,0,1');
        }
        else { // its short
            p = -(exitPrice - entryPrice).toFixed(2);
            pp = (100 * p / entryPrice).toFixed(2);
            SetProfit(p.toString() + 'pts')

            if (pp > 0) SetProfitP('+' + pp.toString() + '%')
            else SetProfitP(pp.toString() + '%')

            if (p >= 0) SetProfitColor('rgb(10,70,10,1');
            else SetProfitColor('rgb(215,0,0,1');
        }

        // if (statDisplay !== 'none') { // these variables should be set only when stat window is showing

        //     if (boxLocation === 'top-left' && statBoxCoordinates !== tmpObjL) SetStatBoxCoordinates(tmpObjL)
        //     else if (boxLocation === 'top-right' && statBoxCoordinates !== tmpObjR) SetStatBoxCoordinates(tmpObjR)
        // }

    }, [lineChartData, boxLocation, statDisplay, tradeDate0, tradeDate1, barChartLongOrShort])




    useEffect(() => {
        if (showCurrentLineChart && statDisplay !== 'none') SetStatDisplay('none');
    }, [showCurrentLineChart, statDisplay, SetStatDisplay]);




    //-------------------------------------------------

    // Prepend seed closes so MAs are fully computed from bar 0 of the display window
    const seedCloses = smaSeedData.map(r => r[4]);
    const allCloses = [...seedCloses, ...dataClose];
    const seedLen = seedCloses.length;

    const computeSMA = (data, period) => {
        return data.map((_, i) => {
            if (i < period - 1) return null;
            const slice = data.slice(i - period + 1, i + 1);
            const valid = slice.filter(v => v !== null && v !== undefined && !isNaN(parseFloat(v)));
            if (valid.length < period) return null;
            return valid.reduce((a, b) => a + parseFloat(b), 0) / period;
        });
    };

    const computeEMA = (data, period) => {
        const k = 2 / (period + 1);
        const result = new Array(data.length).fill(null);
        // Find the first window of `period` valid values for the initial SMA seed
        let seedSum = 0, seedCount = 0, seedEnd = -1;
        for (let i = 0; i < data.length; i++) {
            const v = parseFloat(data[i]);
            if (!isNaN(v)) {
                seedSum += v;
                seedCount++;
                if (seedCount === period) { seedEnd = i; break; }
            }
        }
        if (seedEnd === -1) return result;
        let ema = seedSum / period;
        result[seedEnd] = ema;
        for (let i = seedEnd + 1; i < data.length; i++) {
            const v = parseFloat(data[i]);
            if (isNaN(v)) { result[i] = ema; continue; }
            ema = v * k + ema * (1 - k);
            result[i] = ema;
        }
        return result;
    };

    const enabledMAs = (maConfig || DEFAULT_MA_CONFIG).filter(ma => ma.enabled);
    const maDatasets = enabledMAs.map(ma => {
        const full = ma.type === 'ema'
            ? computeEMA(allCloses, ma.period)
            : computeSMA(allCloses, ma.period);
        return {
            label: `${ma.period} ${ma.type.toUpperCase()}`,
            data: full.slice(seedLen),
            borderWidth: 1,
            borderColor: ma.color,
            borderDash: ma.dash === 'dashed' ? [6, 4] : [],
            backgroundColor: 'transparent',
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0.3,
            spanGaps: false,
        };
    });

    // ── Bollinger Bands ──
    const computeBB = (data, period, multiplier) => {
        const middle = computeSMA(data, period);
        const upper = new Array(data.length).fill(null);
        const lower = new Array(data.length).fill(null);
        for (let i = period - 1; i < data.length; i++) {
            if (middle[i] === null) continue;
            const window = data.slice(i - period + 1, i + 1).map(v => parseFloat(v));
            if (window.some(v => isNaN(v))) continue;
            const mean = middle[i];
            const variance = window.reduce((sum, v) => sum + (v - mean) ** 2, 0) / period;
            const stddev = Math.sqrt(variance);
            upper[i] = mean + multiplier * stddev;
            lower[i] = mean - multiplier * stddev;
        }
        return { middle, upper, lower };
    };

    const bbDatasets = [];
    if (bbConfig && bbConfig.enabled) {
        const bb = computeBB(allCloses, bbConfig.period, bbConfig.multiplier);
        const bbColor = bbConfig.color || '#e8a838';
        // Parse hex to rgb for opacity variants
        const hexToRgb = (hex) => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `${r},${g},${b}`;
        };
        const rgb = hexToRgb(bbColor);
        // Upper band
        bbDatasets.push({
            label: 'BB Upper',
            data: bb.upper.slice(seedLen),
            borderWidth: 1,
            borderColor: bbColor,
            backgroundColor: 'transparent',
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0.3,
            spanGaps: false,
        });
        // Lower band — fill to previous dataset (upper) when fill enabled
        bbDatasets.push({
            label: 'BB Lower',
            data: bb.lower.slice(seedLen),
            borderWidth: 1,
            borderColor: bbColor,
            backgroundColor: bbConfig.fill ? `rgba(${rgb},0.10)` : 'transparent',
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: bbConfig.fill ? '-1' : false,
            tension: 0.3,
            spanGaps: false,
        });
        // Middle band (SMA basis) — dashed, reduced opacity
        bbDatasets.push({
            label: 'BB Middle',
            data: bb.middle.slice(seedLen),
            borderWidth: 1,
            borderColor: `rgba(${rgb},0.5)`,
            borderDash: [4, 4],
            backgroundColor: 'transparent',
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0.3,
            spanGaps: false,
        });
    }

    // ── Seasonal Projection computation ──
    const projectionResult = useMemo(() => {
        const empty = { extraLabels: [], projectionData: [], projectionCount: 0 };
        if (!showCurrentLineChart || !showProjection || !consolidatedSeasonalData || consolidatedSeasonalData.length === 0 || labels.length === 0 || dataClose.length === 0) {
            return empty;
        }

        const lastClosePrice = dataClose[dataClose.length - 1];
        if (lastClosePrice == null || isNaN(lastClosePrice)) return empty;

        // Build MM-DD → cycle index lookup. The cycle is 365 calendar days starting at
        // chart_start_date; we walk by index (not by MM-DD) so the cycle boundary is
        // continuous instead of producing a wrap-around cliff for trending stocks.
        const cycleLen = consolidatedSeasonalData.length;
        const mmddToIdx = {};
        for (let i = 0; i < cycleLen; i++) {
            const mmdd = consolidatedSeasonalData[i][0].substring(5);
            if (mmddToIdx[mmdd] === undefined) mmddToIdx[mmdd] = i;
        }

        // Find todayIdx for the last price chart date (anchor of the projection)
        const lastLabel = labels[labels.length - 1]; // "YYYY-MM-DD"
        const todayMmdd = lastLabel.substring(5);
        let todayIdx = mmddToIdx[todayMmdd];
        // Fallback for Feb 29 or any MM-DD missing from cycle: closest prior MM-DD
        if (todayIdx === undefined) {
            const sortedMmdds = Object.keys(mmddToIdx).sort();
            let closest = null;
            for (const k of sortedMmdds) {
                if (k <= todayMmdd) closest = k;
                else break;
            }
            if (closest === null) closest = sortedMmdds[sortedMmdds.length - 1];
            todayIdx = mmddToIdx[closest];
        }
        const todayReturn = consolidatedSeasonalData[todayIdx][1];

        // Cycle drift: the implied annual normalized appreciation. Used to keep the
        // projection continuous when it walks past the last cycle row and wraps.
        const cycleDrift = consolidatedSeasonalData[cycleLen - 1][1] - consolidatedSeasonalData[0][1];

        // Generate future dates (skip weekends; for weekly, one point per week)
        const periodDays = parseInt(projectionPeriod, 10) || 30;
        const isWeeklyProj = priceChartTimeframe === 'weekly';
        // Map period to calendar weeks: 14→2wk, 30→4wk, 60→8wk, 90→13wk
        const weeklyPointsMap = { 14: 2, 30: 4, 60: 8, 90: 13 };
        const numPoints = isWeeklyProj ? (weeklyPointsMap[periodDays] || Math.round(periodDays / 7)) : periodDays;
        const lastDate = new Date(lastLabel);
        const futureDates = [];
        let d = new Date(lastDate);
        let tradingDayCount = 0;
        while (futureDates.length < numPoints) {
            d.setDate(d.getDate() + 1);
            const dow = d.getDay();
            if (dow === 0 || dow === 6) continue; // skip weekends
            tradingDayCount++;
            if (isWeeklyProj) {
                // Emit a point every 5 trading days (end of each week)
                if (tradingDayCount % 5 !== 0) continue;
            }
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            futureDates.push(`${yyyy}-${mm}-${dd}`);
        }

        // Build projection prices by walking the cycle linearly. cumulativeOffset
        // carries the annual drift across each wrap so the projection stays continuous.
        const extraLabels = [];
        const projectionValues = [];
        let cycleIdx = todayIdx;
        let cumulativeOffset = 0;
        let prevDate = new Date(lastDate);
        for (const fDate of futureDates) {
            const curDate = new Date(fDate);
            const daysDiff = Math.round((curDate - prevDate) / 86400000);
            cycleIdx += daysDiff;
            while (cycleIdx >= cycleLen) {
                cycleIdx -= cycleLen;
                cumulativeOffset += cycleDrift;
            }
            const futureReturn = consolidatedSeasonalData[cycleIdx][1] + cumulativeOffset;
            const projectedPrice = lastClosePrice * (1 + (futureReturn - todayReturn) / 100);
            extraLabels.push(fDate);
            projectionValues.push(projectedPrice);
            prevDate = curDate;
        }

        // Build full projection array: nulls for existing data, then connection point + future
        const projectionData = new Array(dataClose.length - 1).fill(null);
        projectionData.push(lastClosePrice); // connection point at last close
        projectionData.push(...projectionValues);

        return { extraLabels, projectionData, projectionCount: futureDates.length };
    }, [showCurrentLineChart, showProjection, consolidatedSeasonalData, labels, dataClose, projectionPeriod, priceChartTimeframe]);

    // Extend labels and pad datasets when projection is active
    const projCount = projectionResult.projectionCount;
    const extendedLabels = projCount > 0 ? [...labels, ...projectionResult.extraLabels] : labels;
    const paddedDataClose = projCount > 0 ? [...dataClose, ...new Array(projCount).fill(null)] : dataClose;
    const paddedPointStyle = projCount > 0 ? [...pointStyle, ...new Array(projCount).fill('')] : pointStyle;
    const paddedOhlcData = projCount > 0 ? [...ohlcData, ...new Array(projCount).fill(null)] : ohlcData;
    const paddedVolumeData = projCount > 0 && volumeData.length > 0 ? [...volumeData, ...new Array(projCount).fill(null)] : volumeData;
    const paddedMaDatasets = projCount > 0 ? maDatasets.map(ds => ({ ...ds, data: [...ds.data, ...new Array(projCount).fill(null)] })) : maDatasets;
    const paddedBbDatasets = projCount > 0 ? bbDatasets.map(ds => ({ ...ds, data: [...ds.data, ...new Array(projCount).fill(null)] })) : bbDatasets;

    const isLineChart = priceChartType === 'line';
    // For candle/ohlc: compute y-axis bounds from OHLC range so wicks are fully visible
    let ohlcMin, ohlcMax;
    if (!isLineChart && ohlcData.length > 0) {
        const ohlcValid = ohlcData.filter(d => d != null);
        ohlcMin = Math.min(...ohlcValid.map(d => d.low));
        ohlcMax = Math.max(...ohlcValid.map(d => d.high));
        // Include projection values in bounds
        if (projCount > 0 && projectionResult.projectionData.length > 0) {
            const projValues = projectionResult.projectionData.filter(v => v != null);
            if (projValues.length > 0) {
                ohlcMin = Math.min(ohlcMin, ...projValues);
                ohlcMax = Math.max(ohlcMax, ...projValues);
            }
        }
        const pad = (ohlcMax - ohlcMin) * 0.02 || 1;
        ohlcMin -= pad;
        ohlcMax += pad;
    }

    const data = {
        labels: extendedLabels,
        datasets: [
            { fill: true },
            {
                borderWidth: isLineChart ? 1 : 0,
                pointBorderWidth: isLineChart ? 0.1 : 0,
                pointRadius: isLineChart ? undefined : 0,
                data: paddedDataClose,
                backgroundColor: isLineChart ? tc.lineFill : 'transparent',
                borderColor: isLineChart ? tc.lineColor : 'transparent',
                pointStyle: isLineChart ? paddedPointStyle : undefined,
            },
            ...paddedMaDatasets,
            ...paddedBbDatasets,
            ...(projCount > 0 && projectionResult.projectionData.length > 0 ? [{
                label: `Seasonal Projection (${projectionPeriod || 30}d)`,
                data: projectionResult.projectionData,
                borderWidth: 2,
                borderColor: '#e8a838',
                borderDash: [8, 4],
                backgroundColor: 'transparent',
                pointRadius: 0,
                fill: false,
                tension: 0.3,
                spanGaps: false,
            }] : []),
            ...(showVolume && paddedVolumeData.length > 0 ? [{
                label: 'Volume',
                type: 'bar',
                data: paddedVolumeData,
                yAxisID: 'yVolume',
                backgroundColor: UITheme === 'dark' ? 'rgba(100,149,237,0.25)' : 'rgba(100,149,237,0.3)',
                borderWidth: 0,
                barPercentage: 0.4,
                categoryPercentage: 0.9,
                order: 10,
            }] : []),
        ],
    };
    //-------------------------------------------------
    const highlightBox = {

        drawTime: "afterDatasetsDraw",
        display: !showCurrentLineChart, // when showing the current chart don't place annotation for trade
        type: "box",
        xMin: x0,
        xMax: x1,
        // yMin: 50,
        // yMax: 97,
        backgroundColor: tradeBoxColor,
    }

    //-------------------------------------------------
    const tradeLine = {
        xMin: x0,
        xMax: x1,
        yMin: y0,
        yMax: y1,
        borderWidth: 1,
        borderDash: [5, 5],
        borderColor: tradeLineColor,
        display: !activeTrade
    }

    //-------------------------------------------------
    let axisFontSize = '20vw';
    let caretSize = '25';

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        axisFontSize = '14vw';
        caretSize = '22';
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
        axisFontSize = '18vw';
        caretSize = '25'
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        if (window.innerHeight > 1024) {
            axisFontSize = '15vw';
            caretSize = '35'
        }
        else axisFontSize = '12vw';
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape
        axisFontSize = '12vw';
    }
    else if (!rdd.isMobile) {                                       // desktop
        axisFontSize = '10vw';
        caretSize = '20';
    }

    const isMobilePortrait = rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth;

    const options = {
        animation: false,         // disable animation so re-renders don't cause visible flashing
        maintainAspectRatio: false,
        _squareGridColor: UITheme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
        scales: {
            x: {
                grid: {
                    display: false,
                },
                ticks: {
                    color: tc.tickColor,
                    font: { size: axisFontSize },
                    maxRotation: 0,
                    autoSkip: false,
                    callback: function (val, index) {
                        const labels = this.chart.data.labels;
                        const label = labels[index];
                        if (!label || label.length < 10) return null;
                        const dd = parseInt(label.substring(8, 10), 10);
                        const mm = label.substring(5, 7);
                        const prev = index > 0 ? labels[index - 1] : null;
                        const prevMM = prev && prev.length >= 10 ? prev.substring(5, 7) : null;
                        const prevDD = prev && prev.length >= 10 ? parseInt(prev.substring(8, 10), 10) : null;
                        // Month changed → this is the first trading day of a new month
                        if (prevMM && prevMM !== mm) {
                            // Year change (Jan) → show year
                            if (mm === '01') return label.substring(0, 4);
                            if (rdd.isMobile) {
                                const monthNames = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                                return monthNames[parseInt(mm, 10)] || mm;
                            }
                            return mm + '-01';
                        }
                        // Mid-month: first trading day on or after the 15th (skip on mobile portrait)
                        if (!isMobilePortrait && dd >= 15 && prevDD !== null && prevDD < 15) {
                            return mm + '-15';
                        }
                        return null;
                    },
                },
            },
            y: {
                beginAtZero: false,
                ...(ohlcMin !== undefined ? { min: ohlcMin, max: ohlcMax } : {}),
                grid: {
                    display: false,
                },
                ticks: { color: tc.tickColor, font: { size: axisFontSize }, },
            },
            ...(showVolume && paddedVolumeData.length > 0 ? {
                yVolume: {
                    position: 'right',
                    display: false,
                    beginAtZero: true,
                    max: Math.max(...paddedVolumeData.filter(v => v != null)) * 4,
                    grid: { display: false },
                },
            } : {}),
        },
        // showLine:false,
        plugins: {
            legend: {
                display: true,
                labels: {
                    filter: (item) => item.text && (enabledMAs.some(ma => item.text === `${ma.period} ${ma.type.toUpperCase()}`) || item.text === 'BB Upper' || item.text.startsWith('Seasonal Projection')),
                    boxWidth: 20,
                    boxHeight: 2,
                    font: { size: axisFontSize },
                    color: tc.tickColor,
                    padding: 4,
                },
            },
            annotation:
            {
                display: false,
                annotations: {
                    box1: highlightBox,
                    line1: tradeLine,

                }
            }
        }
    };

    //---------------------------------------

    const lArrowClicked = (event) => {
        SetBoxLocation('top-left');
    }
    //---------------------------------------
    const rArrowClicked = (event) => {
        SetBoxLocation('top-right');
    }

    const handleCloseStat = (event) => {
        SetStatDisplay('none');
        saveStatDisplay('none'); // this sets a cookie in stockLineChart.js
    }

    //---------------------------------------
    //   0    1    2      3
    // [top,left,width,height]
    const fWindowStyle = {
        width: statBoxCoordinates[2],
        height: statBoxCoordinates[3],
        top: statBoxCoordinates[0],
        left: statBoxCoordinates[1],
        fontSize: ffontSize(),
        fontWeight: '600',
        display: statDisplay,

        backgroundColor: fBackColor,
        border: '1px solid rgb(0,0,250,0.2)',

    }
    //---------------------------------------
    const fLeftArrowStyle = {
        // display: arrowDisp['left'],
        fill: 'white'
    }
    const fRightArrowStyle = {
        // display: arrowDisp['right'],
        fill: 'white'
    }

    // Keep refs in sync with latest state/props so the plugin (created once) reads live values
    ohlcDataRef.current = paddedOhlcData
    priceChartTypeRef.current = priceChartType
    wickColorRef.current = UITheme === 'dark' ? 'rgba(220,220,220,0.85)' : 'rgba(0,0,0,0.75)'
    priceLevelsRef.current = priceLevels
    selectedLevelIdRef.current = selectedLevelId
    drawingModeRef.current = drawingMode
    earningsRef.current = {
        filings: tradeDetailData?.earnings_filings || [],
        nextEst: tradeDetailData?.next_earnings_est || null,
        daysTo: tradeDetailData?.days_to_earnings ?? null,
        show: showEarnings,
    }

    // Square-grid plugin: draws dashed grid so cells are approximately square
    const squareGridPlugin = {
        id: 'squareGridPlugin',
        beforeDraw: (chart) => {
            const yScale = chart.scales.y;
            const xScale = chart.scales.x;
            if (!yScale || !xScale) return;
            const area = chart.chartArea;
            const chartH = area.bottom - area.top;
            const chartW = area.right - area.left;

            // Determine cell height from y-axis ticks
            const yTicks = yScale.ticks;
            if (!yTicks || yTicks.length < 2) return;
            const cellH = chartH / (yTicks.length - 1);
            if (cellH <= 0) return;

            // How many x cells fit at that same pixel size
            const xCellCount = Math.max(1, Math.round(chartW / cellH));

            const ctx = chart.ctx;
            const gridColor = chart.options._squareGridColor || 'rgba(128,128,128,0.06)';
            ctx.save();
            ctx.strokeStyle = gridColor;
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);

            // Draw vertical lines at equal spacing
            for (let i = 1; i < xCellCount; i++) {
                const x = area.left + (chartW / xCellCount) * i;
                ctx.beginPath();
                ctx.moveTo(x, area.top);
                ctx.lineTo(x, area.bottom);
                ctx.stroke();
            }

            // Draw horizontal lines (matching y ticks)
            for (let i = 0; i < yTicks.length; i++) {
                const y = yScale.getPixelForTick(i);
                ctx.beginPath();
                ctx.moveTo(area.left, y);
                ctx.lineTo(area.right, y);
                ctx.stroke();
            }

            ctx.restore();
        },
    };

    // Permanent watermark plugin - draws on every chart render
    const watermarkPlugin = {
        id: 'watermarkPlugin',
        afterDraw: (chart) => {
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            ctx.save();
            ctx.font = 'bold 14px Arial';
            ctx.fillStyle = UITheme === 'dark' ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'bottom';
            ctx.fillText('TradeWave.AI', chartArea.right - 10, chartArea.bottom - 8);
            ctx.restore();
        },
    };

    // Candlestick / OHLC drawing plugin (created once on mount — reads from refs for live values)
    const candlestickPlugin = {
        id: 'candlestickPlugin',
        afterDraw: (chart) => {
            const type = priceChartTypeRef.current;
            if (type === 'line') return;
            const bars = ohlcDataRef.current;
            if (!bars || bars.length === 0) return;
            // Use meta.data[i].x for exact per-data-point pixel positions (not ticks, which are skipped)
            const meta = chart.getDatasetMeta(1); // dataset 1 = close price line
            const yScale = chart.scales.y;
            if (!meta || !meta.data || meta.data.length === 0 || !yScale) return;
            const ctx = chart.ctx;
            const n = meta.data.length;
            const x0 = meta.data[0]?.x;
            const x1 = meta.data[1]?.x;
            const barW = n > 1 && x0 !== undefined && x1 !== undefined
                ? Math.max(1, Math.abs(x1 - x0) * 0.7)
                : 4;
            const upColor = '#26a69a';
            const downColor = '#ef5350';
            ctx.save();
            bars.forEach((bar, i) => {
                if (!bar) return;
                const pt = meta.data[i];
                if (!pt) return;
                const x = pt.x;
                if (x === undefined || isNaN(x)) return;
                const yH = yScale.getPixelForValue(bar.high);
                const yL = yScale.getPixelForValue(bar.low);
                const yO = yScale.getPixelForValue(bar.open);
                const yC = yScale.getPixelForValue(bar.close);
                const isUp = bar.close >= bar.open;
                const color = isUp ? upColor : downColor;
                if (type === 'candle') {
                    // Wick (black in light mode, light gray in dark mode)
                    ctx.beginPath();
                    ctx.strokeStyle = wickColorRef.current;
                    ctx.lineWidth = 1;
                    ctx.moveTo(x, yH);
                    ctx.lineTo(x, yL);
                    ctx.stroke();
                    // Body
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(1, Math.abs(yC - yO));
                    ctx.fillStyle = color;
                    ctx.fillRect(x - barW / 2, bodyTop, barW, bodyH);
                    ctx.strokeStyle = color;
                    ctx.strokeRect(x - barW / 2, bodyTop, barW, bodyH);
                } else { // ohlc
                    ctx.strokeStyle = color;
                    // Vertical high-low line
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.moveTo(x, yH);
                    ctx.lineTo(x, yL);
                    ctx.stroke();
                    // Open tick (left) and close tick (right) — thicker for visibility
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(x - barW / 2, yO);
                    ctx.lineTo(x, yO);
                    ctx.stroke();
                    ctx.beginPath();
                    ctx.moveTo(x, yC);
                    ctx.lineTo(x + barW / 2, yC);
                    ctx.stroke();
                }
            });
            ctx.restore();
        },
    };

    // Price level drawing plugin
    const priceLevelPlugin = {
        id: 'priceLevelPlugin',
        afterDraw: (chart) => {
            const levels = priceLevelsRef.current
            if (!levels || levels.length === 0) return
            const yScale = chart.scales.y
            if (!yScale) return
            const area = chart.chartArea
            const chartW = area.right - area.left
            const ctx = chart.ctx
            ctx.save()
            levels.forEach(level => {
                const py = yScale.getPixelForValue(level.price)
                if (py < area.top - 5 || py > area.bottom + 5) { ctx.restore(); ctx.save(); return }
                const x0px = area.left + level.x0 * chartW
                const x1px = area.left + level.x1 * chartW
                const isSelected = level.id === selectedLevelIdRef.current
                // Draw line
                ctx.beginPath()
                ctx.strokeStyle = level.color
                ctx.lineWidth = isSelected ? 2.5 : 1.5
                ctx.setLineDash(level.dash === 'dashed' ? [6, 4] : [])
                ctx.moveTo(x0px, py)
                ctx.lineTo(x1px, py)
                ctx.stroke()
                ctx.setLineDash([])
                // Price label above middle of line
                const midX = (x0px + x1px) / 2
                const priceLabel = level.price < 5 ? level.price.toFixed(2) : Math.round(level.price).toString()
                ctx.font = '10px Arial'
                ctx.fillStyle = level.color
                ctx.textBaseline = 'bottom'
                ctx.textAlign = 'center'
                ctx.fillText(priceLabel, midX, py - 3)
                // Handles when selected
                if (isSelected) {
                    ;[x0px, x1px].forEach(hx => {
                        ctx.beginPath()
                        ctx.arc(hx, py, 5, 0, Math.PI * 2)
                        ctx.fillStyle = level.color
                        ctx.fill()
                        ctx.strokeStyle = 'white'
                        ctx.lineWidth = 1.5
                        ctx.stroke()
                    })
                }
            })
            ctx.restore()
        },
    }

    // Earnings date marker plugin — draws professional vertical markers + badges
    // Format "YYYY-MM-DD" → "Jan 29, 2026"
    const fmtEarningsDate = (dateStr) => {
        const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const [y, mo, d] = dateStr.split('-');
        return `${m[parseInt(mo, 10) - 1]} ${parseInt(d, 10)}, ${y}`;
    };

    const earningsPlugin = {
        id: 'earningsPlugin',
        afterEvent: (chart, args) => {
            const event = args.event;
            const hr = earningsHoverRef.current;
            if (event.type === 'mousemove') {
                hr.mouseX = event.x;
                hr.mouseY = event.y;
                const area = chart.chartArea;
                const isNear = area && hr.positions.some(p =>
                    Math.abs(event.x - p.px) < 12 && event.y >= area.top && event.y <= area.bottom + 20
                );
                if (isNear || hr.wasHovering) {
                    args.changed = true;
                }
                hr.wasHovering = isNear;
            } else if (event.type === 'mouseout') {
                hr.mouseX = -1;
                hr.mouseY = -1;
                if (hr.wasHovering) {
                    args.changed = true;
                    hr.wasHovering = false;
                }
            }
        },
        afterDraw: (chart) => {
            const ed = earningsRef.current;
            const hr = earningsHoverRef.current;
            hr.positions = [];
            if (!ed.show) return;
            const filings = ed.filings;
            const nextEst = ed.nextEst;
            if ((!filings || filings.length === 0) && !nextEst) return;

            const xScale = chart.scales.x;
            const yScale = chart.scales.y;
            if (!xScale || !yScale) return;
            const area = chart.chartArea;
            const ctx = chart.ctx;
            const chartLabels = chart.data.labels;
            if (!chartLabels || chartLabels.length === 0) return;

            // Build label→pixel-index lookup for fast matching
            const labelIndexMap = {};
            for (let i = 0; i < chartLabels.length; i++) {
                labelIndexMap[chartLabels[i]] = i;
            }

            const meta = chart.getDatasetMeta(1);
            if (!meta || !meta.data) return;

            const isDark = (chart.options._squareGridColor || '').includes('255,255,255');

            // Helper: get pixel X for a date — exact match first, then nearest label
            // (weekly mode labels are end-of-week dates that won't match daily earnings dates)
            const getPixelX = (dateStr) => {
                const idx = labelIndexMap[dateStr];
                if (idx !== undefined && meta.data[idx]) {
                    return meta.data[idx].x;
                }
                // Find nearest chart label within 6 days (covers weekly buckets)
                let bestIdx = -1;
                let bestDiff = Infinity;
                const target = new Date(dateStr).getTime();
                for (let i = 0; i < chartLabels.length; i++) {
                    const diff = Math.abs(new Date(chartLabels[i]).getTime() - target);
                    if (diff < bestDiff) {
                        bestDiff = diff;
                        bestIdx = i;
                    }
                }
                if (bestIdx >= 0 && bestDiff <= 6 * 86400000 && meta.data[bestIdx]) {
                    return meta.data[bestIdx].x;
                }
                return null;
            };

            // Helper: draw a single earnings marker
            const drawMarker = (px, isProjected, form, dateStr) => {
                if (px === null || px < area.left || px > area.right) return;

                // Record position for hover detection
                hr.positions.push({ px, date: dateStr, isProjected, form });

                ctx.save();

                // Vertical dashed line
                ctx.beginPath();
                ctx.setLineDash(isProjected ? [6, 3] : [4, 4]);
                ctx.lineWidth = isProjected ? 1.5 : 1;
                ctx.strokeStyle = isProjected
                    ? (isDark ? 'rgba(0, 200, 255, 0.55)' : 'rgba(0, 150, 220, 0.55)')
                    : (isDark ? 'rgba(200, 80, 200, 0.45)' : 'rgba(170, 50, 170, 0.45)');
                ctx.moveTo(px, area.top);
                ctx.lineTo(px, area.bottom);
                ctx.stroke();
                ctx.setLineDash([]);

                // Badge at top of chart
                const badgeY = area.top + 10;
                const badgeH = 14;
                const badgeW = isProjected ? 22 : 14;
                const badgeX = px - badgeW / 2;
                const radius = 3;

                // Badge background
                ctx.beginPath();
                ctx.moveTo(badgeX + radius, badgeY);
                ctx.lineTo(badgeX + badgeW - radius, badgeY);
                ctx.quadraticCurveTo(badgeX + badgeW, badgeY, badgeX + badgeW, badgeY + radius);
                ctx.lineTo(badgeX + badgeW, badgeY + badgeH - radius);
                ctx.quadraticCurveTo(badgeX + badgeW, badgeY + badgeH, badgeX + badgeW - radius, badgeY + badgeH);
                ctx.lineTo(badgeX + radius, badgeY + badgeH);
                ctx.quadraticCurveTo(badgeX, badgeY + badgeH, badgeX, badgeY + badgeH - radius);
                ctx.lineTo(badgeX, badgeY + radius);
                ctx.quadraticCurveTo(badgeX, badgeY, badgeX + radius, badgeY);
                ctx.closePath();

                if (isProjected) {
                    ctx.fillStyle = isDark ? 'rgba(0, 180, 240, 0.85)' : 'rgba(0, 140, 200, 0.85)';
                } else {
                    ctx.fillStyle = isDark ? 'rgba(200, 80, 200, 0.85)' : 'rgba(170, 50, 170, 0.85)';
                }
                ctx.fill();

                // Badge text
                ctx.font = 'bold 9px Arial';
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(isProjected ? 'Est' : 'E', px, badgeY + badgeH / 2);

                ctx.restore();
            };

            // Draw past earnings markers
            // Prefer 8-K/E (announcement day) — skip 10-Q/10-K when a preceding 8-K/E
            // exists within 45 days (annual 10-K can lag the announcement by up to ~5 weeks)
            // Fall back to 10-Q/10-K when no 8-K/E data is available (varies by company)
            if (filings && filings.length > 0) {
                const dates8K = [];
                for (const f of filings) {
                    if (f.form === '8-K/E') dates8K.push(new Date(f.date).getTime());
                }
                for (const f of filings) {
                    if (f.form !== '8-K/E' && dates8K.length > 0) {
                        // Skip 10-Q/10-K if a preceding 8-K/E exists within 30 days
                        const fTime = new Date(f.date).getTime();
                        let skip = false;
                        for (const d8Time of dates8K) {
                            const diff = fTime - d8Time;
                            if (diff >= 0 && diff <= 45 * 86400000) { skip = true; break; }
                        }
                        if (skip) continue;
                    }
                    const px = getPixelX(f.date);
                    if (px !== null) {
                        drawMarker(px, false, f.form, f.date);
                    }
                }
            }

            // Draw projected next earnings marker
            if (nextEst && ed.daysTo !== null && ed.daysTo >= 0) {
                const px = getPixelX(nextEst);
                if (px !== null) {
                    drawMarker(px, true, null, nextEst);
                }
            }

            // Draw hover tooltip
            if (hr.mouseX >= 0 && hr.positions.length > 0) {
                let closest = null;
                let closestDist = Infinity;
                for (const p of hr.positions) {
                    const dist = Math.abs(hr.mouseX - p.px);
                    if (dist < 12 && dist < closestDist && hr.mouseY >= area.top && hr.mouseY <= area.bottom + 20) {
                        closest = p;
                        closestDist = dist;
                    }
                }
                if (closest) {
                    const label = closest.isProjected
                        ? `Est. Earnings: ${fmtEarningsDate(closest.date)}`
                        : `Earnings: ${fmtEarningsDate(closest.date)}`;
                    ctx.save();
                    ctx.font = '11px Arial';
                    const textW = ctx.measureText(label).width;
                    const tipW = textW + 14;
                    const tipH = 22;
                    const tipRadius = 4;
                    // Position tooltip below the badge, clamped within chart area
                    let tipX = closest.px - tipW / 2;
                    tipX = Math.max(area.left + 2, Math.min(area.right - tipW - 2, tipX));
                    const tipY = area.top + 30;

                    // Tooltip background
                    ctx.beginPath();
                    ctx.moveTo(tipX + tipRadius, tipY);
                    ctx.lineTo(tipX + tipW - tipRadius, tipY);
                    ctx.quadraticCurveTo(tipX + tipW, tipY, tipX + tipW, tipY + tipRadius);
                    ctx.lineTo(tipX + tipW, tipY + tipH - tipRadius);
                    ctx.quadraticCurveTo(tipX + tipW, tipY + tipH, tipX + tipW - tipRadius, tipY + tipH);
                    ctx.lineTo(tipX + tipRadius, tipY + tipH);
                    ctx.quadraticCurveTo(tipX, tipY + tipH, tipX, tipY + tipH - tipRadius);
                    ctx.lineTo(tipX, tipY + tipRadius);
                    ctx.quadraticCurveTo(tipX, tipY, tipX + tipRadius, tipY);
                    ctx.closePath();
                    ctx.fillStyle = isDark ? 'rgba(30, 30, 50, 0.92)' : 'rgba(255, 255, 255, 0.95)';
                    ctx.fill();
                    ctx.strokeStyle = closest.isProjected
                        ? (isDark ? 'rgba(0, 200, 255, 0.7)' : 'rgba(0, 140, 200, 0.7)')
                        : (isDark ? 'rgba(200, 80, 200, 0.7)' : 'rgba(170, 50, 170, 0.7)');
                    ctx.lineWidth = 1;
                    ctx.stroke();

                    // Tooltip text
                    ctx.fillStyle = isDark ? '#e0e0e0' : '#1a1a1a';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(label, tipX + tipW / 2, tipY + tipH / 2);
                    ctx.restore();
                }
            }
        },
    };

    // Mouse interaction for price levels
    useEffect(() => {
        const chart = chartRef.current
        if (!chart) return
        const canvas = chart.canvas

        const hitTestLevels = (mx, my) => {
            const ch = chartRef.current
            if (!ch) return null
            const area = ch.chartArea
            const yScale = ch.scales.y
            if (!area || !yScale) return null
            const chartW = area.right - area.left
            const levels = priceLevelsRef.current
            for (let i = levels.length - 1; i >= 0; i--) {
                const level = levels[i]
                const py = yScale.getPixelForValue(level.price)
                const x0px = area.left + level.x0 * chartW
                const x1px = area.left + level.x1 * chartW
                // Handle check (selected level only)
                if (level.id === selectedLevelIdRef.current) {
                    if (Math.hypot(mx - x0px, my - py) <= 8) return { type: 'resize-left', levelId: level.id }
                    if (Math.hypot(mx - x1px, my - py) <= 8) return { type: 'resize-right', levelId: level.id }
                }
                // Line body check
                if (mx >= x0px - 6 && mx <= x1px + 6 && Math.abs(my - py) <= 6) {
                    return { type: 'move', levelId: level.id }
                }
            }
            return null
        }

        const onMouseDown = (e) => {
            const ch = chartRef.current
            if (!ch) return
            const area = ch.chartArea
            const yScale = ch.scales.y
            if (!area || !yScale) return
            const rect = canvas.getBoundingClientRect()
            const mx = e.clientX - rect.left
            const my = e.clientY - rect.top
            // Ignore clicks outside chart area
            if (mx < area.left || mx > area.right || my < area.top || my > area.bottom) return

            if (drawingModeRef.current && SetPriceLevels && SetSelectedLevelId && SetDrawingMode) {
                // Create new level
                const price = yScale.getValueForPixel(my)
                const chartW = area.right - area.left
                const clickFrac = (mx - area.left) / chartW
                const newLevel = {
                    id: Date.now().toString(36) + Math.random().toString(36).substr(2, 4),
                    price,
                    x0: Math.max(0, clickFrac),
                    x1: 1,
                    color: '#38b8e8',
                    dash: 'dashed',
                }
                SetPriceLevels(prev => [...prev, newLevel])
                SetSelectedLevelId(newLevel.id)
                SetDrawingMode(false)
                return
            }

            const hit = hitTestLevels(mx, my)
            if (hit) {
                if (SetSelectedLevelId) SetSelectedLevelId(hit.levelId)
                const level = priceLevelsRef.current.find(l => l.id === hit.levelId)
                if (level) {
                    dragRef.current = {
                        type: hit.type,
                        levelId: hit.levelId,
                        startY: my,
                        startPrice: level.price,
                        startX0: level.x0,
                        startX1: level.x1,
                    }
                }
            } else {
                if (SetSelectedLevelId) SetSelectedLevelId(null)
            }
        }

        const onMouseMove = (e) => {
            const ch = chartRef.current
            if (!ch) return
            const area = ch.chartArea
            const yScale = ch.scales.y
            if (!area || !yScale) return
            const rect = canvas.getBoundingClientRect()
            const mx = e.clientX - rect.left
            const my = e.clientY - rect.top
            const chartW = area.right - area.left
            const drag = dragRef.current

            if (drag.type && SetPriceLevels) {
                if (drag.type === 'move') {
                    const newPrice = yScale.getValueForPixel(my)
                    const minPrice = yScale.getValueForPixel(area.bottom)
                    const maxPrice = yScale.getValueForPixel(area.top)
                    const clamped = Math.max(Math.min(minPrice, maxPrice), Math.min(Math.max(minPrice, maxPrice), newPrice))
                    SetPriceLevels(prev => prev.map(l => l.id === drag.levelId ? { ...l, price: clamped } : l))
                } else if (drag.type === 'resize-left' || drag.type === 'resize-right') {
                    let frac = (mx - area.left) / chartW
                    frac = Math.max(0, Math.min(1, frac))
                    SetPriceLevels(prev => prev.map(l => {
                        if (l.id !== drag.levelId) return l
                        if (drag.type === 'resize-left') {
                            return { ...l, x0: Math.min(frac, l.x1 - 0.02) }
                        } else {
                            return { ...l, x1: Math.max(frac, l.x0 + 0.02) }
                        }
                    }))
                }
                return
            }

            // Update cursor based on hover
            if (drawingModeRef.current) {
                if (mx >= area.left && mx <= area.right && my >= area.top && my <= area.bottom) {
                    canvas.style.cursor = 'crosshair'
                } else {
                    canvas.style.cursor = 'default'
                }
                return
            }
            const hit = hitTestLevels(mx, my)
            if (hit) {
                canvas.style.cursor = hit.type === 'move' ? 'ns-resize' : 'ew-resize'
            } else {
                canvas.style.cursor = 'default'
            }
        }

        const onMouseUp = () => {
            dragRef.current = { type: null, levelId: null, startY: 0, startPrice: 0, startX0: 0, startX1: 0 }
        }

        canvas.addEventListener('mousedown', onMouseDown)
        canvas.addEventListener('mousemove', onMouseMove)
        canvas.addEventListener('mouseup', onMouseUp)
        window.addEventListener('mouseup', onMouseUp)

        return () => {
            canvas.removeEventListener('mousedown', onMouseDown)
            canvas.removeEventListener('mousemove', onMouseMove)
            canvas.removeEventListener('mouseup', onMouseUp)
            window.removeEventListener('mouseup', onMouseUp)
        }
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    //------------------------------------------------------------------------------------------
    return (
        <div style={{ backgroundColor: UIcolors(loggedinUser, UITheme)['background_price_chart'], height: "100%" }}>

            {/* floating window section */}
            <div className='f-parent' style={fWindowStyle} >
                <div className='f-row-title' style={{ backgroundColor: 'rgb(200,0,0,0.2)' }}>
                    <div className='title-left' onClick={lArrowClicked} >
                        {boxLocation === 'top-left'
                            ? <BiX size={caretSize} style={fLeftArrowStyle} onClick={handleCloseStat} />
                            : <BsFillCaretLeftFill size={caretSize} style={fLeftArrowStyle} />
                        }
                    </div>

                    <div className='title-center'><span style={{ color: 'red', paddingRight: '2px' }}>{showActive}</span>Trade Stats</div>
                    <div className='title-right' onClick={rArrowClicked} >

                        {boxLocation === 'top-right'
                            ? <BiX size={caretSize} style={fLeftArrowStyle} onClick={handleCloseStat} />
                            : <BsFillCaretRightFill size={caretSize} style={fRightArrowStyle} />
                        }
                    </div>
                </div>
                <div className='f-row'>
                    <div className='f-cell-left f-row-A'>Trade Dir</div>
                    <div className='f-cell-right f-row-A'>{barChartLongOrShort}</div>
                </div>
                <div className='f-row'>
                    <div className='f-cell-left f-row-B'>Entry Price</div>
                    <div className='f-cell-right f-row-B'>{y0}</div>
                </div>
                <div className='f-row'>
                    {activeTrade === true
                        ? <div className='f-cell-left f-row-A'>Current Price</div>
                        : <div className='f-cell-left f-row-A'>Exit Price</div>
                    }
                    <div className='f-cell-right f-row-A'>{y1}</div>
                </div>
                <div className='f-row'>
                    <div className='f-cell-left f-row-B'>profit</div>

                    <div className='f-cell-right f-row-B' style={{ color: profitColor }}>{profit}  {profitP}</div>
                </div>
            </div>
            {/* end floating window section */}

            <div style={{ height: '100%', width: '100%' }}>
                <Line ref={chartRef} data={data} options={options} plugins={[squareGridPlugin, candlestickPlugin, earningsPlugin, priceLevelPlugin, watermarkPlugin]} />
            </div>
        </div>
    )
}

export default LineChart
