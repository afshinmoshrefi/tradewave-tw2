// filters are in visual table used for selecting and ordering the data passed to the table
// starts from index 0

import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/VisualTable.css'
import Tippy from '@tippyjs/react'
import { BsArrowUp, BsArrowDown, BsArrowLeft } from "react-icons/bs";
import { BsInfoCircle } from "react-icons/bs";
import TrendScorePopup from './TrendScorePopup'


const VisualTable = (props) => {

    const [displayedData, SetDisplayedData] = useState({ 'loading': '...' })
    const [displayedIcons, SetDisplayedIcons] = useState(['', '', '', ''])
    const [showTrendPopup, SetShowTrendPopup] = useState(false)
    // const [displayedFillers, SetDisplayedFillers] = useState({ 'loading': '...' }) // fillers for rows less than 4

    const [rowColor, SetRowColor] = useState({ color: 'white' })
    const [fontColor, SetFontColor] = useState({ color: 'white' })
    const { browserH, browserW, rdd, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    // const MAXROWS = 4; // max number of rows displayed

    useEffect(() => {

        var tmp = Object.assign({}, props.data); // make a clone copy of the object
        var k = Object.keys(props.data)

        // console.log(props.data)

        var tmpData1 = {}
        var iconData = {}
        if (props.filter == null) {
            tmpData1 = Object.assign({}, props.data);
        }
        else {

            for (let i = 0; i < props.filter.length; i++) {
                let n = props.filter[i]
                // console.log('*n=',n,k[n],props.data[k[n]])
                if (Object.keys(props.data).length > 0) {

                    // if (props.title === 'Info')console.log(i,k[n],props.icons[i])

                    tmpData1[k[n]] = props.data[k[n]] // "if" eliminates showing undefined when table is empty
                    if (props.icons !== undefined) {
                        iconData[k[n]] = props.icons[i]
                    }
                }
            }
        }

        SetDisplayedIcons(iconData)

        // console.log('tttttttttttttttttttttttttttttttttttmpData1=',tmpData1)
        // console.log('iiiiiiiiiiiiiiiiiiiiiiiiiiiiconData=',iconData)

        var tmpData = {}
        // if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        if (rdd.isMobile) { //all portrait and landscape
            // const replacements = { 'Num Losers': 'Losers', 'Num Winners': 'Winners', 'Percent Profitable': '% Profitable' };
            for (k in tmpData1) {
                if (k === 'Num Losers') tmpData['Losers'] = tmpData1[k]
                else if (k === 'Num Winners') tmpData['Winners'] = tmpData1[k]
                else if (k === 'Percent Profitable') tmpData['% Profitable'] = tmpData1[k]
                else if (k === 'Calendar Days Hold') tmpData['Days Hold'] = tmpData1[k]
                else if (k === 'Cumulative Return') tmpData['Cumulative'] = tmpData1[k]
                else if (k === 'Trade Direction') tmpData['Direction'] = tmpData1[k]
                else if (k === 'Median Profit') tmpData['MED Profit'] = tmpData1[k]
                else if (k === 'Strategy Date Range') tmpData['Date Range'] = tmpData1[k]
                // else if (k === 'Long Score') tmpData['Trend Long'] = tmpData1[k]
                // else if (k === 'Short Score') tmpData['Trend Short'] = tmpData1[k]
                else if (k === 'S&P 500 Buy & Hold') tmpData['S&P 500 B/H'] = tmpData1[k]
                else if (k === 'Trend Alignment') tmpData['Alignment'] = tmpData1[k]
                else tmpData[k] = tmpData1[k]
            }
        }

        else {

            for (k in tmpData1) {
                // console.log(k) 
                // console.log('kkkkkkkkkkkkkkkkkkk=',k)
                // if (k === 'Long Score') tmpData['Long Wave Score'] = tmpData1[k]
                // else if (k === 'Short Score') tmpData['Short Wave Score'] = tmpData1[k]
                if (k === 'Long Score') tmpData['Trend Long'] = tmpData1[k]
                else if (k === 'Short Score') tmpData['Trend Short'] = tmpData1[k]
                else if (k === 'Avg Profit') tmpData['Avg Gain'] = tmpData1[k]
                else if (k === 'Median Profit') tmpData['Median Gain'] = tmpData1[k]
                else tmpData[k] = tmpData1[k]
            }

            // update icon data also becaue the key has changed from long score and short score to trend long and trend short

            // let t = {};
            // for (let item in displayedIcons){
            //     console.log('item=',item,displayedIcons[item])
            //     if (item === 'Long Score') t['Trend Long'] = displayedIcons[item];
            //     else if (item === 'Short Score') t['Trend Short'] = displayedIcons[item];
            //     else t[item] = displayedIcons[item];
            // }

            // console.log('tttttttttt=',t)
            // console.log('old one=',displayedIcons)


            // tmpData = tmpData1;
        }



        // console.log('tttttttttttttttttttttttttttttttttttttttttttmpData=',tmpData)

        SetDisplayedData(tmpData)



        var tmpRowColor = Object.assign({}, props.data); // make a clone copy of the object
        // var rowNum = 0;

        // console.log('tmpData=',tmpData)

        // for (let k in props.data) {
        for (let i = 0; i < Object.keys(tmpData).length; i++) {
            let k = Object.keys(tmpData)[i];

            // console.log('k=',k)

            if (i % 2 === 0) tmpRowColor[k] = tc.statValueBg
            else tmpRowColor[k] = tc.statLabelBg

            let n = parseFloat(props.data[k])
            if (isNaN(n) === false) {
                if (n < 0) tmp[k] = 'red'
                else tmp[k] = tc.text
            }
            else {
                if (k === "Symbol") tmp[k] = UITheme === 'dark' ? 'cyan' : 'blue'
                else if (k.includes("S&P")) tmp[k] = tc.text
                else if (k === 'Trend Alignment' || k === 'Alignment') {
                    let val = tmpData[k] || ''
                    if (typeof val === 'string' && val.startsWith('Aligned')) tmp[k] = 'green'
                    else if (typeof val === 'string' && val.startsWith('Against')) tmp[k] = 'red'
                    else tmp[k] = 'gray'
                }
                else tmp[k] = tc.text;
            }

            // rowNum++;
        }
        SetRowColor(tmpRowColor)
        SetFontColor(tmp)

        // console.log('tmp=', tmpRowColor)

    }, [props.data, UITheme]);




    let vtFontSize = "5vw";
    let titleFontSize = "6vw";


    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { // smartphone portrait
        vtFontSize = "0.60em";
        titleFontSize = "4vw";
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { //smartphone landscape
        vtFontSize = "2.2vw";
        titleFontSize = "3vw";
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { // tablet portrait
        titleFontSize = "3.3vw";
        vtFontSize = "2.4vw";
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { //tablet landscape
        titleFontSize = "2.0vw";
        vtFontSize = "1.2vw";
    }
    else if (!rdd.isMobile) {                                       // desktop
        vtFontSize = "0.9vw";
        titleFontSize = "1.2vw";
    }



    // const GenerateIcon = (udn, props = {}) => {
    //     const IconName = 'BsArrowUp';
    //     return <IconName {...props} />;
    // };



    return (

        <div className='visual-table-parent-div noselect' style={{ borderColor: tc.border }}>

            <div className="title-div" style={{ fontSize: titleFontSize, backgroundColor: tc.statsBarBg, color: tc.text }} >
                {props.title}
            </div>
            <div className="body-div">



                {Object.keys(displayedData).map((x) => {
                    const isTrend = x === 'Trend Long' || x === 'Trend Short' || x === 'Trend Alignment' || x === 'Alignment'
                    const isTrendScore = x === 'Trend Long' || x === 'Trend Short'
                    const shortTip = isTrend
                        ? (x === 'Trend Long' ? 'Bullish score' : x === 'Trend Short' ? 'Bearish score' : 'Trend vs trade direction') + (props.lastPriceDate ? ' as of ' + props.lastPriceDate : '')
                        : ''
                    return (

                    <Tippy disabled={isTrend ? false : !props.tooltipSW} key={x} placement={isTrend ? 'top' : 'right'} content={
                        <div theme="tw" >
                            {props.tooltipSW ? props.tooltips[x] : shortTip}
                        </div>
                    }>


 

                        <div className="row-div" style={{ fontSize: vtFontSize, lineHeight: '1.6vh' }} >

                            <div className='left-cell' style={{ backgroundColor: rowColor[x] }} >
                                <span style={{ color: x.includes('S&P 500') ? 'rgb(170,0,0)' : tc.text }}> {x}</span>
                                {isTrendScore && <BsInfoCircle size={12} style={{ marginLeft: '5px', color: '#60a5fa', cursor: 'pointer', flexShrink: 0 }} onClick={(e) => { e.stopPropagation(); SetShowTrendPopup(true); }} />}
                            </div>

                            <div className='right-cell' style={{ backgroundColor: rowColor[x], color: fontColor[x] }}  >
                                <span style={{ padding: '2px', backgroundColor: x === 'Symbol' ? 'transparent' : 'transparent' }}>{displayedData[x]}</span>

                                {((x === 'Trend Long' || x === 'Trend Short') && displayedIcons[x] === 'u')
                                    &&
                                    <BsArrowUp size={20} style={{ fill: "green" }} />
                                }
                                {((x === 'Trend Short' || x === 'Trend Long') && displayedIcons[x] === 'd')
                                    &&
                                    <BsArrowDown size={20} style={{ fill: "red" }} />
                                }
                                {((x === 'Trend Short' || x === 'Trend Long') && displayedIcons[x] === 'n')
                                    &&
                                    <BsArrowLeft size={20} style={{ fill: "gray" }} />
                                }
                            </div>
                        </div>



                    </Tippy>

                    )
                })}


            </div>

            {showTrendPopup && <TrendScorePopup onClose={() => SetShowTrendPopup(false)} />}

        </div>
    )
}

export default VisualTable



