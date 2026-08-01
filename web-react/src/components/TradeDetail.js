import React, { useState, useEffect, useContext, useImperativeHandle } from 'react'

import GenericLineChart from './GenericLineChart'
import './styles/TradeDetail.css'
import { UserContext } from './UserContext'
import { incrementDate } from './Common'

import VisualTable from './VisualTable'
import VisualTableDesc from './VisualTableDesc'
import { cumulativeReturn } from './Common'
import { monthsOptionsListS, getTodayDate, appserverURL } from './Common'
import { AiOutlineFileJpg } from 'react-icons/ai'
import { GrDocumentCsv } from "react-icons/gr";
import { HiOutlineClipboardDocumentList } from "react-icons/hi2"
import Tippy from '@tippyjs/react'
import { CSVLink, CSVDownload } from "react-csv";
import { BsFillCircleFill } from "react-icons/bs"
import { BiExport, BiClipboard } from 'react-icons/bi'
import { BsReverseBackspaceReverse, BsDownload, BsTable, BsGlobe, BsShareFill, BsPencilSquare } from 'react-icons/bs';
import { FaGlobe, RxGlobe, SlGlobe, FaShareAlt } from 'react-icons/fa'
// import { csvIcon, downloadIcon, jpgIcon, listIcon, list2Icon, list3Icon } from './svg';
import { opp_dashboard_dialog_content } from './Common'
import { brand } from './Common'
import { UIcolors, themeColors } from './Common';
import { markCaptureReady, clearCaptureReady } from './captureReady'
import { hasUsableTrendScore, trendAlignmentLabel } from './trendScoreState'

