import React, {  useState, useEffect } from 'react'
// import { UserContext } from './UserContext'
import './styles/InfoPopup.css'
import { BsXCircle } from "react-icons/bs";
import {introVideoMobile} from './Common'




const InfoPopupHelp = (props) => {

    // const { wpUserLevels, browserH, browserW, rdd, token, globalTextSize, infoTextSize, loggedinUser } = useContext(UserContext)

    const [coordinates, SetCoordinates] = useState({
        'barchart': [0, 0, 0, 0],
    });




    const coverDivColor = 'rgb(255,255,255,0.4)'
    const descDivColor = 'rgb(50,100,200,0.8)'
    const descFontSize = '4.0vh'

    useEffect(() => {


        if (props.swiper == null) return;

        // console.log('props.swiper=',props.swiper)

        var headerDiv = document.getElementById('main-header');



        //-- description for top - center the rectangle
        let elem;
        if (props.swiper.activeIndex === 0) {
            elem = document.querySelector('.opp-container');
        }
        else if (props.swiper.activeIndex === 1) {
            elem = document.querySelector('.barchart');
        }
        else if (props.swiper.activeIndex === 2) {
            elem = document.querySelector('.linechart');
        }
        else if (props.swiper.activeIndex === 3) {
            elem = document.querySelector('.stock-detail-parent-m');
        }
        else if (props.swiper.activeIndex === 4) {
            elem = document.querySelector('.cumulative-linechart');
        }
        else if (props.swiper.activeIndex === 5) {
            elem = document.querySelector('.seasonal-chart-parent');
        }
        let rect = elem.getBoundingClientRect();
        let tmpcoord = coordinates;
        let pctSizeW = 0.85; // this is to size the rect width inside the big one
        let pctSizeH = 0.90; // this is to size the rect height inside the big one
        tmpcoord['barchart'][0] = headerDiv.clientHeight + rect['top'] + (rect['height'] * (1 - pctSizeH) / 2);
        tmpcoord['barchart'][1] = rect['left'] + (rect['width'] * (1 - pctSizeW) / 2);
        tmpcoord['barchart'][2] = rect['width'] * pctSizeW;
        tmpcoord['barchart'][3] = rect['height'] * pctSizeH;
        //---------------------------------------------------
        SetCoordinates({ ...tmpcoord });
    }, [])

    const barChartDescStyle = {
        backgroundColor: descDivColor,
        top: coordinates['barchart'][0],
        left: coordinates['barchart'][1],
        width: coordinates['barchart'][2],
        height: coordinates['barchart'][3],
        padding: '1%',
        lineHeight:'1.1'
    }

    const handleClose = () => {
        props.SetHelpBoxVisible(false);
    }
//-------------------------------------------------------------------------------------------------------
    return (

        <div className='main-cover' style={{ backgroundColor: coverDivColor }} onClick={handleClose}>

            {/*  close circle on the top left  */}
            <div className='close-circle'  >
                <BsXCircle size={40} onClick={handleClose} />
            </div>




            {/*  describe  opportunities table */}
            {props.swiper.activeIndex === 0
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            Seasonal Scanner Opportunities Table - swipe left for more ...
                            <hr />
                            You are looking at opportunities with <br />Start Date :  {[props.dayOfTheMonth] + ' '}
                            of {props.oppTableMonth} <br />
                            Seasonal Years : {props.oppTableYears}<br />
                            Probability Years : {props.oppTablePartialYears} = {Math.round(100 * parseInt(props.oppTablePartialYears) / parseInt(props.oppTableYears))} % <br />
                            <hr /><span style={{ color: 'lightgreen' }}>Click an opportunity to see the trade on Seasonal Viewer</span>
                            <hr />
                            <span style={{ color: 'pink' }}>Change Seasonal Date, Years above & filter below.  </span>

                            <hr /><a href='/learn/#seasonal-viewer'>Learn More</a>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <a href={introVideoMobile}>Watch Video</a>
                        </span>


                    </div>
                </div>
            }




            {/*  describe top section barchart*/}
            {props.swiper.activeIndex === 1
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Seasonal Viewer - swipe right & left for more<hr />
                            Barchart is showing yearly % gain/loss for {props.symbol + '  '}
                            buy on {props.startDate.substring(5, 10)} hold-days:{props.daysOut + ' '} calendar days
                            <hr />swipe right and left to see more ..
                            <hr />Click a bar on Seasonal Viewer to see the stock chart for that year
                            <hr /><a href='/learn/#seasonal-viewer'>Learn More</a>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <a href='/learn/#seasonal-viewer'>Watch Video</a>
                        </span>
                    </div>
                </div>
            }

            {/*  describe top section linechart*/}
            {props.swiper.activeIndex === 2
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the stock line chart <hr />
                            showing the year specific stock trade for {props.symbol} bought on {props.tradeDate0} and sold on {props.tradeDate1}.

                            <hr />Click a bar on the barchart of Seasonal Viewer to see the trade stock chart for that year

                        </span>
                    </div>
                </div>
            }

            {/*  describe top section strategy detail*/}
            {props.swiper.activeIndex === 3
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Strategy Statistics view<hr /> showing the performance characteristics of the current Seasonal Strategy:
                            buying {props.symbol} on {props.tradeDate0.substring(5, 10)} holding it for {props.daysOut}
                            days selling it on {props.tradeDate1.substring(5, 10)}.

                            <hr />Swipe Right or click double left arrow to Opportunities Table.  Click an opportunity on Opportunities Table to see the barchart, strategy performance and cumlative return for that seasonal opportunity.

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

                            Seasonal Chart is a % based 365 day chart.  Chart shows average trend over the years for this stock
                            <hr />Wave Opportunities table lists the segments with consistant average return and low standard deviation.
                        </span>
                    </div>
                </div>
            }
            {/*  describe top section cumulative return*/}
            {props.swiper.activeIndex === 5
                &&
                <div className='help-desc' style={barChartDescStyle} >
                    <div>
                        <span style={{ fontSize: descFontSize, fontWeight: 'bold' }}>
                            This is the Trend Chart <hr />
                            This chart is constructed by normalizing and averaging {props.seasonalYears} years of price data

                            Seasonal Chart is a % based 365 day chart.  Chart shows average trend over the years for this stock
                            <hr />Wave Opportunities table lists the segments with consistant average return and low standard deviation.

                        </span>
                    </div>
                </div>
            }
        </div>
    )
}

export default InfoPopupHelp
