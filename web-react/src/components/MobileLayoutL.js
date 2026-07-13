import React, { useState, useContext, useEffect } from "react"
import SeasonalBarChart from './SeasonalBarChart'
import StockLineChart from './StockLineChart'
import TradeDetailMobile from "./TradeDetailMobile"
import OppTable from './OppTable'
import { cumulativeReturn } from './Common'
import './styles/MobileLayoutL.css'
import AddGC from './AddGC'
import { UserContext } from './UserContext'
import GenericLineChart from './GenericLineChart'
import SeasonalChart from './SeasonalChart'
import { Swiper, SwiperSlide } from "swiper/react";
import HelpPanelPopup from './HelpPanelPopup'
import InfoPopup from './InfoPopup'
import InfoPopupHelp from './InfoPopupHelpMobileL';
import ReportsDashboard from './ReportsDashboard';
import PortfolioSettings from './PortfolioSettings';
import WatchlistSettings from './WatchlistSettings';
import OppNote from "./OppNote"
import Settings from './Settings'
import PopulatePortfolio from './PopulatePortfolio'
import TradeInstrument from "./TradeInstrument"
import PublishArticle from "./PublishArticle";
import AutoTrade from "./AutoTrade"
import TradeReport from "./PortfolioTradeReport"
import { BsListUl } from "react-icons/bs"


// Import Swiper styles
import "swiper/swiper.min.css";
import "swiper/components/pagination/pagination.min.css"
import "swiper/components/navigation/navigation.min.css"

// import Swiper core and required modules
// import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';

// install Swiper modules
// SwiperCore.use([Pagination, Navigation, Virtual]);

// import Swiper core and required modules
import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';

// install Swiper modules
SwiperCore.use([Pagination, Navigation, Virtual]);


