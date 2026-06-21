// got rid of geo fetching from client side

// to change the userid and userlevel for testing, it needs to be changed in 2 places startss as if (debug) ...
// 1) line 1025 - changes level
// 2) line 1060 - changes userid
// 3) line 1163 - changes level



import React, { useState, useLayoutEffect, useEffect, useMemo, useRef } from "react"
import { getTodayDate, monthsOptionsList, DarkBGColor, LightBGColor } from './Common'
import * as rdd from 'react-device-detect';
import DesktopLayout from './DesktopLayout'
import MobileLayoutP from './MobileLayoutP'
import MobileLayoutL from './MobileLayoutL'
import { BrowserView, MobileView } from 'react-device-detect';
import { UserContext } from './UserContext'
import 'tippy.js/dist/tippy.css';

// import { flaskServerIP } from './Common'   // for login
import { freeYears, startingSecurity, startingSecurityName } from './Common' // for free users
import { incrementDate } from './Common'
import { debug } from './Common';
import { appserverURL, securities_groups_default_years, default_years_pe, securities_groups_default_years_pe } from './Common'
import { getSelectedIDFromSecuritiesList2 } from './Common'
import { trend_chart_left_gap_days } from './Common'
import { userAccessToSelectedSecurity } from './Common'

import { getCookie, setCookie } from './Common'
import { lsGet, lsSet, lsRemove, clearUserStorage } from './Common'
import { twFetch, registerTwFetchAuth } from './twFetch'
import ErrorBoundary from './ErrorBoundary'
import jwt_decode from 'jwt-decode'
//-------------------- swiper -----------------------------
// Import Swiper styles
import "swiper/swiper.min.css";
import "swiper/components/pagination/pagination.min.css"
import "swiper/components/navigation/navigation.min.css"
// import Swiper core and required modules
import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';
// import { waitForElementToBeRemoved } from "@testing-library/react";
// install Swiper modules
SwiperCore.use([Pagination, Navigation, Virtual]);
//-------------------- swiper -----------------------------

