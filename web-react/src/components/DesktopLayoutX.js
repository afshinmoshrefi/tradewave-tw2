import React, { useContext, useEffect, useState } from "react"

import PopulatePortfolio from './PopulatePortfolio'
import PortfolioSettings from './PortfolioSettings'
import SeasonalBarChart from './SeasonalBarChart'
import TradeInstrument from './TradeInstrument'
import StockLineChart from './StockLineChart'
import SeasonalChart from './SeasonalChart'
import TradeDetail from './TradeDetail'
import InfoPopup from './InfoPopup'
import OppTable from './OppTable'
import AddGC from './AddGC'
import ReportsDashboard from './ReportsDashboard'
import InfoPopupHelp from './InfoPopupHelp'
import HelpPanelPopup from './HelpPanelPopup'
import SelectBox from './SelectBox'
import Settings from './Settings'
import SecuritiesGroupSettings from './SecuritiesGroupSettings'
import OppNote from "./OppNote"

import AutoTrade from "./AutoTrade"
import TradeReport from "./PortfolioTradeReport"
import TradeInstrumentReport from "./TradeInstrumentReport"

import { AiOutlineSmallDash } from "react-icons/ai";

import TestGIS from './TestGIS'

import './styles/DesktopLayout.css'
import { UserContext } from './UserContext'
import { AiOutlineDollarCircle } from "react-icons/ai";
import { BsFillCircleFill } from "react-icons/bs"
import { SlSettings } from "react-icons/sl";
import { toggle_off_64, toggle_on_64 } from './Common';
import { settings_dialog_content } from './Common'
import { incrementDate } from './Common'
//---------------------- swiper --------------------------
import { Swiper, SwiperSlide } from "swiper/react";
// import * as htmlToImage from 'html-to-image';
// import { toPng, toJpeg, toBlob, toPixelData, toSvg } from 'html-to-image';
import html2canvas from "html2canvas"
// Import Swiper styles
import "swiper/swiper.min.css";
import "swiper/components/pagination/pagination.min.css"
import "swiper/components/navigation/navigation.min.css"
// import Swiper core and required modules
import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';
import { getCookie, setCookie } from './Common'


// install Swiper modules
SwiperCore.use([Pagination, Navigation, Virtual]);

//------------------------ swiper -------------------------

