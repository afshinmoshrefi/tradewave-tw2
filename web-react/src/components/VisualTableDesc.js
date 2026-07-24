// filters are in visual table used for selecting and ordering the data passed to the table
// starts from index 0

import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import './styles/VisualTableDesc.css'
import Tippy from '@tippyjs/react'
// import { BsArrowUp, BsArrowDown, BsArrowLeft } from "react-icons/bs";
import { appserverURL, getSelectedIDFromSecuritiesList2, getTodayDate, customYearsDesc, themeColors } from './Common'

const VisualTableDesc = (props) => {

    const { browserH, browserW, rdd, token, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    // const MAXROWS = 4; // max number of rows displayed

    const [lastPriceDisplay, SetLastPriceDisplay] = useState('Not Traded')
    const [yearsFilterDesc, SetYearsFilterDesc] = useState(props.seasonalYears);

    useEffect(() => { // assigns the text description for the selected seasonal years
        // let val = Number(props.seasonalYears) ? true : false; // if false its a custom year - only show seasonalchart with jan-dec checked
        const val = props.PEselected === 'cons';
        if (val === false) {
            let ftext = props.PEselected.toUpperCase()
            if (ftext === 'PE0')ftext = 'PE';
            else ftext = ftext.replace('PE','PE+');
            SetYearsFilterDesc(`${props.seasonalYears} ${ftext} Years` )
            // SetYearsFilterDesc(customYearsDesc[props.seasonalYears].replace('Presidential Election', 'Pres Election').replace('Years', 'Yrs'))
        }
        else {
            SetYearsFilterDesc(props.seasonalYears + ' Years');
        }


    }, [props.seasonalYears,props.PEselected]);
    //---------------------------------------------
    useEffect(() => {


        var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
        var asURL = appserverURL()
        var url = `${asURL}/StockLastPrice/${id}/${props.symbol}?token=${token}`


        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {


                if (g['StockLastPrice'][0] !== 0) { // this symbol is not traded



                    props.SetLastPrice(g['StockLastPrice'])

                    let td = new Date(getTodayDate() + 'T00:00:00')
                    let sd = new Date(g['StockLastPrice'][0] + 'T00:00:00')
                    let days_since_last_price = Math.floor((td - sd) / 86400000)

                    if (days_since_last_price < 7) SetLastPriceDisplay(g['StockLastPrice'][1])
                    else SetLastPriceDisplay('Not Traded')
                }
            })
            .catch(err => {
                console.log('error retrieving stockLastPrice', err)
            })

    }, [props.symbol]);


    // yearsFilterDesc



    let vtFontSize = "5vw";
    let titleFontSize = "6vw";
    let securitiesGroupFont = '0.9vw'


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
        securitiesGroupFont = '0.82vw';
    }




    var ss = props.selectedSecurity;
    if (ss === 'FUTURES & COMMODITIES') ss = 'Futures & Commodities';
    if (ss === 'GOVERNMENT BONDS') ss = 'Government Bonds';



    return (

        <div className='desc-visual-table-parent-div' style={{ borderColor: tc.border, backgroundColor: tc.panelBg, color: tc.text }}>

            <div className="desc-title-div" style={{ fontSize: titleFontSize, backgroundColor: tc.statsBarBg, color: tc.text }} >
                General
            </div>
            <div className="body-div">
                <div className="row-div" style={{ fontSize: vtFontSize, lineHeight: '1.6vh', alignItems: 'center', justifyContent: 'center', backgroundColor: tc.statValueBg, color: tc.text }} >
                    <div className='left-cell' style={{ backgroundColor: tc.statValueBg, color: tc.text }} >
                        Years Filter
                    </div>
                    <div className='desc-right-cell' style={{ backgroundColor: tc.statValueBg, color: tc.text }}  >
                        {yearsFilterDesc}
                    </div>
                </div>

                <div className="row-div" style={{ fontSize: vtFontSize, lineHeight: '1.6vh' }} >
                    <div className='left-cell' style={{ backgroundColor: tc.statLabelBg, color: tc.text }} >
                        Securities Group
                    </div>
                    <div className='desc-right-cell' style={{ backgroundColor: tc.statLabelBg, color: tc.text, fontSize: securitiesGroupFont }}  >
                        {ss}
                    </div>
                </div>



                <Tippy placement={'top'} content={
                    <div theme="tw" >
                        {/* {props.tooltipSW ? props.tooltips[x] : ''} */}
                        {lastPriceDisplay !== 'Not Traded'
                            ? 'Last Price of ' + props.symbol + ' on date : ' + props.lastPrice[0]
                            : props.symbol + ' has not been traded since : ' + props.lastPrice[0]
                        }
                    </div>
                }>


                    <div className="row-div" style={{ fontSize: vtFontSize, lineHeight: '1.6vh', alignItems: 'center', justifyContent: 'center' }} >
                        <div className='left-cell' style={{ backgroundColor: tc.statValueBg, color: tc.text }} >
                            Last Price
                        </div>
                        <div className='desc-right-cell' style={{ backgroundColor: tc.statValueBg, color: tc.text }}  >
                            {lastPriceDisplay}
                        </div>
                    </div>

                </Tippy>


                <div className="row-div" style={{ backgroundColor: tc.statLabelBg, color: tc.text, fontSize: vtFontSize, lineHeight: '1.6vh', alignItems: 'center', justifyContent: 'center' }} >

                    TradeWave.AI

                </div>

            </div>

        </div>
    )
}

export default VisualTableDesc



