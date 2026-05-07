import React, { useContext, useState, useEffect } from 'react'
import { UserContext } from './UserContext'
import './styles/InfoPopup.css'
// import { BsXCircle, BsQuestionCircle, BsArrowUp, BsArrowDown, BsArrowRight, BsArrowLeft, BsArrowUpCircle, BsArrowDownCircle, BsArrowRightCircle, BsArrowLeftCircle } from "react-icons/bs";
import { BsXCircle } from "react-icons/bs";

import {introVideoDesktop} from './Common'


function incrementDate(dateStr, days) { //increment date in format of yyyy-mm-dd and return same format
    var d = new Date(dateStr + 'T00:00:00')
    d.setDate(d.getDate() + parseInt(days))
    var incDate = d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate()
    return (incDate)
}



const InfoPopupHelp = (props) => {

    const {   infoTextSize } = useContext(UserContext)

    const [coordinates, SetCoordinates] = useState({
        'barchart': [0, 0, 0, 0],
        'linechart': [0, 0, 0, 0],
        'opptable': [0, 0, 0, 0],
        'oppcontrols': [0, 0, 0, 0],
        'oppfilter': [0, 0, 0, 0],
        'barcontrols': [0, 0, 0, 0],
        'bardesc': [0, 0, 0, 0],
        'linechartdesc': [0, 0, 0, 0],
        'linechartleft': [0, 0, 0, 0],
        'linechartright': [0, 0, 0, 0]
    });

    const coverDivColor = 'rgb(255,255,255,0.4)'
    const descDivColor = 'rgb(50,100,200,0.8)'
    const descFontSize = infoTextSize;//globalTextSize, infoTextSize


    useEffect(() => {

        //-- description for barchart - center rectangle
        let elem = document.querySelector('.barchart');
        let rect = elem.getBoundingClientRect();
        let tmpcoord = coordinates;
        let pctSizeW = 0.8; // this is to size the rect width inside the big one
        let pctSizeH = 0.7; // this is to size the rect height inside the big one
        tmpcoord['barchart'][0] = rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['barchart'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['barchart'][2] = rect['width'] * pctSizeW;
        tmpcoord['barchart'][3] = rect['height'] * pctSizeH;
        // SetCoordinates({ ...tmpcoord });
        //---------------------------------------------------



        //-- description for linechart - center rectangle
        // if (props.swiper.activeIndex == 0) {
        //     // elem = document.querySelector('.linechart-parent');
        //     elem = document.querySelector('.swiper-container');
        // }
        // else {
        //     // elem = document.querySelector('.stock-detail-parent');
        //     elem = document.querySelector('.swiper-container');
        // }
        elem = document.querySelector('.swiper-container');
        rect = elem.getBoundingClientRect();
        // tmpcoord = coordinates;
        pctSizeW = 0.8; // this is to size the rect width inside the big one
        pctSizeH = 0.7; // this is to size the rect height inside the big one
        tmpcoord['linechart'][0] = rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['linechart'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['linechart'][2] = rect['width'] * pctSizeW;
        tmpcoord['linechart'][3] = rect['height'] * pctSizeH;
        // SetCoordinates({ ...tmpcoord });
        //---------------------------------------------------

        //-- description for opptable - center rectangle
        elem = document.querySelector('.opp-container');
        rect = elem.getBoundingClientRect();
        // tmpcoord = coordinates;
        pctSizeW = 0.8; // this is to size the rect width inside the big one
        pctSizeH = 0.7; // this is to size the rect height inside the big one
        tmpcoord['opptable'][0] = rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['opptable'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['opptable'][2] = rect['width'] * pctSizeW;
        tmpcoord['opptable'][3] = rect['height'] * pctSizeH;

        //---------------------------------------------------
        SetCoordinates({ ...tmpcoord });
    }, [])





    const barChartDescStyle = {
        backgroundColor: descDivColor,
        top: coordinates['barchart'][0],
        left: coordinates['barchart'][1],
        width: coordinates['barchart'][2],
        height: coordinates['barchart'][3],
        padding: '1%'
    }


    const lineChartDescStyle = {
        backgroundColor: descDivColor,
        top: coordinates['linechart'][0],
        left: coordinates['linechart'][1],
        width: coordinates['linechart'][2],
        height: coordinates['linechart'][3],
        padding: '1%'
    }

    const oppTableDescStyle = {
        backgroundColor: descDivColor,
        top: coordinates['opptable'][0],
        left: coordinates['opptable'][1],
        width: coordinates['opptable'][2],
        height: coordinates['opptable'][3],
        padding: '1%'
    }




    const handleClose = () => {
        props.SetHelpBoxVisible(false);
    }


    return (

        <div className='main-cover' style={{ backgroundColor: coverDivColor }} onClick={handleClose}>

            {/*  close circle on the top left  */}
            <div className='close-circle'  >
                <BsXCircle size={40} onClick={handleClose} />
            </div>

            {/*  describe seasonal viewer barchart */}
            <div className='help-desc' style={barChartDescStyle} >
                <div>
                    <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                        This is the Seasonal Viewer<hr /> The barchart is showing yearly % gain or loss when {props.symbol} was
                        bought on {props.startDate.substring(5, 10)} holding it for {props.daysOut} calendar days until
                        {' ' + incrementDate(props.startDate, props.daysOut).substring(5, 10)}.  Seasonal History for {props.seasonalYears + ' '}
                        years is displayed.
                        <hr />You can customize Seasonal parameters by adjusting the controls above.
                        customize days out and years to see how barchart changes
                        <hr /><a style={{ color: 'red' }} href='/learn/#seasonal-viewer'>Learn More ..</a>
                        <br /><a style={{ color: 'red' }} href={introVideoDesktop}  target='_blank' rel="noreferrer">Watch Video</a>
                    </span>
                </div>
            </div>



            {/*  describe linechart or trade details*/}
            <div className='help-desc' style={lineChartDescStyle} >
                <div>

                    {props.swiper.activeIndex === 0
                        &&
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Strategy Statistics Report<hr /> showing the performance characteristics of the above Seasonal Strategy:
                            buying {props.symbol} on {props.tradeDate0.substring(5, 10)} holding it for {props.daysOut}
                            days selling it on {props.tradeDate1.substring(5, 10)}.
                            Strategy performance is based on the last {props.seasonalYears} years.

                            <hr />you can customize strategy characteristics on the Seasonal Viewer above to see how the performance is effected.
                            <hr />Click an
                            opportunity on the left to see the strategy performance for that seasonal opportunity.
                        </span>
                    }

                    {props.swiper.activeIndex === 1
                        && <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Price chart <hr />
                            chart is showing the seasonal trade for {props.symbol} bought on {props.tradeDate0} and sold on {props.tradeDate1}.

                            <hr />Click any bars on the barchart above to see the trade price chart for that year
                            <hr />  Click the arrows on the right side
                            to view overall strategy detail.
                        </span>

                    }
                    {props.swiper.activeIndex === 2
                        &&
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Trend Chart <hr />
                            This chart is constructed by normalizing and averaging {props.seasonalYears} years of price data

                            Trend of the chart shows average trend over the years for this stock
                            Standalone Chart is limited by outliers and high standard deviation returns.
                            <hr />Wave Opportunities table lists the segments with consistant average return and low standard deviation.


                        </span>
                    }
                </div>
            </div>





            {/*  describe opportunities table */}
            <div className='help-desc' style={oppTableDescStyle} >
                <div>

                    <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                        Seasonal Scanner Opportunities Table
                        <hr />
                        Listing Opportunities with <br />Start Date :  {[props.dayOfTheMonth] + ' '}
                        of {props.oppTableMonth} <br />
                        Wave Years : {props.oppTableYears}<br />
                        {/* Probability Years : {props.oppTablePartialYears} = {Math.round(100 * parseInt(props.oppTablePartialYears) / parseInt(props.oppTableYears))} % <br /> */}


                        <hr /><span style={{ color: 'lightgreen' }}>Click an opportunity on the Table to see the trade on Wave Viewer</span>
                        <hr />
                        <span style={{ color: 'pink' }}>Change Wave Years above to 8 years to see Wave Opportunities based on 8 years</span>
                        <hr />
                        Change filter below to 1% to see Opportunities that have reached at least 1%

                    </span>


                </div>
            </div>



        </div>
    )
}

export default InfoPopupHelp
