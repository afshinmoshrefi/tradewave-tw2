import React, { useState, useEffect, useContext } from "react"
import SeasonalBarChart from './SeasonalBarChart'
import GenericLineChart from './GenericLineChart'
import StockLineChart from './StockLineChart'
import SeasonalChart from './SeasonalChart'
import OppTable from './OppTable'
import { cumulativeReturn } from './Common'
import './styles/MobileLayoutP.css'
import { UserContext } from './UserContext'
import TradeDetailMobile from "./TradeDetailMobile"
import AddGC from './AddGC'
import InfoPopup from './InfoPopup'
import InfoPopupHelp from './InfoPopupHelpMobileP'
import HelpPanelPopup from './HelpPanelPopup'
import { Swiper, SwiperSlide } from "swiper/react";
import ReportsDashboard from './ReportsDashboard'
// import TradeDetail from './TradeDetail'
import PortfolioSettings from './PortfolioSettings'
import WatchlistSettings from './WatchlistSettings'
import OppNote from "./OppNote"
import Settings from './Settings'
import { SlSettings } from "react-icons/sl";
import { BsListUl } from "react-icons/bs";
import PopulatePortfolio from './PopulatePortfolio'
import TradeInstrument from "./TradeInstrument"
import PublishArticle from "./PublishArticle";
import AutoTrade from "./AutoTrade"
import TradeReport from "./PortfolioTradeReport"
import AIScorePanel from './AIScorePanel'
import { supportsAIScoreSlide, resolveMobileSlideIndex } from './bottomSlides'


// Import Swiper styles
import "swiper/swiper.min.css";
import "swiper/components/pagination/pagination.min.css"
import "swiper/components/navigation/navigation.min.css"

// import Swiper core and required modules
import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';

// install Swiper modules
SwiperCore.use([Pagination, Navigation, Virtual]);




