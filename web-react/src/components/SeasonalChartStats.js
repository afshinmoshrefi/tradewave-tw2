// seasonal chart stats are the display of stats in seasonal chart displays

import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/SeasonalChartStats.css'


const SeasonalChartStats = (props) => {

    const tc = themeColors(props.UITheme)
    const { browserH, browserW, rdd } = useContext(UserContext)
    const [scStatData, SetSCStatData] = useState({ 'Sharpe Ratio': '0', 'Avg Profit': '0', 'Percent Profitable': '0', 'Cumulative Return': '0' });

    var showBH = true;

    let vtFontSize = "5vw";

    // let titleFontSize = "6vw";

    // let stat_labels = ['Sharpe Ratio', 'Avg Profit', 'Percent Profitable', 'Cumulative Return'];
    let stat_labels = ['Sharpe Ratio', 'Avg Gain', '% Profitable', 'B&H ' + props.symbol, 'Cumulative Ret'];

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { // smartphone portrait
        vtFontSize = "2.7vw";
        // titleFontSize = "4vw";
        stat_labels = ['SR', 'Avg Gain', '% Wins', 'B&H ' + props.symbol, 'Cum Ret'];
        showBH = false;
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { //smartphone landscape
        vtFontSize = "1.9vw";
        stat_labels = ['SR', 'Avg Gain', '% Wins', 'B&H ' + props.symbol, 'Cum Ret'];
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { // tablet portrait
        // titleFontSize = "3.3vw";
        vtFontSize = "1.7vw";
        // stat_labels = ['Sharpe Ratio', 'Avg Profit', '% Profitable', 'Cumulative'];
        stat_labels = ['SR', 'Avg Gain', '% Proftble', 'B&H ' + props.symbol, 'Cumulativ'];
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { //tablet landscape
        // titleFontSize = "2.0vw";
        vtFontSize = "1.2vw";
        // stat_labels = ['Sharpe Ratio', 'Avg Profit', '% Profitable', 'Cumulative'];
        stat_labels = ['Sharpe Ratio', 'Avg Gain', '% Profitable', 'B&H ' + props.symbol, 'Cumulative'];
    }
    else if (!rdd.isMobile) {                                       // desktop
        vtFontSize = "0.8vw";
        // titleFontSize = "1.2vw";
    }



    useEffect(() => {
        let trData = JSON.parse(JSON.stringify(props.tradeDetailData));

        if (showBH) { // only true on desktop 
            if (props.showSR2) SetSCStatData({ 'Sharpe Ratio': trData['Sharpe Ratio']+'*'+trData['Sharpe Ratio2'], 'Avg Profit': trData['Avg Profit'], 'Percent Profitable': trData['Percent Profitable'], 'B&H Return': props.securityBHstats['Cumulative Return'], 'Cumulative Return': trData['Cumulative Return'] })
            else SetSCStatData({ 'Sharpe Ratio': trData['Sharpe Ratio'], 'Avg Profit': trData['Avg Profit'], 'Percent Profitable': trData['Percent Profitable'], 'B&H Return': props.securityBHstats['Cumulative Return'], 'Cumulative Return': trData['Cumulative Return'] })
        }
        else { // this is mobile
            if (props.showSR2) SetSCStatData({ 'Sharpe Ratio': trData['Sharpe Ratio']+' - '+trData['Sharpe Ratio2'], 'Avg Profit': trData['Avg Profit'], 'Percent Profitable': trData['Percent Profitable'], 'Cumulative Return': trData['Cumulative Return'] })
            else SetSCStatData({ 'Sharpe Ratio': trData['Sharpe Ratio'], 'Avg Profit': trData['Avg Profit'], 'Percent Profitable': trData['Percent Profitable'], 'Cumulative Return': trData['Cumulative Return'] })
        }


    }, [props.tradeDetailData, props.trData, props.symbol, props.startDate, props.daysOut,props.seasonalYears,props.securityBHstats['Cumulative Return']])

    // props.securityBHstats['Cumulative Return'] is added to useEffect for timing of the buy and hold of the security - was not working before

    // const [scStatData,SetSCStatData] = useState({'Sharpe Ratio':trData['Sharpe Ratio'],'Avg Profit':trData['Avg Profit'],'Percent Profitable':trData['Percent Profitable'],'Cumulative Return':trData['Cumulative Return']})

    return (

        <div className="seasonal-chart-stats noselect" style={{ height: props.height, fontSize: vtFontSize, backgroundColor: tc.statsBarBg }}>

            <div className="info-cell noselect" style={{ borderBottom: '1px solid ' + tc.border, backgroundColor: tc.statsBarBg }}>
                {/* the crazy regular expression is there to place multiple spaces between 2 numbers by replacing * with 3 spaces  */}
                <div className="info-cell-left noselect" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}>{stat_labels[0]}</div> <div className="info-cell-right" style={{ backgroundColor: tc.statValueBg, color: tc.text }}>{(scStatData['Sharpe Ratio'] || '').replace(/\*/g, '\u00A0'.repeat(3))}</div>

            </div>

            <div className="info-cell noselect" style={{ borderBottom: '1px solid ' + tc.border, backgroundColor: tc.statsBarBg }}>
                <div className="info-cell-left noselect" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}>{stat_labels[1]}</div> <div className="info-cell-right" style={{ backgroundColor: tc.statValueBg, color: tc.text }}>{scStatData['Avg Profit']}</div>
            </div>

            <div className="info-cell noselect" style={{ borderBottom: '1px solid ' + tc.border, backgroundColor: tc.statsBarBg }}>
                <div className="info-cell-left noselect" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}>{stat_labels[2]}</div> <div className="info-cell-right" style={{ backgroundColor: tc.statValueBg, color: tc.text }}>{scStatData['Percent Profitable']}</div>
            </div>

            <div className="info-cell noselect" style={{ borderBottom: '1px solid ' + tc.border, backgroundColor: tc.statsBarBg }}>
                <div className="info-cell-left noselect" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}>{stat_labels[4]}</div> <div className="info-cell-right" style={{ backgroundColor: tc.statValueBg, color: tc.text }}>{scStatData['Cumulative Return']}</div>
            </div>

            {showBH &&

                <div className="info-cell noselect" style={{ borderBottom: '1px solid ' + tc.border, backgroundColor: tc.statsBarBg }}>
                    <div className="info-cell-left-bh noselect" style={{ backgroundColor: tc.statLabelBg, color: tc.text }}><span style={{ fontWeight: "bold" }} >B&H</span>
                        {(!rdd.isMobile || rdd.isTablet || browserH > browserW) &&
                            <span style={{ color: "red", fontWeight: "bold" }}>&nbsp;{props.symbol}</span>
                        }
                    </div>
                    <div className="info-cell-right-bh" style={{ backgroundColor: tc.statValueBg, color: tc.text }}>{scStatData['B&H Return']}
                    </div>
                </div>
            }


        </div>
    )
}

export default SeasonalChartStats