const App = () => {


  // if (debug) userid = '1'; // this is Tidal Yearly 
  // if (debug) userid = '19'; // this is free Ripple 
  // if (debug) userid = testUserID; // this is for testing Free Ripple level only
  // if (debug) userid = '17'; // this is me - this is basic - 15 is premium

  // if (debug) userid = '16'; // this is me - this is free registered
  // if (debug) userid = '0'; // testing non loggedin user

  // assinged only when debug === true
  const testUserLevel = '9'; // '0' is not loggedin 1 is free Ripple 2 is splash_monthly 4 is yearly 5 is surf_monthly 6 is yearly tidal 8 and 9
  const testUserID = '1';    // userid=0 is not_loggedin userid = 19 has free explorer 1 is strategist yearly 

  //############################# parameters ##############################
  // const debug = true;   // set to true to use port 3000 debugging 
  // const { qstr } = useParams(); // this is to get the querystring in react 5/8/2023 - didn't work - using windows funcs instead


  //-------- set to false not to display the disclosure box in app start
  const [infoBoxVisible, SetInfoBoxVisible] = useState(false); //default of next 3 should be false
  const [helpBoxVisible, SetHelpBoxVisible] = useState(false);
  const [videosBoxVisible, SetVideosBoxVisible] = useState(false);
  const [reportsDashVisible, SetReportsDashVisible] = useState(false);
  const [sessionExpired, SetSessionExpired] = useState(false);

  const [dialogType, SetDialogType] = useState('terms-conditions');
  const [dialogProp, SetDialogProp] = useState({ title: 'init', contentText: 'none', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' }) // this is used to pass properties for info-box dialog
  const [swiper, setSwiper] = useState(null);

  const [browserH, SetBrowserH] = useState(window.innerHeight)
  const [browserW, SetBrowserW] = useState(window.innerWidth)

  const [globalTextSize, SetGlobalTextSize] = useState('1vw') // use this throughout the app to display text on various devices
  const [checkboxZoom, SetCheckboxZoom] = useState('1')
  const [tableTextSize, SetTableTextSize] = useState('1vw');
  const [tableTitleTextSize, SetTableTitleTextSize] = useState('1vw');
  const [infoTextSize, SetInfoTextSize] = useState('1vw');

  // reactpress sizing modifications code
  const [seasonalAppDivH, setSeasonalAppDivH] = useState(0)   //dekstop app height with react press with header and footer
  const [seasonalAppDivH2, setSeasonalAppDivH2] = useState(0) //dekstop app height with react press without header and footer

  // console.log(rdd.isMobile, browserH, browserW)

  const [seasonalBarChartData, SetSeasonalBarChartData] = useState([])
  const [tradeDetailData, SetTradeDetailData] = useState([])
  const [consolidatedSeasonalData, SetConsolidatedSeasonalData] = useState([])
  const [janDecDateRange, SetJanDecDateRange] = useState(false);

  const [startDate, SetStartDate] = useState(getTodayDate());

  const [symbol, SetSymbol] = useState("");
  const [company, SetCompany] = useState("");
  const [daysOut, SetDaysOut] = useState("30");


  const [seasonalYears, SetSeasonalYears] = useState("10");
  const [monthsAndQtrs, SetMonthsAndQtrs] = useState('Months & Qtrs');

  const [oppTableLength, SetOppTableLength] = useState(0); // this is the number displayed in the bottom of opp table


  const [showMFE, setShowMFE] = useState(() => {
    let ret = true;
    let MFEdisp = getCookie('MFE');

    if (MFEdisp == null) ret = false; // default value
    else {
      if (MFEdisp === 'true') ret = true;
      else ret = false;
    }
    return ret;
  });
  const [showMAE, setShowMAE] = useState(() => {
    let ret = true;
    let MAEdisp = getCookie('MAE');

    if (MAEdisp == null) ret = false; // default value
    else {
      if (MAEdisp === 'true') ret = true;
      else ret = false;
    }
    return ret;
  });

  const [helpEmailDisplay, SetHelpEmailDisplay] = useState('none'); // css display value for help dialog

  const [barChartLongOrShort, SetBarChartLongOrShort] = useState('long')
  const [lineChartYear, SetLineChartYear] = useState(0)

  const [tradeActive, SetTradeActive] = useState(false) // true if the latest trade is active 
  const [tradeDate0, SetTradeDate0] = useState('') //current linechart date0
  const [tradeDate1, SetTradeDate1] = useState('') //current linechart date1

  const [lastPrice, SetLastPrice] = useState(['', 0]); // last stock price to be shown in VisualTableDesc.js

  const [token, SetToken] = useState('')

  const [securityTypeList, SetSecurityTypeList] = useState([])
  const [securityTypeList2, SetSecurityTypeList2] = useState([]) // 4/12/2022 new format - keeping

  const [selectedSecurity, SetSelectedSecurity] = useState(() => {
    // console.log('iiiiiiiiiinitialize setting selected security to blank')
    return '';
  });

  const [selectedSecurityType, SetSelectedSecurityType] = useState('F') //'F' or 'P' free or premium



  // 8/22/2021 moved it from oppTable 
  const [opportunities, SetOpportunities] = useState([])// opportinities table data
  const [activeOpportunities, SetActiveOpportunities] = useState([])// 5/2/2024
  const [showActiveOpps, SetShowActiveOpps] = useState(false); // 5/2/2024

  const [oppTableMonth, SetOppTableMonth] = useState(() => {
    var TodayDate = new Date();
    var isLeapDay = TodayDate.getMonth() === 1 && TodayDate.getDate() === 29;
    if (isLeapDay) return 'March'; // skipping feb 29th and going straight to march 1st
    // console.log('*******************************',monthsOptionsList[TodayDate.getMonth()]['value'])
    return (monthsOptionsList[TodayDate.getMonth()]['value'])
  })
  const [oppTableYears, SetOppTableYears] = useState("12")


  const [oppTablePartialYears, SetOppTablePartialYears] = useState(-1)


  const [appliedFilter, SetAppliedFilter] = useState('no filter')

  const [rowIndexClicked, SetRowIndexClicked] = useState(-1);

  // user data
  const [loggedinUser, SetLoggedinUser] = useState('0')
  const [wpUserLevels, SetWpUserLevels] = useState([0]) // level 0 is for non logged-in users


  const [userDateRange, SetUserDateRange] = useState([]) // mainly for level 1 week


  // had to move here because when mobile orientation chagnes, there was an undefined bug
  const [statBoxCoordinates, SetStatBoxCoordinates] = useState(['13%', '4.5%', '25%', '30%'])


  //-------------------------------------------------------------------------------------------------------
  // this is for the day of the month textbox
  const [dayOfTheMonth, SetDayOfTheMonth] = useState(parseInt(getTodayDate().substring(8, 10)).toString())
  const [daysOfMonthList, SetDaysOfMonthList] = useState([]) // 4/30/2022 switching opp day to pull down
  //---------------------------------------------------------------


  // const [userGeoData, SetUserGeoData] = useState({ 'error': '!', 'IPv4': '' })

  const [allowedSymbols, SetAllowedSymbols] = useState({})


  // tooltip on/off
  const [tooltipSW, SetTooltipSW] = useState(false)


  //4/12/2022 - 
  const [resourceObj, SetResourceObj] = useState({})



  const [userFreeResources, SetUserFreeResources] = useState([])
  const [userPremResources, SetUserPremResources] = useState([])
  // const [userNonLoggedResources, SetUserNonLoggedResources] = useState([])



  const [yearsMetaData, SetYearsMetaData] = useState([]); // get all years and partial years based on data 
  const [yearsMetaDataPE, SetYearsMetaDataPE] = useState([]); // get all years and partial years based on data for PE years 
  const [showPEOpps, SetShowPEOpps] = useState(() => getCookie('showPEOpps') === 'true'); // when true, the presidential election opportunities are loaded
  const [PEOppsChecked, SetPEOppsChecked] = useState(false);

  const [stockScoreCurrent, SetStockScoreCurrent] = useState(true) // toggle between historical and current stockscore.  when historical, use the start date set on seasonalviewer


  const [exportImage, SetExportImage] = useState(false)

  const [numReportsAllowed, SetNumReportsAllowed] = useState(0); // this is the number of reports a user is allowed to generate
  const [numReportsCreated, SetNumReportsCreated] = useState(-1); // -1 means it has been loaded yet
  const [numPortfoliosAllowed, SetNumPortfoliosAllowed] = useState(0);
  const [reportsList, SetReportsList] = useState([]);

  const [upgradeMessage, SetUpgradeMessage] = useState('') // this is the message that is displayed when user is free ripple to upgrade
  const [promotionMessage, SetPromotionMessage] = useState('') // this is the message that is displayed when user is free ripple and has promotions
  const [promotionCouponCode, SetPromotionCouponCode] = useState('') // this is the message that is displayed when user is free ripple and has promotions
  const [showUpgradeBanner, SetShowUpgradeBanner] = useState(false) // this is the switch to display the upgrade banner
  const [promotionBackColor, SetPromotionBackColor] = useState('orange')

  const [addGCVisible, SetAddGCVisible] = useState(false);
  const [googleCalendarDict, SetGoogleCalendarDict] = useState({});

  const [multiPortfolios, SetMultiPortfolios] = useState(true); // switch to turn multi portfolios on and off
  const [showPortfolioSettings, SetShowPortfolioSettings] = useState(false);
  const [reportsDashRect, SetReportsDashRect] = useState(null);

  const [showSettings, SetShowSettings] = useState(false);

  // TW2 defaults: Date, Ticker, Days, DIR, SR, AvgP, Price + AI Win% + AI PredR. Everything else hidden.
  const DEFAULT_COL_VISIBILITY = {
    date: true, symbol: true, daysOut: true, lOrS: true, sharpe_ratio: true,
    avg_profit: true, price: true, win_prob: true, pred_return: true,
    avg_profit2: false, sharpe_ratio2: false, TL: false, ml_score: false, pred_mfe: false,
  };
  const [columnVisibility, SetColumnVisibility] = useState(() => {
    const saved = lsGet('oppTableColumnVisibility');
    if (saved) return { ...DEFAULT_COL_VISIBILITY, ...saved };
    return { ...DEFAULT_COL_VISIBILITY };
  });
  const handleSetColumnVisibility = (newVis) => {
    SetColumnVisibility(newVis);
    lsSet('oppTableColumnVisibility', newVis);
  };

  const DEFAULT_COL_ORDER = ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'avg_profit', 'avg_profit2', 'sharpe_ratio2', 'TL', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'];
  const [columnOrder, SetColumnOrder] = useState(() => {
    const parsed = lsGet('oppTableColumnOrder');
    if (Array.isArray(parsed)) {
      const validSet = new Set(DEFAULT_COL_ORDER);
      const result = parsed.filter(c => validSet.has(c));
      DEFAULT_COL_ORDER.forEach(c => { if (!result.includes(c)) result.push(c); });
      return result;
    }
    return [...DEFAULT_COL_ORDER];
  });
  const handleSetColumnOrder = (newOrder) => {
    SetColumnOrder(newOrder);
    lsSet('oppTableColumnOrder', newOrder);
  };

  const [showVolume, SetShowVolume] = useState(() => {
    const saved = lsGet('showVolume');
    return saved === null ? true : !!saved;
  });
  const handleSetShowVolume = (val) => {
    SetShowVolume(val);
    lsSet('showVolume', val);
  };

  const DEFAULT_MA_CONFIG = [
    { enabled: false, period: 20,  type: 'ema', color: '#e8a838', dash: 'solid' },
    { enabled: true,  period: 50,  type: 'sma', color: '#c850c8', dash: 'solid' },
    { enabled: false, period: 100, type: 'sma', color: '#38b8e8', dash: 'solid' },
    { enabled: false, period: 200, type: 'sma', color: '#48c848', dash: 'solid' },
  ];
  const [maConfig, SetMaConfig] = useState(() => {
    const saved = lsGet('maConfig');
    return saved || DEFAULT_MA_CONFIG;
  });
  const handleSetMaConfig = (val) => {
    SetMaConfig(val);
    lsSet('maConfig', val);
  };

  const DEFAULT_BB_CONFIG = {
    enabled: false,
    period: 20,
    multiplier: 2,
    color: '#e8a838',
    fill: true,
  };
  const [bbConfig, SetBbConfig] = useState(() => {
    const saved = lsGet('bbConfig');
    return saved || DEFAULT_BB_CONFIG;
  });
  const handleSetBbConfig = (val) => {
    SetBbConfig(val);
    lsSet('bbConfig', val);
  };

  const [showProjection, SetShowProjection] = useState(() => {
    const saved = lsGet('showProjection');
    return saved === null ? true : !!saved;
  });
  const handleSetShowProjection = (val) => {
    SetShowProjection(val);
    lsSet('showProjection', val);
  };

  const [projectionPeriod, SetProjectionPeriod] = useState(() => {
    const saved = lsGet('projectionPeriod');
    return saved || '90';
  });
  const handleSetProjectionPeriod = (val) => {
    SetProjectionPeriod(val);
    lsSet('projectionPeriod', val);
  };

  const [priceChartTimeframe, SetPriceChartTimeframe] = useState(() => {
    return lsGet('priceChartTimeframe') || 'daily';
  });
  const handleSetPriceChartTimeframe = (val) => {
    SetPriceChartTimeframe(val);
    lsSet('priceChartTimeframe', val);
  };

  const [showEarnings, SetShowEarnings] = useState(() => {
    const saved = lsGet('showEarnings');
    return saved === null ? true : !!saved;
  });
  const handleSetShowEarnings = (val) => {
    SetShowEarnings(val);
    lsSet('showEarnings', val);
  };

  const [chartRange, SetChartRange] = useState(() => {
    return lsGet('chartRange') || '6m';
  });
  const handleSetChartRange = (val) => {
    SetChartRange(val);
    lsSet('chartRange', val);
  };

  const [portfolios, SetPortfolios] = useState([]);

  const [selectedPortfolio, SetSelectedPortfolio] = useState(() => {

    let cookie = getCookie('selected_portfolio')

    if (cookie !== null) {
      return cookie.split(',')[1];
    }
    else return 'main';
  });
  const [selectedPortfolioID, SetSelectedPortfolioID] = useState(() => {
    let cookie = getCookie('selected_portfolio')

    if (cookie !== null) {
      return cookie.split(',')[0];
    }

    else return 0;
  });


  const [watchlists, SetWatchlists] = useState([]);
  const [defaultWatchlistName, SetDefaultWatchlistName] = useState('');
  const [defaultWatchlistItems, SetDefaultWatchlistItems] = useState([]);
  const [defaultWatchlistResourceId, SetDefaultWatchlistResourceId] = useState(-1); // resource id of the default watchlist
  const [numWatchlistsAllowed, SetNumWatchlistsAllowed] = useState(0);
  const [numWatchlistItemsAllowed, SetNumWatchlistItemsAllowed] = useState(0);
  const [showWatchlistSettings, SetShowWatchlistSettings] = useState(false);
  const [showWatchlistOnFocus, SetShowWatchlistOnFocus] = useState(() => {
    let saved = getCookie('show_watchlist_on_focus');
    return saved === null ? true : saved === 'true';
  });
  const [activeWatchlistFilter, SetActiveWatchlistFilter] = useState(null); // {name, resourceId, symbols: Set} when watchlist selected in securities dropdown

  const [publishedLists, SetPublishedLists] = useState([]);
  const [isAdmin, SetIsAdmin] = useState(false);
  const [userRoles, SetUserRoles] = useState(window.tw2_user_roles || ['user']);
  const [securitiesPrefs, SetSecuritiesPrefs] = useState({ hidden_groups: [], enabled_published: [] });
  const [showSecuritiesGroupSettings, SetShowSecuritiesGroupSettings] = useState(false);

  const [qparams, SetQparams] = useState(''); // this is used to know if the session started with passed parameter
  const [showOppNote, SetShowOppNote] = useState(false);

  // selectedNote and selectedDRID are used for updating the note for the opp
  const [selectedNote, SetSelectedNote] = useState('');
  const [selectedDRID, SetSelectedDRID] = useState('');
  const [selectedPortfolioRec, SetSelectedPortfolioRec] = useState('');

  // this is used for comparing the current security to another - by default its S&P500 index 9/9/2023

  const [compareSecurity, SetCompareSecurity] = useState([5, 'SPX', '01-01', 366]); // last 2 are start date and num days for S&p500 



  const [compareSecurityBarChartData, SetCompareSecurityBarChartData] = useState([]);
  const [compareSecurityTradeDetailData, SetCompareSecurityTradeDetailData] = useState([]);
  const [compareSecurityLongOrShort, SetCompareSecurityLongOrShort] = useState('long');

  const [securityBHstats, SetSecurityBHstats] = useState([]);

  const [reverseDateSelected, SetReverseDateSelected] = useState(false); // this flag is used by consolidatedSeasonalChart to set a better initial date for the reversed chart

  // this used for the start date and end date of the trend chart
  // its initially set to the current opportunity start date - 14 days
  // if date range is reversed its again set to the reversed opportunity start date - 14
  // it does not   
  const [trendChartStartDate, SetTrendChartStartDate] = useState('') // this used for the start date and end date of the trend chart

  const [initialWindowNum, SetInitialWindowNum] = useState(() => {
    let bottomWindowNumber = getCookie('WindowNumber');

    let queryString = window.location.search;
    if (queryString.length > 0 && queryString !== '?set=on') {
      bottomWindowNumber = 2; // slide 3 (current price chart) for querystring loads
    }

    if (bottomWindowNumber === null) return "1";
    return bottomWindowNumber;
  });

  // trim year is used to trim the oldest years for special years like odd, even, PE, PE1, PE2, PE3 - 
  // trimyear only effects those special years, regular years has no change by trim year
  const [trimYear, SetTrimYear] = useState(0); // used for setting the oldest year cut off - useful for cutting the 1928 ... in 95 year PE3 SPX for example

  const [autoTradePortfolioMonth, SetAutoTradePortfolioMonth] = useState('');

  // this is an array of display switches.  before everytime I created a new dialog I declared a new variable - now let's just use this as an array 11/18/2023
  // [0] = populate_portfolio dialog
  const [showPopulatePortfolio, SetShowPopulatePortfolio] = useState(false);
  const [showAutoTrade, SetShowAutoTrade] = useState(false);
  const [showTradeReport, SetShowTradeReport] = useState(false);

  const [showTradeInstrumentReport, SetShowTradeInstrumentReport] = useState(false);
  const [tradeInstrumentReportDict, SetTradeInstrumentReportDict] = useState({});

  const [showSR2, SetShowSR2] = useState(false); // this is to control the configuration of oppTable that display 2 additional columns for AP2 and SR2
  const [shortDates, SetShortDates] = useState(() => {
    return lsGet('tw_short_dates') === '1' || lsGet('tw_short_dates') === true;
  });

  const [switchStreamingQuotes, SetSwitchStreamingQuotes] = useState(true); // this is to switch streaming quotes on and off
  const [switchStreamingAccount, SetSwitchStreamingAccount] = useState(true); // this is to switch streaming account on and off

  const [showWatermark, SetShowWatermark] = useState(false); // this is to show the watermark on the chart
  const [downloadImageName, SetDownloadImageName] = useState('initial.jpg');

  const [showChatbot, SetShowChatbot] = useState(false);
  const [chatbotEnabled, SetChatbotEnabled] = useState(false);
  const [chatbotIconBlink, SetChatbotIconBlink] = useState(false);
  const [chatbotPendingTip, SetChatbotPendingTip] = useState(null);
  const [chatbotPrefill, SetChatbotPrefill] = useState(null); // home-page "ask Tara" question to auto-send (desktop)
  const [askMobileNote, SetAskMobileNote] = useState(false);  // mobile note when home asks Tara but no chat UI exists
  const chatbotTipTimerRef = useRef(null);
  const queryStringLoadedRef = useRef(false);
  const askHandledRef = useRef(false);  // one-shot guard for home-page ?ask= deep-link
  const arrivedViaPatternLink = useRef(window.location.search.length > 0 && window.location.search !== '?set=on');
  const historyInitialized = useRef(false);  // true after first URL is written
  const isPopstateNav = useRef(false);       // true when navigating via back/forward
  const prevPatternKey = useRef('');          // tracks symbol|startDate to detect deliberate changes

  // Used to manually trigger a refresh of the useEffect below.
  // Every time we increment refreshKey, the effect re-runs.
  // This is useful when external actions need to force a re-load or re-fetch,
  // even if dependencies haven't naturally changed.
  const [refreshKey, SetRefreshKey] = useState(0);

  const [showArticlePublish, SetShowArticlePublish] = useState(false);

  const [PEselected, SetPEselected] = useState('cons');

  const [UITheme, SetUITheme] = useState(() => localStorage.getItem('UITheme') || 'dark');

  const [backgroundColor, SetBackgroundColor] = useState(() => (localStorage.getItem('UITheme') || 'dark') === 'dark' ? DarkBGColor : LightBGColor)

  // Force dark mode on mobile (non-tablet-landscape) - no toggle available
  useEffect(() => {
    if (rdd.isMobile && !(rdd.isTablet && window.innerWidth > window.innerHeight)) {
      SetUITheme('dark');
      SetBackgroundColor(DarkBGColor);
    }
  }, []);

  // ########################################################################################################################################################
  // #################################################################### End Declerations ##################################################################
  // ########################################################################################################################################################

  //--------create list for day of the month selectbox 4/30/2022-----------------------------------------------------------------------------------------------

  const dayOfMonthList = (m) => {

    // now create SetDaysOfMonthList  4/30/2022
    // get current opp_date before increment 
    // let monthNum = 0;
    let lastDayOfMonth = '';
    for (let i = 0; i < monthsOptionsList.length; i++) {
      if (monthsOptionsList[i]['label'] === m) {
        lastDayOfMonth = parseInt(monthsOptionsList[i]['range'][1].split('-')[1]) // get last day from common

        // console.log('found=',monthsOptionsList[i]['label'] , oppTableMonth)
        break;

      }
    }

    // console.log('lastDayOfMonth=', lastDayOfMonth, props.oppTableMonth)


    // console.log('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',process.env.REACT_APP_HELP_VIDEOS)

    let tmp = []

    for (let i = 1; i <= lastDayOfMonth; i++) {
      tmp.push({ id: i, value: i.toString(), label: i.toString() })
    }
    SetDaysOfMonthList(tmp) // 4/30/2022 for use with day of the month pulldown
  }


  //-------------------------------------------------------------------------------------------------------
  // Get saved oppTable years/pyears for a security group, falling back to Common.js defaults
  // Resolution: global default -> per-market override -> cookie. PE mode uses
  // a separate global default ([6,6]), separate override dict, and a separate
  // cookie slot so PE and cons selections persist independently. This is the
  // ONLY source of the years value on a market switch — the SeasonalBarChart
  // "max years" computation must never silently rewrite it (that produced the
  // jump-to-4 / empty-chart bug).
  const getOppYearsForGroup = (groupName, peMode = false) => {
    let [y1, y2] = peMode ? [...default_years_pe] : [10, 10];
    const overrideDict = peMode ? securities_groups_default_years_pe : securities_groups_default_years;
    if (groupName in overrideDict) {
      [y1, y2] = overrideDict[groupName];
    }
    const cookieKey = peMode ? 'oppYearsPerGroupPE' : 'oppYearsPerGroup';
    try {
      const saved = JSON.parse(getCookie(cookieKey) || '{}');
      if (saved[groupName]) {
        [y1, y2] = saved[groupName];
      }
    } catch (e) { }
    return [y1, y2];
  }

  const saveOppYearsForGroup = (groupName, y1, y2, peMode = false) => {
    const cookieKey = peMode ? 'oppYearsPerGroupPE' : 'oppYearsPerGroup';
    // Clamp min-profitable-years (y2) to the lookback window (y1). The Years
    // dropdown handler saves [newYears, currentPartialYears], so lowering Years
    // below a previously-set partial-years would otherwise persist an invalid
    // pair (e.g. [15,18]) for which no Monthly_Opp_<month>_<y1>_<y2> dataset
    // exists — the appserver then returns its -1 sentinel and the opp table
    // shows "Data temporarily unavailable".
    if (Number.isFinite(y1) && Number.isFinite(y2) && y2 > y1) y2 = y1;
    let saved = {};
    try { saved = JSON.parse(getCookie(cookieKey) || '{}'); } catch (e) { }
    saved[groupName] = [y1, y2];
    setCookie(cookieKey, JSON.stringify(saved), 300);
  }

  //-------------------------------------------------------------------------------------------------------

  //- increment decrement or set date to a new number - returns true if number has changed - otherwise false
  const incdecDay = (incnum, newnum) => {

    // get current opp_date before increment 
    var monthNum = 0;
    for (let i = 0; i < monthsOptionsList.length; i++) {
      if (monthsOptionsList[i]['label'] === oppTableMonth) {
        monthNum = monthsOptionsList[i]['id']; break;
      }
    }

    var tmp_dayOfTheMonth = parseInt(dayOfTheMonth)
    tmp_dayOfTheMonth = (tmp_dayOfTheMonth < 10 ? '0' : '') + tmp_dayOfTheMonth.toString()

    // console.log('dayofthemonth=', dayOfTheMonth, typeof (dayOfTheMonth))

    var opp_date = getTodayDate().substring(0, 4) + '-' + (monthNum < 10 ? '0' : '') + monthNum.toString() + '-' + tmp_dayOfTheMonth;
    var new_opp_date = incrementDate(opp_date, incnum)


    if (userDateRange.length === 2) { // this user has restrictions currenlty due to free registered.  
      if (new_opp_date < userDateRange[0] || new_opp_date > userDateRange[1]) {
        // this user does not have access to dates beyond userDateRange.  Show message
        // console.log('false')
        return false;
      }
    }

    // check if + or - was clicked at the first day or last days of the month
    // where month and day should change - change day and month for continuity
    if (opp_date.substring(5, 7) !== new_opp_date.substring(5, 7)) {

      var new_month_num = new_opp_date.substring(5, 7)
      new_month_num = parseInt(new_month_num)

      var newMonth = monthsOptionsList[new_month_num - 1].value
      var newDay = new_opp_date.substring(8, 10)

      SetDayOfTheMonth(parseInt(newDay))
      SetOppTableMonth(newMonth)
      dayOfMonthList(newMonth)  // 4/30/2022 - this is to create day of the month selectbox for opptable
      return true
    }


    let d = parseInt(dayOfTheMonth) // currently set dayofthemonth


    let orig_num = d;
    if (incnum !== 0) {
      d += incnum;
    }
    else {
      d = newnum
    }

    monthNum = 0;
    let range = []
    for (let i = 0; i < monthsOptionsList.length; i++) {
      if (monthsOptionsList[i]['label'] === oppTableMonth) {
        monthNum = monthsOptionsList[i]['id'];
        range = monthsOptionsList[i]['range']
        break;
      }
    }

    let maxMonthNum = parseInt(range[1].substring(3, 5))



    if (d > 0 && d <= maxMonthNum) {
      SetDayOfTheMonth(d)

      return true;
    }
    else {
      SetDayOfTheMonth(orig_num)
      return false;
    }
  }
  //---------------------------------------------------------------
  // this is event handler for increment and decrement of the day of the month 
  const dayIncrement = () => { // num should be 1 or -1


    if (loggedinUser === '0' || (wpUserLevels.length === 1 && wpUserLevels[0] === '1')) {  // removing the 1 week allowance for registered free
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }


    // if selected security is Free, change the oppTable date to today
    let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
    if (retArray[0] === 'F') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }




    if (incdecDay(1, 0))
      SetOpportunities([]) //clear opportunties table becaues there will be a new fetch
  }
  //---------------------------------------------------------------
  const dayDecrement = () => { // num should be 1 or -1
    if (loggedinUser === '0' || (wpUserLevels.length === 1 && wpUserLevels[0] === '1')) {  // see above
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }

    let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
    if (retArray[0] === 'F') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }


    if (incdecDay(-1, 0))
      SetOpportunities([]) //clear opportunties table becaues there will be a new fetch
  }
  //---------------------------------------------------------------
  const handleBlurInc = (event) => {
    // console.log('blur')
    if (loggedinUser === '0') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }
    // if (wpUserLevels.length == 1 && wpUserLevels[0] == '1') return; //free registered can't type and press enter

    if (incdecDay(0, event.target.value)) // set to the number that was typed in
      SetOpportunities([]) //clear opportunties table becaues there will be a new fetch
  }
  //---------------------------------------------------------------
  const handleEnterInc = (event) => {
    if (event.key === 'Enter') {
      if (loggedinUser === '0') {
        SetDialogType('free-register')
        SetInfoBoxVisible(true);
        return;
      }
      // if (wpUserLevels.length == 1 && wpUserLevels[0] == '1') return; //free registered can't type and press enter

      if (incdecDay(0, event.target.value)) // set to the number that was typed in
        SetOpportunities([]) //clear opportunties table becaues there will be a new fetch
    }
  }
  //---------------------------------------------------------------
  const handleDayChange = (event) => {


    if (loggedinUser === '0') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }
    if (wpUserLevels.length === 1 && wpUserLevels[0] === '1') return; //free registered can't type and press enter

    let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
    if (retArray[0] === 'F') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }

    if (incdecDay(0, event.target.value)) // set to the number that was typed in
      SetOpportunities([]) //clear opportunties table becaues there will be a new fetch
  }
  //---------------------------------------------------------------
  // this serves oppTable selectboxes
  //---------------------------------------------------------------
  const selectboxChanged = (event) => {

    // console.log('...........event.......... selectboxchanged   ')

    if (wpUserLevels.length === 1 && wpUserLevels[0] === '1' && event.target.id !== 'filter' && event.target.id !== 'years' && event.target.id !== 'partialYears' && event.target.id !== 'securityTypeList') { //free registered
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }

    // supressing non-loggedin users from changing the years in the opportunity table
    if (event.target.id === 'years' && loggedinUser === '0') {
      SetDialogType('free-register')
      SetInfoBoxVisible(true);
      return;
    }

    // 5/2/2024 turning off the active opps visible variable when these selectboxes change
    if (event.target.id === 'months' || event.target.id === 'day' || event.target.id === 'years' || event.target.id === 'partialYears') {
      SetShowActiveOpps(false); // 5/2/2024
    }


    if (event.target.id === 'months') {

      if (loggedinUser === '0') {
        SetDialogType('free-register')
        SetInfoBoxVisible(true);
        return;
      }

      // console.log('props.selectedSecurity=', selectedSecurity)
      // console.log('securityTypeList2=', securityTypeList2)

      // 4/13/2022 - check if the selected security is Free or Premium for this user
      let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
      SetSelectedSecurityType(retArray[0])

      if (retArray[0] === 'F') {
        SetDialogType('free-register')
        SetInfoBoxVisible(true);
        return;
      }

      SetOppTableMonth(event.target.value)
      dayOfMonthList(event.target.value)  // 4/30/2022 - this is to create day of the month selectbox for opptable
      SetDayOfTheMonth('1')

    }
    else if (event.target.id === 'years') {


      //  if (retArray[0] === 'F') {
      //   SetDialogType('free-register')
      //   SetInfoBoxVisible(true);
      //   return;
      // }



      SetOppTableYears(event.target.value)
      saveOppYearsForGroup(selectedSecurity, parseInt(event.target.value), parseInt(oppTablePartialYears), PEselected !== 'cons')
      SetOppTablePartialYears(-1) // (1) this is to force render only after new partial year is established.  fixed the lockup bug 8/22/2021
    }
    else if (event.target.id === 'partialYears') {
      SetOpportunities([])
      SetOppTablePartialYears(event.target.value)
      saveOppYearsForGroup(selectedSecurity, parseInt(oppTableYears), parseInt(event.target.value), PEselected !== 'cons')
    }
    else if (event.target.id === 'day') {  // 4/30/2022 - changed day of the month to a pull down

      if (loggedinUser === '0') {
        SetDialogType('free-register')
        SetInfoBoxVisible(true);
        return;
      }

      let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
      // the returned array consists of 3 items  
      // [0] = access type for selected security: 'F' or 'P'
      // [1] = premium access count
      // [2] = free access count
      if (retArray[0] === 'F') {
        SetDialogType('free-register')
        SetInfoBoxVisible(true);
        return;
      }

      // console.log('----------------x------------------------------',securityTypeList2)
      // console.log('selected_security=',selectedSecurity)


      SetDayOfTheMonth(event.target.value)



    }
    else if (event.target.id === 'filter') {

      if (showActiveOpps == false) { // no % filtering for active opps
        SetAppliedFilter(event.target.value)
        if (event.target.value !== 'no filter') {
          setShowMFE(true)
        }
      }
      else {
        SetDialogType('info-box');
        SetDialogProp({ title: 'Active Opportunities', contentText: 'Cannot Filter Active Opportunities!', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        SetInfoBoxVisible(true)
      }
    }


    else if (event.target.id === 'securityTypeList') {



      // show message to non-loggedin users to register to get more data
      if (event.target.value.includes('More..')) {
        SetDialogType('register');
        SetInfoBoxVisible(true)
      }

      // ignore separator click
      else if (event.target.value === '_sep_' || event.target.value === '_sep_pl_') {
        return;
      }

      // published list selected from securities dropdown
      else if (event.target.value.startsWith('pl:')) {
        const plName = event.target.value.slice(3);
        const pl = publishedLists.find(p => p.name === plName);
        if (!pl) return;

        const parentGroupName = resourceObj[pl.resource_id] || '';

        SetShowActiveOpps(false);
        SetSelectedSecurity(parentGroupName);

        SetActiveWatchlistFilter({
          name: plName,
          resourceId: pl.resource_id,
          parentGroupName: parentGroupName,
          symbols: new Set(pl.symbols || [])
        });

        const [y1, y2] = getOppYearsForGroup(parentGroupName, PEselected !== 'cons');

        SetOppTableYears(-1);
        SetOppTablePartialYears(-1);
        SetConsolidatedSeasonalData([]);
        SetSymbol('');
        SetOppTableYears(y1.toString());
        SetOppTablePartialYears(y2.toString());
        setCookie('selectedSecurity', parentGroupName, 300);
        SetLastPrice(['', 0]);
        SetSeasonalBarChartData([]);
        SetLineChartYear(0);
        SetOpportunities([]);

        // Clear querystring so stale pattern URL doesn't snap back to the old group
        if (window.location.search.length > 0) {
          window.history.replaceState(null, '', window.location.pathname);
          queryStringLoadedRef.current = true;
          historyInitialized.current = false;
        }

        return;
      }

      // watchlist selected from securities dropdown
      else if (event.target.value.startsWith('wl:')) {
        if (loggedinUser === '0') {
          SetDialogType('free-register')
          SetInfoBoxVisible(true);
          return;
        }

        const wlName = event.target.value.slice(3);
        const wl = watchlists.find(w => w.name === wlName);
        if (!wl) return;

        // resolve the parent securities group display name from resourceObj
        const parentGroupName = resourceObj[wl.resourceId] || '';

        SetShowActiveOpps(false);
        SetSelectedSecurity(parentGroupName) // use real group name so all API calls resolve correctly

        // set filter immediately (without symbols) so OppTable can filter
        SetActiveWatchlistFilter({
          name: wlName,
          resourceId: wl.resourceId,
          parentGroupName: parentGroupName,
          symbols: null // will be populated after fetch
        });

        const [y1, y2] = getOppYearsForGroup(parentGroupName, PEselected !== 'cons');

        SetOppTableYears(-1)
        SetOppTablePartialYears(-1)
        SetConsolidatedSeasonalData([])
        SetSymbol('')

        SetOppTableYears(y1.toString())
        SetOppTablePartialYears(y2.toString())

        setCookie('selectedSecurity', parentGroupName, 300) // save the real group name

        SetLastPrice(['', 0])
        SetSymbol('')
        SetSeasonalBarChartData([])
        SetLineChartYear(0)

        // Clear querystring so stale pattern URL doesn't snap back to the old group
        if (window.location.search.length > 0) {
          window.history.replaceState(null, '', window.location.pathname);
          queryStringLoadedRef.current = true;
          historyInitialized.current = false;
        }

        // fetch watchlist items and update filter with symbols - triggers re-filter via opportunities refetch
        let asURL = appserverURL()
        twFetch(`${asURL}/get_user_watchlist_items/${wlName}?token=${token}`)
          .then(res => res.json())
          .then(data => {
            SetActiveWatchlistFilter(prev => ({
              ...prev,
              symbols: new Set(data['watchlist_items'] || [])
            }));
            // re-trigger opp table fetch now that symbols are available
            SetOpportunities([]);
          })
          .catch(err => console.log('fetch watchlist filter items error:', err.message))

        return; // don't clear opportunities yet - will be cleared after watchlist items arrive
      }

      else {


        if (loggedinUser === '0') {
          SetDialogType('free-register')
          SetInfoBoxVisible(true);
          return;
        }

        SetShowActiveOpps(false); // 5/2/2024

        // console.log('setSelectedSecurity=', event.target.value);
        // console.log('..................', securities_groups_default_years);

        // y1 and y2 are default number of years set in common for this securities group 11/19/2022


        // check if key exist first:

        const [y1, y2] = getOppYearsForGroup(event.target.value, PEselected !== 'cons');





        // console.log('y1,y2=',y1,y2)
        // console.log('sssssssssssssssssselect box changed setting selectedSecurity to ', event.target.value)
        const sameGroup = event.target.value === selectedSecurity;
        SetSelectedSecurity(event.target.value)
        SetActiveWatchlistFilter(null) // clear watchlist filter when switching to regular group
        let retArray = userAccessToSelectedSecurity(securityTypeList2, event.target.value)

        SetOppTableYears(-1)        // force reset of the selected year
        SetOppTablePartialYears(-1) // force reset of partial years
        if (!sameGroup) {
          SetYearsMetaData([])
          SetYearsMetaDataPE([])
        }
        SetOppTableYears(-1) // -1 forces initializing #years when new security type is selected/loaded
        SetConsolidatedSeasonalData([])
        SetSymbol('')


        // if selected security is Free, change the oppTable date to today

        if (retArray[0] === 'F') {
          var today = new Date();

          // var isLeapDay = today.getMonth() === 1 && today.getDate() === 29;

          SetOppTableMonth(monthsOptionsList[today.getMonth()]['value'])
          dayOfMonthList(monthsOptionsList[today.getMonth()]['value'])  // 4/30/2022 - this is to create day of the month selectbox for opptable
          SetDayOfTheMonth(String(today.getDate()))
        }


        SetOppTableYears(y1.toString())
        SetOppTablePartialYears(y2.toString())
        // Wave-viewer years follows the same cookie->override->default model.
        // Previously nothing set seasonalYears on a market switch; the only
        // thing touching it was the SeasonalBarChart max-years clamp, which
        // collapsed it to ~4 under a PE filter (the reported bug).
        SetSeasonalYears(y1.toString())


        setCookie('selectedSecurity', event.target.value, 300)

        SetLastPrice(['', 0])
        SetSymbol('')
        SetSeasonalBarChartData([])
        SetLineChartYear(0)

        // Clear querystring so stale pattern URL doesn't snap back to the old group
        if (window.location.search.length > 0) {
          window.history.replaceState(null, '', window.location.pathname);
          queryStringLoadedRef.current = true;
          historyInitialized.current = false;
        }

      }



    }
    SetOpportunities([]) //clear opportunties table becaues there will be a new fetch

  }

  //---------------------------------------------------------------

  // combine securities groups with watchlists and published lists, filtered by user prefs
  const securityTypeListCombined = useMemo(() => {
    if (!securityTypeList || securityTypeList.length === 0) return securityTypeList;

    // filter out hidden groups based on user prefs
    const hiddenSet = new Set(securitiesPrefs.hidden_groups || []);
    let base = securityTypeList.filter(item => !hiddenSet.has(item.value));

    // add published lists that user has enabled
    const enabledPublished = securitiesPrefs.enabled_published || [];
    const plEntries = publishedLists
      .filter(pl => enabledPublished.includes(pl.name))
      .map((pl, i) => ({
        id: 8000 + i,
        value: `pl:${pl.name}`,
        label: pl.name,
        type: 'PL'
      }));

    if (plEntries.length > 0) {
      const moreIdx = base.findIndex(x => x.value === 'More...');
      const plSep = { id: 7999, value: '_sep_pl_', label: '── Published Lists ──', type: 'SEP' };
      if (moreIdx >= 0) {
        base.splice(moreIdx, 0, plSep, ...plEntries);
      } else {
        base.push(plSep, ...plEntries);
      }
    }

    // add user watchlists with addToSecurities enabled
    const wlEntries = watchlists
      .filter(w => w.addToSecurities)
      .map((w, i) => ({
        id: 9000 + i,
        value: `wl:${w.name}`,
        label: w.name,
        type: 'WL'
      }));

    if (wlEntries.length > 0) {
      const moreIdx = base.findIndex(x => x.value === 'More...');
      const separator = { id: 8999, value: '_sep_', label: '── Watchlists ──', type: 'SEP' };
      if (moreIdx >= 0) {
        base.splice(moreIdx, 0, separator, ...wlEntries);
      } else {
        base.push(separator, ...wlEntries);
      }
    }

    return base;
  }, [securityTypeList, watchlists, publishedLists, securitiesPrefs]);

  // dropdown shows watchlist name when active, otherwise the real group name
  const selectedSecurityDisplay = activeWatchlistFilter
    ? (publishedLists.some(pl => pl.name === activeWatchlistFilter.name) ? `pl:${activeWatchlistFilter.name}` : `wl:${activeWatchlistFilter.name}`)
    : selectedSecurity;

  const chartProps = {
    startDate,
    symbol,
    company,
    daysOut,
    seasonalYears,
    showMFE,
    showMAE,
    barChartLongOrShort,
    lineChartYear,
    tradeActive,
    monthsAndQtrs,
    securityTypeList: securityTypeListCombined,
    selectedSecurity,
    selectedSecurityDisplay,
    opportunities,
    oppTableMonth,
    oppTableYears,
    oppTablePartialYears,
    appliedFilter,
    rowIndexClicked,
    seasonalBarChartData,
    tradeDetailData,
    dayOfTheMonth,
    statBoxCoordinates,
    loggedinUser,
    infoBoxVisible,
    helpBoxVisible,
    tradeDate0,
    tradeDate1,
    dialogType,
    swiper,
    dialogProp,
    // allowedSymbols,
    tooltipSW,
    yearsMetaData,
    yearsMetaDataPE,
    showPEOpps,
    PEOppsChecked,
    resourceObj,  //4/12/2022 - this is all resources object obtained by calling getResourcesObj API
    userFreeResources, //4/12/2022 - list of users free resource
    userPremResources, //4/12/2022 - list of users prem resource
    securityTypeList2,

    daysOfMonthList, // 4/30/2022 - switching day of the month to a pulldown
    stockScoreCurrent, // 5/17/2022 - true false - when false its historical
    exportImage, // 5/24/2022
    lastPrice, // 6/21/2022
    consolidatedSeasonalData, //7/17/2022
    janDecDateRange, // 8/6/2022
    oppTableLength, // 8/28/2022
    videosBoxVisible, // 9/14/2022
    reportsDashVisible, // 3/8/2023
    reportsList, // 3/10/2023
    numReportsCreated,
    numReportsAllowed,
    addGCVisible,
    googleCalendarDict,
    multiPortfolios,    // true or false - switches multi portfolio capability 
    showPortfolioSettings,
    reportsDashRect,
    showSettings,
    portfolios,
    selectedPortfolio,
    selectedPortfolioID,
    numPortfoliosAllowed,
    watchlists,
    defaultWatchlistName,
    defaultWatchlistItems,
    defaultWatchlistResourceId,
    numWatchlistsAllowed,
    numWatchlistItemsAllowed,
    showWatchlistSettings,
    showWatchlistOnFocus,
    qparams,
    showOppNote,
    selectedNote,
    selectedDRID,
    selectedPortfolioRec,
    helpEmailDisplay,
    compareSecurity, // 9/9/2023
    compareSecurityBarChartData, // 9/9/2023
    compareSecurityTradeDetailData, // 9/9/2023
    compareSecurityLongOrShort, // 9/9/2023
    initialWindowNum, // 9/26/2023
    securityBHstats, // 10/9/2023  - this is for getting the buy and hold of the current security for display
    reverseDateSelected, // used to correctly set the initial date of the reversed consolidated seasonal chart
    trendChartStartDate,
    trimYear, // this is for setting the trim year (oldest year we want) for special years such as odd, even, PE, PE1 PE2 PE3
    autoTradePortfolioMonth, // this is for generating a portoflio for audo trading for the month selected

    showPopulatePortfolio,
    showAutoTrade,
    showTradeReport,
    showTradeInstrumentReport,
    tradeInstrumentReportDict,
    showSR2, // this is for the configuration that oppTable shows SR, AP, SR2 & AP2
    switchStreamingQuotes,
    switchStreamingAccount,
    activeOpportunities,
    showActiveOpps,
    upgradeMessage,
    promotionMessage,
    promotionCouponCode,
    showUpgradeBanner,
    promotionBackColor,
    showWatermark,
    downloadImageName,
    showChatbot,
    chatbotEnabled,
    chatbotIconBlink,
    chatbotPendingTip,
    chatbotPrefill,
    refreshKey,
    showArticlePublish,
    PEselected,
    UITheme,
    backgroundColor,
    columnVisibility,
    columnOrder,
    activeWatchlistFilter,
    publishedLists,
    isAdmin,
    userRoles,
    securitiesPrefs,
    showSecuritiesGroupSettings,
    showVolume,
    maConfig,
    bbConfig,
    showProjection,
    projectionPeriod,
    priceChartTimeframe,
    showEarnings,
    chartRange,
    shortDates,

  }

  const chartSetProps = {
    SetStartDate,
    SetSymbol,
    SetCompany,
    SetDaysOut,
    SetSeasonalYears,
    setShowMFE,
    setShowMAE,
    SetBarChartLongOrShort,
    SetLineChartYear,
    SetTradeActive,
    SetMonthsAndQtrs,
    SetSecurityTypeList,
    SetSelectedSecurity,

    SetOpportunities,
    SetOppTableMonth,
    SetOppTableYears,
    SetOppTablePartialYears,
    selectboxChanged,
    SetAppliedFilter,
    SetRowIndexClicked,
    SetSeasonalBarChartData,
    SetTradeDetailData,
    SetDayOfTheMonth,

    dayIncrement,
    dayDecrement,

    handleEnterInc,
    handleBlurInc,
    handleDayChange,
    SetStatBoxCoordinates,
    SetLoggedinUser,
    SetInfoBoxVisible,
    SetHelpBoxVisible,
    SetTradeDate0,
    SetTradeDate1,
    SetDialogType,
    setSwiper,
    SetDialogProp,
    // SetAllowedSymbols,
    SetTooltipSW,
    SetYearsMetaData,
    SetYearsMetaDataPE,
    SetShowPEOpps,
    SetPEOppsChecked,
    SetPEselected,   // wave-viewer per-security PE selector (chat update_view actuation)

    SetResourceObj,  //4/12/2022 - this is all resources object obtained by calling getResourcesObj API
    SetUserFreeResources,
    SetUserPremResources,
    SetSecurityTypeList2,

    SetDaysOfMonthList, // 4/30/2022  switcdhing day of the month to a
    dayOfMonthList,     // 4/30/2022
    SetStockScoreCurrent,   // true = current , false = historical
    SetExportImage, // 5/24/2022 - true of false to signal exporting the visible div as jpg or png
    SetLastPrice, // 6/21/2022
    SetConsolidatedSeasonalData, //7/17/2022
    SetJanDecDateRange, //8/6/2022
    SetOppTableLength, // 8/28/2022
    SetVideosBoxVisible, // 9/14/2022
    SetReportsDashVisible, // 3/8/2023
    SetReportsList, // 3/10/2023
    SetNumReportsCreated,
    SetNumReportsAllowed,
    SetAddGCVisible,       //3/25/2023
    SetGoogleCalendarDict,
    SetMultiPortfolios,
    SetShowPortfolioSettings,
    SetReportsDashRect,
    SetShowSettings,
    SetPortfolios,
    SetSelectedPortfolio,
    SetSelectedPortfolioID,
    SetNumPortfoliosAllowed,
    SetWatchlists,
    SetDefaultWatchlistName,
    SetDefaultWatchlistItems,
    SetNumWatchlistsAllowed,
    SetNumWatchlistItemsAllowed,
    SetShowWatchlistSettings,
    SetShowWatchlistOnFocus,
    SetQparams,
    SetShowOppNote,
    SetSelectedNote,
    SetSelectedDRID,
    SetSelectedPortfolioRec,
    SetHelpEmailDisplay,
    SetCompareSecurity, // 9/9/2023
    SetCompareSecurityBarChartData,  // 9/9/2023
    SetCompareSecurityTradeDetailData, // 9/9/2023
    SetCompareSecurityLongOrShort,  // 9/9/2023
    SetInitialWindowNum, // 9/26/2023
    SetSecurityBHstats, // 10/9/2023  - this is for getting the buy and hold of the current security for display
    SetReverseDateSelected, // used to correctly set the initial date of the reversed consolidated seasonal chart
    SetTrendChartStartDate,
    SetToken,
    SetTrimYear,
    SetAutoTradePortfolioMonth,

    SetShowPopulatePortfolio,
    SetShowAutoTrade,
    SetShowTradeReport,
    SetShowTradeInstrumentReport,
    SetTradeInstrumentReportDict,
    SetShowSR2,
    SetSwitchStreamingQuotes,
    SetSwitchStreamingAccount,
    SetActiveOpportunities,
    SetShowActiveOpps,
    SetUpgradeMessage,
    SetPromotionMessage,
    SetPromotionCouponCode,
    SetShowUpgradeBanner,
    SetPromotionBackColor,
    SetShowWatermark,
    SetDownloadImageName,
    SetShowChatbot,
    SetChatbotIconBlink,
    SetChatbotPendingTip,
    SetChatbotPrefill,
    onChatbotIconClick: () => { SetChatbotIconBlink(false); },
    SetRefreshKey,
    SetShowArticlePublish,
    SetPEselected,
    SetUITheme,
    SetBackgroundColor,
    SetColumnVisibility: handleSetColumnVisibility,
    SetColumnOrder: handleSetColumnOrder,
    SetActiveWatchlistFilter,
    SetPublishedLists,
    SetIsAdmin,
    SetSecuritiesPrefs,
    SetShowSecuritiesGroupSettings,
    SetShowVolume: handleSetShowVolume,
    SetMaConfig: handleSetMaConfig,
    SetBbConfig: handleSetBbConfig,
    SetShowProjection: handleSetShowProjection,
    SetProjectionPeriod: handleSetProjectionPeriod,
    SetPriceChartTimeframe: handleSetPriceChartTimeframe,
    SetShowEarnings: handleSetShowEarnings,
    SetChartRange: handleSetChartRange,
    SetShortDates,
  }



  let resizeWindow = () => {
    // console.log('resize window width',browserW,window.innerWidth)
    // console.log('resize window Height',browserH,window.innerHeight)

    if (rdd.isMobile && browserH !== window.innerHeight && browserW === window.innerWidth) { // condition that search box is clicked and height is reduced but with is the same
      return;
    }

    SetBrowserH(window.innerHeight);
    SetBrowserW(window.innerWidth);


    // const [browserH, SetBrowserH] = useState(window.innerHeight)
    // const [browserW, SetBrowserW] = useState(window.innerWidth)

    var headerDivH = document.getElementById('main-header')?.clientHeight ?? 0;
    //-- footer-bottom is the Id for the default footer -
    // var footerDivH = document.getElementById('footer-bottom').clientHeight;

    var footerDivH = 0;  // TW2: no footer on /app/
    if (!debug) {
      footerDivH = document.getElementsByClassName('et-l')[0]?.clientHeight ?? 0 // when using a custom footer
    }
    // console.log('heights=', window.innerHeight, headerDivH, footerDivH)

    setSeasonalAppDivH(window.innerHeight - headerDivH - footerDivH)
    if (rdd.isTablet) {
      if (window.innerHeight > window.innerWidth) setSeasonalAppDivH2(window.innerHeight); // don't show header and footer on portrait
      else setSeasonalAppDivH2(window.innerHeight - headerDivH - footerDivH); // show header and footer on landscape
    }
    else {
      setSeasonalAppDivH2(window.innerHeight)
    }



    // setSeasonalAppDivH2(window.innerHeight)

    var textsize = '0.9vw';
    var zoom = '1'; // zoom determines the size of the checkboxes
    var table_text_size = '1vw';
    var table_title_text_size = '1vw';
    var info_text_size = '1.1vw'



    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
      textsize = '3.3vw'; zoom = '1'; table_text_size = '3.0vw'; table_title_text_size = '3.0vw'; info_text_size = '3.5vw';
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
      textsize = '2.0vw'; zoom = '1'; table_text_size = '2.0vw'; table_title_text_size = '2.0vw'; info_text_size = '2.2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
      if (window.innerWidth < 1024) {
        textsize = '1.7vw'; zoom = '1.2'; table_text_size = '3.1vw'; table_title_text_size = '2.8vw'; info_text_size = '1.8vw';
      }
      else {
        textsize = '2.0vw'; zoom = '2'; table_text_size = '2.8vw'; table_title_text_size = '2.8vw'; info_text_size = '1.8vw'; //tablet landscape
      }
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape
      if (window.innerHeight < 1024) {
        textsize = '1.0vw'; zoom = '1.4'; table_text_size = '1.2vw'; table_title_text_size = '0.9vw'; info_text_size = '1.2vw';
      }
      else {
        textsize = '1.0vw'; zoom = '1.4'; table_text_size = '1.3vw'; table_title_text_size = '0.9vw'; info_text_size = '1.2vw';
      }
    }
    else if (!rdd.isMobile) {                                       // desktop
      textsize = '0.95em'; table_text_size = '0.9vw'; table_title_text_size = '0.8vw'; info_text_size = '0.9vw';

      // console.log('......................rdd=',rdd)

      if (rdd.isSafari) {
        // console.log('-------------############################### its safari')
        info_text_size = '0.60vw';
      }
      else {
        info_text_size = '0.85vw';
      }
    }

    SetGlobalTextSize(textsize);
    SetCheckboxZoom(zoom);
    SetTableTextSize(table_text_size);
    SetTableTitleTextSize(table_title_text_size);
    SetInfoTextSize(info_text_size);

  };

  //- end of resizeWindow() ----------------------------------------------------------------------------------------

  useLayoutEffect(() => {
    resizeWindow();
    window.addEventListener("resize", resizeWindow);
    return () => window.removeEventListener("resize", resizeWindow);
  }, [])

  //-------------------------------------------------------------------------------
  // login handshake helpers - used by the login useEffect below AND by the
  // twFetch 401 re-login so a long-lived tab can self-heal at token expiry
  //-------------------------------------------------------------------------------
  const detectDevice = () => {
    let deviceType = '!';
    let deviceOS = '!';
    if (rdd.isDesktop) {
      deviceType = 'D'
      if (rdd.isMacOs) deviceOS = 'M';
      else if (rdd.isWindows) deviceOS = 'W';
      else if (rdd.osName === 'Linux') deviceOS = 'L'
      else deviceOS = rdd.osName
    }
    if (rdd.isTablet) {
      deviceType = 'T';
      if (rdd.isAndroid) deviceOS = 'A';
      else if (rdd.isIOS) deviceOS = 'I';
      else if (rdd.osName === 'Linux') deviceOS = 'L'
      else deviceOS = rdd.osName
    }
    if (!rdd.isTablet && rdd.isMobile) { //smartphone
      deviceType = 'S';
      if (rdd.isAndroid) deviceOS = 'A';
      else if (rdd.isIOS) deviceOS = 'I';
      else if (rdd.osName === 'Linux') deviceOS = 'L';
      else if (rdd.isWindows) deviceOS = 'W';
    }
    return [deviceType, deviceOS];
  };

  const effectiveUserLevel = () => {
    let lvl = window.current_user_level;

    //#######################################################################  need fixing ##########
    if (!lvl) lvl = '6'  // passing the user_level from the React to appserver here during login

    var numbers = lvl.split(",").map(Number); // convert array of strings to array of numbers
    var largestNumber = Math.max(...numbers); // find largest number in the array
    lvl = largestNumber.toString();

    if (window.current_user_level === '2,1,4,') lvl = '6' // this is a weird one - for admin I have to fix it in worpdress where userlevel is passed

    // settig user level for debug when free ripple user
    if (debug) lvl = testUserLevel; // this is for testing Free Ripple level only
    //#######################################################################

    return lvl;
  };

  // Re-derive the /login handshake URL from the page credentials (window
  // globals re-minted by Flask on every /app/ load, legacy 'apsl' cookie
  // fallback). Returns null when no credentials are present.
  const buildLoginUrl = () => {
    let cookie = null;
    if (window.current_user_id && window.ltk) cookie = `${window.current_user_id},${window.ltk}`;
    else cookie = getCookie('apsl');
    if (cookie === null) return null;

    let userid = cookie.split(',')[0];
    let loginToken = cookie.split(',')[1];
    if (debug) userid = testUserID;
    if (debug) loginToken = process.env.REACT_APP_DEBUG_LOGIN_TOKEN;

    const [deviceType, deviceOS] = detectDevice();
    return `${appserverURL()}/login/${userid}/${effectiveUserLevel()}/${deviceType}/${deviceOS}/${loginToken}`;
  };

  //-------------------------------------------------------------------------------
  // twFetch auth wiring: on a 401 from a data endpoint the wrapper re-runs the
  // login handshake once and replays the request with the fresh token; if the
  // handshake fails too (LTK expired), show the Session Expired overlay.
  //-------------------------------------------------------------------------------
  useEffect(() => {
    registerTwFetchAuth({
      relogin: () => {
        const url = buildLoginUrl();
        if (!url) return Promise.resolve(null);
        // twFetch (skipAuthRetry) so a transient 429/5xx during the ONE re-login
        // attempt retries with backoff instead of falsely latching sessionDead.
        return twFetch(url, { skipAuthRetry: true })
          .then((res) => {
            const contentType = res.headers.get("content-type");
            if (!res.ok || !contentType || contentType.indexOf("application/json") === -1) return null;
            return res.json().then((t) => (t && t['token']) ? t['token'] : null);
          })
          .then((newToken) => {
            if (newToken) SetToken(newToken); // effects refetch with the new token
            return newToken;
          })
          .catch(() => null);
      },
      onSessionExpired: () => SetSessionExpired(true),
    });
  }, [])

  //-------------------------------------------------------------------------------
  // start login useeffect - login
  //-------------------------------------------------------------------------------
  useEffect(() => {
    let tmp_selected_security = '';
    var tmp = window.current_user_level;  // thsi is in wordpress page for /seasonals source



    // ###########################################################################
    // if (debug) (tmp = '1,2,4,6,')// set levels here during DEBUG.  :3000 won't work otherwise
    // if (debug) (tmp = '1,2,') // testing basic monthly - remove
    // if (debug) (tmp = '6,')





    // ###########################################################################
    if (tmp.substr(-1) === ',') tmp = tmp.substring(0, tmp.length - 1);
    tmp = tmp.split(',')


    if (debug) tmp = [testUserLevel];  // this is for testing Free Ripple level only 

    // console.log('..................................................wpUserLevels=',tmp)

    SetWpUserLevels(tmp)


    if (tmp.length === 1 && tmp[0] === '1') { // get first and last day of the week
      var curr = new Date(); // get current date
      var curr2 = new Date();
      var first = curr.getDate() - curr.getDay(); // First day is the day of the month - the day of the week
      var last = first + 6; // last day is the first day + 6


      var d = new Date(curr.setDate(first))
      var d1 = d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate()
      d = new Date(curr2.setDate(last))
      var d2 = d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate()
      SetUserDateRange([d1, d2])
    }
    else SetUserDateRange([])

    // TW2: always prefer the freshly-injected window globals - Flask re-mints the
    // LTK on every /app/ load, so a page-reload picks up DB tier / legacy_level
    // changes immediately. Only fall back to legacy 'apsl' cookie if globals are
    // missing (TW1 / dev shim path).
    var userid = '0';
    var loginToken = 'no token';
    var cookie = null;
    if (window.current_user_id && window.ltk) {
      cookie = `${window.current_user_id},${window.ltk}`;
    } else {
      cookie = getCookie('apsl');
    }

    if (cookie === null) {
      console.log('missing cookie "apsl" and no window.current_user_id/window.ltk fallback')
    }
    else {
      userid = cookie.split(',')[0];

      // if (debug) userid = '1'; // this is Tidal Yearly 
      // if (debug) userid = '19'; // this is free Ripple 
      if (debug) userid = testUserID; // this is for testing Free Ripple level only
      // if (debug) userid = '17'; // this is me - this is basic - 15 is premium

      // if (debug) userid = '16'; // this is me - this is free registered
      // if (debug) userid = '0'; // testing non loggedin user

      loginToken = cookie.split(',')[1];

      // if (debug) loginToken = "b3976554cdd244e38c21d67f95dc0862"; // some reason port 3000 cookie doesn't work anymore - this works
      if (debug) loginToken = process.env.REACT_APP_DEBUG_LOGIN_TOKEN

      // console.log('ddddddddddddddddddddebug loginToken=',loginToken,userid)
      // as long as generate_key in crontab does not run 
      // this only works on dev

      SetLoggedinUser(userid)

      // Validate selected_portfolio cookie belongs to this user.
      // If it was set by a different account (e.g. a test account), reset to default.
      const portfolioUidCookie = getCookie('selected_portfolio_uid')
      if (portfolioUidCookie === null || portfolioUidCookie !== userid) {
        SetSelectedPortfolio('main')
        SetSelectedPortfolioID(0)
      }

      if (userid === '0') {
        SetOppTableYears(freeYears[0].toString())  // set to 8 or 10 
        SetOppTablePartialYears(freeYears[1].toString())
      }
      else {
        if (tmp_selected_security === '') {
          tmp_selected_security = getCookie('selectedSecurity')

          if (tmp_selected_security === null) {

            // tmp_selected_security = securityTypeList[startingSecurity];
            tmp_selected_security = startingSecurityName;
          }

        }

        // console.log('.......................tmp_selected_security=',tmp_selected_security)

        if (wpUserLevels.length === 1 && wpUserLevels[0] === '1') { //free registered

          const [y1, y2] = getOppYearsForGroup(tmp_selected_security, PEselected !== 'cons');
          SetOppTableYears(y1.toString())
          SetOppTablePartialYears(y2.toString())
        }
        else { // all paid registered users
          const [y1, y2] = getOppYearsForGroup(tmp_selected_security, PEselected !== 'cons');
          SetOppTableYears(y1.toString())
          SetOppTablePartialYears(y2.toString())
        }
      }
    }

    // console.log('tttttttttttttttttttttttttttttttttttoken=',token)

    // this useEffect comes through twice, early mistake and react basics
    // second time, token is already establsihed, so we don't login again
    // if (true){
    // if (token && token.length === 0) {  // if token already obtained, this is the second pass, don't need to login again
    if (!token || token.length === 0) {  // 5/9/2025 - dev stopped working - I think the above line was the reason.  changed it to this
      let asURL = appserverURL()

      const [deviceType, deviceOS] = detectDevice();
      tmp = effectiveUserLevel();

      let url = `${asURL}/login/${userid}/${tmp}/${deviceType}/${deviceOS}/${loginToken}`

      if (debug) console.log('login url =', url)

      // console.log('.................login url =', url)
      console.log('.') ; // I think this helps make login work for non logged in with trxstat.com - it was crashing for some reason

      var stat = ''
      // login to appserver - twFetch retries transient 429/5xx with backoff;
      // skipAuthRetry because a 401 here means the LTK itself is dead
      twFetch(url, { skipAuthRetry: true })
        .then(res => {

          const contentType = res.headers.get("content-type");

          // console.log('res fetch returned:', res.status, res.statusText, contentType)

          if (contentType && contentType.indexOf("application/json") !== -1) {
            stat = 'OK'
            return res.json();
          }
          else if (res.status === 429) { // too many requests
            stat = 'rate-limit'
            SetDialogType('rate-limit'); //429
            SetInfoBoxVisible(true)
          }
          else {
            stat = 'unreachable'
            SetDialogType('info-box');
            SetDialogProp({ title: 'App Server Unreachable', contentText: 'Cannot communicate with the application server.  Try refreshing the browser or try accessing the Wave Viewer later. returned message:a-' + res.status, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
            SetInfoBoxVisible(true)
          }

          // throw new Error('Network response was not ok.');
        })

        .then((t) => {
          // console.log('Login response:', t);  
          if (t && t['token']) SetToken(t['token']) //token is for flask and is passed with usecontext
        })
        .catch(err => {
          // console.log('stat=', stat)
          // console.log('catch login error=', err.message)
          if (stat === '') { // if stat is blank, rate-limit is not the reason for failure - its because appserver is not running or erroed out
            SetDialogType('info-box');
            let content = 'Cannot communicate with the application server.  Try refreshing the browser or try accessing Wave Viewer later.'
            if (err.message.includes('token')) content += 'status:T404';
            else if (err.message.includes('fetch')) content += 'status:A502';
            else content += 'message:' + err.message;
            SetDialogProp({ title: 'App Server Unreachable', contentText: content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
            SetInfoBoxVisible(true)
          }
        })

    }

    // console.log('token=', token)

    if (token.length > 0) {

      var decoded;
      try { decoded = jwt_decode(token); } catch (e) { console.error('jwt_decode failed in login effect:', e.message); return; }
      SetNumReportsAllowed(decoded['num_reports_allowed']);
      SetNumReportsCreated(decoded['num_reports_created']); // when logging in - the initial number created is loaded here
      SetNumPortfoliosAllowed(decoded['num_portfolios_allowed']);

      if (decoded['num_watchlists_allowed'] !== undefined)
        SetNumWatchlistsAllowed(decoded['num_watchlists_allowed']);
      if (decoded['num_watchlist_items_allowed'] !== undefined)
        SetNumWatchlistItemsAllowed(decoded['num_watchlist_items_allowed']);
      if (decoded['is_admin'] !== undefined)
        SetIsAdmin(decoded['is_admin']);

      if (decoded['roles'] !== undefined)
        SetUserRoles(decoded['roles']);

      if (decoded['upgrade_message']) {
        SetUpgradeMessage(decoded['upgrade_message']);
      }

      if (decoded['promotion_message']) {
        SetPromotionMessage(decoded['promotion_message']);
      }

      if (decoded['promotion_coupon_code']) {
        SetPromotionCouponCode(decoded['promotion_coupon_code']);
      }

      if (decoded['promotion_back_color']) {
        SetPromotionBackColor(decoded['promotion_back_color']);
      }

      if (decoded['upgrade_message'] !== '') {
        SetShowUpgradeBanner(true)
      }

      // get resources list for this user from the token 
      tmp = [];

      for (var i = 0; i < decoded['resource_disp'].length; i++) {
        tmp.push({ id: (decoded['lid'] && decoded['lid'][i] != null) ? parseInt(decoded['lid'][i]) : i, value: decoded['resource_disp'][i], label: decoded['resource_disp'][i] });
      }

      // add more ... to the bottom of the list for non logged-in users
      if (loggedinUser === '0') {
        tmp.push({ id: i + 1, value: 'More...', label: 'More...' })
      }

      SetSecurityTypeList(tmp) // securities type list for selection  

      if (userid === '0') {

        // this one sets the financial groups as s&p500
        tmp_selected_security = tmp[startingSecurity].value; // startingSecurity is the number on the list of securities for initial selected security
        // used to be 0 for dow 30 now we can set it on Common - trying s&p which is 2 11/18/2022

        if (!debug) {
          // non-logged-in pattern link visitors must sign up to see the pattern
        }

      }
      else {

        // Default-security fallback: the hard-coded startingSecurityName (or a
        // stale selectedSecurity cookie from a higher-access session, e.g. a
        // lapsed reverse trial) may not be in this user's resource_disp list.
        // A missing name used to resolve to id=-1 and the OppTable silently
        // skipped its OppList4 fetch (the Explorer blank-table bug) - fall
        // back to the first accessible security instead.
        if (tmp.length > 0 && !tmp.some(item => item.value === tmp_selected_security)) {
          tmp_selected_security = tmp[0].value;
        }

        // for every person that is logged-in show terms popup once and save it in a cookie so it won't show again
        let ta = getCookie('terms_accepted')

        if (ta == null || ta !== userid) {
          // console.log('222222222222222222222222',ta,userid)
          SetDialogType('terms-conditions')
          SetInfoBoxVisible(true); // show the dialog for terms and conditions
          setCookie('terms_accepted', userid, 365)
        }

      }

      if (tmp_selected_security !== '') {
        SetSelectedSecurity(tmp_selected_security) // pull down on the top left s&p dji commodities ...
      }
      let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
      SetSelectedSecurityType(retArray[0]) // 'F' or 'P'  free or premium

    }
  }, [token, loggedinUser])
  //-------- end of login useEffect


  //---------------------------------------------------------------------------------
  // check if chatbot is enabled for this user
  useEffect(() => {
    if (token && token.length > 0) {
      let asURL = appserverURL()
      twFetch(`${asURL}/chatbot/chatbot_access?token=${token}`)
        .then(res => res.json())
        .then(data => {
          const allowed = data.allowed === true;
          SetChatbotEnabled(allowed);
        })
        .catch(() => { SetChatbotEnabled(false) })
    }
  }, [token])

  //---------------------------------------------------------------------------------
  // Tara onboarding tip system
  // Tips only pulse when chatbot is CLOSED. Timers start when chatbot closes.
  // If user opens chatbot before a tip fires, that tip is skipped (user already knows).
  //
  // localStorage keys:
  //   tw_tara_tip_index  - which tip is next (0-4, 4 = done)
  //   tw_tara_last_close - timestamp of last chatbot close (delays measured from this)
  //
  // Schedule:
  //   tip 0: 90s after login (only if user hasn't opened chatbot yet)
  //   tip 1: 10 min after chatbot closes
  //   tip 2: 1 day after chatbot closes
  //   tip 3: 4 days after chatbot closes, then done
  const TARA_TIPS = [
    "Hi, I'm <b>Tara</b>! Ask me for today's best setups, a stock's seasonal pattern, or a concept - I'll pull it up on the chart and explain it. Try <b>what's the best setup today?</b>",
    "<b>Tip:</b> You can ask me to explain anything you see - try asking <b>what is a sharpe ratio?</b> or <b>explain this pattern</b> after loading a ticker.",
    "<b>Tip:</b> Type <b>compare</b> to learn how to compare a pattern against a benchmark, or ask me <b>what are the best opportunities today?</b>",
    "<b>Tip:</b> You can filter opportunities with powerful commands in the search box - try <b>SR>2</b> or <b>AP>10</b>. Ask me <b>how do I filter?</b> to learn more."
  ];
  // Tip 0 delay is from login; tips 1-3 are from last chatbot close
  const TARA_TIP_DELAYS = [90 * 1000, 10 * 60 * 1000, 24 * 60 * 60 * 1000, 4 * 24 * 60 * 60 * 1000];

  const scheduleTaraTip = (tipIndex) => {
    if (tipIndex >= TARA_TIPS.length) return;
    const lastClose = parseInt(lsGet('tw_tara_last_close') || '0', 10);
    const elapsed = lastClose > 0 ? Date.now() - lastClose : 0;
    const delay = Math.max(TARA_TIP_DELAYS[tipIndex] - elapsed, 0);
    chatbotTipTimerRef.current = setTimeout(() => {
      lsSet('tw_tara_tip_index', (tipIndex + 1).toString());
      SetChatbotPendingTip(TARA_TIPS[tipIndex]);
      SetChatbotIconBlink(true);
    }, delay);
  };

  // On chatbot open/close transitions
  const prevShowChatbotRef = useRef(null);
  useEffect(() => {
    if (!chatbotEnabled) return;
    const tipIndex = parseInt(lsGet('tw_tara_tip_index') || '0', 10);

    if (showChatbot && prevShowChatbotRef.current === false) {
      // Chatbot just opened - cancel any pending tip timer
      if (chatbotTipTimerRef.current) { clearTimeout(chatbotTipTimerRef.current); chatbotTipTimerRef.current = null; }
      // If tip 0 hasn't fired yet, user found chatbot on their own - skip intro tip
      if (tipIndex === 0) {
        lsSet('tw_tara_tip_index', '1');
      }
      SetChatbotIconBlink(false);
    }

    if (!showChatbot && prevShowChatbotRef.current === true) {
      // Chatbot just closed - record close time and schedule next tip
      lsSet('tw_tara_last_close', Date.now().toString());
      const nextTip = parseInt(lsGet('tw_tara_tip_index') || '0', 10);
      scheduleTaraTip(nextTip);
    }

    prevShowChatbotRef.current = showChatbot;
  }, [showChatbot, chatbotEnabled])

  // On initial load (chatbot closed), schedule tip 0 or resume pending tip
  useEffect(() => {
    if (!chatbotEnabled || showChatbot) return;
    const tipIndex = parseInt(lsGet('tw_tara_tip_index') || '0', 10);
    if (tipIndex >= TARA_TIPS.length) return;
    if (tipIndex === 0) {
      // First time user - schedule intro pulse after 90s
      chatbotTipTimerRef.current = setTimeout(() => {
        lsSet('tw_tara_tip_index', '1');
        SetChatbotPendingTip(TARA_TIPS[0]);
        SetChatbotIconBlink(true);
      }, TARA_TIP_DELAYS[0]);
    } else {
      // Resume: schedule next tip based on time since last close
      scheduleTaraTip(tipIndex);
    }
    return () => { if (chatbotTipTimerRef.current) clearTimeout(chatbotTipTimerRef.current); };
  }, [chatbotEnabled])

  // fetch watchlist names and default watchlist items on login
  useEffect(() => {
    if (token && token.length > 0 && loggedinUser !== '0') {
      let asURL = appserverURL()
      twFetch(`${asURL}/get_user_watchlist_names?token=${token}`)
        .then(res => res.json())
        .then(data => {
          if (data['watchlist_names_list'] && Array.isArray(data['watchlist_names_list'])) {
            SetWatchlists(data['watchlist_names_list'])
            let defWL = data['watchlist_names_list'].find(w => w.isDefault === true)
            if (defWL) {
              SetDefaultWatchlistName(defWL.name)
              SetDefaultWatchlistResourceId(defWL.resourceId)
              twFetch(`${asURL}/get_user_watchlist_items/${defWL.name}?token=${token}`)
                .then(res2 => res2.json())
                .then(data2 => {
                  if (data2['watchlist_items'] && Array.isArray(data2['watchlist_items'])) {
                    SetDefaultWatchlistItems(data2['watchlist_items'])
                  }
                })
                .catch(err => console.log('fetch default watchlist items error:', err.message))
            }
          }
        })
        .catch(err => console.log('fetch watchlist names error:', err.message))
    }
  }, [token, loggedinUser])

  // fetch published securities lists and user securities preferences
  useEffect(() => {
    if (token && token.length > 0 && loggedinUser !== '0') {
      let asURL = appserverURL()
      twFetch(`${asURL}/get_published_lists?token=${token}`)
        .then(res => res.json())
        .then(data => {
          if (data['published_lists']) SetPublishedLists(data['published_lists'])
          if (data['is_admin'] !== undefined) SetIsAdmin(data['is_admin'])
        })
        .catch(err => console.log('fetch published lists error:', err.message))

      twFetch(`${asURL}/get_securities_prefs?token=${token}`)
        .then(res => res.json())
        .then(data => {
          if (data['securities_prefs']) SetSecuritiesPrefs(data['securities_prefs'])
        })
        .catch(err => console.log('fetch securities prefs error:', err.message))
    }
  }, [token, loggedinUser])

  //-------------------------------------------------------------------------------
  // Session expiry monitor - checks JWT exp and warns before session dies
  //-------------------------------------------------------------------------------
  useEffect(() => {
    if (!token || token.length === 0) return;
    let decoded;
    try { decoded = jwt_decode(token); } catch (e) { return; }
    if (!decoded || !decoded.exp) return;

    const checkExpiry = () => {
      const now = Math.floor(Date.now() / 1000);
      const remaining = decoded.exp - now;
      if (remaining <= 0) {
        SetSessionExpired(true);
      }
    };
    // Check every 60 seconds
    checkExpiry();
    const interval = setInterval(checkExpiry, 60000);
    return () => clearInterval(interval);
  }, [token])

  // get resources from appserver  4/12/2022
  // this is the create SetSecurityTypeList2 which is the new format
  //---------------------------------------------------------------------------------
  useEffect(() => {

    let asURL = appserverURL()
    let url = `${asURL}/getResourcesObj?token=${token}`

    if (token && token.length > 0) {
      twFetch(url)
        .then((res) => {
          return res.json();
        })
        .then((g) => {


          SetResourceObj(g['resources']) // added on 3/9/2023

          // console.log('rrrrrrrrrrrrrrrrrrrrr',typeof(g['resources']),g['resources'])


          let resourcesObj = g['resources']
          let freeObj = g['free']
          let premObj = g['prem']
          let nonlog = g['nonloggedin-resources'] // this is a list not an object

          let userFree = [];
          let userPrem = [];

          // console.log('g["free"]=', freeObj)
          // console.log('g["prem"]=', premObj)


          // console.log('wpUserLevels=', wpUserLevels)

          if (loggedinUser === 0) {
            userFree = nonlog; // set userFree list to the non loggedin resource list from server
          }
          else { // create userFree and userPrem list based on their access level
            for (let i = 0; i < wpUserLevels.length; i++) {
              if (freeObj[wpUserLevels[i]] !== undefined) userFree.push(...freeObj[wpUserLevels[i]]) //extending userFree with freeObj[i] list
              if (premObj[wpUserLevels[i]] !== undefined) userPrem.push(...premObj[wpUserLevels[i]])
            }
          }
          // get rid of duplicates in userFree and userPrem
          userFree = [...new Set(userFree)]
          userPrem = [...new Set(userPrem)]



          // remove items from userFree that are in userPrem
          userFree = userFree.filter((userFree) => !userPrem.includes(userFree));


          // console.log('111111111111111111 userFree=',userFree)
          // console.log('222222222222222222 userPrem=',userPrem)


          // console.log('resourcesObj=', resourcesObj)
          // now create a list of objects for the user based on free and prem 
          var tmp = []
          for (var i = 0; i < userPrem.length; i++) {
            tmp.push({ id: i, value: userPrem[i], label: resourcesObj[userPrem[i]], type: 'P' })
          }
          for (var j = 0; j < userFree.length; j++) {
            tmp.push({ id: i + j, value: userFree[j], label: resourcesObj[userFree[j]], type: 'F' })
          }
          if (loggedinUser === 0) {
            tmp.push({ id: i + j + 1, value: '', label: 'More...', type: '' })
          }


          // console.log('ttttttttttttttttttttmp=',tmp)

          SetSecurityTypeList2(tmp)
        })
        .catch(err => {
          // without the resources list the whole app is blank - surface it
          // (twFetch already retried transient failures with backoff)
          console.log('getResourcesObj error=', err.message)
          SetDialogType('info-box');
          SetDialogProp({ title: 'Data Temporarily Unavailable', contentText: 'The securities list could not be loaded. Please refresh the browser to try again.', button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
          SetInfoBoxVisible(true)
        })


    }


  }, [token, loggedinUser])


  //-------------------------------------------------------------------------------
  // Allowed Symbols after token is obtained
  //-------------------------------------------------------------------------------
  // useEffect(() => {

  //   //-------------------------------------------------------------------------------------------------------------
  //   // for some reason I don't know, when the selected security is one of the non US stocks, the selectedSecurity
  //   // variable become blank after refreshing the browser.  I don't know why but it caused problems loading
  //   // the correct allowedSymbols to determine the company name.  to fix this I added a condition to only
  //   // load allowedSymbols, if selectedSecurity.length > 0 to prevent this rogue loading of the wrong list
  //   // I don't know why its happending but adding this condition seems to fix the problem  8/19/2023
  //   //-------------------------------------------------------------------------------------------------------------
  //   if (selectedSecurity.length > 0) {
  //     let id = getSelectedIDFromSecuritiesList2(securityTypeList, selectedSecurity);


  //     let asURL = appserverURL()
  //     let url = `${asURL}/GetListSymbols/${id}?token=${token}`

  //     // SetAllowedSymbols
  //     if (token.length > 0) {
  //       fetch(url)
  //         .then((res) => {
  //           // console.log('--------------------------------------------------fetch allowed symbols')
  //           return res.json();
  //         })
  //         .then((g) => {
  //           // console.log('set allowed symbols is called with selectedSecurity=', selectedSecurity)
  //           // console.log('1111111111111111111111111set allowed symbols in main useEffect', selectedSecurity)
  //           SetAllowedSymbols(g['AllowedSymbols'])
  //         })
  //         .catch(err => {
  //           console.log('GetListSymbols error=', err.message)
  //         })
  //     }
  //   }
  // }, [token, selectedSecurity])


  //-------------------------------------------------------------------------------
  // capture the query string parameters
  //-------------------------------------------------------------------------------
  useEffect(() => {
    // <a target='_blank' href='{domain_root}seasonals?fg={financial_group_id}&s={symbol}&d={date1}&dh={days_hold}&y={history_years}'>Seasonal Viewer</a>

    // Home-page "ask Tara" deep link: ?ask=<plain url-encoded question>. The home page
    // uses encodeURIComponent (NOT base64, unlike ?o=), so URLSearchParams.get('ask')
    // already returns decoded plain text. Handled before the queryStringLoadedRef guard
    // and the pattern logic - it needs no token/resourceObj/opportunities (the chat itself
    // has the token). One-shot via askHandledRef; scrubbed from the URL so a refresh/back/
    // bookmark won't re-ask.
    if (!askHandledRef.current) {
      const askParams = new URLSearchParams(window.location.search);
      const ask = askParams.get('ask');
      if (ask && ask.trim()) {
        askHandledRef.current = true;
        // scrub only the ?ask= param, preserving any others (e.g. ?o=) so a refresh won't re-ask
        askParams.delete('ask');
        const remaining = askParams.toString();
        window.history.replaceState({}, '', window.location.pathname + (remaining ? '?' + remaining : ''));
        if (!rdd.isMobile) {
          // desktop: open Tara and hand the question to the Chatbot to auto-send
          SetShowChatbot(true);
          SetChatbotPrefill(ask.trim());
        } else {
          // mobile: no chat UI exists - show a brief graceful note instead
          SetAskMobileNote(true);
        }
      }
    }

    if (queryStringLoadedRef.current) return; // pattern already loaded from querystring, don't re-apply

    let queryString = window.location.search;

    if (queryString.length > 0) {
      // console.log('qs=', queryString, window.current_user_id)

      if (queryString === '?set=on') { // with this querystring when tradewave-viewer is envoked, it automatically open settings window
        // remove the querystring 
        window.history.replaceState(null, '', window.location.href.split('?')[0]);
        // turn on the settings window


        if (window.current_user_id == '0') { // userid 0 has to login to before can  get the settings window opened

          window.location.href = '/member-login';
        }
        else {
          const timeout = setTimeout(() => {
            //     SetShowSettings(true);
          }, 1000); // display the settings window after 2 seconds - gives time for SV to load
        }
      }

      else {
        SetQparams(queryString)

        let urlParams = new URLSearchParams(queryString);
        let b64 = urlParams.get('o');

        let param_str;
        try { param_str = window.atob(b64); } catch (e) { console.error('Invalid querystring base64:', e.message); window.history.replaceState(null, '', window.location.href.split('?')[0]); return; }
        // console.log('decoded=',param_str)

        let params = param_str.split('|')


        // the reason for opportunities.length > 0 is that there was a timing issue - pull down would change but
        // kept the old list - by checking opportunities.length > 0 - its delaying the update until other things are 
        // loaded and ready

        if (token && b64 !== null && token.length > 0 && Object.keys(resourceObj).length > 0 && queryString.length > 0 && opportunities.length > 0) {
          // let urlParams = new URLSearchParams(queryString);
          let fg_id = params[0];
          let resource_group = resourceObj[parseInt(fg_id)]
          let symbol = params[1];
          let date1 = params[2];
          let days_hold = params[3];
          let history_years = params[4].toLowerCase(); // tolowercase is because reports pass PE1 PE2  ..  app recognizes pe1 pe2 ..

          if (fg_id === null || resource_group === null || symbol === null || date1 === null || days_hold === null || history_years === null) {
            return
          }


          // SetStartDate(date1)
          // SetSymbol(symbol)
          // SetDaysOut(days_hold)
          // SetSeasonalYears(history_years)
          // SetMonthsAndQtrs('Months & Qtrs')

          SetStartDate(date1)
          SetSymbol(symbol)
          SetDaysOut(days_hold)

          // Parse PE years format: "pe2-10" -> PE cycle="pe2", years="10"
          let parsedPE = 'cons';
          let parsedYears = history_years;
          if (history_years.startsWith('pe') && history_years.includes('-')) {
            const [peType, yearCount] = history_years.split('-');
            parsedPE = peType;
            parsedYears = /^\d+$/.test(yearCount) ? yearCount : '10'; // guard against corrupted values
          } else if (history_years.startsWith('pe')) {
            parsedPE = history_years;
            parsedYears = '10';
          }
          SetPEselected(parsedPE);
          SetSeasonalYears(parsedYears);

          SetMonthsAndQtrs('Months & Qtrs')


          SetConsolidatedSeasonalData([]) //2022-09-27


          let trend_chart_start_date = incrementDate(date1, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common
          SetTrendChartStartDate(trend_chart_start_date)

          SetSelectedSecurity(resource_group)
          setCookie('selectedSecurity', resource_group, 300) // sync cookie so refresh without querystring loads correct group

          let [y1, y2] = getOppYearsForGroup(resource_group, parsedPE !== 'cons');


          const timer = setTimeout(() => {
            SetOppTableYears(parsedYears) // removed then readded with timer on 3/27/2025 -
          }, 1000); // 1000ms = 1s delay



          if (parseInt(history_years) === y1) {
            SetOppTablePartialYears(y2.toString())
          }
          else {
            SetOppTablePartialYears(-1) // -1 defaults the partial years to the first one on the list
          }
          // Don't clear opportunities here: OppTable refetches whenever its
          // resolved URL changes (selectedSecurity / partialYears / oppTableYears
          // etc.). If the cookie already pointed at the pattern's market with
          // matching partial-years, the URL is identical and OppTable.js:317
          // dedupes the refetch; clearing here would leave the table stuck on
          // "Loading..." because the dedupe skips the (legitimately needed) refetch.


          // if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
          if (!rdd.isMobile) {
            setCookie('WindowNumber', '2', 300) // 0-indexed: slide 3 (current price chart)
          }

          // Querystring loads (from articles/reports) show the current price chart
          // with projection and daily timeframe for first-time visitors
          SetShowProjection(true);
          SetProjectionPeriod('60');
          SetPriceChartTimeframe('daily');
          SetShowEarnings(true);

          // keep the querystring in the URL so users can share pattern links
          queryStringLoadedRef.current = true;
        }
      }
    }

  }, [token, Object.keys(resourceObj).length, opportunities.length])

  //-------------------------------------------------------------------------------
  // Keep URL querystring in sync with current pattern so the URL is always shareable
  // Uses pushState for deliberate pattern changes (symbol or startDate) so the
  // browser back button walks through previously viewed patterns.
  //-------------------------------------------------------------------------------
  useEffect(() => {
    if (!symbol || !startDate || !selectedSecurity || !daysOut) return;
    if (Object.keys(resourceObj).length === 0) return;

    // reverse lookup: find resource ID from selectedSecurity name
    let fg_id = null;
    for (const [id, name] of Object.entries(resourceObj)) {
      if (name === selectedSecurity) { fg_id = id; break; }
    }
    if (fg_id === null) return;

    // encode years: consecutive = "10", PE = "pe2-10"
    // guard: seasonalYears must be numeric; if corrupted, don't write bad URL
    const safeYears = /^\d+$/.test(seasonalYears) ? seasonalYears : '10';
    const years_str = PEselected && PEselected !== 'cons'
      ? PEselected + '-' + safeYears
      : safeYears;

    const param_str = fg_id + '|' + symbol + '|' + startDate + '|' + daysOut + '|' + years_str;
    const b64 = window.btoa(param_str);
    const newUrl = window.location.pathname + '?o=' + b64;

    const patternKey = symbol + '|' + startDate;

    if (!historyInitialized.current) {
      // first URL write: replace, don't add history entry
      window.history.replaceState({ tw: b64 }, '', newUrl);
      historyInitialized.current = true;
    } else if (isPopstateNav.current) {
      // back/forward navigation: don't push, just update URL to match state
      isPopstateNav.current = false;
    } else if (patternKey !== prevPatternKey.current && prevPatternKey.current !== '') {
      // deliberate pattern change (symbol or date changed): push new history entry
      window.history.pushState({ tw: b64 }, '', newUrl);
    } else {
      // minor tweak (days out, years, etc.): update current entry
      window.history.replaceState({ tw: b64 }, '', newUrl);
    }

    prevPatternKey.current = patternKey;
  }, [symbol, startDate, daysOut, seasonalYears, PEselected, selectedSecurity, Object.keys(resourceObj).length])

  //-------------------------------------------------------------------------------
  // Handle browser back/forward button to restore previous patterns
  //-------------------------------------------------------------------------------
  useEffect(() => {
    const handlePopState = (event) => {
      const state = event.state;
      if (!state || !state.tw) return;
      if (!token || token.length === 0 || Object.keys(resourceObj).length === 0) return;

      let param_str;
      try { param_str = window.atob(state.tw); } catch (e) { return; }
      const params = param_str.split('|');
      if (params.length < 5) return;

      const fg_id = params[0];
      const resource_group = resourceObj[parseInt(fg_id)];
      if (!resource_group) return;

      const sym = params[1];
      const date1 = params[2];
      const days_hold = params[3];
      const history_years = params[4].toLowerCase();

      isPopstateNav.current = true;
      prevPatternKey.current = sym + '|' + date1;

      SetStartDate(date1);
      SetSymbol(sym);
      SetDaysOut(days_hold);

      let parsedPE = 'cons';
      let parsedYears = history_years;
      if (history_years.startsWith('pe') && history_years.includes('-')) {
        const [peType, yearCount] = history_years.split('-');
        parsedPE = peType;
        parsedYears = /^\d+$/.test(yearCount) ? yearCount : '10';
      } else if (history_years.startsWith('pe')) {
        parsedPE = history_years;
        parsedYears = '10';
      }
      SetPEselected(parsedPE);
      SetSeasonalYears(parsedYears);

      SetMonthsAndQtrs('Months & Qtrs');
      SetConsolidatedSeasonalData([]);
      let trend_chart_start_date = incrementDate(date1, -trend_chart_left_gap_days);
      SetTrendChartStartDate(trend_chart_start_date);
      SetSelectedSecurity(resource_group);
      SetOpportunities([]);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [token, Object.keys(resourceObj).length])

  //-------------------------------------------------------------------------------------
  useEffect(() => {
    if (selectedSecurity.length > 0 && token.length > 0 && symbol.length > 0) {
      let id = getSelectedIDFromSecuritiesList2(securityTypeList, selectedSecurity);

      let asURL = appserverURL()
      let url = `${asURL}/NameFromTicker/${id}/${symbol}?token=${token}`

      twFetch(url)
        .then((res) => {
          return res.json();
        })
        .then((g) => {
          SetCompany(g['name'])
        })
        .catch(err => {
          console.log('NameFromTicker error=', err.message)
        })


      // if (token && token.length > 0 && symbol.length > 0 && Object.keys(allowedSymbols).length > 0) {
      //   SetCompany(allowedSymbols[symbol])
      // }
      // else {
      //   SetCompany('');
      // }

    }

  }, [symbol, token])
  //------------------------------------------------------------------------------------------------------------------------------------------------------
  // refresh when mobile orientation changes
  //------------------------------------------------------------------------------------------------------------------------------------------------------
  const refreshPage = () => {
    window.location.reload();
  };
  //------------------------------------------------------------------------------------------------------------------------------------------------------
  // Add an event listener for the 'orientationchange' event and call the refreshPage function when it occurs.
  useEffect(() => {
    window.addEventListener('orientationchange', refreshPage);

    // Clean up the event listener when the component unmounts.
    return () => {
      window.removeEventListener('orientationchange', refreshPage);
    };
  }, []);
  //------------------------------------------------------------------------------------------------------------------------------------------------------
  // Logout: clear this user's localStorage entries before navigation.
  // The header renders a small <form method="POST" action="/logout"> in the
  // Flask-substituted nav, so we intercept on submit (form path) and on
  // anchor-click (legacy/fallback path).
  useEffect(() => {
    const matchLogout = (s) => s === '/logout' || s.endsWith('/logout') || s.indexOf('/logout?') !== -1;
    const handleClick = (ev) => {
      try {
        const a = ev.target && ev.target.closest && ev.target.closest('a[href]');
        if (!a) return;
        const href = a.getAttribute('href') || '';
        if (matchLogout(href)) {
          clearUserStorage();
        }
      } catch (e) { /* never block navigation on a clear-storage error */ }
    };
    const handleSubmit = (ev) => {
      try {
        const f = ev.target && ev.target.closest && ev.target.closest('form');
        if (!f) return;
        const action = (f.getAttribute('action') || '');
        if (matchLogout(action)) {
          clearUserStorage();
        }
      } catch (e) { /* never block navigation on a clear-storage error */ }
    };
    document.addEventListener('click', handleClick, true);
    document.addEventListener('submit', handleSubmit, true);
    return () => {
      document.removeEventListener('click', handleClick, true);
      document.removeEventListener('submit', handleSubmit, true);
    };
  }, []);
  //------------------------------------------------------------------------------------------------------------------------------------------------------
  return (

    <>
      {askMobileNote && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100000,
          backgroundColor: '#1e1e2e', color: '#e0e0e0',
          borderBottom: '1px solid rgba(255,255,255,0.12)',
          fontFamily: 'system-ui, sans-serif', fontSize: '14px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', gap: '12px', lineHeight: 1.4,
        }}>
          <span>Tara chat is available on desktop - open this on a larger screen to chat.</span>
          <button onClick={() => SetAskMobileNote(false)} aria-label="Dismiss" style={{
            backgroundColor: 'transparent', color: '#93b5f6', border: 'none',
            fontSize: '20px', lineHeight: 1, cursor: 'pointer', padding: '0 4px', flexShrink: 0,
          }}>
            &times;
          </button>
        </div>
      )}
      {sessionExpired && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
          backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontFamily: 'system-ui, sans-serif',
        }}>
          <div style={{
            backgroundColor: '#1e1e2e', color: '#e0e0e0', borderRadius: '12px',
            padding: '28px 36px', maxWidth: '420px', textAlign: 'center',
            border: '1px solid rgba(255,255,255,0.1)',
          }}>
            <div style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>Session Expired</div>
            <div style={{ fontSize: '14px', opacity: 0.7, marginBottom: '20px', lineHeight: 1.5 }}>
              Your session has expired due to inactivity. Click below to refresh.
              Your last loaded pattern will be restored automatically.
            </div>
            <button onClick={() => window.location.reload()} style={{
              backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px',
              padding: '10px 28px', fontSize: '15px', fontWeight: 600, cursor: 'pointer',
            }}>
              Reload TradeWave
            </button>
          </div>
        </div>
      )}
      {loggedinUser === '0' && !debug && !arrivedViaPatternLink.current && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
          backgroundColor: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontFamily: 'system-ui, sans-serif',
        }}>
          <div style={{
            backgroundColor: '#1e1e2e', color: '#e0e0e0', borderRadius: '12px',
            padding: '36px 44px', maxWidth: '460px', textAlign: 'center',
            border: '1px solid rgba(255,255,255,0.1)',
          }}>
            <div style={{ fontSize: '22px', fontWeight: 700, marginBottom: '2px', color: '#fff' }}>
              Markets Repeat
            </div>
            <div style={{ fontSize: '18px', fontWeight: 600, marginBottom: '6px', color: 'rgb(100, 180, 255)' }}>
              TradeWave Finds the Patterns
            </div>
            <div style={{ fontSize: '14px', opacity: 0.5, marginBottom: '20px' }}>
              Free account. No credit card. Takes 30 seconds.
            </div>
            <div style={{ fontSize: '15px', opacity: 0.75, marginBottom: '28px', lineHeight: 1.7, textAlign: 'left' }}>
              <div style={{ marginBottom: '8px' }}>TradeWave scans {new Date().getFullYear() - 1928} years of market history to surface seasonal patterns for you to judge. Sign up and get:</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; Top 5 ranked patterns delivered daily</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; Stocks, ETFs, futures, forex, crypto, and more</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; AI assistant to explain patterns and suggest strategies</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; Portfolio manager to track your seasonal trades</div>
            </div>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button onClick={() => window.location.href = '/register/?lid=1'} style={{
                backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px',
                padding: '12px 32px', fontSize: '15px', fontWeight: 600, cursor: 'pointer',
              }}>
                Sign Up Free
              </button>
              <button onClick={() => window.location.href = '/member-login/'} style={{
                backgroundColor: 'transparent', color: '#93b5f6', border: '1px solid rgba(100,180,255,0.3)', borderRadius: '8px',
                padding: '12px 32px', fontSize: '15px', fontWeight: 600, cursor: 'pointer',
              }}>
                Login
              </button>
            </div>
          </div>
        </div>
      )}
      {loggedinUser === '0' && !debug && arrivedViaPatternLink.current && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
          backgroundColor: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontFamily: 'system-ui, sans-serif',
        }}>
          <div style={{
            backgroundColor: '#1e1e2e', color: '#e0e0e0', borderRadius: '12px',
            padding: '36px 44px', maxWidth: '500px', width: '90%', textAlign: 'center',
            border: '1px solid rgba(255,255,255,0.1)',
          }}>
            <div style={{ fontSize: '22px', fontWeight: 700, marginBottom: '6px', color: '#fff' }}>
              This pattern is waiting for you
            </div>
            <div style={{ fontSize: '14px', opacity: 0.5, marginBottom: '20px' }}>
              Free account. No credit card. Takes 30 seconds.
            </div>
            <div style={{ fontSize: '15px', opacity: 0.75, marginBottom: '28px', lineHeight: 1.7, textAlign: 'left' }}>
              <div style={{ marginBottom: '8px' }}>Sign up and you'll get:</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; This pattern, plus the top 5 ranked patterns every day</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; 10,000+ securities across {new Date().getFullYear() - 1928} years of data</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; AI assistant to explain patterns and suggest strategies</div>
              <div style={{ paddingLeft: '8px' }}>&#10003; Portfolio tracking to monitor your trades</div>
            </div>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button onClick={() => window.location.href = '/register/?lid=1'} style={{
                backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px',
                padding: '12px 32px', fontSize: '15px', fontWeight: 600, cursor: 'pointer',
              }}>
                Sign Up Free
              </button>
              <button onClick={() => window.open('/member-login/', '_blank')} style={{
                backgroundColor: 'transparent', color: '#93b5f6', border: '1px solid rgba(100,180,255,0.3)', borderRadius: '8px',
                padding: '12px 32px', fontSize: '15px', fontWeight: 600, cursor: 'pointer',
              }}>
                Login
              </button>
            </div>
          </div>
        </div>
      )}
      <UserContext.Provider value={{ selectedSecurityType, resourceObj, debug, wpUserLevels, seasonalAppDivH, seasonalAppDivH2, browserH, browserW, rdd, token, globalTextSize, checkboxZoom, tableTextSize, tableTitleTextSize, infoTextSize, loggedinUser, UITheme }} >
        {/* had to add test !rdd.isMobile only for safari on ipad */}
        {/*
            Nested ErrorBoundary wraps each layout root so a crash in DesktopLayout
            (chart canvas, OppTable, etc.) doesn't kill the whole shell - the user
            sees a localized "panel encountered an error" + reload-only-this-panel
            UI, not the full-screen "Session interrupted" outer fallback.
            Pattern: wrap any high-risk subtree (chart canvas, settings dialog,
            reports dashboard, watchlist editor) with <ErrorBoundary name="X">.
        */}
        <BrowserView>
          {
            !rdd.isMobile
            &&
            <ErrorBoundary name="DesktopLayout">
              <DesktopLayout {...chartProps} {...chartSetProps} />
            </ErrorBoundary>
          }
        </BrowserView>

        <MobileView>
          {
            rdd.isTablet && browserH < browserW
            &&
            <ErrorBoundary name="DesktopLayout-Tablet">
              <DesktopLayout {...chartProps} {...chartSetProps} />
            </ErrorBoundary>
          }
          {
            !rdd.isTablet && browserH < browserW
            &&
            <ErrorBoundary name="MobileLayoutL">
              <MobileLayoutL {...chartProps} {...chartSetProps} {...browserH} {...browserW} />
            </ErrorBoundary>
          }
          {
            browserH > browserW
            &&
            <ErrorBoundary name="MobileLayoutP">
              <MobileLayoutP {...chartProps} {...chartSetProps} {...browserH} {...browserW} />
            </ErrorBoundary>
          }
        </MobileView>
      </UserContext.Provider>
    </>

  );
}

export default App;
