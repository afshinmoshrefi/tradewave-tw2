// difference of tradeDetail and tradeDetailMobile is:
// tradeDetail is for the desktop view - shows all 4 windows and cumulative together
// tradeDetailMobile shows the 4 windows together and does not display cumulative chart

import React, { useState, useEffect, useContext } from 'react'

import './styles/TradeDetailMobile.css'
import { UserContext } from './UserContext'
import { incrementDate, themeColors } from './Common'
import VisualTable from './VisualTable'
import { cumulativeReturn } from './Common'
import { FaAngleDoubleLeft } from "react-icons/fa";
import { BsQuestionCircle } from "react-icons/bs";
import { monthsOptionsListS } from './Common'

const TradeDetailMobile = (props) => {

    const { browserH, browserW, rdd, infoTextSize, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme);

    const [tradeReportData, SetTradeReportData] = useState({ 'heading': 'heading value' })
    // const [tradeReportDataColor, SetTradeReportDataColor] = useState({ 'color': 'black' })


    const [vtTradeDetail, SetVtTradeDetail] = useState({ 'Symbol': props.symbol, 'Trade Direction': 'long', 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })
    const [vtStrategyPL, SetVTStrategyPL] = useState({ 'Num Losers': '0', 'Num Winnder': '10', 'Percent Profitable': '100%', 'Biggest Winnder': '25.41%' })

    const [cumulativeGrowth, SetCumulativeGrowth] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthL, SetCumulativeGrowthL] = useState(['2009', '2010', '2011', '2000', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])

    const [lsIcon, SetLsIcon] = useState('')
    const [ssIcon, SetSsIcon] = useState('')

    let tradeDetailControlsHeight = '12%'
    let tradeDetailHeight = '88%'


    var caretSize = '30'
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) caretSize = '20' //smartphone portrat
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) caretSize = '30'



    var questionSize = 16;
    if (rdd.isTablet && browserH > browserW) {
        if (browserH > 1024) questionSize = 30;
        else questionSize = 22;
    }



    const tradedetailControlsStyle = {
        height: tradeDetailControlsHeight,
        display: "flex",
    }


    const tradeDetailDescStyle = {
        fontSize: infoTextSize,
        // backgroundColor: "gold",
        color: "white",
        flexGrow: "2",
        // alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        display: "flex"
    }


    const tradeDetailStyle = {
        height: tradeDetailHeight,
    }


  


    useEffect(() => {

        var cret = cumulativeReturn(props.seasonalBarChartData, props.barChartLongOrShort) //moved to common.js

        SetCumulativeGrowth(cret['cdata'])
        SetCumulativeGrowthL(cret['cdataL'])

        if (props.symbol.length > 0) {
            // let sd = props.startDate.substring(5);
            // let m  = parseInt(props.startDate.substring(5,7)) - 1;



            let sd = props.startDate.substring(5);
            let m0 = parseInt(props.startDate.substring(5, 7)) - 1;

            let ed = incrementDate(props.startDate, props.daysOut - 1).substring(5, 10)
            let m1 = parseInt(ed) - 1;



            // sd= monthsOptionsList[m]['label']+' ' + parseInt(props.startDate.substring(8)).toString() + '  ('+sd+')'
            sd = monthsOptionsListS[m0]['label'] + ' ' + parseInt(props.startDate.substring(8)).toString()
            ed = monthsOptionsListS[m1]['label'] + ' ' + parseInt(ed.substring(3, 5)).toString()

            // sd= monthsOptionsList[m]['label']+' ' + parseInt(props.startDate.substring(8)).toString() + '  ('+sd+')'
            // sd= monthsOptionsList[m]['label']+' ' + parseInt(props.startDate.substring(8)).toString() 


            let trData = JSON.parse(JSON.stringify(props.tradeDetailData))

            // // set up down netural icons for long score and short score
            // // icons define arrows that determines the trend direction from one period prior
            // if (trData['Long Score'] > trData['Long Score1']) SetLsIcon('u')
            // else if (trData['Long Score'] < trData['Long Score1']) SetLsIcon('d')
            // else if (trData['Long Score'] === trData['Long Score1']) SetLsIcon('n')

            // if (trData['Short Score'] > trData['Short Score1']) SetSsIcon('u')
            // else if (trData['Short Score'] < trData['Short Score1']) SetSsIcon('d')
            // else if (trData['Short Score'] === trData['Short Score1']) SetSsIcon('n')


            // set up down netural icons for long score and short score
            // icons define arrows that determines the trend direction from one period prior
            if (trData['Trend Long'] > trData['Trend Long1']) SetLsIcon('u')
            else if (trData['Trend Long'] < trData['Trend Long1']) SetLsIcon('d')
            else if (trData['Trend Long'] === trData['Trend Long1']) SetLsIcon('n')

            if (trData['Trend Short'] > trData['Trend Short1']) SetSsIcon('u')
            else if (trData['Trend Short'] < trData['Trend Short1']) SetSsIcon('d')
            else if (trData['Trend Short'] === trData['Trend Short1']) SetSsIcon('n')


            let largest = 0;
            let smallest = -0;
            for (var i = 0; i < props.seasonalBarChartData.length; i++) {
                let tmp = props.seasonalBarChartData[i]['pct'].split(',')[0];
                tmp = parseFloat(tmp);
                if (tmp > largest) largest = tmp;
                if (tmp < smallest) smallest = tmp;

                // props.barChartLongOrShort
            }

            // console.log('ttttttttttttttttttt',trData)

            SetTradeReportData(trData)




            // SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Date Range': sd, 'Calendar Days Hold': props.daysOut })
            SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Date Range': sd + '-' + ed, 'Calendar Days Hold': props.daysOut })

            if (props.compareSecurityLongOrShort === 'long') {
                // SetVTStrategyPL({ 'Num Losers': trData['Num Losers'], 'Num Winners': trData['Num Winners'], 'Percent Profitable': trData['Percent Profitable'], 'Lrgst Winner': largest.toString() + '%' })
                SetVTStrategyPL({  'Num Winners': trData['Num Winners'],'Num Losers': trData['Num Losers'], 'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 B/H': props.compareSecurityTradeDetailData['Cumulative Return'] })
            }
            else {
                // SetVTStrategyPL({ 'Num Losers': trData['Num Losers'], 'Num Winners': trData['Num Winners'], 'Percent Profitable': trData['Percent Profitable'], 'Lrgst Winner': (-smallest).toString() + '%' })
                SetVTStrategyPL({  'Num Winners': trData['Num Winners'],'Num Losers': trData['Num Losers'], 'Cumulative Return': props.tradeDetailData['Cumulative Return'], 'S&P 500 B/H': props.compareSecurityTradeDetailData['Cumulative Return'] })
            }

        }
        else {
            SetTradeReportData([])
            SetVtTradeDetail({})
        }
        // }, [props.tradeDetailData, props.barChartLongOrShort]);
    }, [props.compareSecurityTradeDetailData, props.compareSecurityLongOrShort, props.compareSecurity[1], props.tradeDetailData, props.compareSecurityTradeDetailData, props.barChartLongOrShort, props.symbol]);




    const doubleLeftArrow = (event) => {
        props.chartTo(0)
    }

    const handleHelpClicked = () => {
        // props.SetHelpBoxVisible(!props.helpBoxVisible);
        props.SetVideosBoxVisible(true);
    }

    var svFont = '10vw';

    const darkBg = 'rgb(30, 27, 42)';

    return (
        <div className="stock-detail-parent-m" style={{ backgroundColor: darkBg }}>

            <div className="trade-detail-controls-m" style={{ ...tradedetailControlsStyle, backgroundColor: tc.controlBar }}>
                <div style={{ height: '100%', width: '10%', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={doubleLeftArrow} >
                    <FaAngleDoubleLeft size={caretSize} style={{ fill: "white" }} />
                </div>
                <div style={tradeDetailDescStyle} >
                    &nbsp; <span style={{ color: "red" }}><strong>{props.symbol}</strong></span><span style={{ color: "white" }}>&nbsp; strategy {props.startDate.substring(5, 10)} to  {incrementDate(props.startDate, props.daysOut - 1).substring(5, 10)} </span><span style={{ color: 'red', fontSize: "15px", paddingLeft: '10px' }}>{props.tradeActive ? "Active" : ""}</span>
                </div>
                {/* <div style={{ height: '100%', width: '10%' }}></div> */}


                <div style={{ paddingRight: '2%', display: 'flex', width: '10%', alignItems: 'center', justifyContent: 'flex-end' }}>
                    <BsQuestionCircle size={questionSize} style={{ fill: "white" }} onClick={handleHelpClicked} />
                </div>


            </div>

            {props.symbol !== ''
                ? <div className="trade-detail-m" style={{ ...tradeDetailStyle, backgroundColor: darkBg }}>

                    <div className="report-div-row-m" style={{ backgroundColor: darkBg }}>
                        <div className="report-div-m"> <VisualTable title="Wave Detail" data={vtTradeDetail} /> </div>
                        {/* <div className="report-div-m"> <VisualTable title="Strategy Profit Loss" data={tradeReportData} filter={[8, 9,10]} /> </div> */}
                        <div className="report-div-m"> <VisualTable title="Wave Profit Loss" data={vtStrategyPL} /> </div>
                    </div>


                    <div className="report-div-row-m" style={{ backgroundColor: darkBg }}>

                        <div className="report-div-m"> <VisualTable title="Wave Stats" data={tradeReportData} filter={[4, 5, 9,17]} /> </div>
                        <div className="report-div-m"> <VisualTable title="Wave Info" data={tradeReportData} filter={[12, 15, 19, 21]} icons={['', '', lsIcon, ssIcon]} /> </div>

                    </div>
                </div>

                : <div className="trade-detail-m trade-detail-blank-m" style={{ ...tradeDetailStyle, backgroundColor: darkBg }}>
                    <span style={{ fontSize: svFont, color: 'rgb(153, 196, 210)' }} >Wave Stats</span>
                </div>
            }
        </div>
    )
}

export default TradeDetailMobile