const TradeDetail = (props) => {
    const tc = themeColors(props.UITheme)



    // const toggle_width = '2vw';

    const { browserH, browserW, rdd, infoTextSize, loggedinUser, token } = useContext(UserContext)

    const [tradeReportData, SetTradeReportData] = useState({ 'heading': 'heading value' })

    const [vtTradeDetail, SetVtTradeDetail] = useState({ 'Symbol': props.symbol, 'Trade Direction': 'long', 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })

    const [vtStrategyPL, SetVTStrategyPL] = useState({ 'Num Losers': '0', 'Num Winners': '10', 'Percent Profitable': '100%', 'Biggest Winnder': '25.41%' })

    const [vtWaveStats, SetVTWaveStats] = useState({ 'Avg Loss': '0', 'Avg Gain': '0%', 'Median Gain': '0%', 'Std Dev': '0%' })



    const [cumulativeGrowth, SetCumulativeGrowth] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthCompare, SetCumulativeGrowthCompare] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthL, SetCumulativeGrowthL] = useState(['2009', '2010', '2011', '2000', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])

    const [lsIcon, SetLsIcon] = useState('')
    const [ssIcon, SetSsIcon] = useState('')

    const [csvData, SetCsvData] = useState([
        ["firstname", "lastname", "email"],
        ["Ahmed", "Tomi", "ah@smthing.co.com"],
        ["Raed", "Labes", "rl@smthing.co.com"],
        ["Yezzi", "Min l3b", "ymin@cocococo.com"]
    ])

    const [mqx, SetMqx] = useState(''); // extension added to the csv file export only when Months and Qtrs are selected

    let compared_security = props.compareSecurity[1] + ' Return'; // this is the key for the compared security

    let tradeDetailControlsHeight = '8%'
    let tradeDetailHeight = '92%'

    // let tradeDetailDescFontSize = '2.9vw'


    const tradeDetailToolTips = {
        'Symbol': 'Ticker Symbol for the strategy',
        'Trade Direction': 'Direction of the strategy.  Either Long or Short',
        'Entry Date': 'Start date of the seasonal pattern',
        'Calendar Days Hold': 'Number of calendar days the pattern is held, from entry to exit. You can see the date range determined by start-date and days-hold on the header of the seasonal viewer',
        'Avg Loss': 'Average loss across the losing years in this pattern',
        'Avg Gain': 'Avg Gain shows two values: The first number is the average gain of winning years only, which reflects the typical return when the pattern is profitable. The second number is the overall average gain, which includes both winning and losing years, giving a broader view of the pattern’s performance over time.',
        'Median Profit': 'Median profit for this seasonal pattern',
        'Std Dev': 'Standard Deviation of the profits year to year.  This percentage shows the amount of fluctuation in the profits year to year',
        'Num Losers': 'Number of losing years in this seasonal pattern',
        'Num Winners': 'Number of winning years in this seasonal pattern',
        'Percent Profitable': 'Percentage of years that were profitable; 100% means every year was profitable',
        'Cumulative Return': 'Cumulative return of the seasonal pattern over the number of historical years being analyzed',
        'Sharpe Ratio': 'The Sharpe Ratio gauges the quality of a pattern by comparing its average profit to how much those profits vary year to year. Above 1 means the average profit is larger than the year-to-year fluctuation - a sign of a consistent pattern. Below 1 means the fluctuation outweighs the average profit. It is the default sort for the opportunity table.',
        'Trend Long': 'Trend Long measures whether price has been moving upward over roughly the last one to two weeks, on a scale of 0 to 100 as of ' + (props.lastPrice[0] || '') + '. A high score means recent movement supports a long direction. A low score means it has not been moving strongly upward; it is not a prediction that the seasonal pattern will lose. The arrow shows whether the score rose, fell, or stayed unchanged since the prior reading.',
        'Trend Short': 'Trend Short measures whether price has been moving downward over roughly the last one to two weeks, on a scale of 0 to 100 as of ' + (props.lastPrice[0] || '') + '. A high score means recent movement supports a short direction. A low score means it has not been moving strongly downward; it is not a prediction that the seasonal pattern will lose. The arrow shows whether the score rose, fell, or stayed unchanged since the prior reading.',
        'Trend Alignment': 'Compares recent price movement with this seasonal setup\'s direction. For a long setup, it uses Trend Long and asks whether price has recently been moving upward. For a short setup, it uses Trend Short and asks whether price has recently been moving downward. Aligned (above 60) means recent movement confirms that direction; Against (below 40) means it does not; Neutral (40-60) means no clear confirmation. This is separate from the historical win rate. Unavailable means no usable current score was returned.',

        'S&P 500 Buy & Hold': 'The S&P 500 return is the equivalent return of the S&P 500 index for the entire year. It is useful for comparing this pattern to a buy & hold of the broader market. The cumulative S&P 500 return is also shown as the dark red line on the Cumulative Return chart.',
        'Date Range': "The date range of a seasonal pattern defines the specific period each year when the pattern occurs. For example, a date range from March 5 to April 10 means we measure how the stock performed during this exact period in past years, using the closing price at the start and end of the range each year. This surfaces consistent tendencies - whether a stock has tended to rise or fall during this window - for you to evaluate.",
        'Median Gain': "Median Gain represents the middle value of all yearly returns when sorted in ascending order. Unlike the Average Gain, which calculates the mean of winning years, the Median Gain helps reduce the impact of extreme outliers, providing a more balanced view of typical returns.",







    }


    var svFont = '7vw';
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { // smartphone portrait
        svFont = '10vw';
    }


    const tradedetailControlsStyle = {
        height: tradeDetailControlsHeight,
        display: "flex",
        backgroundColor: tc.controlBar,
        justifyContent: props.seasonalBarChartData.length > 0 ? 'center' : 'left'
    }



    const tradeDetailDescStyle = {
        fontSize: infoTextSize,
        // backgroundColor: "gold",
        color: tc.textOnControl,
        flexGrow: "2",
        // alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        display: "flex"
    }


    const tradeDetailStyle = {
        height: tradeDetailHeight,
        backgroundColor: tc.panelBg,
        color: tc.text,
    }
    const tradeDetailReady =
        props.tradeDetailData &&
        !Array.isArray(props.tradeDetailData) &&
        Object.keys(props.tradeDetailData).length > 0

    useEffect(() => { clearCaptureReady('tradeDetail') }, [props.symbol]) // new symbol selected - a fresh fetch is starting upstream

    useEffect(() => {

        var cret = cumulativeReturn(props.seasonalBarChartData, props.barChartLongOrShort) //moved to common.js
        var cretCompare = cumulativeReturn(props.compareSecurityBarChartData, props.compareSecurityLongOrShort)


        SetCumulativeGrowth(cret['cdata'])
        SetCumulativeGrowthL(cret['cdataL'])

        SetCumulativeGrowthCompare(cretCompare['cdata'])

        // console.log("cretCompare=",cretCompare)


        if (props.symbol.length > 0 && props.startDate && props.startDate.length >= 10 && props.daysOut != null && tradeDetailReady) {



            let sd = props.startDate.substring(5);
            let m0 = parseInt(props.startDate.substring(5, 7)) - 1;

            // let ed = incrementDate(props.startDate, props.daysOut).substring(5, 10)
            // ed decremented by 1 for cosmetics 9/4/2022
            let ed = incrementDate(props.startDate, props.daysOut - 1).substring(5, 10)

            let m1 = parseInt(ed) - 1;

            // Guard against out-of-range month indices
            if (m0 < 0 || m0 > 11 || m1 < 0 || m1 > 11) return;

            // sd= monthsOptionsList[m]['label']+' ' + parseInt(props.startDate.substring(8)).toString() + '  ('+sd+')'
            sd = monthsOptionsListS[m0]['label'] + ' ' + parseInt(props.startDate.substring(8)).toString()
            ed = monthsOptionsListS[m1]['label'] + ' ' + parseInt(ed.substring(3, 5)).toString()

            // console.log('yyyy=', sd, ed)


            let trData = JSON.parse(JSON.stringify(props.tradeDetailData));



            // A numeric zero is valid market data only when the server explicitly says
            // the provider returned a score. Older responses used 0/0/0/0 as a missing
            // fallback, so keep that legacy shape from becoming a false "Against" label.
            const trendKey = props.barChartLongOrShort === 'long' ? 'Trend Long' : 'Trend Short'
            const trendScore = trData[trendKey]
            const trendScoreAvailable = hasUsableTrendScore(trData, props.barChartLongOrShort)

            if (trendScoreAvailable) {
                // Icons show whether each score improved versus its prior reading.
                if (trData['Trend Long'] > trData['Trend Long1']) SetLsIcon('u')
                else if (trData['Trend Long'] < trData['Trend Long1']) SetLsIcon('d')
                else SetLsIcon('n')

                if (trData['Trend Short'] > trData['Trend Short1']) SetSsIcon('u')
                else if (trData['Trend Short'] < trData['Trend Short1']) SetSsIcon('d')
                else SetSsIcon('n')

                const alignLabel = trendAlignmentLabel(trendScore)
                trData['Trend Alignment'] = alignLabel + ' (' + trendScore + ')'
            } else {
                SetLsIcon('')
                SetSsIcon('')
                trData['Trend Long'] = 'Unavailable'
                trData['Trend Short'] = 'Unavailable'
                trData['Trend Alignment'] = 'Unavailable'
            }
            delete trData['Trend Score Available']


            // for some reason the added item in the dict is there but not visible !!!! not sure why net 6/16/2022 - try adding it in appserver

            let largest = 0;
            let smallest = -0;
            for (var i = 0; i < props.seasonalBarChartData.length; i++) {
                let tmp = props.seasonalBarChartData[i]['pct'].split(',')[0];
                tmp = parseFloat(tmp);
                if (tmp > largest) largest = tmp;
                if (tmp < smallest) smallest = tmp;

                // props.barChartLongOrShort
            }

            // console.log('trData=',trData)

            SetTradeReportData(trData)
            // SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Entry Date': sd, 'Calendar Days Hold': props.daysOut })
            SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Date Range': sd + '-' + ed, 'Calendar Days Hold': props.daysOut })

            // if (props.barChartLongOrShort === 'long') {
            if (props.compareSecurityLongOrShort === 'long') {
                // SetVTStrategyPL({ 'Num Losers': trData['Num Losers'], 'Num Winners': trData['Num Winners'], 'Percent Profitable': trData['Percent Profitable'], 'Biggest Winner': largest.toString() + '%' })
                // SetVTStrategyPL({ 'Num Winners': trData['Num Winners'],'Num Losers': trData['Num Losers'],  'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 Buy & Hold': props.compareSecurityTradeDetailData['Cumulative Return'] })
                SetVTStrategyPL({ 'Num Winners': trData['Num Winners'], 'Num Losers': trData['Num Losers'], 'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 Buy & Hold': props.compareSecurityTradeDetailData['Cumulative Return'] })
            }

            else {
                // SetVTStrategyPL({ 'Num Losers': trData['Num Losers'], 'Num Winners': trData['Num Winners'], 'Percent Profitable': trData['Percent Profitable'], 'Biggest Winner': (-smallest).toString() + '%' })
                // SetVTStrategyPL({  'Num Winners': trData['Num Winners'],'Num Losers': trData['Num Losers'], 'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 Buy & Hold': props.compareSecurityTradeDetailData['Cumulative Return'] })
                SetVTStrategyPL({ 'Num Winners': trData['Num Winners'], 'Num Losers': trData['Num Losers'], 'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 Buy & Hold': props.compareSecurityTradeDetailData['Cumulative Return'] })
            }

            // vtWaveStats, SetVTWaveStats

            SetVTWaveStats({ 'Avg Loss': trData['Avg Loss'], 'Avg Gain': trData['Avg Profit'] + ', ' + trData['Avg Profit - All'], 'Median Gain': trData['Median Profit'], 'Std Dev': trData['Std Dev'] })

            let biggest_winner = largest;
            if (props.barChartLongOrShort !== 'long') biggest_winner = -smallest;

            let dr = props.monthsAndQtrs;

            if (dr === 'Months & Qtrs') dr = 'custom';

            let sya = props.seasonalYears;



            switch (sya) {
                case "pe0": sya = "Presidential Election Years"; break;
                case "pe1": sya = "Presidential Election+1 Years"; break;
                case "pe2": sya = "Presidential Election+2 Years"; break;
                case "pe3": sya = "Presidential Election+3 Years+1"; break;
            }

            let spxResult = props.compareSecurityTradeDetailData['Cumulative Return'];
            if (props.compareSecurityLongOrShort === 'short') spxResult += ' short';

            let csvTmp = [
                ["Report Date", getTodayDate()],
                ["Securities Group", props.selectedSecurity],
                ["Ticker", props.symbol],
                ["Securities Name", props.company],
                ["Opportunity Direction", props.barChartLongOrShort],
                ["Date1", sd],
                ["Date2", ed],
                ["Date Range", dr],
                ["Calendar Days Hold", props.daysOut],

                ["Historical Years Analyzed", sya],

                ["# Winners", trData['Num Winners']],
                ["# Losers", trData['Num Losers']],
                ["Percent Profitable", trData['Percent Profitable']],
                ["Biggest Winner", biggest_winner + '%'],
                ["Avg Loss", trData['Avg Loss']],
                ["Avg Profit", trData['Avg Profit']],
                ["Median Profit", trData['Median Profit']],
                ["Std Dev", trData['Std Dev']],
                ["Cumulative Return", trData['Cumulative Return']],
                ["S&P 500 Return", spxResult],
                ["Sharpe Ratio", trData['Sharpe Ratio']],

            ];
            // gain loss for each year
            for (i = 0; i < props.seasonalBarChartData.length; i++) {
                let y = props.seasonalBarChartData[i]['year'];
                let pct = props.seasonalBarChartData[i]['pct'].split(',');
                let price = props.seasonalBarChartData[i]['price'].split(',');
                let gainLoss = pct[0];
                if (props.barChartLongOrShort === 'short') {
                    let p = -parseFloat(pct[0]);
                    gainLoss = p.toString();
                }
                csvTmp.push([y + ' gain/loss', gainLoss + '%'])
            }
            // mfe percent
            for (i = 0; i < props.seasonalBarChartData.length; i++) {
                let y = props.seasonalBarChartData[i]['year'];
                let pct = props.seasonalBarChartData[i]['pct'].split(',');
                let price = props.seasonalBarChartData[i]['price'].split(',');
                if (props.barChartLongOrShort === 'long') csvTmp.push([y + ' MFE', pct[1] + '%'])
                else {
                    let mfe = (-parseFloat(pct[2])).toString();
                    csvTmp.push([y + ' MFE', mfe + '%']);
                }
            }
            // mae percent
            for (i = 0; i < props.seasonalBarChartData.length; i++) {
                let y = props.seasonalBarChartData[i]['year'];
                let pct = props.seasonalBarChartData[i]['pct'].split(',');
                let price = props.seasonalBarChartData[i]['price'].split(',');


                if (props.barChartLongOrShort === 'long') csvTmp.push([y + ' MAE', pct[2] + '%']);
                else {
                    let mae = (-parseFloat(pct[1])).toString();
                    csvTmp.push([y + ' MAE', mae + '%']);
                }

            }


            SetCsvData(csvTmp)
            markCaptureReady('tradeDetail', { symbol: props.symbol })

        }
        else {

            SetTradeReportData([])
            SetVtTradeDetail({})
            SetVTStrategyPL({})
            SetVTWaveStats({})
            SetCumulativeGrowth([])
            SetCumulativeGrowthL([])
            clearCaptureReady('tradeDetail')
        }

    }, [props.compareSecurityTradeDetailData, props.compareSecurityLongOrShort, props.compareSecurity[1], props.tradeDetailData, props.compareSecurityTradeDetailData, props.barChartLongOrShort, props.symbol, tradeDetailReady]);

    // console.log('tradeReportData=',tradeReportData)

    // add an extension for the csv file export if it was selected from month * qtrs pull down
    useEffect(() => {
        let mq = props.monthsAndQtrs;
        if (mq !== 'Months & Qtrs') SetMqx('_' + mq);
        else SetMqx('');
    }, [props.monthsAndQtrs]);
    //--------------------------------------------------------------------
    const handleSSSW = () => {
        props.SetStockScoreCurrent(!props.stockScoreCurrent)
    }
    //------------------------------------------------------------------------------------------
    const handleExport = () => {
        props.SetShowWatermark(true);
        props.SetExportImage(true)
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
    //------------------------------------------------------------------------------------------


    // console.log ('ttttttttttttttradeReportData=',tradeReportData)

    return (
        <div className="stock-detail-parent" style={{ backgroundColor: tc.panelBg, color: tc.text, borderColor: tc.border }}>


            <div className="trade-detail-controls-parent" style={tradedetailControlsStyle}>

                <div className="trade-detail-controls-left" >
                    {/* -------------------------------------------------------------------------------------------- */}
                    <Tippy  placement={'right'} disabled = {!props.tooltipSW} content={
                        <div theme="tw" >
                            {props.tooltipSW ? 'Portfolio Manager' : ''}
                        </div>
                    }>

                        {/* add padding below because I can't vertically center it when I use CSVLink component!!  */}
                        <div style={{ backgroundColor: 'transparent', color: 'white', paddingLeft: '3px', paddingRight: '10px', display: 'flex', alignItems: 'center' }}>
                            <BsPencilSquare size={20} style={{ fill: "white" }} onClick={handleDRreport} />
                        </div>

                    </Tippy>
                    {/* -------------------------------------------------------------------------------------------- */}


                    {props.symbol !== '' &&
                        <Tippy disabled = {!props.tooltipSW} placement={'right'} content={
                            <div theme="tw" >
                                {props.tooltipSW ? 'Export Strategy barchart and Strategy Report as Jpeg' : ''}
                            </div>
                        }>
                            <div style={{ backgroundColor: 'transparent', color: 'white', paddingLeft: '3px', paddingRight: '10px', display: 'flex', alignItems: 'center' }} >
                                {/* import {csvIcon, downloadIcon ,jpgIcon , listIcon,list2Icon,list3Icon} from './svg'; */}

                                <BsDownload size={20} style={{ fill: "white" }} onClick={handleExport} />
                            </div>
                        </Tippy>
                    }
                    {/* -------------------------------------------------------------------------------------------- */}

                    {props.symbol !== '' &&
                        <Tippy disabled = {!props.tooltipSW} placement={'right'} content={
                            <div theme="tw" >
                                {props.tooltipSW ? 'Export Strategy statistics as CSV' : ''}
                            </div>
                        }>

                            {/* add padding below because I can't vertically center it when I use CSVLink component!!  */}
                            <div style={{ paddingTop: '0.4vh', backgroundColor: 'transparent', color: 'white', paddingLeft: '3px', paddingRight: 'px', display: 'flex', alignItems: 'center' }} >
                                <CSVLink data={csvData} filename={props.symbol + " TradeWave Opportunity csv report" + mqx + ".csv"}  >
                                    <BsTable size={16} style={{ fill: "white" }} />
                                </CSVLink>
                            </div>

                        </Tippy>
                    }
                </div>

                {props.symbol !== ''
                    ?
                    <Tippy disabled = {!props.tooltipSW} placement={'bottom'} content={
                        <div theme="tw" >
                            {props.tooltipSW ? 'Security name + Strategy Date Range.  When ACTIVE label is displayed, current date is within the strategy date range' : ''}
                        </div>
                    }>
                        <div className="trade-detail-controls-mid" style={tradeDetailDescStyle}>
                            TradeWave Stats Date : {getTodayDate()} &nbsp; for &nbsp; <span style={{ color: UIcolors(loggedinUser, props.UITheme)['security_name'] }}><strong>{props.company}</strong></span>
                            <span style={{ color: 'red', fontSize: "1vw", paddingLeft: '10px' }}>{props.tradeActive ? "ACTIVE" : ""}</span>
                        </div>
                    </Tippy>
                    :
                    <div className="trade-detail-controls-mid" style={tradeDetailDescStyle}></div>
                }

                <div className="trade-detail-controls-right">


                    <Tippy  placement={'top'} content={
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
                        <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}> <BsFillCircleFill size={12} style={{ fill: "red" }} /></div>

                    </Tippy>



                    <Tippy placement={'top'} content={
                        <div theme="tw" >
                            {'Price Chart'}
                        </div>
                    }>
                        <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}> <BsFillCircleFill size={12} style={{ fill: "white" }} onClick={() => props.chartTo(2)} /></div>
                    </Tippy>

                </div>

            </div>
            {/* the stats tables start here  */}
            {
                props.symbol !== ''
                    ? tradeDetailReady
                    ? <div className="trade-detail" style={tradeDetailStyle}>
                        <div className="report-div-row" style={{ backgroundColor: tc.panelBg }}>
                            <div className="report-div">
                                <VisualTable title="Wave Detail" data={vtTradeDetail} tooltips={tradeDetailToolTips} tooltipSW={props.tooltipSW} />
                            </div>
                            {/* <div className="report-div"> <VisualTable title="Strategy Profit Loss" data={tradeReportData} filter={[8, 9, 10]} tooltips={tradeDetailToolTips} tooltipSW={props.tooltipSW} /> </div> */}
                            <div className="report-div">
                                <VisualTable title="Wave Profit Loss" data={vtStrategyPL} tooltips={tradeDetailToolTips} tooltipSW={props.tooltipSW} />
                            </div>


                            <div className="report-div">
                                <GenericLineChart chartTitle="Cumulative Return" chartData={cumulativeGrowth} chartLabels={cumulativeGrowthL} chartDataCompare={cumulativeGrowthCompare} symbol={props.symbol} UITheme={props.UITheme} />
                            </div>
                        </div>

                        <div className="report-div-row" style={{ backgroundColor: tc.panelBg }}>
                            <div className="report-div">
                                <VisualTable title="Wave Stats" data={vtWaveStats} tooltips={tradeDetailToolTips} tooltipSW={props.tooltipSW} />
                            </div>
                            <div className="report-div">
                                {(() => {
                                    const keys = Object.keys(tradeReportData)
                                    const isLong = props.barChartLongOrShort === 'long'
                                    const trendKey = isLong ? 'Trend Long' : 'Trend Short'
                                    const trendIcon = isLong ? lsIcon : ssIcon
                                    const trendIdx = keys.indexOf(trendKey)
                                    const alignIdx = keys.indexOf('Trend Alignment')
                                    return <VisualTable title="Wave Info" data={tradeReportData} filter={[12, 15, alignIdx, trendIdx]} icons={['', '', '', trendIcon]} stockscore={props.stockScore} tooltips={tradeDetailToolTips} tooltipSW={props.tooltipSW} lastPriceDate={props.lastPrice[0]} />
                                })()}
                            </div>
                            <div className="report-div report-info-div" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}>

                                <VisualTableDesc {...props} />

                            </div>
                        </div>

                    </div>
                    : <div className="trade-detail trade-detail-blank" style={tradeDetailStyle} role="status" aria-live="polite">
                        <span style={{ fontSize: infoTextSize, color: tc.watermark }}>Loading statistics for {props.symbol}...</span>
                    </div>
                    : <div className="trade-detail trade-detail-blank" style={tradeDetailStyle} >
                        <span style={{ fontSize: svFont, color: tc.watermark }} >{brand['strategy stats']}</span>
                    </div>
            }
        </div >
    )
}

export default TradeDetail