const MobileLayoutP = (props) => {



    // console.log(browserH,browserW,rdd.isTablet)
    const { seasonalAppDivH2, debug, rdd, loggedinUser } = useContext(UserContext)


    const [tradeReportData, SetTradeReportData] = useState({ 'heading': 'heading value' })


    const [vtTradeDetail, SetVtTradeDetail] = useState({ 'Symbol': props.symbol, 'Trade Direction': 'long', 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })

    const [cumulativeGrowth, SetCumulativeGrowth] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthCompare, SetCumulativeGrowthCompare] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [cumulativeGrowthL, SetCumulativeGrowthL] = useState(['2009', '2010', '2011', '2000', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])



    // if true show 4 windows in 1 windows.  if false show 1 at a time
    const [showDetail4, SetShowDetail4] = useState(true)





    // const [touchStart, setTouchStart] = useState(0);
    // const [touchEnd, setTouchEnd] = useState(0);

    // const swiperRef = useRef(null);
    // const [swiper, setSwiper] = useState(null);

    // AI Scores ride between the bar chart and the price chart, but ONLY on the
    // markets that are actually scored (US stocks + ETFs). Same allowlist the
    // desktop lower carousel uses, so the two layouts cannot disagree.
    const hasAIScores = supportsAIScoreSlide(props.selectedSecurity)

    // auto switch displayed chart by an event not swipe.
    // Accepts the legacy numbers (0 bar chart, 1 price chart, 2 trade detail) and
    // semantic names such as 'ai_scores'. Resolving through the slide contract is
    // what keeps chartTo(1) on the price chart once the AI slide is inserted.
    const chartTo = (destination) => {
        const idx = resolveMobileSlideIndex(destination, { hasAIScores })
        if (idx >= 0 && props.swiper) props.swiper.slideTo(idx)
    }



    let resizeWindow = () => {
        // if (!debug) {
        var headerDiv = document.getElementById('main-header');
        var footerDiv = document.getElementsByClassName('et-l')[0]; // custom footers have class css not id
        var pageContainerDiv = document.getElementById('page-container');
        if (footerDiv) footerDiv.style.cssText = "display:none !important" //am
        if (pageContainerDiv) {
            pageContainerDiv.style.paddingTop = "0px !important"
            pageContainerDiv.style.cssText = "margin-top: -1px !important"
        }
        window.scrollTo(0, headerDiv?.clientHeight ?? 0);
        // }
    };

    setTimeout(function () { resizeWindow(); }, 500);
    setTimeout(function () { resizeWindow(); }, 1000);




    //-------------------------------------------------------------------------------------------------------



    useEffect(() => { //reset the chart to barchart in mobile portrait
        // if (swiper) chartTo(0)

        var cret = cumulativeReturn(props.seasonalBarChartData, props.barChartLongOrShort) //moved to common.js
        var cretCompare = cumulativeReturn(props.compareSecurityBarChartData, props.compareSecurityLongOrShort)

        SetCumulativeGrowth(cret['cdata'])
        SetCumulativeGrowthL(cret['cdataL'])
        SetTradeReportData(JSON.parse(JSON.stringify(props.tradeDetailData)))
        SetVtTradeDetail({ 'Symbol': props.symbol, 'Trade Direction': props.barChartLongOrShort, 'Entry Date': props.startDate, 'Calendar Days Hold': props.daysOut })

        SetCumulativeGrowthCompare(cretCompare['cdata'])

        SetShowDetail4(true); // set to false to show details 1 at a time vs 4 in a window 


    }, [props.startDate, props.symbol, props.daysOut, props.seasonalYears, props.showMAE, props.showMFE, props.tradeDetailData, props.barChartLongOrShort])


    const appContainerP = {
        height: seasonalAppDivH2
    }

    var FITitleFont = '3vw';

    if (rdd.isTablet && window.innerHeight > window.innerWidth) { // only for portrait tablet
        FITitleFont = '2.2vw';
    }
    return (
        <div className="app-container-p" style={appContainerP}>


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
            {props.showPopulatePortfolio && <PopulatePortfolio {...props} />}

            {props.showAutoTrade && <AutoTrade {...props} />}
            {props.showTradeReport && <TradeReport {...props} />}

            {props.showArticlePublish && <PublishArticle {...props} />}

            <div className="p-title-content" style={{ backgroundColor: 'rgb(30, 27, 42)', color: 'cyan', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ alignSelf: "center", fontSize: FITitleFont }}>{props.company}</span>
                {loggedinUser !== '0' &&
                    <BsListUl size={14} style={{ fill: props.showWatchlistSettings ? 'cyan' : 'white', marginLeft: '8px', cursor: 'pointer' }} onClick={() => props.SetShowWatchlistSettings(true)} />
                }
            </div>

            <div className="p-top-content" >


                <Swiper onSwiper={(s) => { props.setSwiper(s); }} navigation={false} className="mySwiper" >

                    <SwiperSlide>
                        <SeasonalBarChart {...props} chartTo={chartTo} />
                    </SwiperSlide>

                    {hasAIScores && (
                        <SwiperSlide>
                            <AIScorePanel
                                compact
                                viewModel={props.opportunityAIState}
                                active={true}
                                tooltipsEnabled={props.tooltipSW}
                            />
                        </SwiperSlide>
                    )}

                    <SwiperSlide>
                        <StockLineChart {...props} chartTo={chartTo} />
                    </SwiperSlide>

                    <SwiperSlide>
                        <TradeDetailMobile {...props} chartTo={chartTo} />
                    </SwiperSlide>

                    <SwiperSlide>
                        <div className="report-div-mp">
                            <GenericLineChart {...props} chartTitle="Cumulative Return" chartData={cumulativeGrowth} chartLabels={cumulativeGrowthL} chartTo={chartTo} chartDataCompare={cumulativeGrowthCompare} />
                        </div>
                    </SwiperSlide>

                    <SwiperSlide>
                        <SeasonalChart {...props} chartTitle="Seasonal Chart" chartData={props.consolidatedSeasonalData} chartTo={chartTo} />
                    </SwiperSlide>

                </Swiper>


            </div>


            <div className="p-bottom-content" >
                <OppTable {...props} />
            </div>


        </div>
    )
}

export default MobileLayoutP
