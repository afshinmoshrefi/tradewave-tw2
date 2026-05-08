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
        'Entry Date': 'Start Date of the TradeWave Opportunity',
        'Calendar Days Hold': 'Number of calendar days to hold the security for this TradeWave Opportunity.  You can see the date range determined by start-date and days-hold on the header of seasoanl viewer',
        'Avg Loss': 'Average loss for losing trades in this TradeWave Opportunity',
        'Avg Gain': 'Avg Gain shows two values: The first number is the average gain of winning years only, which reflects the typical return when the pattern is profitable. The second number is the overall average gain, which includes both winning and losing years, giving a broader view of the pattern’s performance over time.',
        'Median Profit': 'Median Profit for this TradeWave Opportunity',
        'Std Dev': 'Standard Deviation of the profits year to year.  This percentage shows the amount of fluctuation in the profits year to year',
        'Num Losers': 'Number of losing trades in this TradeWave Opportunity',
        'Num Winners': 'Number of winning trades in this TradeWave Opportunity',
        'Percent Profitable': 'Percentage of trades that were profitable; 100% means every year was profitable',
        'Cumulative Return': 'Cumulative return of the TradeWave Opportunity over the number of historical years being analyzed',
        'Sharpe Ratio': 'Sharpe ratio is used to evaluate quality of a trade.  It is a measure showing if average profit is higher than free market return and stability of profits year to year. If sharpe ratio is  larger than 1, it means the average profit is higher than profit fluctuation year to year; that is a sign of a strategy with stable returns.  If Sharpe ratio is below 1 it will be due to average profit being lower than profit fluctuation year to year. Sharpe-ratio is the default sort for the opportunities list',
        'Trend Long': 'Trend Long measures how bullish (upward) the current price trend is on a scale of 0 to 100 as of ' + (props.lastPrice[0] || '') + '. A high score (e.g. 80+) means the price is well above its key moving averages and momentum is pointing up - a good sign for long (buy) trades. A low score means the price is below most indicators. The arrow shows if the score improved (green up), declined (red down), or stayed the same (gray) since the previous day. To visually verify, go to the Price Chart - click the right arrow or the rightmost dot on the title bar.',
        'Trend Short': 'Trend Short measures how bearish (downward) the current price trend is on a scale of 0 to 100 as of ' + (props.lastPrice[0] || '') + '. A high score (e.g. 80+) means the price is well below its key moving averages and momentum is pointing down - a good sign for short (sell) trades. A low score means the price is below most indicators. The arrow shows if the score improved (green up), declined (red down), or stayed the same (gray) since the previous day. To visually verify, go to the Price Chart - click the right arrow or the rightmost dot on the title bar.',
        'Trend Alignment': 'Shows whether the current price trend supports this trade direction. "Aligned" (score above 60) means the trend favors this trade - "Against" (score below 40) means the trend is working against it - "Neutral" (40-60) means the trend is mixed. For a long trade, this uses the Trend Long score. For a short trade, it uses the Trend Short score.',

        'S&P 500 Buy & Hold': 'The S&P 500 return is the equivalent return of the S&P500 index for the entire year.  This value is useful for comparing the current opportunity to buy & hold of the broader market, the S&P 500 index.   The cumulative return of S&P 500 is also shown on the Cumulative Return chart displayed as dark red line on the chart.',
        'Date Range': "The date range of a seasonal pattern defines the specific period each year when the pattern occurs. For example, if a pattern has a date range from March 5 to April 10, that means we analyze how the stock performed during this exact period in past years. The values are based on the closing price at the start and end of the range each year. This helps identify consistent trends - like whether a stock tends to rise or fall during this time - giving traders an edge in timing their entries and exits.",
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


    useEffect(() => {

        var cret = cumulativeReturn(props.seasonalBarChartData, props.barChartLongOrShort) //moved to common.js
        var cretCompare = cumulativeReturn(props.compareSecurityBarChartData, props.compareSecurityLongOrShort)


        SetCumulativeGrowth(cret['cdata'])
        SetCumulativeGrowthL(cret['cdataL'])

        SetCumulativeGrowthCompare(cretCompare['cdata'])

        // console.log("cretCompare=",cretCompare)


        if (props.symbol.length > 0 && props.startDate && props.startDate.length >= 10 && props.daysOut != null) {



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



            // set up down netural icons for long score and short score
            // icons define arrows that determines the trend direction from one period prior
            if (trData['Trend Long'] > trData['Trend Long1']) SetLsIcon('u')
            else if (trData['Trend Long'] < trData['Trend Long1']) SetLsIcon('d')
            else if (trData['Trend Long'] === trData['Trend Long1']) SetLsIcon('n')

            if (trData['Trend Short'] > trData['Trend Short1']) SetSsIcon('u')
            else if (trData['Trend Short'] < trData['Trend Short1']) SetSsIcon('d')
            else if (trData['Trend Short'] === trData['Trend Short1']) SetSsIcon('n')

            // Trend Alignment - does the current trend support the trade direction?
            let trendScore = props.barChartLongOrShort === 'long' ? trData['Trend Long'] : trData['Trend Short']
            let alignLabel = 'Neutral'
            if (trendScore > 60) alignLabel = 'Aligned'
            else if (trendScore < 40) alignLabel = 'Against'
            trData['Trend Alignment'] = alignLabel + ' (' + trendScore + ')'


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


        }
        else {

            SetTradeReportData([])
            SetVtTradeDetail({})
        }

    }, [props.compareSecurityTradeDetailData, props.compareSecurityLongOrShort, props.compareSecurity[1], props.tradeDetailData, props.compareSecurityTradeDetailData, props.barChartLongOrShort, props.symbol]);

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
                    : <div className="trade-detail trade-detail-blank" style={tradeDetailStyle} >
                        <span style={{ fontSize: svFont, color: tc.watermark }} >{brand['strategy stats']}</span>
                    </div>
            }
        </div >
    )
}

export default TradeDetail