const MobileLayoutL = (props) => {


    const { browserH, browserW, rdd, seasonalAppDivH2, debug, loggedinUser } = useContext(UserContext)

    const [tradeReportData, SetTradeReportData] = useState({ 'heading': 'heading value' })
    // const [tradeReportDataColor, SetTradeReportDataColor] = useState({ 'color': 'black' })
    const [vtTradeDetail, SetVtTradeDetail] = useState({ 'Symbol': props.symbol, 'Trade Direction': 'long', 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })

    const [cumulativeGrowth, SetCumulativeGrowth] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthCompare, SetCumulativeGrowthCompare] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthL, SetCumulativeGrowthL] = useState(['2009', '2010', '2011', '2000', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])




    // console.log(browserH,browserW,rdd.isTablet,seasonalAppDivH2,browserH)


    // const [touchStart, setTouchStart] = useState(0);
    // const [touchEnd, setTouchEnd] = useState(0);

    // const swiperRef = useRef(null);
    // const [swiper, setSwiper] = useState(null);

    // auto switch displayed chart by an event not swipe
    const chartTo = (idx) => {
        // idx=0 is barchart idx=1 is linechart
        props.swiper.slideTo(idx)
    }




    // let resizeWindow = () => {

    //     var headerDiv = document.getElementById('main-header');
    //     var pageContainerDiv = document.getElementById('page-container');


    //     headerDiv.style.cssText = "display:none !important"
    //     pageContainerDiv.style.paddingTop = "0px"

    //     window.scrollTo(0, 1);

    // };

    let resizeWindow = () => {
        if (!debug) {
            var headerDiv = document.getElementById('main-header');
            var footerDiv = document.getElementsByClassName('et-l')[0]; // custom footers have class css not id
            var pageContainerDiv = document.getElementById('page-container');
            if (footerDiv) footerDiv.style.cssText = "display:none !important" //am
            if (pageContainerDiv) {
                pageContainerDiv.style.paddingTop = "0px !important"
                pageContainerDiv.style.cssText = "margin-top: -1px !important"
            }
            window.scrollTo(0, headerDiv?.clientHeight ?? 0);
        }
    };

    setTimeout(function () { resizeWindow(); }, 500);
    setTimeout(function () { resizeWindow(); }, 1000);



    useEffect(() => { //reset the chart to barchart in mobile

        // console.log('useEffect in mobile L called')

        if (rdd.isTablet && browserW > browserH) { } // can't call swiper when ipad landscape - get memory leak warning
        else {
            if (props.swiper) {
                // console.log('rowIndexClicked=', props.rowIndexClicked)
                if (props.rowIndexClicked == null) {
                    // chartTo(0) // first time 
                    // console.log('swiper=',props.swiper)
                    props.swiper.slideTo(0)

                }
                else chartTo(1) // after selection made
            }
        }

        // if (swiper) chartTo(0)
        var cret = cumulativeReturn(props.seasonalBarChartData, props.barChartLongOrShort) //func moved to common.js
        var cretCompare = cumulativeReturn(props.compareSecurityBarChartData, props.barChartLongOrShort)

        SetCumulativeGrowth(cret['cdata'])
        SetCumulativeGrowthL(cret['cdataL'])
        SetTradeReportData(JSON.parse(JSON.stringify(props.tradeDetailData)))
        SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })

        SetCumulativeGrowthCompare(cretCompare['cdata'])

        // console.log('useEffect in mobile L 2 called')

    }, [props.startDate, props.symbol, props.daysOut, props.seasonalYears, props.showMAE, props.showMFE, props.tradeDetailData, props.barChartLongOrShort])





    const appContainerL = {
        // height:"100vh",
        // height: window.innerHeight,
        height: seasonalAppDivH2
    }


    return (
        <div className="app-container-l" style={appContainerL} >



            {props.infoBoxVisible && <InfoPopup {...props} />}
            {/* {props.helpBoxVisible && <InfoPopupHelp {...props} />} */}
            {props.videosBoxVisible && <HelpPanelPopup onClose={() => props.SetVideosBoxVisible(false)} />}
            {props.reportsDashVisible && <ReportsDashboard {...props} />}
            {/* {props.addGCVisible && <AddGC {...props} />} */}
            {/* forceGC: the Remind me bell's Edit link always means the calendar dialog */}
            {props.addGCVisible && props.selectedPortfolio[0] === '&' && !props.googleCalendarDict['forceGC'] && <TradeInstrument {...props} />}
            {props.addGCVisible && (props.selectedPortfolio[0] !== '&' || props.googleCalendarDict['forceGC']) && <AddGC {...props} />}
            {props.showPortfolioSettings && <PortfolioSettings {...props} />}
            {props.showWatchlistSettings && <WatchlistSettings {...props} />}
            {props.showOppNote && <OppNote {...props} />}
            {props.showSettings && <Settings {...props} />}
            {/* showDialog is an array being used instead of individual show vars 11/18/2023*/}
            {props.showPopulatePortfolio && <PopulatePortfolio {...props} />}

            {props.showAutoTrade && <AutoTrade {...props} />}
            {props.showTradeReport && <TradeReport {...props} />}

            {props.showArticlePublish && <PublishArticle {...props} />}

            {loggedinUser !== '0' &&
                <div style={{ position: 'absolute', top: '2px', right: '6px', zIndex: 100, cursor: 'pointer' }} onClick={() => props.SetShowWatchlistSettings(true)}>
                    <BsListUl size={14} style={{ fill: props.showWatchlistSettings ? 'cyan' : 'white' }} />
                </div>
            }

            <div className="l-content" >

                <Swiper onSwiper={(s) => { props.setSwiper(s); }} navigation={false} className="mySwiper" >

                    <SwiperSlide>
                        <OppTable {...props} chartTo={chartTo} />
                    </SwiperSlide>


                    <SwiperSlide>
                        <SeasonalBarChart {...props} chartTo={chartTo} />
                    </SwiperSlide>

                    <SwiperSlide>
                        <StockLineChart {...props} chartTo={chartTo} />
                    </SwiperSlide>




                    <SwiperSlide>
                        <div className="report-div-body-ml">
                            <TradeDetailMobile {...props} chartTo={chartTo} />
                        </div>
                    </SwiperSlide>
                    <SwiperSlide>
                        <div className="report-div-mp"> <GenericLineChart {...props} chartTitle="Cumulative Return" chartData={cumulativeGrowth} chartLabels={cumulativeGrowthL} chartTo={chartTo} chartDataCompare={cumulativeGrowthCompare} /></div>
                    </SwiperSlide>

                    <SwiperSlide>
                        <SeasonalChart {...props} chartTitle="Seasonal Chart" chartData={props.consolidatedSeasonalData} chartTo={chartTo} />
                    </SwiperSlide>



                </Swiper>








            </div>





        </div>
    )
}

export default MobileLayoutL