const DesktopLayout = (props) => {


  const [initialSlide, SetInitialSlide] = useState(() => {
    // let bottomWindowNumber = getCookie('WindowNumber');



    // if (bottomWindowNumber === null) return "1";
    // return bottomWindowNumber;
  });


  const [coverOpp, SetCoverOpp] = useState(false);
  const [coverBottomCharts, SetCoverBottomCharts] = useState(false);
  const [coverTopCharts, SetCoverTopCharts] = useState(false);


  const { seasonalAppDivH, seasonalAppDivH2, rdd, loggedinUser, wpUserLevels } = useContext(UserContext)

  const toggle_width = '2.2vw';


  const settingsSize = 18;



  let DivH = (rdd.isMobile) ? seasonalAppDivH2 : seasonalAppDivH;

  const appContainerStyle = {
    display: "flex",
    padding: "0px",
    margin: "0px",
    backgroundColor: "purple",
    height: DivH,
    width: "100vw",
    overflow: "hidden"

  }

  // const handleBackClick = () => {
  //   redirectBackFromSeasonals();
  // }

  let resizeWindow = () => {

    window.scrollTo(0, 1);

  };

  setTimeout(function () {
    resizeWindow();
  }, 100);

  // auto switch displayed chart by an event not swipe
  const chartTo = (idx) => {
    // idx=0 is barchart idx=1 is linechart
    props.swiper.slideTo(idx)
  }

  const handleDollarClicked = () => {
    window.open('/#pricing', '_blank')
  }


  const handleAMbutton = (n) => {
    if (n === 1) SetCoverOpp(!coverOpp);
    if (n === 2) SetCoverBottomCharts(!coverBottomCharts);
    if (n === 3) SetCoverTopCharts(!coverTopCharts);
    // console.log('rdddddddddddddddddddddddddddddddddddddddddddd=',rdd.osName,rdd.isChrome)
  }

  const handleSecurityDivClicked = () => {

    // let elem = document.querySelector('.left-nav');
    // let rect = elem.getBoundingClientRect();
    // console.log(rect) 
  }

  const handleTooltipSW = () => {
    props.SetTooltipSW(!props.tooltipSW);
  }

  // SetExportImage

  useEffect(() => {


    if (props.exportImage) {

      // htmlToImage.toJpeg(document.getElementById('right-content'), { quality: 0.95 })
      //   .then(function (dataUrl) {
      //     var link = document.createElement('a');
      //     link.download = 'TradeSeasonals-Export.jpeg';
      //     link.href = dataUrl;
      //     link.click();
      //   })
      //   .catch((err) => {
      //     console.log(err)
      //   })

      // switched to html2canvas because it html-to-img incorrectly scrolled pull-downs to first element and dropped 2 chars of 
      // data range shown above the tradedetail
      // still using html-to-image save library from html-to-image

      const timeoutid = setTimeout(() => {

        html2canvas(document.getElementById("right-content")).then(canvas => {
          const imgData = canvas.toDataURL('img/jpg');

          var link = document.createElement('a');
          link.download = props.downloadImageName;
          link.href = imgData;
          link.click();

          props.SetShowWatermark(false);
        });

      }, 2000);
    }
    props.SetExportImage(false) //reset the clicked export button 
  }, [props.exportImage])
  //------------------------------------------------------------------------------------------
  const handle_Settings_clicks = () => {

    if (loggedinUser === '0') {
      props.SetDialogType('info-box');
      props.SetDialogProp({ title: 'Settings', contentText: settings_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
      props.SetInfoBoxVisible(true);
    }
    else {
      props.SetShowSettings(true);
    }
  }
  //------------------------------------------------------------------------------------------
  const handle_slide_change = (swiperCore) => {

  }
  //------------------------------------------------------------------------------------------
  return (
    <div style={appContainerStyle}>

      {/* afshin covers only */}
      {coverOpp && <div className='opp-cover'></div>}
      {coverBottomCharts && <div className='bottom-chart-cover'></div>}
      {coverTopCharts && <div className='top-chart-cover'></div>}



      {/* {props.helpBoxVisible && <InfoPopupHelp {...props} />} */}
      {props.videosBoxVisible && <HelpPanelPopup onClose={() => props.SetVideosBoxVisible(false)} />}
      {props.reportsDashVisible && <ReportsDashboard {...props} />}
      {/* {props.reportsDashVisible && <TestGIS {...props} />} */}


      {props.addGCVisible && props.selectedPortfolio[0] === '&' && <TradeInstrument {...props} />}
      {props.addGCVisible && props.selectedPortfolio[0] !== '&' && <AddGC {...props} />}

      {props.infoBoxVisible && <InfoPopup {...props} />}
      {props.showPortfolioSettings && <PortfolioSettings {...props} />}
      {props.showOppNote && <OppNote {...props} />}
      {props.showSettings && <Settings {...props} />}
      {props.showSecuritiesGroupSettings && <SecuritiesGroupSettings {...props} />}

      {props.showPopulatePortfolio && <PopulatePortfolio {...props} />}

      {props.showAutoTrade && <AutoTrade {...props} />}

      {props.showTradeReport && <TradeReport {...props} />}

      {props.showTradeInstrumentReport && <TradeInstrumentReport {...props} />}



      <div className='left-nav'>

        <div className='security-selection' onClick={handleSecurityDivClicked}>

          <div style={{ width: "50%", height: "100%", backgroundColor: 'transparent', justifyContent: "center", display: "flex", userSelect: 'none' }}>
            <div style={{ paddingTop: '2px', display: 'flex', alignItems: 'center' }} >
              {/* <BsInfoCircle size={18} style={{ fill: props.tooltipSW ? "red" : "white" }} onClick={handleTooltipSW} /> */}

              <span style={{ color: "white", margin: "8px" }} >tooltips</span>
              {
                props.tooltipSW
                  ? <img src={"data:image/png;base64, " + toggle_on_64} alt="" style={{ width: toggle_width }} onClick={handleTooltipSW} />
                  : <img src={"data:image/png;base64, " + toggle_off_64} alt="" style={{ width: toggle_width }} onClick={handleTooltipSW} />
              }

              <div style={{ paddingLeft: '1vw', display: "flex", flexDirection: 'row', alignItems: "center", "justifyContent": "flex-start", height: "100%", width: "100%", backgroundColor: 'transparent' }} onClick={handle_Settings_clicks}>
                {(props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16' || props.loggedinUser === '190') &&
                  <SlSettings size={settingsSize} style={{ fill: "white", backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                }
              </div>



              {/* clicking the stars above oppTable will show the upgrade stuff in desktop  */}
              {props.upgradeMessage != '' && !props.showUpgradeBanner &&
                <div
                  style={{
                    paddingLeft: '1vw',
                    display: "flex",
                    flexDirection: 'row',
                    alignItems: "center",
                    justifyContent: "flex-start",
                    height: "100%",
                    width: "100%",
                    backgroundColor: 'transparent'
                  }}
                  onClick={() => props.SetShowUpgradeBanner(true)} // Update onClick handler
                >
                  <span style={{
                    color: "white",
                    margin: "8px",
                    fontSize: '1vw'
                  }}>
                    ✨
                  </span>
                </div>
              }

            </div>
          </div>

          <div style={{ display: "flex", flexDirection: 'row', alignItems: "center", "justifyContent": "flex-start", height: "100%", width: "34%", backgroundColor: 'transparent' }}>
            {props.loggedinUser === '0' &&
              <AiOutlineDollarCircle size={20} style={{ fill: "white" }} onClick={handleDollarClicked} />

            }
          </div>


          {(props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16') &&
            <div style={{ display: "flex", flexDirection: 'row', alignItems: "center", "justifyContent": "flex-start", height: "100%", width: "34%", backgroundColor: 'transparent' }}>

              <div style={{ marginLeft: '1vw' }}> <BsFillCircleFill size={8} style={{ fill: "white" }} onClick={() => handleAMbutton(1)} /></div>
              <div style={{ marginLeft: '1vw' }}> <BsFillCircleFill size={8} style={{ fill: "white" }} onClick={() => handleAMbutton(2)} /></div>
              <div style={{ marginLeft: '1vw' }}> <BsFillCircleFill size={8} style={{ fill: "white" }} onClick={() => handleAMbutton(3)} /></div>

            </div>
          }

          <div style={{ width: "33%", marginRight: "12px", display: "flex", alignItems: "center", justifyContent: 'flex-end', userSelect: 'none' }}>
            <SelectBox tooltipContent={props.tooltipSW ? 'r,Set Securities Group' : ''} optionList={props.securityTypeList} name="securityTypeList" value={props.selectedSecurity} sbChanged={props.selectboxChanged} />
          </div>

        </div>

        <div className='opp_table_div'>
          <OppTable {...props} />
        </div>
      </div>

      <div id='right-content' >

        <div className='seasonal-barchart-parent'>
          <SeasonalBarChart {...props} chartTo={chartTo} />
        </div>

        <div className='stock-linechart-parent'>

          {/* handle_slide_change */}

          {/* <Swiper onSwiper={(s) => { props.setSwiper(s); }} navigation={true} className="mySwiper" initialSlide={initialSlide} onSlideChange={(swiperCore) => { const { activeIndex } = swiperCore; setCookie('WindowNumber', activeIndex.toString(), 300) }} > */}
          <Swiper onSwiper={(s) => { props.setSwiper(s); }}
            navigation={true}

            className="mySwiper no-mouse-drag"
            initialSlide={props.initialWindowNum}
            onSlideChange={(swiperCore) => { const { activeIndex } = swiperCore; setCookie('WindowNumber', activeIndex.toString(), 300) }}
            allowSlideNext={true}
            allowSlidePrev={true}
          // noSwiping={true}
          // noSwipingClass= 'swiper-no-swiping'
          >

            <SwiperSlide>
              <SeasonalChart
                {...props}
                chartTo={chartTo}
                chartTitle="Seasonal Chart"
                chartData={props.consolidatedSeasonalData}

              />
            </SwiperSlide>

            <SwiperSlide>
              <TradeDetail {...props} chartTo={chartTo} />
            </SwiperSlide>


            <SwiperSlide>
              <StockLineChart {...props} chartTo={chartTo} />
            </SwiperSlide>

          </Swiper>

        </div>

      </div>

    </div>
  );
}

export default DesktopLayout;
