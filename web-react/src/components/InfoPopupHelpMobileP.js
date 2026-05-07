import React, { useState, useEffect, useContext } from 'react'
// import { UserContext } from './UserContext'
import './styles/InfoPopup.css'
import { BsXCircle } from "react-icons/bs";
import { introVideoMobile, introVideoIpad } from './Common'
import { UserContext } from './UserContext'



const InfoPopupHelp = (props) => {

    const { rdd } = useContext(UserContext)

    const [coordinates, SetCoordinates] = useState({
        'barchart': [0, 0, 0, 0],
        'opptable': [0, 0, 0, 0],
    });

    const coverDivColor = 'rgb(255,255,255,0.4)'
    const descDivColor = 'rgb(50,100,200,0.8)'
    const descFontSize = '2.2vh'

    useEffect(() => {

        var headerDiv = document.getElementById('main-header');



        //-- description for top - center the rectangle
        let elem;
        if (props.swiper.activeIndex === 0) {
            elem = document.querySelector('.barchart');
        }
        else if (props.swiper.activeIndex === 1) {
            elem = document.querySelector('.linechart');
        }
        else if (props.swiper.activeIndex === 2) {
            elem = document.querySelector('.trade-detail-m');
        }
        else if (props.swiper.activeIndex === 3) {
            elem = document.querySelector('.cumulative-linechart');
        }
        else if (props.swiper.activeIndex === 4) {
            elem = document.querySelector('.seasonal-chart-parent');
        }


        let rect = elem.getBoundingClientRect();
        let tmpcoord = coordinates;
        let pctSizeW = 0.85; // this is to size the rect width inside the big one
        let pctSizeH = 0.9; // this is to size the rect height inside the big one
        tmpcoord['barchart'][0] = headerDiv.clientHeight + rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['barchart'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['barchart'][2] = rect['width'] * pctSizeW;
        tmpcoord['barchart'][3] = rect['height'] * pctSizeH;
        // SetCoordinates({ ...tmpcoord });
        //---------------------------------------------------




        //-- description for opptable - center rectangle
        elem = document.querySelector('.opp-container');
        rect = elem.getBoundingClientRect();
        // tmpcoord = coordinates;
        pctSizeW = 0.85; // this is to size the rect width inside the big one
        pctSizeH = 0.9; // this is to size the rect height inside the big one
        tmpcoord['opptable'][0] = headerDiv.clientHeight + rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['opptable'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['opptable'][2] = rect['width'] * pctSizeW;
        tmpcoord['opptable'][3] = rect['height'] * pctSizeH;



        // console.log('tmpcoord=', tmpcoord)

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

    const videoURL = () => {
        if (rdd.isTablet)return introVideoIpad;
        return introVideoMobile;
    }

    return (

        <div className='main-cover' style={{ backgroundColor: coverDivColor }} onClick={handleClose}>

            {/*  close circle on the top left  */}
            <div className='close-circle'  >
                <BsXCircle size={40} onClick={handleClose} />
            </div>








            {/*  describe top section barchart*/}
            {props.swiper.activeIndex === 0
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Seasonal Viewer<hr />
                            Barchart is showing yearly % gain/loss for {props.symbol + ' '}
                            buy on {props.startDate.substring(5, 10)} hold:{props.daysOut} calendar days
                            <hr />Click down caret for the controls.
                            <hr />swipe right and left to see more ..
                            <hr /><a href='/learn/#seasonal-viewer'>Learn More</a>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <a href={videoURL()}>Watch Video</a>
                        </span>
                    </div>
                </div>
            }

            {/*  describe top section linechart*/}
            {props.swiper.activeIndex === 1
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the stock line chart <hr />
                            showing the year specific stock trade for {props.symbol} bought on {props.tradeDate0} and sold on {props.tradeDate1}.

                            <hr />Click a bar on the barchart above to see the trade price chart for that year

                        </span>
                    </div>
                </div>
            }

            {/*  describe top section strategy detail*/}
            {props.swiper.activeIndex === 2
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Strategy Detail view<hr /> showing the performance characteristics of the current Seasonal Strategy:
                            buying {props.symbol} on {props.tradeDate0.substring(5, 10)} holding it for {props.daysOut}
                            days selling it on {props.tradeDate1.substring(5, 10)}.

                            <hr />Click an opportunity below to see the strategy performance for that seasonal opportunity.

                        </span>
                    </div>
                </div>
            }


            {/*  describe top section cumulative return*/}
            {props.swiper.activeIndex === 3
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Cumulative Return graph <hr />
                            This graph is showing capital growth of the current seasonal strategy over the number of years selected.
                            <hr />
                            Click an opportunity below to see how cumulative graph changes for various opportunities.
                        </span>
                    </div>
                </div>
            }

            {props.swiper.activeIndex === 4
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Trend Chart <hr />
                            This chart is constructed by normalizing and averaging {props.seasonalYears} years of price data

                            Trend of the chart shows average trend over the years for this stock
                            Standalone Chart is limited by outliers and high standard deviation returns.
                            <hr />Wave Opportunities table lists the segments with consistant average return and low standard deviation.


                        </span>
                    </div>
                </div>
            }


            {/*  describe bottom section opportunities table */}
            <div className='help-desc' style={oppTableDescStyle} >
                <div>

                    <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                        This is the Opportunities Table
                        <hr />
                        You are looking at opportunities with <br />Start Date :  {[props.dayOfTheMonth] + ' '}
                        of {props.oppTableMonth} <br />
                        Seasonal Years : {props.oppTableYears}<br />
                        Probability Years : {props.oppTablePartialYears} = {Math.round(100 * parseInt(props.oppTablePartialYears) / parseInt(props.oppTableYears))} % <br />


                        <hr /><span style={{ color: 'lightgreen' }}>Click an opportunity on the Table to see the trade on Seasonal Viewer</span>
                        <hr />
                        <span sytle={{ color: 'pink' }}>Change Years above to 8 years to see Wave Opportunities based on 8 years</span>
                        <hr />
                        Change filter below to 1% to see Opportunities that have reached at least 1%
                    </span>


                </div>
            </div>



        </div>
    )
}

export default InfoPopupHelp
